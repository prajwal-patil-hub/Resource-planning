"""HTTP API and server-rendered pages.

Every write is attributed to the signed-in person. Until Feature 2 this was an
`X-Actor-Id` header defaulting to person #1, which meant the audit trail — the
product's entire data source under ADR-001 — was attributable to nobody.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.access import Forbidden, Permission, can, require, visible_team_ids
from app.auth import (
    MAX_FAILED_LOGINS,
    SESSION_COOKIE,
    AuthError,
    anyone_can_sign_in,
    authenticate,
    end_session,
    person_for_token,
    revoke_all_for,
    set_password,
    start_session,
)
from app.config import settings
from app.db import get_session
from app.flow.attention import build_attention
from app.flow.calendar import load_calendar
from app.flow.load import assignment_options, load_for_team
from app.people.absence import (
    AbsenceError,
    absences_for,
    approve as approve_absence,
    cancel as cancel_absence,
    record_absence,
    upcoming,
    uncovered_work,
)
from app.flow.timeline import build_timeline, format_duration, state_label
from app.models import (
    Absence,
    Client,
    NonWorkingDay,
    Person,
    Role,
    Team,
    WorkItem,
    WorkItemParticipant,
    WorkItemType,
)
from app.work.lifecycle import LABELS, OPEN_STATES, IllegalTransition, State
from app.work.timing import TimingError, parse_when, was_backdated
from app.work.service import (
    EDITABLE,
    WorkItemError,
    assign,
    create_work_item,
    current_owner,
    transition,
    update_work_item,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
templates.env.filters["duration"] = format_duration
templates.env.filters["state_label"] = lambda s: state_label(State(s))

app = FastAPI(title="Resource Planning", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


class NeedsLogin(Exception):
    """Raised by the auth dependency; handled below as a redirect.

    A custom exception rather than HTTPException(303) because FastAPI renders
    HTTPException as JSON, and a browser hitting a page while signed out should
    be sent to the sign-in screen, not shown a JSON body.
    """

    def __init__(self, next_url: str = "/"):
        self.next_url = next_url


def signed_in(
    request: Request,
    rp_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
) -> Person:
    """The signed-in person. One dependency, so no route can forget to check."""
    person = person_for_token(session, rp_session)
    if person is None:
        raise NeedsLogin(str(request.url.path))
    return person


def signed_in_id(person: Person = Depends(signed_in)) -> int:
    return person.id


templates.env.globals["can"] = can
templates.env.globals["Permission"] = Permission
templates.env.globals["was_backdated"] = was_backdated


@app.exception_handler(NeedsLogin)
async def _needs_login(request: Request, exc: NeedsLogin):
    target = "/login" + (f"?next={exc.next_url}" if exc.next_url not in ("/", "") else "")
    return RedirectResponse(target, status_code=303)


@app.exception_handler(Forbidden)
async def _forbidden(request: Request, exc: Forbidden):
    return templates.TemplateResponse(request, "forbidden.html", {"message": str(exc)}, status_code=403)


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
    actor_id: int = Depends(signed_in_id),
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
    actor_id: int = Depends(signed_in_id),
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
    actor_id: int = Depends(signed_in_id),
) -> WorkItemOut:
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        assign(session, item=item, person_id=person_id, actor_id=actor_id)
    except WorkItemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(session, item)


class UpdateWorkItem(BaseModel):
    """Every field optional — a partial update changes only what is sent.

    `extra="forbid"` so a caller that tries to set `state` here is told no,
    rather than getting a 200 and silently having it ignored. State moves only
    through /transition, which records an event.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    type_id: int | None = None
    client_id: int | None = None
    priority: int | None = Field(default=None, ge=0, le=4)
    due_date: date | None = None


