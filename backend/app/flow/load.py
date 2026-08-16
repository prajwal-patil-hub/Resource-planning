"""Load and availability (ADR-001).

Load is measured in items, not hours, because effort data will not be entered
(K-019). Every function here returns the evidence alongside the number, per
BR-020 — a figure a lead cannot interrogate will not be trusted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Absence, Person, WorkItem, WorkItemParticipant  # type: ignore[attr-defined]
from app.work.lifecycle import LOAD_BEARING, State


@dataclass
class PersonLoad:
    person_id: int
    name: str
    normal_load: int
    #: Items currently IN_PROGRESS and owned by this person.
    in_progress: list[WorkItem] = field(default_factory=list)
    #: Owned but not started — the personal queue, made visible.
    queued: list[WorkItem] = field(default_factory=list)
    absent_today: bool = False

    @property
    def load(self) -> int:
        return len(self.in_progress)

    @property
    def is_overloaded(self) -> bool:
        """RULE-007: relative to this person's own normal level, never a global
        threshold. People genuinely differ, and one number would be wrong for
        most of them."""
        return self.load > self.normal_load

    @property
    def has_room(self) -> bool:
        return self.load < self.normal_load and not self.absent_today

    @property
    def explanation(self) -> str:
        """BR-020: how this figure was arrived at."""
        titles = ", ".join(f"#{i.id}" for i in self.in_progress) or "nothing"
        return (
            f"{self.load} item(s) in progress ({titles}); "
            f"normal level for {self.name} is {self.normal_load}"
        )


def load_for_team(
    session: Session,
    team_id: int | None = None,
    *,
    team_ids: list[int] | None = None,
    today: date | None = None,
) -> list[PersonLoad]:
    """Current load per active person, optionally scoped to one or more teams."""
    today = today or datetime.now(UTC).date()

    query = select(Person).where(Person.active.is_(True))
    if team_ids is not None:
        query = query.where(Person.team_id.in_(team_ids))
    elif team_id is not None:
        query = query.where(Person.team_id == team_id)
    people = list(session.scalars(query.order_by(Person.name)))

    result: list[PersonLoad] = []
    for person in people:
        owned = list(
            session.scalars(
                select(WorkItem)
                .join(
                    WorkItemParticipant,
                    WorkItemParticipant.work_item_id == WorkItem.id,
                )
                .where(
                    WorkItemParticipant.person_id == person.id,
                    WorkItemParticipant.participation == "OWNER",
                    WorkItemParticipant.to_ts.is_(None),
                )
                .order_by(WorkItem.priority, WorkItem.id)
            )
        )
        entry = PersonLoad(
            person_id=person.id,
            name=person.name,
            normal_load=person.normal_load,
            in_progress=[i for i in owned if State(i.state) in LOAD_BEARING],
            queued=[i for i in owned if State(i.state) is State.QUEUED],
            absent_today=_is_absent(session, person.id, today),
        )
        result.append(entry)
    return result


def _is_absent(session: Session, person_id: int, day: date) -> bool:
    row = session.execute(
        select(Absence.id).where(
            Absence.person_id == person_id,
            Absence.cancelled_at.is_(None),
            Absence.period.op("@>")(day),
        )
    ).first()
    return row is not None


# --------------------------------------------------------------------------
# Assignment context (BR-016)
# --------------------------------------------------------------------------


@dataclass
class AssignmentOption:
    """One person, as they look at the moment someone is choosing an assignee.

    BR-016 asks that load and absence be visible *before* assigning. The load
    strip already showed both, on a different part of a different screen — which
    satisfies the letter of the requirement and none of its purpose. A lead
    picking a name from a dropdown was choosing blind, and the system knew.
    """

    person_id: int
    name: str
    load: int
    normal_load: int
    queued: int
    #: First day back, where they are away today. `None` means they are here.
    returns_on: date | None = None

    @property
    def is_away(self) -> bool:
        return self.returns_on is not None

    @property
    def is_over(self) -> bool:
        return self.load > self.normal_load

    @property
    def has_room(self) -> bool:
        return self.load < self.normal_load and not self.is_away

    @property
    def label(self) -> str:
        """What goes in the dropdown itself.

        Deliberately terse and uniform: this is read while the reader is doing
        something else, so it has to be scannable at a glance rather than read.
        """
        if self.is_away:
            return f"{self.name} — away until {self.returns_on.strftime('%-d %b')}"
        state = "over" if self.is_over else ("free" if self.has_room else "full")
        tail = f", {self.queued} waiting" if self.queued else ""
        return f"{self.name} — {self.load} of {self.normal_load}{tail} · {state}"

    @property
    def explanation(self) -> str:
        """BR-020. The label is a number; this is where it came from."""
        parts = [
            f"{self.load} item(s) in progress against a normal level of "
            f"{self.normal_load} for {self.name}"
        ]
        if self.queued:
            parts.append(f"{self.queued} more owned but not started")
        if self.is_away:
            parts.append(f"away today, back {self.returns_on.strftime('%-d %b')}")
        return "; ".join(parts)


def assignment_options(
    session: Session,
    *,
    team_ids: list[int] | None = None,
    today: date | None = None,
) -> list[AssignmentOption]:
    """Everyone who could take this work, with what it would cost them.

    Note what this deliberately does **not** do: it does not rank people, and it
    does not refuse anyone. Assignment is not reserved to one role (K-029), and
    people are assigned work for reasons the system cannot see — they know the
    client, they wrote the code, they are back tomorrow. Sorting by spare
    capacity would quietly turn a fact into an instruction, and refusing an
    absent person would be wrong the first time someone queues up Monday's work
    on Friday. So: state the facts plainly, in a stable order, and let the
    person choosing decide.
    """
    today = today or datetime.now(UTC).date()
    entries = load_for_team(session, team_ids=team_ids, today=today)

    options = [
        AssignmentOption(
            person_id=entry.person_id,
            name=entry.name,
            load=entry.load,
            normal_load=entry.normal_load,
            queued=len(entry.queued),
            returns_on=_returns_on(session, entry.person_id, today)
            if entry.absent_today
            else None,
        )
        for entry in entries
    ]
    # Alphabetical, because the reader is looking for a name they already have
    # in mind and any other order makes them hunt for it. Grouping the away
    # people apart is the template's job — that is presentation, not policy.
    return sorted(options, key=lambda o: o.name)


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
