"""Where the work went, by client and by kind (BR-019).

The manager-facing view, and the one question the product could not answer
before: *"which clients consume us, and what does that consumption look like?"*

**A warning that shapes this whole module.**

The obvious heading for this page is "share of effort", and it would be a lie.
Under ADR-001 nobody records effort — there are no hours and there never will
be. What the record contains is **elapsed working time per item**, and two items
open across the same week contribute two item-weeks while costing one week of
the team.

So nothing here is presented as person-hours, capacity, or cost. It is presented
as what it is: how many items each client sent, how long those items were alive,
and how that time divided between us and them. Those are real, checkable
quantities. "Northwind consumed 34% of the team" is not, and this module refuses
to imply it.

**The number worth the page.** For each client, elapsed time splits in two:
time the work sat with us, and time it sat waiting on the client to answer
(RULE-005). A client whose work takes three weeks, two of which are their own
silence, is a completely different conversation from one whose work takes three
weeks of ours — and until now both looked identical.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.flow.statistics import Cohort, Sample
from app.models import Client, Person, WorkItem, WorkItemParticipant, WorkItemType
from app.work.lifecycle import OPEN_STATES


@dataclass
class ClientReport:
    """One client's demand on the team, measured from finished work."""

    client_id: int | None
    name: str
    samples: list[Sample] = field(default_factory=list)
    #: Still open right now — current commitment rather than history.
    open_now: int = 0
    #: Counts by work type name, so the *shape* of the demand is visible.
    mix: dict[str, int] = field(default_factory=dict)

    @property
    def finished(self) -> int:
        return len(self.samples)

    @property
    def total_elapsed(self) -> timedelta:
        return sum((s.elapsed for s in self.samples), timedelta())

    @property
    def ours(self) -> timedelta:
        """Working time the work sat with us."""
        return sum((s.accountable for s in self.samples), timedelta())

    @property
    def theirs(self) -> timedelta:
        """Working time the clock was stopped waiting on them (RULE-005)."""
        return sum((s.client_wait for s in self.samples), timedelta())

    @property
    def their_share(self) -> float:
        """Fraction of elapsed time that was the client's own wait.

        The figure this page exists to produce. High is not automatically bad —
        some work genuinely needs the client to decide something — but it is
        always worth knowing, and it is invisible without this.
        """
        total = self.total_elapsed.total_seconds()
        return (self.theirs.total_seconds() / total) if total else 0.0

    @property
    def cohort(self) -> Cohort:
        """So RULE-013 applies here exactly as it does everywhere else."""
        return Cohort(basis=f"work for {self.name}", samples=self.samples)

    @property
    def mix_summary(self) -> str:
        if not self.mix:
            return "—"
        ordered = sorted(self.mix.items(), key=lambda pair: -pair[1])
        return ", ".join(f"{name} ×{count}" for name, count in ordered[:4])

    def share_of(self, total_items: int) -> float:
        return (self.finished / total_items) if total_items else 0.0

    def explanation(self, total_items: int) -> str:
        """BR-020. Never a bare percentage."""
        return (
            f"{self.finished} of {total_items} finished item(s) "
            f"({self.share_of(total_items) * 100:.0f}%) were for {self.name}. "
            f"Those items were alive for {_d(self.total_elapsed)} of working time "
            f"in total — {_d(self.ours)} with us and {_d(self.theirs)} waiting on "
            f"them. This is elapsed time per item, not person-hours: two items "
            f"open the same week count twice and cost the team one week."
        )


def _d(value: timedelta) -> str:
    days = value.total_seconds() / 86400
    if days < 1:
        return f"{value.total_seconds() / 3600:.0f}h"
    return f"{days:.1f}d".replace(".0d", "d")


@dataclass
class ClientReportSet:
    reports: list[ClientReport] = field(default_factory=list)
    window_days: int = 0
    #: True when the viewer sees only some teams, so the totals are partial and
    #: the page must say so rather than presenting them as organisation-wide.
    scoped: bool = False

    @property
    def total_items(self) -> int:
        return sum(r.finished for r in self.reports)

    @property
    def total_elapsed(self) -> timedelta:
        return sum((r.total_elapsed for r in self.reports), timedelta())

    @property
    def total_theirs(self) -> timedelta:
        return sum((r.theirs for r in self.reports), timedelta())

    @property
    def overall_their_share(self) -> float:
        total = self.total_elapsed.total_seconds()
        return (self.total_theirs.total_seconds() / total) if total else 0.0