@app.patch("/api/work-items/{item_id}", response_model=WorkItemOut)
def api_update(
    item_id: int,
    payload: UpdateWorkItem,
    session: Session = Depends(get_session),
    actor_id: int = Depends(signed_in_id),
) -> WorkItemOut:
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    # exclude_unset distinguishes "set this to null" from "leave it alone" —
    # without it, every PATCH would silently clear the fields it omitted.
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _to_out(session, item)
    try:
        update_work_item(session, item=item, actor_id=actor_id, changes=changes)
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


SORTABLE = {
    "id": "w.id",
    "title": "lower(w.title)",
    "type": "wt.name",
    "client": "c.name",
    "assignee": "lower(p.name)",
    "state": "w.state",
    "priority": "w.priority",
    "age": "first_seen",
    "moved": "last_moved",
    "due": "w.due_date",
}

#: One query for the whole table. A per-row lookup would be simpler to write and
#: would issue N queries for N rows; at a few thousand items that is the
#: difference between a snappy screen and a slow one.
TABLE_SQL = """
SELECT w.id, w.title, w.description, w.state, w.priority, w.due_date,
       wt.name AS type_name, c.name AS client_name,
       p.name  AS assignee_name, p.id AS assignee_id,
       d.title AS displaced_by_title, w.displaced_by_id,
       t.first_seen, t.last_moved, t.moves
FROM work_item w
LEFT JOIN work_item_type wt ON wt.id = w.type_id
LEFT JOIN client c ON c.id = w.client_id
LEFT JOIN work_item_participant wip
       ON wip.work_item_id = w.id
      AND wip.participation = 'OWNER'
      AND wip.to_ts IS NULL
LEFT JOIN person p ON p.id = wip.person_id
LEFT JOIN work_item d ON d.id = w.displaced_by_id
LEFT JOIN LATERAL (
    SELECT min(occurred_at) AS first_seen,
           max(occurred_at) AS last_moved,
           count(*)         AS moves
    FROM state_transition WHERE work_item_id = w.id
) t ON true
{where}
ORDER BY {order} {direction} NULLS LAST, w.id DESC
"""


#: Filtering by team resolves through the OWNER's team — a work item has no
#: team of its own, and inventing one would be a second place for the same fact
#: to live and drift.
#:
#: Unowned items therefore belong to no team. They are ALWAYS shown, whatever
#: filter is active. Hiding them would mean the one thing the product exists to
#: prevent — work nobody has picked up quietly disappearing from view (F-001,
#: BO-1). A filter that can hide unclaimed work is a filter that recreates the
#: original problem.
TEAM_CLAUSE = """(
    wip.person_id IS NULL
    OR p.team_id = ANY(:team_ids)
)"""


def _selected_team_ids(raw: list[int] | None, teams: list) -> list[int]:
    """Empty selection means all teams — the safe default is to hide nothing."""
    if not raw:
        return [t.id for t in teams]
    valid = {t.id for t in teams}
    chosen = [t for t in raw if t in valid]
    return chosen or [t.id for t in teams]


def _table_rows(
    session: Session, *, sort: str, direction: str, include_closed: bool,
    team_ids: list[int],
):
    order = SORTABLE.get(sort, SORTABLE["priority"])
    direction = "DESC" if direction.lower() == "desc" else "ASC"
    clauses = [] if include_closed else ["w.state NOT IN ('DONE','CANCELLED')"]
    clauses.append(TEAM_CLAUSE)
    where = "WHERE " + " AND ".join(clauses)
    sql = TABLE_SQL.format(where=where, order=order, direction=direction)

    now = datetime.now(UTC)
    rows = []
    for r in session.execute(text(sql), {"team_ids": team_ids}).mappings():
        last_moved = r["last_moved"]
        first_seen = r["first_seen"]
        rows.append(
            {
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "state": r["state"],
                "state_label": LABELS[State(r["state"])],
                "priority": r["priority"],
                "type_name": r["type_name"],
                "client_name": r["client_name"],
                "assignee_name": r["assignee_name"],
                "assignee_id": r["assignee_id"],
                "displaced_by_id": r["displaced_by_id"],
                "displaced_by_title": r["displaced_by_title"],
                "moves": r["moves"] or 0,
                "due_date": r["due_date"],
                "age": now - first_seen if first_seen else None,
                "since_moved": now - last_moved if last_moved else None,
                # BO-2: stalled work must surface without anyone looking for it.
                "stale": bool(
                    last_moved
                    and State(r["state"]) not in (State.DONE, State.CANCELLED)
                    and (now - last_moved).days >= settings.stale_after_days
                ),
                "overdue": bool(
                    r["due_date"]
                    and State(r["state"]) not in (State.DONE, State.CANCELLED)
                    and r["due_date"] < now.date()
                ),
            }
        )
    return rows


