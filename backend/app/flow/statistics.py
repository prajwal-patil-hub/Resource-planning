"""Forecasting from history (BR-018, RULE-009, RULE-010, RULE-013, BO-6).

This is the module ADR-001 was written to make possible. Nobody will enter an
estimate (K-019), so the only honest way to answer *"when will this be done?"*
is to look at how long comparable work has actually taken.

**Three decisions govern everything here.**

**1. Percentiles, not averages.** Cycle times are right-skewed — most items
finish quickly and a few drag on for weeks. The mean sits above the majority and
below the tail, describing nothing that happens. "Half finish within 2 days, and
85% within 6" is both true and usable; "the average is 4.1 days" is neither.

**2. A range with a stated confidence, never a date** (RULE-010). A single date
is a promise the data cannot support, and a promise that breaks costs more trust
than a range that was honest about being one.

**3. Silence above a wrong answer** (RULE-013). Below a minimum sample this
module returns "not yet known" and says why. Forecasting from three completed
items produces a confident number with no basis, and the first time it is wrong
it takes every other figure in the product down with it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.flow.calendar import WorkingCalendar, resolve_optional_days, working_duration
from app.models import StateTransition, WorkItem
from app.work.lifecycle import State

#: Fewest comparable finished items required before this module will answer.
#:
#: RULE-013. Eight is the point where a percentile stops being an anecdote: the
#: 85th is the second-slowest observation rather than the slowest, so one
#: unusual item can no longer define the whole upper bound on its own. For a
#: team recording twenty to forty items a month it is reachable in three to
#: four weeks, which is the timescale the stakeholder was told to expect.
MIN_SAMPLE = 8

#: How far back to look. Older work reflects a different team, a different
#: codebase and different clients, so including it makes the sample larger and
#: less relevant — the opposite of the trade the sample size is meant to buy.
DEFAULT_WINDOW_DAYS = 180


@dataclass(frozen=True)
class Sample:
    """One finished item, measured."""

    item_id: int
    type_id: int | None
    priority: int
    finished_at: datetime
    #: Working time from first record to done, weekends and holidays removed.
    elapsed: timedelta
    #: The same, less time spent waiting on the client (RULE-005).
    accountable: timedelta


@dataclass
class Cohort:
    """The comparable work a forecast was drawn from.

    Carried around with the forecast rather than discarded, because BR-020
    applies most sharply here: a predicted range that cannot be traced back to
    the items it came from is indistinguishable from a guess.
    """

    #: How these were judged comparable, in words a reader can check.
    basis: str
    samples: list[Sample] = field(default_factory=list)
    #: How specific this cohort is — 0 = type and priority, 2 = all work.
    precision: int = 0

    @property
    def size(self) -> int:
        return len(self.samples)

    @property
    def is_sufficient(self) -> bool:
        return self.size >= MIN_SAMPLE

    def percentile(self, p: float) -> timedelta:
        """Nearest-rank percentile of accountable working time.

        Deliberately not interpolated. With eight observations, interpolating
        between the sixth and seventh manufactures a precision the sample does
        not contain — and the whole point of this module is to stop doing that.
        """
        if not self.samples:
            return timedelta()
        ordered = sorted(s.accountable for s in self.samples)
        rank = max(1, min(len(ordered), int(-(-p * len(ordered) // 1))))
        return ordered[rank - 1]


@dataclass
class Forecast:
    """An answer, or an honest refusal to give one."""

    known: bool
    cohort: Cohort | None = None
    #: Half of comparable work finished within this.
    typical: timedelta = timedelta()
    #: 85% finished within this. The number to plan against.
    likely_within: timedelta = timedelta()
    #: The slowest comparable item, kept so the tail is never hidden.
    worst: timedelta = timedelta()
    #: Why there is no answer, when there is none.
    reason: str = ""

    @property
    def confidence(self) -> str:
        """Stated plainly, per RULE-010. Never a percentage we cannot defend."""
        if not self.known or self.cohort is None:
            return "not yet known"
        if self.cohort.size >= 30:
            return "good — a solid run of comparable work"
        if self.cohort.size >= 15:
            return "fair — enough to be useful, still moving"
        return "low — a small sample, treat as indicative"

    @property
    def explanation(self) -> str:
        """BR-020. The derivation travels with the number, always."""
        if not self.known or self.cohort is None:
            return self.reason
        return (
            f"From {self.cohort.size} finished item(s) — {self.cohort.basis}. "
            f"Half finished within {_days(self.typical)}, 85% within "
            f"{_days(self.likely_within)}, the slowest took {_days(self.worst)}. "
            f"Working time only, with time waiting on the client removed."
        )


def _days(value: timedelta) -> str:
    days = value.total_seconds() / 86400
    if days < 1:
        return f"{value.total_seconds() / 3600:.0f} working hours"
    return f"{days:.1f} working days".replace(".0 ", " ")


# --------------------------------------------------------------------------
# Measuring what already happened
# --------------------------------------------------------------------------


def collect_samples(
    session: Session,
    calendar: WorkingCalendar,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: datetime | None = None,
) -> list[Sample]:
    """Measure every finished item in the window.

    One query for all transitions rather than a timeline per item: rebuilding
    each history separately would issue a query per item to draw one page, and
    this runs on every board load once forecasting is wired in.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=window_days)

    rows = session.execute(
        select(
            StateTransition.work_item_id,
            StateTransition.to_state,
            StateTransition.occurred_at,
            WorkItem.type_id,
            WorkItem.priority,
        )
        .join(WorkItem, WorkItem.id == StateTransition.work_item_id)
        .where(
            WorkItem.state == State.DONE.value,
            StateTransition.occurred_at >= since,
        )
        .order_by(StateTransition.work_item_id, StateTransition.occurred_at, StateTransition.id)
    ).all()

    if not rows:
        return []

    # Optional days (Saturdays) are resolved once across the whole window, not
    # per item: a Saturday somebody worked was a working day for the
    # organization, and re-deriving it per item would be the same query repeated.
    earliest = min(r.occurred_at for r in rows).date()
    calendar = resolve_optional_days(session, calendar, earliest, now.date())

    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row.work_item_id, []).append(row)

    samples: list[Sample] = []
    for item_id, events in grouped.items():
        # An item only counts once it has actually finished. A DONE item whose
        # DONE transition fell outside the window is measured from whatever is
        # inside it, so skip anything without both ends.
        done = next((e for e in events if e.to_state == State.DONE.value), None)
        if done is None or events[0].to_state != State.NEW.value:
            continue

        started, finished = events[0].occurred_at, done.occurred_at
        if finished <= started:
            continue

        elapsed = working_duration(started, finished, calendar)

        # Time the clock was stopped because we were waiting on them (RULE-005).
        client_wait = timedelta()
        for index, event in enumerate(events):
            if event.to_state != State.BLOCKED_ON_CLIENT.value:
                continue
            ends = events[index + 1].occurred_at if index + 1 < len(events) else finished
            client_wait += working_duration(event.occurred_at, ends, calendar)

        samples.append(
            Sample(
                item_id=item_id,
                type_id=events[0].type_id,
                priority=events[0].priority,
                finished_at=finished,
                elapsed=elapsed,
                accountable=max(timedelta(), elapsed - client_wait),
            )
        )

    return samples


