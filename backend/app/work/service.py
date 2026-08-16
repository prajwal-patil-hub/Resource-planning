"""Work item services.

The single code path for creating items, assigning them, and moving them
through the lifecycle. Everything the product measures is produced here, so
this module is deliberately small and heavily constrained.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.access import can_assign_to
from app.models import Person, StateTransition, WorkItem, WorkItemParticipant
from app.work.lifecycle import IllegalTransition, State, check_transition


class WorkItemError(Exception):
    """A business rule prevented the operation."""


def _set_actor(session: Session, actor_id: int) -> None:
    """Tell the audit trigger who is acting (ADR-003).

    set_config(..., true) scopes the setting to the current transaction, so it
    cannot leak into another request sharing the connection.
    """
    session.execute(
        text("SELECT set_config('app.actor_id', :actor, true)"),
        {"actor": str(actor_id)},
    )


def _open_state_gate(session: Session) -> None:
    """Permit work_item.state to change for this transaction only (INV-7).

    The trigger `work_item_state_guarded` rejects any state change without this,
    which is what keeps the denormalized `state` column honest.
    """
    session.execute(text("SELECT set_config('app.transition_in_progress', 'on', true)"))


def create_work_item(
    session: Session,
    *,
    title: str,
    created_by_id: int,
    description: str | None = None,
    type_id: int | None = None,
    client_id: int | None = None,
    priority: int = 2,
    due_date=None,
    owner_id: int | None = None,
    occurred_at: datetime | None = None,
) -> WorkItem:
    """Record a piece of work.

    BR-002 / D-005: `title` and the author are the only things required. Every
    other field is optional and can be filled in later. This is the single most
    important constraint in the product — if recording costs more than telling a
    colleague, nothing gets recorded and every metric becomes fiction.

    An item may be created unassigned (K-012, RULE-001); passing `owner_id`
    assigns it in the same transaction, which is what the UI does when the
    person recording it already knows who is taking it (C-007).
    """
    if not title or not title.strip():
        raise WorkItemError("A work item needs a title.")

    now = datetime.now(UTC)
    occurred = occurred_at or now
    if occurred > now:
        raise WorkItemError("Work cannot be recorded as having happened in the future.")

    _set_actor(session, created_by_id)

    item = WorkItem(
        title=title.strip(),
        description=description,
        type_id=type_id,
        client_id=client_id,
        priority=priority,
        due_date=due_date,
        state=State.NEW.value,
        created_by_id=created_by_id,
        created_at=now,
    )
    session.add(item)
    session.flush()

    # The creation event. Without this the item has no history, and cycle time
    # from creation would be unmeasurable.
    session.add(
        StateTransition(
            work_item_id=item.id,
            from_state=None,
            to_state=State.NEW.value,
            occurred_at=occurred,
            recorded_at=now,
            changed_by_id=created_by_id,
        )
    )

    if owner_id is not None:
        assign(
            session, item=item, person_id=owner_id, actor_id=created_by_id,
            occurred_at=occurred,
        )

    session.flush()
    return item


def current_owner(session: Session, work_item_id: int) -> WorkItemParticipant | None:
    return session.scalar(
        select(WorkItemParticipant).where(
            WorkItemParticipant.work_item_id == work_item_id,
            WorkItemParticipant.participation == "OWNER",
            WorkItemParticipant.to_ts.is_(None),
        )
    )


def assign(
    session: Session,
    *,
    item: WorkItem,
    person_id: int,
    actor_id: int,
    participation: str = "OWNER",
    occurred_at: datetime | None = None,
) -> WorkItemParticipant:
    """Give the item an owner, or add a collaborator.

    Ownership is time-bounded (D-012): reassigning closes the previous owner's
    row rather than overwriting a field, so "who held this when it stalled?"
    stays answerable. INV-1 — at most one current owner — is enforced by a
    partial unique index, so this holds even under concurrent writes.

    Collaborators work under the owner and do not carry the item in their own
    load (RULE-003). Accountability stays with exactly one person.
    """
    person = session.get(Person, person_id)
    if person is None or not person.active:
        raise WorkItemError("That person is not available for assignment.")

    # RULE-011 enforced where it bites, not only where it shows. The dropdown is
    # already scoped by team, but a filtered list is a convenience and not a
    # control — the form beneath it will accept any id that is posted.
    actor = session.get(Person, actor_id)
    if not can_assign_to(actor, person):
        raise WorkItemError(
            f"{person.name} is in another team. Ask their lead to take this on, "
            f"or have someone who can see both teams assign it."
        )

    # BR-004: work recorded after the fact carries the time it really happened,
    # so ownership periods can be backdated too. Without this the ownership
    # report would show wall-clock seconds for work that took days.
    now = datetime.now(UTC)
    effective = occurred_at or now
    if effective > now:
        raise WorkItemError("Assignment cannot be dated in the future.")

    _set_actor(session, actor_id)

    if participation == "OWNER":
        existing = current_owner(session, item.id)
        if existing is not None:
            if existing.person_id == person_id:
                return existing
            # Close the previous ownership rather than deleting it.
            session.execute(
                update(WorkItemParticipant)
                .where(WorkItemParticipant.id == existing.id)
                .values(to_ts=effective)
            )
            session.flush()

    participant = WorkItemParticipant(
        work_item_id=item.id,
        person_id=person_id,
        participation=participation,
        from_ts=effective,
        to_ts=None,
        assigned_by_id=actor_id,
    )
    session.add(participant)
    session.flush()
    return participant


#: Fields a user may change after creation. Deliberately narrow: state is not
#: here (it moves only through `transition`), and neither are created_by or
#: created_at, which are facts about what happened rather than editable data.
EDITABLE = ("title", "description", "type_id", "client_id", "priority", "due_date")


def update_work_item(
    session: Session,
    *,
    item: WorkItem,
    actor_id: int,
    changes: dict,
) -> WorkItem:
    """Fill in or correct a work item after it was recorded.

    D-005 promises that a title alone is enough to save, and everything else can
    be added later. This is "later". Without it the promise is unkeepable and
    the field-history trigger from ADR-003 can never fire.

    Field history is captured by a database trigger, not here — a log the
    application writes is only as complete as the code paths that remember to
    call it, and this will not be the only path forever.
    """
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise WorkItemError(f"Not editable: {', '.join(sorted(unknown))}")

    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise WorkItemError("A work item needs a title.")
        changes["title"] = title

    if "priority" in changes and changes["priority"] is not None:
        if not 0 <= int(changes["priority"]) <= 4:
            raise WorkItemError("Priority must be between P0 and P4.")

    _set_actor(session, actor_id)

    for field, value in changes.items():
        setattr(item, field, value)

    # Flush inside the actor setting so the trigger sees who made the change.
    session.flush()
    return item


def transition(
    session: Session,
    *,
    item: WorkItem,
    to_state: State,
    actor_id: int,
    occurred_at: datetime | None = None,
    displaced_by_id: int | None = None,
    note: str | None = None,
) -> StateTransition:
    """Move an item to a new state, recording the event.

    This is the ONLY way work_item.state may change — the database trigger
    rejects anything else. That is what makes the denormalized state column
    trustworthy and what makes application-level enforcement of INV-8 safe.
    """
    current = State(item.state)
    check_transition(current, to_state)

    now = datetime.now(UTC)
    occurred = occurred_at or now
    if occurred > now:
        raise WorkItemError("A change cannot be recorded as happening in the future.")

    # BR-004 permits end-of-day catch-up, but a transition still cannot predate
    # the one before it, or the timeline would be incoherent.
    latest = session.scalar(
        select(StateTransition.occurred_at)
        .where(StateTransition.work_item_id == item.id)
        .order_by(StateTransition.occurred_at.desc(), StateTransition.id.desc())
        .limit(1)
    )
    if latest is not None and occurred < latest:
        raise WorkItemError(
            "This change is dated before the previous one on the same item."
        )

    if to_state is State.ON_HOLD_PREEMPTED:
        # INV-3 / BO-4. The database enforces this too, but failing here gives a
        # usable message instead of a constraint violation.
        if displaced_by_id is None:
            raise WorkItemError(
                "Say which work displaced this one — that is what lets us explain "
                "the delay later."
            )
        if displaced_by_id == item.id:
            raise WorkItemError("An item cannot displace itself.")
        if _would_cycle(session, item.id, displaced_by_id):
            raise WorkItemError(
                "That would create a loop of items displacing each other."
            )

    if to_state is State.IN_PROGRESS and current_owner(session, item.id) is None:
        # INV-6: work cannot be in progress with nobody accountable for it.
        raise WorkItemError("Assign an owner before starting this work.")

    _set_actor(session, actor_id)
    _open_state_gate(session)

    item.state = to_state.value
    # Cleared on resume so a resumed item does not still claim to be displaced.
    item.displaced_by_id = displaced_by_id if to_state is State.ON_HOLD_PREEMPTED else None

    event = StateTransition(
        work_item_id=item.id,
        from_state=current.value,
        to_state=to_state.value,
        occurred_at=occurred,
        recorded_at=now,
        changed_by_id=actor_id,
        displaced_by_id=displaced_by_id if to_state is State.ON_HOLD_PREEMPTED else None,
        note=note,
    )
    session.add(event)
    session.flush()
    return event


def _would_cycle(session: Session, item_id: int, displacer_id: int) -> bool:
    """INV-4: displacement must not form a cycle.

    A CHECK constraint cannot traverse a graph, so this is one of the four rules
    the database cannot enforce. Safe because this is the only code path that
    sets displaced_by_id.
    """
    seen: set[int] = {item_id}
    cursor: int | None = displacer_id
    while cursor is not None:
        if cursor in seen:
            return True
        seen.add(cursor)
        cursor = session.scalar(
            select(WorkItem.displaced_by_id).where(WorkItem.id == cursor)
        )
    return False