def build_client_reports(
    session: Session,
    samples: list[Sample],
    *,
    team_ids: list[int] | None = None,
    window_days: int = 0,
) -> ClientReportSet:
    """Group measured work by client.

    Scoped by the owner's team where the viewer cannot see everything. A client
    report names commercial volumes, so it follows the same visibility rule as
    the work it is built from (RULE-011) rather than quietly reaching wider —
    the same leak that was found in the load strip.

    A *finished* item always had an owner: INV-6 forbids work being in progress
    with nobody accountable, and `DONE` is only reachable through it. So a null
    team here means the owner belongs to no team, not that the work was
    ownerless — and those are included rather than dropped, because silently
    losing them would make the totals disagree with the board.

    Open work is scoped the same way. Leaving that column unscoped while the
    rest of the row was narrowed would put two different populations side by
    side in one table, which is worse than either alone.
    """
    scoped = team_ids is not None
    permitted = set(team_ids) if scoped else set()
    if scoped:
        samples = [s for s in samples if s.team_id is None or s.team_id in permitted]

    names = {row.id: row.name for row in session.scalars(select(Client))}
    type_names = {row.id: row.name for row in session.scalars(select(WorkItemType))}

    grouped: dict[int | None, ClientReport] = {}
    for sample in samples:
        report = grouped.get(sample.client_id)
        if report is None:
            report = ClientReport(
                client_id=sample.client_id,
                # Internal work is not an error and not a gap — it is a real
                # category, and lumping it under a blank would hide how much of
                # the team's time never reaches a client at all.
                name=names.get(sample.client_id, "No client — internal"),
            )
            grouped[sample.client_id] = report
        report.samples.append(sample)
        kind = type_names.get(sample.type_id, "Untyped")
        report.mix[kind] = report.mix.get(kind, 0) + 1

    # Open work, counted separately: history says what a client has cost, this
    # says what they are costing right now, and a manager needs both.
    open_query = (
        select(WorkItem.client_id, func.count(WorkItem.id))
        .outerjoin(
            WorkItemParticipant,
            (WorkItemParticipant.work_item_id == WorkItem.id)
            & (WorkItemParticipant.participation == "OWNER")
            & (WorkItemParticipant.to_ts.is_(None)),
        )
        .outerjoin(Person, Person.id == WorkItemParticipant.person_id)
        .where(WorkItem.state.in_([s.value for s in OPEN_STATES]))
        .group_by(WorkItem.client_id)
    )
    if scoped:
        # Open work genuinely can be ownerless — that is the whole point of
        # BR-003 — and unowned work is everybody's problem, so it stays visible
        # in every narrowed view, exactly as it does on the board.
        open_query = open_query.where(
            Person.team_id.is_(None) | Person.team_id.in_(permitted)
        )
    for client_id, count in session.execute(open_query):
        report = grouped.get(client_id)
        if report is None:
            report = ClientReport(
                client_id=client_id,
                name=names.get(client_id, "No client — internal"),
            )
            grouped[client_id] = report
        report.open_now = count

    # Sorted by volume: the page is read top-down and the clients that consume
    # most are the ones the reader came for.
    return ClientReportSet(
        reports=sorted(grouped.values(), key=lambda r: (-r.finished, -r.open_now, r.name)),
        window_days=window_days,
        scoped=scoped,
    )


def by_type_totals(samples: list[Sample], type_names: dict[int | None, str]) -> list[tuple[str, int, timedelta]]:
    """The other half of BR-019 — where work goes by kind, not by client."""
    totals: dict[int | None, list[Sample]] = {}
    for sample in samples:
        totals.setdefault(sample.type_id, []).append(sample)
    rows = [
        (
            type_names.get(type_id, "Untyped"),
            len(group),
            sum((s.elapsed for s in group), timedelta()),
        )
        for type_id, group in totals.items()
    ]
    return sorted(rows, key=lambda row: -row[1])