# --------------------------------------------------------------------------
# Turning it into an answer
# --------------------------------------------------------------------------


class FlowStatistics:
    """Built once per request and asked many questions.

    Holding the sample in memory rather than querying per forecast is what makes
    it affordable to put a forecast on every row of a list.
    """

    def __init__(self, samples: list[Sample], *, min_sample: int = MIN_SAMPLE):
        self.samples = samples
        self.min_sample = min_sample

    # -- the cohort ladder --------------------------------------------------
    #
    # "Comparable" is a judgement, and narrowing it improves relevance while
    # destroying sample size. Rather than pick one compromise, this walks from
    # the most specific grouping to the least and stops at the first that has
    # enough data — then says which rung it landed on, so a reader can see
    # whether the answer came from work genuinely like theirs or from the
    # general run of things.

    def cohort_for(self, *, type_id: int | None, priority: int, type_name: str | None = None) -> Cohort:
        label = type_name or "this kind of work"
        ladder = [
            Cohort(
                basis=f"{label} at P{priority}",
                precision=0,
                samples=[s for s in self.samples if s.type_id == type_id and s.priority == priority],
            ),
            Cohort(
                basis=str(label),
                precision=1,
                samples=[s for s in self.samples if s.type_id == type_id],
            ),
            Cohort(
                basis="all finished work",
                precision=2,
                samples=list(self.samples),
            ),
        ]
        for cohort in ladder:
            if cohort.size >= self.min_sample:
                return cohort
        return ladder[-1]

    def forecast(
        self, *, type_id: int | None, priority: int, type_name: str | None = None
    ) -> Forecast:
        """How long comparable work has taken — or why we will not say."""
        cohort = self.cohort_for(type_id=type_id, priority=priority, type_name=type_name)

        if not cohort.is_sufficient:
            # RULE-013. This is the answer, not a failure to produce one.
            need = self.min_sample - cohort.size
            return Forecast(
                known=False,
                cohort=cohort,
                reason=(
                    f"Not enough history yet — {cohort.size} comparable finished "
                    f"item(s), and {self.min_sample} are needed before a range "
                    f"means anything. {need} more to go. Forecasting from this "
                    f"much data would produce a confident number with nothing "
                    f"behind it."
                ),
            )

        return Forecast(
            known=True,
            cohort=cohort,
            typical=cohort.percentile(0.50),
            likely_within=cohort.percentile(0.85),
            worst=cohort.percentile(1.0),
        )

    # -- the overview page --------------------------------------------------

    def by_type(self, type_names: dict[int | None, str]) -> list[tuple[str, Cohort]]:
        """Cycle time per work type, for the flow screen."""
        groups: dict[int | None, list[Sample]] = {}
        for sample in self.samples:
            groups.setdefault(sample.type_id, []).append(sample)
        out = [
            (
                type_names.get(type_id, "Untyped"),
                Cohort(basis=type_names.get(type_id, "Untyped"), samples=rows),
            )
            for type_id, rows in groups.items()
        ]
        return sorted(out, key=lambda pair: -pair[1].size)

    def throughput(self, *, weeks: int = 8, now: datetime | None = None) -> list[tuple[str, int]]:
        """Items finished per week — the other half of flow.

        Cycle time says how long one item takes; throughput says how many the
        team gets through. A team can improve one while damaging the other, so
        neither is reported alone.
        """
        now = now or datetime.now(UTC)
        buckets: list[tuple[str, int]] = []
        for index in range(weeks - 1, -1, -1):
            end = now - timedelta(weeks=index)
            start = end - timedelta(weeks=1)
            count = sum(1 for s in self.samples if start < s.finished_at <= end)
            buckets.append((end.strftime("%-d %b"), count))
        return buckets


