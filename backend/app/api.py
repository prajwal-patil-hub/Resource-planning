"""HTTP API and server-rendered pages.

Feature 1 — record a work item — as a vertical slice: database, business logic,
API, UI, tests.

Authentication is deliberately not built yet. `X-Actor-Id` stands in for the
signed-in user so the vertical slice is complete and testable without dragging
identity, sessions and password policy into the first feature. Recorded as a
known gap in PROJECT_STATE.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.flow.load import load_for_team
from app.flow.timeline import build_timeline, format_duration, state_label
from app.models import Client, Person, WorkItem, WorkItemType
from app.work.lifecycle import LABELS, OPEN_STATES, IllegalTransition, State
from app.work.service import (
    WorkItemError,
    assign,
    create_work_item,
    current_owner,
    transition,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
templates.env.filters["duration"] = format_duration
templates.env.filters["state_label"] = lambda s: state_label(State(s))

app = FastAPI(title="Resource Planning", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


def actor(x_actor_id: int = Header(default=1, alias="X-Actor-Id")) -> int:
    return x_actor_id


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class CreateWorkItem(BaseModel):
    """BR-002: only `title` is required. Everything else is optional."""

    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    type_id: int | None = None
    client_id: int | None = None
    priority: int = Field(default=2, ge=0, le=4)
    due_date: date | None = None
    owner_id: int | None = None
    occurred_at: datetime | None = None


class TransitionRequest(BaseModel):
    to_state: State
    displaced_by_id: int | None = None
    note: str | None = None
    occurred_at: datetime | None = None


class WorkItemOut(BaseModel):
    id: int
    title: str
    state: str
    state_label: str
    priority: int
    owner: str | None
    due_date: date | None
    created_at: datetime


def _to_out(session: Session, item: WorkItem) -> WorkItemOut:
    owner = current_owner(session, item.id)
    return WorkItemOut(
        id=item.id,
        title=item.title,
        state=item.state,
        state_label=LABELS[State(item.state)],
        priority=item.priority,
        owner=owner.person.name if owner else None,
        due_date=item.due_date,
        created_at=item.created_at,
    )


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


@app.post("/api/work-items", response_model=WorkItemOut, status_code=201)
def api_create(
    payload: CreateWorkItem,
    session: Session = Depends(get_session),
    actor_id: int = Depends(actor),
) -> WorkItemOut:
    try:
        item = create_work_item(
            session,
            title=payload.title,
            created_by_id=actor_id,
            description=payload.description,
            type_id=payload.type_id,
            client_id=payload.client_id,
            priority=payload.priority,
            due_date=payload.due_date,
            owner_id=payload.owner_id,
            occurred_at=payload.occurred_at,
        )
    except WorkItemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(session, item)


@app.get("/api/work-items", response_model=list[WorkItemOut])
def api_list(
    include_closed: bool = False,
    session: Session = Depends(get_session),
) -> list[WorkItemOut]:
    query = select(WorkItem).order_by(WorkItem.priority, WorkItem.id.desc())
    if not include_closed:
        query = query.where(WorkItem.state.in_([s.value for s in OPEN_STATES]))
    return [_to_out(session, item) for item in session.scalars(query)]


@app.post("/api/work-items/{item_id}/transition", response_model=WorkItemOut)
def api_transition(
    item_id: int,
    payload: TransitionRequest,
    session: Session = Depends(get_session),
    actor_id: int = Depends(actor),
) -> WorkItemOut:
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        transition(
            session,
            item=item,
            to_state=payload.to_state,
            actor_id=actor_id,
            displaced_by_id=payload.displaced_by_id,
            note=payload.note,
            occurred_at=payload.occurred_at,
        )
    except IllegalTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkItemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(session, item)


@app.post("/api/work-items/{item_id}/assign", response_model=WorkItemOut)
def api_assign(
    item_id: int,
    person_id: int,
    session: Session = Depends(get_session),
    actor_id: int = Depends(actor),
) -> WorkItemOut:
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        assign(session, item=item, person_id=person_id, actor_id=actor_id)
    except WorkItemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(session, item)


@app.get("/api/work-items/{item_id}/timeline")
def api_timeline(item_id: int, session: Session = Depends(get_session)) -> dict:
    """ADR-003: the audit trail as data, with every figure's inputs alongside it."""
    try:
        tl = build_timeline(session, item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "item_id": tl.item_id,
        "title": tl.title,
        "state": tl.state.value,
        "total_elapsed_seconds": tl.total_elapsed.total_seconds(),
        "accountable_elapsed_seconds": tl.accountable_elapsed.total_seconds(),
        "active_seconds": tl.active_time.total_seconds(),
        "waiting_on_us_seconds": tl.waiting_on_us.total_seconds(),
        "waiting_on_client_seconds": tl.waiting_on_client.total_seconds(),
        "verification_seconds": tl.verification_time.total_seconds(),
        "time_to_first_touch_seconds": (
            tl.time_to_first_touch.total_seconds() if tl.time_to_first_touch else None
        ),
        "rework_count": tl.rework_count,
        "preemption_count": tl.preemption_count,
        "max_recording_lag_seconds": tl.max_recording_lag.total_seconds(),
        "time_in_state": {
            s.value: d.total_seconds() for s, d in tl.time_in_state.items()
        },
        "owners": [
            {
                "person": o.person_name,
                "assigned_by": o.assigned_by,
                "from": o.from_ts.isoformat(),
                "to": o.to_ts.isoformat() if o.to_ts else None,
                "duration_seconds": o.duration.total_seconds(),
            }
            for o in tl.owners
        ],
        "displacements": [
            {
                "occurred_at": d.occurred_at.isoformat(),
                "displaced_by_id": d.displaced_by_id,
                "displaced_by_title": d.displaced_by_title,
                "by_person": d.by_person,
            }
            for d in tl.displacements
        ],
        "transitions": [
            {
                "from": t.from_state,
                "to": t.to_state,
                "occurred_at": t.occurred_at.isoformat(),
                "recorded_at": t.recorded_at.isoformat(),
                "by": t.changed_by.name,
                "note": t.note,
            }
            for t in tl.transitions
        ],
        "field_changes": [
            {
                "field": c.field,
                "old": c.old_value,
                "new": c.new_value,
                "occurred_at": c.occurred_at.isoformat(),
            }
            for c in tl.field_changes
        ],
    }