@app.get("/", response_class=HTMLResponse)
def page_board(
    request: Request,
    view: str = "board",
    sort: str = "priority",
    dir: str = "asc",
    state: str = "",
    team: list[int] = Query(default=[]),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    all_teams = list(session.scalars(select(Team).where(Team.active.is_(True)).order_by(Team.name)))
    # RULE-011 / BR-025: you can only filter within what you are allowed to see.
    # Narrowing the option list rather than the results means the UI never
    # offers a choice that would silently return nothing.
    permitted = visible_team_ids(me, [t.id for t in all_teams])
    teams = [t for t in all_teams if t.id in set(permitted)]

    team_ids = _selected_team_ids(team, teams)
    all_selected = len(team_ids) == len(teams)

    common = {
        "me": me,
        "view": view if view in ("board", "table", "focus") else "board",
        "people": list(session.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.name))),
        "types": list(session.scalars(select(WorkItemType).where(WorkItemType.active.is_(True)).order_by(WorkItemType.sort_order))),
        "clients": list(session.scalars(select(Client).where(Client.active.is_(True)).order_by(Client.name))),
        # The load strip narrows with the filter too — showing every person's
        # load beside one team's board would be comparing different things.
        #
        # "All teams" means all the teams *this person may see*, not every team
        # in the organization. Passing None here leaked the whole company's load
        # to a developer scoped to one team: their team filter offered a single
        # option, that option counted as "all", and the strip then went
        # unfiltered. RULE-011 was enforced on the choice and lost on the query.
        "loads": load_for_team(session, team_ids=permitted if all_selected else team_ids),
        # BR-016: the composer's assignee list carries load and absence, and is
        # scoped the same way the assign endpoint now enforces. Offering a name
        # that the next click would refuse is worse than not offering it.
        "assignees": assignment_options(session, team_ids=permitted),
        "teams": teams,
        "selected_teams": set(team_ids) if not all_selected else set(),
        "all_teams": all_selected,
    }

    if common["view"] == "focus":
        # Focus mode: one state at a time, with everything about each item on
        # the card. The board answers "where is everything"; this answers
        # "what exactly is in this column, and what do I do about it".
        chosen = state if state in [s.value for s in OPEN_STATES] else State.IN_PROGRESS.value
        rows = _table_rows(
            session, sort="priority", direction="asc",
            include_closed=False, team_ids=team_ids,
        )
        counts = {}
        for r in rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        return templates.TemplateResponse(
            request,
            "focus.html",
            {
                **common,
                "chosen": chosen,
                "chosen_label": LABELS[State(chosen)],
                "rows": [r for r in rows if r["state"] == chosen],
                "counts": counts,
                "columns": [
                    (s.value, LABELS[s], counts.get(s.value, 0))
                    for s in [
                        State.NEW, State.QUEUED, State.IN_PROGRESS,
                        State.ON_HOLD_PREEMPTED, State.BLOCKED_ON_CLIENT,
                        State.IN_VERIFICATION,
                    ]
                ],
            },
        )

    if common["view"] == "table":
        return templates.TemplateResponse(
            request,
            "table.html",
            {
                **common,
                "rows": _table_rows(
                    session, sort=sort, direction=dir, include_closed=False,
                    team_ids=team_ids,
                ),
                "sort": sort,
                "dir": dir,
            },
        )

    items = list(
        session.scalars(
            select(WorkItem)
            .outerjoin(
                WorkItemParticipant,
                (WorkItemParticipant.work_item_id == WorkItem.id)
                & (WorkItemParticipant.participation == "OWNER")
                & (WorkItemParticipant.to_ts.is_(None)),
            )
            .outerjoin(Person, Person.id == WorkItemParticipant.person_id)
            .where(
                WorkItem.state.in_([s.value for s in OPEN_STATES]),
                # Unowned work always survives the filter — see TEAM_CLAUSE.
                (WorkItemParticipant.id.is_(None)) | (Person.team_id.in_(team_ids)),
            )
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
        {**common, "columns": [(s, LABELS[s], by_state.get(s.value, [])) for s in column_order]},
    )


@app.post("/items")
def page_create(
    title: str = Form(...),
    owner_id: str = Form(default=""),
    type_id: str = Form(default=""),
    client_id: str = Form(default=""),
    priority: int = Form(default=2),
    view: str = Form(default="board"),
    happened_at: str = Form(default=""),
    tz_offset: str = Form(default=""),
    session: Session = Depends(get_session),
    actor_id: int = Depends(signed_in_id),
):
    """The composer. Title is the only field the user must fill."""
    back = f"/?view={view}" if view in ("board", "table", "focus") else "/"
    try:
        # BR-004. Blank means now, which is the overwhelmingly common case and
        # costs nothing; a stated time is honoured, so an entry caught up at the
        # end of the day carries the hour the work actually started.
        occurred = parse_when(happened_at, tz_offset)
        create_work_item(
            session,
            title=title,
            created_by_id=actor_id,
            owner_id=int(owner_id) if owner_id else None,
            type_id=int(type_id) if type_id else None,
            client_id=int(client_id) if client_id else None,
            priority=priority,
            occurred_at=occurred,
        )
    except (TimingError, WorkItemError) as exc:
        return RedirectResponse(f"{back}{'&' if '?' in back else '?'}error={quote(str(exc))}", status_code=303)
    return RedirectResponse(back, status_code=303)


@app.get("/items/{item_id}", response_class=HTMLResponse)
def page_item(
    item_id: int,
    request: Request,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
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
            # BR-016. Scoped the same way the assign endpoint now enforces, so
            # the list never offers a name the next click would refuse.
            "assignees": assignment_options(
                session,
                team_ids=visible_team_ids(
                    me, list(session.scalars(select(Team.id).where(Team.active.is_(True))))
                ),
            ),
            "types": list(session.scalars(select(WorkItemType).where(WorkItemType.active.is_(True)).order_by(WorkItemType.sort_order))),
            "clients": list(session.scalars(select(Client).where(Client.active.is_(True)).order_by(Client.name))),
            "me": me,
        },
    )