def load_statistics(
    session: Session,
    calendar: WorkingCalendar,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: datetime | None = None,
) -> FlowStatistics:
    return FlowStatistics(
        collect_samples(session, calendar, window_days=window_days, now=now)
    )


def accountable_so_far(
    session: Session,
    calendar: WorkingCalendar,
    *,
    now: datetime | None = None,
) -> dict[int, timedelta]:
    """Working time each still-open item has already consumed.

    The same measure as `Sample.accountable`, applied to work in flight, so an
    open item and the finished items it is compared against are measured with
    one ruler. Comparing calendar time against working time — or against time
    that still includes client wait — would make every item look worse than the
    history it is judged by, and the flags built on it would be noise.
    """
    now = now or datetime.now(UTC)

    rows = session.execute(
        select(
            StateTransition.work_item_id,
            StateTransition.to_state,
            StateTransition.occurred_at,
        )
        .join(WorkItem, WorkItem.id == StateTransition.work_item_id)
        .where(WorkItem.state.not_in([State.DONE.value, State.CANCELLED.value]))
        .order_by(StateTransition.work_item_id, StateTransition.occurred_at, StateTransition.id)
    ).all()

    if not rows:
        return {}

    earliest = min(r.occurred_at for r in rows).date()
    calendar = resolve_optional_days(session, calendar, earliest, now.date())

    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row.work_item_id, []).append(row)

    result: dict[int, timedelta] = {}
    for item_id, events in grouped.items():
        started = events[0].occurred_at
        elapsed = working_duration(started, now, calendar)

        client_wait = timedelta()
        for index, event in enumerate(events):
            if event.to_state != State.BLOCKED_ON_CLIENT.value:
                continue
            ends = events[index + 1].occurred_at if index + 1 < len(events) else now
            client_wait += working_duration(event.occurred_at, ends, calendar)

        result[item_id] = max(timedelta(), elapsed - client_wait)

    return result


# --------------------------------------------------------------------------
# Applying it to work that is still open (RULE-009, BR-017)
# --------------------------------------------------------------------------


@dataclass
class Projection:
    """Where one open item stands against comparable finished work."""

    forecast: Forecast
    #: Working time this item has already consumed, client wait removed.
    spent: timedelta
    #: What is left, if it behaves like 85% of its cohort. None when unknown.
    remaining: timedelta | None
    #: True once it has already outlasted 85% of comparable work.
    overrunning: bool = False

    @property
    def explanation(self) -> str:
        if not self.forecast.known:
            return self.forecast.reason
        if self.overrunning:
            return (
                f"Already {_days(self.spent)} in. 85% of comparable work finished "
                f"within {_days(self.forecast.likely_within)}, so this one is "
                f"behaving unlike the rest — worth asking why."
            )
        return (
            f"{_days(self.spent)} in. Comparable work finishes within "
            f"{_days(self.forecast.likely_within)} in 85% of cases, leaving "
            f"about {_days(self.remaining or timedelta())} if this behaves the same."
        )


def project(forecast: Forecast, spent: timedelta) -> Projection:
    """Compare one open item against its cohort.

    Note what this does not do: it does not produce a finish date. Converting
    "about three working days left" into "Thursday" would hide the range inside
    a date and hand someone a promise the data never made (RULE-010).
    """
    if not forecast.known:
        return Projection(forecast=forecast, spent=spent, remaining=None)

    overrunning = spent > forecast.likely_within
    return Projection(
        forecast=forecast,
        spent=spent,
        remaining=None if overrunning else forecast.likely_within - spent,
        overrunning=overrunning,
    )
