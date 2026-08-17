"""What needs someone today (BR-007, BR-016, BO-2).

The board shows everything. This shows only what is wrong, and it is the
difference between a system you look at and a system that tells you.

**The governing rule for this module: everything on the list must need action.**
One item that does not belong teaches people to skim, and a list people skim is
worse than no list — it provides the feeling of having checked without the fact
of it. So each detector below excludes cases that look wrong and are not, and
each exclusion is stated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.flow.calendar import WorkingCalendar, resolve_optional_days, working_duration
from app.flow.statistics import FlowStatistics, accountable_so_far, project
from app.models import Person, StateTransition, WorkItem, WorkItemParticipant
from app.people.absence import absent_person_ids
from app.work.lifecycle import TERMINAL, State


@dataclass
class Flag:
    """One thing that needs attention, with the reason it was flagged.

    `why` is not decoration. BR-020: every figure the product shows must be
    explainable, and a list of problems is a figure.
    """

    item: WorkItem
    owner_name: str | None
    why: str
    severity: int          #: 0 = act now, 1 = today, 2 = this week
    measure: str = ""      #: the number behind the flag
    detail: str = ""       #: the full derivation, where one exists (BR-020)


@dataclass
class Attention:
    unowned: list[Flag] = field(default_factory=list)
    stalled: list[Flag] = field(default_factory=list)
    overdue: list[Flag] = field(default_factory=list)
    at_risk: list[Flag] = field(default_factory=list)
    overrunning: list[Flag] = field(default_factory=list)
    uncovered: list[Flag] = field(default_factory=list)
    overloaded: list[str] = field(default_factory=list)

    @property
    def groups(self) -> tuple[list[Flag], ...]:
        return (
            self.unowned, self.stalled, self.overdue,
            self.at_risk, self.overrunning, self.uncovered,
        )

    @property
    def total(self) -> int:
        return sum(len(group) for group in self.groups)

    @property
    def act_now(self) -> int:
        return sum(1 for group in self.groups for flag in group if flag.severity == 0)


def _fmt_days(delta: timedelta) -> str:
    days = delta.total_seconds() / 86400
    if days < 1:
        return f"{delta.total_seconds() / 3600:.0f}h"
    return f"{days:.1f}d".replace(".0d", "d")


def build_attention(
    session: Session,
    *,
    calendar: WorkingCalendar,
    team_ids: list[int] | None = None,
    stale_after_days: int = 3,
    now: datetime | None = None,
    stats: FlowStatistics | None = None,
) -> Attention:
    now = now or datetime.now(UTC)
    today = now.date()
    result = Attention()

    # BR-017 / RULE-009. Without history this stays None and the two
    # history-driven flags below simply do not fire — which is RULE-013 working
    # as intended, not a degraded mode.
    spent_by_item = accountable_so_far(session, calendar, now=now) if stats else {}

    # One query for every open item with its owner and last movement. A
    # per-item lookup would issue hundreds of queries to build one screen.
    rows = session.execute(
        select(
            WorkItem,
            Person,
            select(StateTransition.occurred_at)
            .where(StateTransition.work_item_id == WorkItem.id)
            .order_by(StateTransition.occurred_at.desc())
            .limit(1)
            .scalar_subquery()
            .label("last_moved"),
            select(StateTransition.occurred_at)
            .where(StateTransition.work_item_id == WorkItem.id)
            .order_by(StateTransition.occurred_at)
            .limit(1)
            .scalar_subquery()
            .label("first_seen"),
        )
        .outerjoin(
            WorkItemParticipant,
            (WorkItemParticipant.work_item_id == WorkItem.id)
            & (WorkItemParticipant.participation == "OWNER")
            & (WorkItemParticipant.to_ts.is_(None)),
        )
        .outerjoin(Person, Person.id == WorkItemParticipant.person_id)
        .where(WorkItem.state.not_in([s.value for s in TERMINAL]))
        .order_by(WorkItem.priority, WorkItem.id)
    ).all()

    if team_ids is not None:
        rows = [r for r in rows if r[1] is None or r[1].team_id in team_ids]

    if not rows:
        return result

    earliest = min((r.first_seen or now) for r in rows).date()
    calendar = resolve_optional_days(session, calendar, earliest, today)
    away = absent_person_ids(session, today)

    for item, owner, last_moved, _first_seen in rows:
        state = State(item.state)
        owner_name = owner.name if owner else None

        # ---- Nobody owns it (F-001) -------------------------------------
        if owner is None:
            age = working_duration(last_moved or now, now, calendar)
            result.unowned.append(
                Flag(
                    item=item,
                    owner_name=None,
                    why="Nobody has picked this up",
                    severity=0 if item.priority <= 1 else 1,
                    measure=f"recorded {_fmt_days(age)} ago",
                )
            )
            # Deliberately no `continue`: unowned work can also be overdue, and
            # a lead needs to know both.

        # ---- Stopped moving (F-002, BO-2) -------------------------------
        #
        # Excluded: items waiting on the client. They are not stalled by us,
        # and including them would fill the list with things nobody here can
        # act on — which is exactly how a list stops being read.
        is_stalled = False
        if last_moved and state is not State.BLOCKED_ON_CLIENT:
            still = working_duration(last_moved, now, calendar)
            if still >= timedelta(days=stale_after_days):
                is_stalled = True
                result.stalled.append(
                    Flag(
                        item=item,
                        owner_name=owner_name,
                        why="No movement",
                        severity=0 if item.priority <= 1 else 1,
                        measure=f"{_fmt_days(still)} of working time",
                    )
                )

        # ---- Past its due date (K-023) ----------------------------------
        if item.due_date and item.due_date < today:
            late = calendar.working_days_between(item.due_date, today) - 1
            result.overdue.append(
                Flag(
                    item=item,
                    owner_name=owner_name,
                    why="Past the date the client was given",
                    severity=0,
                    measure=f"{max(late, 0)} working day(s) over",
                )
            )

        # ---- Going to miss its date (BR-017) ----------------------------
        #
        # Not "is it late" but "will it be". Flagged only where there is still
        # time to act — an item due tomorrow that has not started is worth a
        # nudge; one due in three weeks is not.
        elif item.due_date and state in (State.NEW, State.QUEUED, State.ON_HOLD_PREEMPTED):
            left = calendar.working_days_between(today, item.due_date) - 1
            if 0 <= left <= 2:
                result.at_risk.append(
                    Flag(
                        item=item,
                        owner_name=owner_name,
                        why="Due soon and not started",
                        severity=0 if left == 0 else 1,
                        measure=f"{left} working day(s) left",
                    )
                )

        # ---- What the history says (BR-017, RULE-009) -------------------
        #
        # The two flags above read the calendar. These read the record: how long
        # work like this has actually taken. That is the stronger form of the
        # requirement, and the reason this could not be built until recorded
        # timestamps were trustworthy.
        #
        # Both stay silent when the sample is too small (RULE-013). A quiet
        # screen is the correct output of a system that does not yet know.
        if stats is not None and state not in (State.BLOCKED_ON_CLIENT,):
            spent = spent_by_item.get(item.id)
            if spent is not None:
                forecast = stats.forecast(
                    type_id=item.type_id,
                    priority=item.priority,
                    type_name=item.type.name if item.type else None,
                )
                projection = project(forecast, spent)

                if projection.overrunning and not is_stalled:
                    # RULE-009. It has outlasted 85% of comparable work, so
                    # whatever is happening is not the normal course of this
                    # kind of job.
                    #
                    # Suppressed when the item is already flagged as stalled.
                    # Both are true and the second adds nothing: "nothing has
                    # happened for four weeks" already explains why it has
                    # outrun its history, and it is the more actionable of the
                    # two. Two rows saying one thing is exactly the noise D-031
                    # forbids — a list people skim is worse than no list.
                    result.overrunning.append(
                        Flag(
                            item=item,
                            owner_name=owner_name,
                            why="Taking longer than work like it usually does",
                            severity=0 if item.priority <= 1 else 1,
                            measure=(
                                f"{_fmt_days(spent)} spent, 85% finish inside "
                                f"{_fmt_days(forecast.likely_within)}"
                            ),
                            detail=projection.explanation,
                        )
                    )
                elif (
                    item.due_date
                    and item.due_date >= today
                    and projection.remaining is not None
                ):
                    # Whole days are counted whole throughout this product
                    # (see calendar.working_duration), so a "working day" of
                    # elapsed time is directly comparable to a count of working
                    # days on the calendar.
                    days_needed = projection.remaining.total_seconds() / 86400
                    days_left = calendar.working_days_between(today, item.due_date) - 1
                    if days_needed > days_left:
                        result.at_risk.append(
                            Flag(
                                item=item,
                                owner_name=owner_name,
                                why="History says this will not make its date",
                                severity=0 if days_left <= 1 else 1,
                                measure=(
                                    f"needs about {days_needed:.1f} more working "
                                    f"day(s), {days_left} left"
                                ),
                                detail=projection.explanation,
                            )
                        )

        # ---- Owner is away (BO-3) ---------------------------------------
        if owner and owner.id in away and state is not State.BLOCKED_ON_CLIENT:
            result.uncovered.append(
                Flag(
                    item=item,
                    owner_name=owner_name,
                    why=f"{owner.name} is away",
                    severity=0 if item.priority <= 1 else 2,
                    measure="needs cover",
                )
            )

    for group in result.groups:
        group.sort(key=lambda f: (f.severity, f.item.priority))

    return result