@app.post("/items/{item_id}/transition")
def page_transition(
    item_id: int,
    to_state: str = Form(...),
    displaced_by_id: str = Form(default=""),
    note: str = Form(default=""),
    happened_at: str = Form(default=""),
    tz_offset: str = Form(default=""),
    session: Session = Depends(get_session),
    actor_id: int = Depends(signed_in_id),
):
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        # BR-004 matters most here. Creation times are usually close to the
        # truth; state changes are what cycle time is measured from, and "I
        # started this at 9am" typed at 6pm is the entry that would otherwise
        # lose a whole working day.
        transition(
            session,
            item=item,
            to_state=State(to_state),
            actor_id=actor_id,
            displaced_by_id=int(displaced_by_id) if displaced_by_id else None,
            note=note or None,
            occurred_at=parse_when(happened_at, tz_offset),
        )
    except (TimingError, WorkItemError, IllegalTransition) as exc:
        return RedirectResponse(f"/items/{item_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@app.post("/items/{item_id}/edit")
def page_edit(
    item_id: int,
    title: str = Form(...),
    description: str = Form(default=""),
    type_id: str = Form(default=""),
    client_id: str = Form(default=""),
    priority: int = Form(default=2),
    due_date: str = Form(default=""),
    session: Session = Depends(get_session),
    actor_id: int = Depends(signed_in_id),
):
    """Fill in the details that were skipped at record time (D-005)."""
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        update_work_item(
            session,
            item=item,
            actor_id=actor_id,
            changes={
                "title": title,
                "description": description or None,
                "type_id": int(type_id) if type_id else None,
                "client_id": int(client_id) if client_id else None,
                "priority": priority,
                "due_date": date.fromisoformat(due_date) if due_date else None,
            },
        )
    except (WorkItemError, ValueError) as exc:
        return RedirectResponse(f"/items/{item_id}?error={exc}", status_code=303)
    return RedirectResponse(f"/items/{item_id}", status_code=303)


@app.post("/items/{item_id}/assign")
def page_assign(
    item_id: int,
    person_id: int = Form(...),
    happened_at: str = Form(default=""),
    tz_offset: str = Form(default=""),
    session: Session = Depends(get_session),
    actor_id: int = Depends(signed_in_id),
):
    item = session.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such work item")
    try:
        assign(
            session,
            item=item,
            person_id=person_id,
            actor_id=actor_id,
            occurred_at=parse_when(happened_at, tz_offset),
        )
    except (TimingError, WorkItemError) as exc:
        return RedirectResponse(f"/items/{item_id}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/items/{item_id}", status_code=303)

# --------------------------------------------------------------------------
# Sign in / first-run setup
# --------------------------------------------------------------------------


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,      # JavaScript cannot read it, so XSS cannot steal it
        samesite="lax",     # blocks cross-site form posts riding the session
        secure=settings.cookies_secure,
        max_age=60 * 60 * 24 * 14,
        path="/",
    )


