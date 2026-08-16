"""Absence — recording it, approving it, and finding uncovered work.

BO-3: absence must never silently stall client work. That objective has two
halves, and the second is the one that matters. Recording leave is easy;
noticing that a client is waiting on someone who is away is the point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from psycopg.types.range import Range
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flow.calendar import WorkingCalendar
from app.models import Absence, Person, WorkItem, WorkItemParticipant
from app.work.lifecycle import TERMINAL, State

KINDS = ("LEAVE", "HOLIDAY", "OTHER")


class AbsenceError(Exception):
    """A business rule prevented the change."""


def record_absence(
    session: Session,
    *,
    person_id: int,
    start: date,
    end: date,
    kind: str,
    created_by: Person,
    note: str | None = None,
    approved_by: Person | None = None,
) -> Absence:
    """Book time off. `end` is inclusive — the last day away.

    Stored as a half-open `[start, end+1)` range because that is what
    PostgreSQL's `daterange` and its overlap operator expect. Getting this
    wrong by one day is the classic date-range bug, so the conversion happens
    in exactly one place.
    """
    if kind not in KINDS:
        raise AbsenceError(f"Kind must be one of: {', '.join(KINDS)}")
    if end < start:
        raise AbsenceError("The last day cannot be before the first day.")
    if (end - start).days > 365:
        raise AbsenceError("That is longer than a year — record it in shorter blocks.")

    person = session.get(Person, person_id)
    if person is None or not person.active:
        raise AbsenceError("That person is not active.")

    absence = Absence(
        person_id=person_id,
        period=Range(start, end + timedelta(days=1), bounds="[)"),
        kind=kind,
        note=note or None,
        created_at=datetime.now(UTC),
        created_by_id=created_by.id,
        created_by_name=created_by.name,
        approved_by_id=approved_by.id if approved_by else None,
        approved_at=datetime.now(UTC) if approved_by else None,
    )
    session.add(absence)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        # INV-5, enforced by the EXCLUDE constraint. Caught here to turn a
        # constraint violation into something a person can act on.
        raise AbsenceError(
            f"{person.name} already has absence recorded that overlaps those dates."
        ) from exc
    return absence


def approve(session: Session, absence: Absence, approver: Person) -> Absence:
    if absence.cancelled_at is not None:
        raise AbsenceError("That absence was cancelled.")
    absence.approved_by_id = approver.id
    absence.approved_at = datetime.now(UTC)
    session.flush()
    return absence


def cancel(session: Session, absence: Absence, actor: Person) -> Absence:
    """Cancelled, never deleted — consistent with every other record here."""
    if absence.cancelled_at is not None:
        return absence
    absence.cancelled_at = datetime.now(UTC)
    absence.cancelled_by_id = actor.id
    session.flush()
    return absence


def absences_for(
    session: Session, person_id: int, *, include_cancelled: bool = False
) -> list[Absence]:
    query = select(Absence).where(Absence.person_id == person_id)
    if not include_cancelled:
        query = query.where(Absence.cancelled_at.is_(None))
    return list(session.scalars(query.order_by(Absence.period.desc())))


def absent_person_ids(session: Session, day: date) -> set[int]:
    """Everyone away on a given day. One query, not one per person."""
    rows = session.execute(
        select(Absence.person_id).where(
            Absence.cancelled_at.is_(None),
            Absence.period.op("@>")(day),
        )
    ).scalars()
    return set(rows)


def upcoming(session: Session, *, within_days: int = 14, team_ids: list[int] | None = None) -> list[Absence]:
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=within_days)
    query = (
        select(Absence)
        .join(Person, Person.id == Absence.person_id)
        .where(
            Absence.cancelled_at.is_(None),
            Person.active.is_(True),
            Absence.period.op("&&")(Range(today, horizon, bounds="[)")),
        )
    )
    if team_ids is not None:
        query = query.where(Person.team_id.in_(team_ids))
    return list(session.scalars(query.order_by(Absence.period)))


# --------------------------------------------------------------------------
# CoverService — the half of BO-3 that actually matters
# --------------------------------------------------------------------------


@dataclass
class UncoveredWork:
    """Open work owned by someone who is away."""

    person_id: int
    person_name: str
    returns_on: date | None
    items: list[WorkItem] = field(default_factory=list)

    @property
    def urgent_count(self) -> int:
        return sum(1 for i in self.items if i.priority <= 1)

    def explanation(self, calendar: WorkingCalendar) -> str:
        """BR-020: the figure never travels without its derivation."""
        if self.returns_on is None:
            return f"{self.person_name} is away; return date unknown"
        days = calendar.working_days_between(datetime.now(UTC).date(), self.returns_on)
        return (
            f"{self.person_name} is away until {self.returns_on:%d %b} "
            f"({days} working day(s)), holding {len(self.items)} open item(s)"
        )


def uncovered_work(
    session: Session, *, day: date | None = None, team_ids: list[int] | None = None
) -> list[UncoveredWork]:
    """Open work whose owner is away today (BR-013, BO-3).

    Excludes items already parked on the client — if we are waiting for them,
    our absence is not what is holding it up, and flagging it would add noise
    to a list whose whole value is that everything on it needs action.
    """
    day = day or datetime.now(UTC).date()
    away = absent_person_ids(session, day)
    if not away:
        return []

    query = (
        select(WorkItem, Person)
        .join(
            WorkItemParticipant,
            (WorkItemParticipant.work_item_id == WorkItem.id)
            & (WorkItemParticipant.participation == "OWNER")
            & (WorkItemParticipant.to_ts.is_(None)),
        )
        .join(Person, Person.id == WorkItemParticipant.person_id)
        .where(
            Person.id.in_(away),
            WorkItem.state.not_in([s.value for s in TERMINAL]),
            WorkItem.state != State.BLOCKED_ON_CLIENT.value,
        )
        .order_by(Person.name, WorkItem.priority, WorkItem.id)
    )
    if team_ids is not None:
        query = query.where(Person.team_id.in_(team_ids))

    grouped: dict[int, UncoveredWork] = {}
    for item, person in session.execute(query):
        entry = grouped.get(person.id)
        if entry is None:
            entry = UncoveredWork(
                person_id=person.id,
                person_name=person.name,
                returns_on=_returns_on(session, person.id, day),
            )
            grouped[person.id] = entry
        entry.items.append(item)

    return sorted(grouped.values(), key=lambda e: (-e.urgent_count, e.person_name))


def _returns_on(session: Session, person_id: int, day: date) -> date | None:
    """First day back — the exclusive upper bound of the covering absence."""
    row = session.scalar(
        select(Absence.period).where(
            Absence.person_id == person_id,
            Absence.cancelled_at.is_(None),
            Absence.period.op("@>")(day),
        )
    )
    return row.upper if row is not None else None