@app.get("/api/load")
def api_load(team_id: int | None = None, session: Session = Depends(get_session)) -> list[dict]:
    return [
        {
            "person_id": entry.person_id,
            "name": entry.name,
            "load": entry.load,
            "normal_load": entry.normal_load,
            "overloaded": entry.is_overloaded,
            "has_room": entry.has_room,
            "absent_today": entry.absent_today,
            # BR-020: the number never travels without its derivation.
            "explanation": entry.explanation,
        }
        for entry in load_for_team(session, team_id)
    ]


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def page_board(request: Request, session: Session = Depends(get_session)):
    items = list(
        session.scalars(
            select(WorkItem)
            .where(WorkItem.state.in_([s.value for s in OPEN_STATES]))
            .order_by(WorkItem.priority, WorkItem.id.desc())
        )
    )
    by_state: dict[str, list] = {s.value: [] for s in OPEN_STATES}
    for item in items:
        owner = current_owner(session, item.id)
        by_state[item.state].append(
            {
                "item": item,
                "owner": owner.person.name if owner else None,
                "type": item.type.name if item.type else None,
                "client": item.client.name if item.client else None,
            }
        )

    column_order = [
        State.NEW,
        State.QUEUED,
        State.IN_PROGRESS,
        State.ON_HOLD_PREEMPTED,
        State.BLOCKED_ON_CLIENT,
        State.IN_VERIFICATION,
    ]
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            "columns": [(s, LABELS[s], by_state.get(s.value, [])) for s in column_order],
            "people": list(session.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.name))),
            "types": list(session.scalars(select(WorkItemType).where(WorkItemType.active.is_(True)).order_by(WorkItemType.sort_order))),
            "clients": list(session.scalars(select(Client).where(Client.active.is_(True)).order_by(Client.name))),
            "loads": load_for_team(session),
        },
    )


@app.post("/items")
def page_create(
    title: str = Form(...),
    owner_id: str = Form(default=""),
    type_id: str = Form(default=""),
    client_id: str = Form(default=""),
    priority: int = Form(default=2),
    session: Session = Depends(get_session),
    actor_id: int = Depends(actor),
):
    """The quick-add form. Title is the only field the user must fill."""
    create_work_item(
        session,
        title=title,
        created_by_id=actor_id,
        owner_id=int(owner_id) if owner_id else None,
        type_id=int(type_id) if type_id else None,
        client_id=int(client_id) if client_id else None,
        priority=priority,
    )
    return RedirectResponse("/", status_code=303)


@app.get("/items/{item_id}", response_class=HTMLResponse)
def page_item(item_id: int, request: Request, session: Session = Depends(get_session)):
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    tl = build_timeline(session, item_id)
    current = State(item.state)
    from app.work.lifecycle import ALLOWED

    return templates.TemplateResponse(
        request,
        "item.html",
        {
            "item": item,
            "tl": tl,
            "allowed": sorted(ALLOWED[current], key=lambda s: s.value),
            "labels": LABELS,
            "owner": current_owner(session, item_id),
            "open_items": list(
                session.scalars(
                    select(WorkItem)
                    .where(
                        WorkItem.state.in_([s.value for s in OPEN_STATES]),
                        WorkItem.id != item_id,
                    )
                    .order_by(WorkItem.id.desc())
                )
            ),
            "people": list(session.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.name))),
        },
    )


@app.post("/items/{item_id}/transition")
def page_transition(
    item_id: int,
    to_state: str = Form(...),
    displaced_by_id: str = Form(default=""),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
    actor_id: int = Depends(actor),
):
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        transition(
            session,
            item=item,
            to_state=State(to_state),
            actor_id=actor_id,
            displaced_by_id=int(displaced_by_id) if displaced_by_id else None,
            note=note or None,
        )
    except (WorkItemError, IllegalTransition) as exc:
        return RedirectResponse(f"/items/{item_id}?error={exc}", status_code=303)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@app.post("/items/{item_id}/assign")
def page_assign(
    item_id: int,
    person_id: int = Form(...),
    session: Session = Depends(get_session),
    actor_id: int = Depends(actor),
):
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    assign(session, item=item, person_id=person_id, actor_id=actor_id)
    return RedirectResponse(f"/items/{item_id}", status_code=303)