@app.get("/login", response_class=HTMLResponse)
def page_login(request: Request, next: str = "/", session: Session = Depends(get_session)):
    # BR-021: no configuration step. Creating the first administrator is the one
    # unavoidable exception, so it is offered rather than documented.
    if not anyone_can_sign_in(session):
        return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"next": next, "error": request.query_params.get("error")}
    )


@app.post("/login")
def do_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/"),
    session: Session = Depends(get_session),
):
    try:
        person = authenticate(session, email, password)
    except AuthError as exc:
        return RedirectResponse(f"/login?error={exc}", status_code=303)

    token = start_session(session, person, user_agent=request.headers.get("user-agent", ""))
    target = "/change-password" if person.must_change_password else (next or "/")
    response = RedirectResponse(target, status_code=303)
    _set_session_cookie(response, token)
    return response


@app.post("/logout")
def do_logout(
    rp_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
):
    end_session(session, rp_session)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/setup", response_class=HTMLResponse)
def page_setup(request: Request, session: Session = Depends(get_session)):
    if anyone_can_sign_in(session):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "setup.html", {"error": request.query_params.get("error")}
    )


@app.post("/setup")
def do_setup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """Create the first administrator. Only reachable while none exists."""
    if anyone_can_sign_in(session):
        # Guards against a second call racing the first — otherwise anyone could
        # mint themselves an admin by hitting this endpoint.
        return RedirectResponse("/login", status_code=303)

    admin_role = session.scalar(select(Role).where(Role.code == "ADMIN"))
    default_team = session.scalar(select(Team).order_by(Team.id).limit(1))
    email_clean = email.strip().lower()

    existing = session.scalar(select(Person).where(func.lower(Person.email) == email_clean))
    person = existing or Person(
        name=name.strip(),
        email=email_clean,
        role_id=admin_role.id,
        team_id=default_team.id if default_team else None,
        normal_load=3,
        active=True,
    )
    if existing:
        # Someone already in the directory is promoted rather than duplicated.
        person.role_id = admin_role.id
        person.active = True
    else:
        session.add(person)
    session.flush()

    try:
        set_password(session, person, password)
    except AuthError as exc:
        session.rollback()
        return RedirectResponse(f"/setup?error={exc}", status_code=303)

    token = start_session(session, person, user_agent=request.headers.get("user-agent", ""))
    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, token)
    return response


