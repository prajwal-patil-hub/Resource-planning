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


def load_for_team(session: Session, team_id: int | None = None, *, today: date | None = None) -> list[PersonLoad]:
    """Current load for every active person, optionally scoped to one team."""
    today = today or datetime.now(UTC).date()

    query = select(Person).where(Person.active.is_(True))
    if team_id is not None:
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
            Absence.period.op("@>")(day),
        )
    ).first()
    return row is not None