@app.get("/change-password", response_class=HTMLResponse)
def page_change_password(request: Request, me: Person = Depends(signed_in)):
    return templates.TemplateResponse(
        request, "change_password.html", {"me": me, "error": request.query_params.get("error")}
    )


@app.post("/change-password")
def do_change_password(
    password: str = Form(...),
    confirm: str = Form(...),
    rp_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    if password != confirm:
        return RedirectResponse("/change-password?error=Those two do not match.", status_code=303)
    try:
        set_password(session, me, password)
    except AuthError as exc:
        return RedirectResponse(f"/change-password?error={exc}", status_code=303)

    # Every other session for this person ends — a password change is what you
    # do when you think someone else has your access.
    revoke_all_for(session, me.id)
    token = start_session(session, me)
    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, token)
    return response


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


@app.get("/people", response_class=HTMLResponse)
def page_people(request: Request, me: Person = Depends(signed_in), session: Session = Depends(get_session)):
    require(me, Permission.MANAGE_PEOPLE)
    return templates.TemplateResponse(
        request,
        "people.html",
        {
            "me": me,
            "people": list(session.scalars(select(Person).order_by(Person.active.desc(), Person.name))),
            "roles": list(session.scalars(select(Role).where(Role.active.is_(True)).order_by(Role.id))),
            "teams": list(session.scalars(select(Team).where(Team.active.is_(True)).order_by(Team.name))),
            "error": request.query_params.get("error"),
            "notice": request.query_params.get("notice"),
        },
    )


@app.post("/people")
def do_add_person(
    name: str = Form(...),
    email: str = Form(...),
    role_id: int = Form(...),
    team_id: str = Form(default=""),
    normal_load: int = Form(default=3),
    password: str = Form(default=""),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    email_clean = email.strip().lower()
    if session.scalar(select(Person).where(func.lower(Person.email) == email_clean)):
        return RedirectResponse("/people?error=Someone already has that email.", status_code=303)

    person = Person(
        name=name.strip(),
        email=email_clean,
        role_id=role_id,
        team_id=int(team_id) if team_id else None,
        normal_load=max(1, min(20, normal_load)),
        active=True,
    )
    session.add(person)
    session.flush()

    if password:
        try:
            # They must change it at first sign-in: a password chosen by someone
            # else is known by someone else.
            set_password(session, person, password, must_change=True)
        except AuthError as exc:
            session.rollback()
            return RedirectResponse(f"/people?error={exc}", status_code=303)
        return RedirectResponse("/people?notice=Added. They must change the password at first sign-in.", status_code=303)

    return RedirectResponse("/people?notice=Added to the directory. No login yet.", status_code=303)


@app.post("/people/{person_id}")
def do_edit_person(
    person_id: int,
    name: str = Form(...),
    role_id: int = Form(...),
    team_id: str = Form(default=""),
    normal_load: int = Form(default=3),
    active: str = Form(default=""),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No such person")

    now_active = active == "on"
    if person.id == me.id and not now_active:
        # Locking the last admin out of their own system is not a state anyone
        # intends to reach.
        return RedirectResponse("/people?error=You cannot deactivate yourself.", status_code=303)

    person.name = name.strip()
    person.role_id = role_id
    person.team_id = int(team_id) if team_id else None
    person.normal_load = max(1, min(20, normal_load))

    if person.active and not now_active:
        person.active = False
        person.left_on = datetime.now(UTC).date()
        # INV-11: never deleted. Access ends immediately; history stays intact.
        revoke_all_for(session, person.id)
    elif not person.active and now_active:
        person.active = True
        person.left_on = None

    session.flush()
    return RedirectResponse("/people?notice=Saved.", status_code=303)


@app.post("/people/{person_id}/reset-password")
def do_reset_password(
    person_id: int,
    password: str = Form(...),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No such person")
    try:
        set_password(session, person, password, must_change=True)
    except AuthError as exc:
        return RedirectResponse(f"/people?error={exc}", status_code=303)
    revoke_all_for(session, person.id)
    return RedirectResponse("/people?notice=Password reset. They must change it at next sign-in.", status_code=303)


# --------------------------------------------------------------------------
# Absence and the working calendar (BO-3, BR-012, BR-013, BR-014)
# --------------------------------------------------------------------------


@app.get("/absence", response_class=HTMLResponse)
def page_absence(
    request: Request,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    calendar = load_calendar(session)
    all_teams = list(session.scalars(select(Team).where(Team.active.is_(True))))
    permitted = visible_team_ids(me, [t.id for t in all_teams])

    return templates.TemplateResponse(
        request,
        "absence.html",
        {
            "me": me,
            "calendar": calendar,
            "mine": absences_for(session, me.id),
            "upcoming": upcoming(session, team_ids=permitted or None),
            # BO-3: this is the half that matters — not who is away, but whose
            # client work is sitting still because they are.
            "uncovered": uncovered_work(session, team_ids=permitted or None),
            "people": list(
                session.scalars(
                    select(Person)
                    .where(Person.active.is_(True))
                    .order_by(Person.name)
                )
            ),
            "holidays": list(
                session.scalars(select(NonWorkingDay).order_by(NonWorkingDay.day.desc()))
            ),
            "can_approve": can(me, Permission.APPROVE_ABSENCE),
            "can_manage": can(me, Permission.MANAGE_PEOPLE),
            "error": request.query_params.get("error"),
            "notice": request.query_params.get("notice"),
        },
    )


@app.post("/absence")
def do_record_absence(
    person_id: int = Form(...),
    start: str = Form(...),
    end: str = Form(...),
    kind: str = Form(default="LEAVE"),
    note: str = Form(default=""),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    # Anyone may book their own time off; booking someone else's is a lead's job.
    if person_id != me.id:
        require(me, Permission.APPROVE_ABSENCE)
    try:
        record_absence(
            session,
            person_id=person_id,
            start=date.fromisoformat(start),
            end=date.fromisoformat(end),
            kind=kind,
            created_by=me,
            note=note or None,
            # A lead recording it has approved it by doing so; asking them to
            # approve their own entry would be ceremony.
            approved_by=me if can(me, Permission.APPROVE_ABSENCE) else None,
        )
    except (AbsenceError, ValueError) as exc:
        return RedirectResponse(f"/absence?error={exc}", status_code=303)
    return RedirectResponse("/absence?notice=Recorded.", status_code=303)


@app.post("/absence/{absence_id}/approve")
def do_approve_absence(
    absence_id: int,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.APPROVE_ABSENCE)
    absence = session.get(Absence, absence_id)
    if absence is None:
        raise HTTPException(status_code=404, detail="No such absence")
    try:
        approve_absence(session, absence, me)
    except AbsenceError as exc:
        return RedirectResponse(f"/absence?error={exc}", status_code=303)
    return RedirectResponse("/absence?notice=Approved.", status_code=303)


@app.post("/absence/{absence_id}/cancel")
def do_cancel_absence(
    absence_id: int,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    absence = session.get(Absence, absence_id)
    if absence is None:
        raise HTTPException(status_code=404, detail="No such absence")
    if absence.person_id != me.id:
        require(me, Permission.APPROVE_ABSENCE)
    cancel_absence(session, absence, me)
    return RedirectResponse("/absence?notice=Cancelled.", status_code=303)


@app.post("/holidays")
def do_add_holiday(
    day: str = Form(...),
    name: str = Form(...),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        return RedirectResponse("/absence?error=That date is not valid.", status_code=303)
    if session.get(NonWorkingDay, parsed):
        return RedirectResponse("/absence?error=That day is already a holiday.", status_code=303)
    session.add(NonWorkingDay(day=parsed, name=name.strip() or "Holiday"))
    return RedirectResponse("/absence?notice=Holiday added.", status_code=303)


@app.post("/holidays/{day}/remove")
def do_remove_holiday(
    day: str,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    holiday = session.get(NonWorkingDay, date.fromisoformat(day))
    if holiday:
        session.delete(holiday)
    return RedirectResponse("/absence?notice=Holiday removed.", status_code=303)


@app.post("/settings/working-week")
async def do_set_working_week(
    request: Request,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    """The working week is a business fact, so it is editable without a deploy.

    Three states per day rather than a checkbox: a day the team sometimes works
    is neither worked nor not worked, and forcing it into a boolean makes every
    duration on that day wrong in one direction or the other.
    """
    require(me, Permission.MANAGE_PEOPLE)
    from app.models import OrgSetting

    form = await request.form()
    never, optional = [], []
    for day in range(1, 8):
        choice = form.get(f"day{day}", "worked")
        if choice == "never":
            never.append(day)
        elif choice == "optional":
            optional.append(day)

    setting = session.get(OrgSetting, 1)
    if setting is None:
        setting = OrgSetting(id=1, weekend_days=[7], optional_days=[6], stale_after_days=3)
        session.add(setting)
    setting.weekend_days = never
    setting.optional_days = optional
    return RedirectResponse("/absence?notice=Working week saved.", status_code=303)


# --------------------------------------------------------------------------
# Person settings (replaces the inline password row)
# --------------------------------------------------------------------------


@app.post("/people/{person_id}/sessions/revoke")
def do_revoke_sessions(
    person_id: int,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    revoke_all_for(session, person_id)
    return RedirectResponse("/people?notice=Signed out everywhere.", status_code=303)


@app.post("/people/{person_id}/unlock")
def do_unlock(
    person_id: int,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No such person")
    person.locked_until = None
    person.failed_logins = 0
    return RedirectResponse("/people?notice=Unlocked.", status_code=303)


@app.post("/people/{person_id}/force-change")
def do_force_change(
    person_id: int,
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    require(me, Permission.MANAGE_PEOPLE)
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="No such person")
    if not person.password_hash:
        return RedirectResponse("/people?error=They have no login yet.", status_code=303)
    person.must_change_password = True
    return RedirectResponse(
        "/people?notice=They must choose a new password at next sign-in.", status_code=303
    )


# --------------------------------------------------------------------------
# Attention — what needs someone today (BR-007, BO-2)
# --------------------------------------------------------------------------


@app.get("/attention", response_class=HTMLResponse)
def page_attention(
    request: Request,
    team: list[int] = Query(default=[]),
    me: Person = Depends(signed_in),
    session: Session = Depends(get_session),
):
    all_teams = list(session.scalars(select(Team).where(Team.active.is_(True)).order_by(Team.name)))
    permitted = set(visible_team_ids(me, [t.id for t in all_teams]))
    teams = [t for t in all_teams if t.id in permitted]
    team_ids = _selected_team_ids(team, teams)

    from app.models import OrgSetting

    setting = session.get(OrgSetting, 1)
    attention = build_attention(
        session,
        calendar=load_calendar(session),
        team_ids=team_ids,
        stale_after_days=setting.stale_after_days if setting else settings.stale_after_days,
    )
    return templates.TemplateResponse(
        request,
        "attention.html",
        {
            "me": me,
            "view": "attention",
            "attention": attention,
            "loads": load_for_team(session, team_ids=team_ids),
            "stale_after_days": setting.stale_after_days if setting else settings.stale_after_days,
        },
    )
