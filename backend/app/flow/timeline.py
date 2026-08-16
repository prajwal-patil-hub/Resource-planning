"""Item timeline and time-in-state report (ADR-003).

Answers "how long did this take, and where did the time go" purely from recorded
events — no estimates, no timesheets (ADR-001).

Every figure returned here carries the inputs it was derived from, because
BR-020 requires that a user be able to interrogate any number the system shows.
A metric that arrives as a bare number is a metric nobody can check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Person,
    StateTransition,
    WorkItem,
    WorkItemAudit,
    WorkItemParticipant,
)
from app.flow.calendar import WorkingCalendar, working_duration
from app.work.lifecycle import CLOCK_STOPPED, LABELS, TERMINAL, State


@dataclass
class Span:
    """A period the item spent in one state."""

    state: State
    entered_at: datetime
    left_at: datetime | None
    duration: timedelta
    #: The same span with weekends and holidays removed (BR-014).
    working_duration: timedelta = timedelta()

    @property
    def is_open(self) -> bool:
        return self.left_at is None


@dataclass
class OwnerSpell:
    """A period one person owned the item."""

    person_name: str
    person_id: int
    assigned_by: str
    from_ts: datetime
    to_ts: datetime | None
    duration: timedelta


@dataclass
class Displacement:
    """A moment this item was set aside for something more urgent."""

    occurred_at: datetime
    displaced_by_id: int
    displaced_by_title: str
    by_person: str


@dataclass
class ItemTimeline:
    """The full history of one work item, with derived measures."""

    item_id: int
    title: str
    state: State
    created_at: datetime
    finished_at: datetime | None

    spans: list[Span] = field(default_factory=list)
    owners: list[OwnerSpell] = field(default_factory=list)
    displacements: list[Displacement] = field(default_factory=list)
    field_changes: list[WorkItemAudit] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)

    time_in_state: dict[State, timedelta] = field(default_factory=dict)
    working_time_in_state: dict[State, timedelta] = field(default_factory=dict)
    total_elapsed: timedelta = timedelta()
    working_elapsed: timedelta = timedelta()
    active_time: timedelta = timedelta()
    waiting_on_us: timedelta = timedelta()
    waiting_on_client: timedelta = timedelta()
    verification_time: timedelta = timedelta()
    time_to_first_touch: timedelta | None = None
    rework_count: int = 0
    preemption_count: int = 0
    max_recording_lag: timedelta = timedelta()

    @property
    def accountable_elapsed(self) -> timedelta:
        """Working time we are answerable for.

        Two corrections applied to raw elapsed time, for two different reasons:

        - **weekends and holidays removed** (BR-014) — nobody was working, so
          counting it would make every Friday-afternoon request look mishandled;
        - **time waiting on the client removed** (RULE-005) — the delay was
          theirs.

        This is the number to use when discussing lateness. `total_elapsed`
        stays calendar time, because that is what the client actually waited.
        """
        return max(
            timedelta(),
            self.working_elapsed - self.working_time_in_state.get(State.BLOCKED_ON_CLIENT, timedelta()),
        )

    @property
    def weekend_and_holiday_time(self) -> timedelta:
        """How much of the wall clock was non-working. Shown so the difference
        between the two elapsed figures is never mysterious (BR-020)."""
        return max(timedelta(), self.total_elapsed - self.working_elapsed)


def build_timeline(
    session: Session,
    work_item_id: int,
    *,
    now: datetime | None = None,
    calendar: WorkingCalendar | None = None,
) -> ItemTimeline:
    """Reconstruct one item's history from its recorded events."""
    item = session.get(WorkItem, work_item_id)
    if item is None:
        raise LookupError(f"No work item {work_item_id}")

    now = now or datetime.now(UTC)
    if calendar is None:
        from app.flow.calendar import load_calendar

        calendar = load_calendar(session)

    transitions = list(
        session.scalars(
            select(StateTransition)
            .where(StateTransition.work_item_id == work_item_id)
            .order_by(StateTransition.occurred_at, StateTransition.id)
        )
    )

    # Anchor elapsed time on the FIRST EVENT's occurred_at, not on the row's
    # created_at. BR-004 permits recording work after the fact, so created_at is
    # when the row was typed — using it would make a backdated item's elapsed
    # time wrong, and in the worst case negative. Same class of mistake as
    # measuring cycle time from recorded_at.
    started_at = transitions[0].occurred_at if transitions else item.created_at

    timeline = ItemTimeline(
        item_id=item.id,
        title=item.title,
        state=State(item.state),
        created_at=started_at,
        finished_at=None,
        transitions=transitions,
    )

    # ---- Spans: walk consecutive transitions and take the gaps ----
    for index, event in enumerate(transitions):
        entered = event.occurred_at
        # An item's final span is still running unless it reached a terminal state.
        is_last = index == len(transitions) - 1
        left = None if is_last else transitions[index + 1].occurred_at
        state = State(event.to_state)

        if is_last and state in TERMINAL:
            timeline.finished_at = entered
            duration = timedelta()
        else:
            duration = (left or now) - entered

        working = (
            timedelta()
            if duration == timedelta()
            else working_duration(entered, left or now, calendar)
        )
        span = Span(
            state=state, entered_at=entered, left_at=left,
            duration=duration, working_duration=working,
        )
        timeline.spans.append(span)
        timeline.time_in_state[state] = timeline.time_in_state.get(state, timedelta()) + duration
        timeline.working_time_in_state[state] = (
            timeline.working_time_in_state.get(state, timedelta()) + working
        )

        lag = event.recorded_at - event.occurred_at
        timeline.max_recording_lag = max(timeline.max_recording_lag, lag)

        if event.to_state == State.ON_HOLD_PREEMPTED.value:
            timeline.preemption_count += 1
        if (
            event.from_state == State.IN_VERIFICATION.value
            and event.to_state == State.IN_PROGRESS.value
        ):
            timeline.rework_count += 1

    end = timeline.finished_at or now
    timeline.total_elapsed = end - timeline.created_at
    timeline.working_elapsed = working_duration(timeline.created_at, end, calendar)

    # These are reported in working time: they describe how long WE had the
    # item, and counting a weekend against a developer is simply wrong.
    working = timeline.working_time_in_state
    timeline.active_time = working.get(State.IN_PROGRESS, timedelta())
    timeline.verification_time = working.get(State.IN_VERIFICATION, timedelta())
    timeline.waiting_on_client = sum(
        (working.get(s, timedelta()) for s in CLOCK_STOPPED), timedelta()
    )
    timeline.waiting_on_us = (
        working.get(State.NEW, timedelta())
        + working.get(State.QUEUED, timedelta())
        + working.get(State.ON_HOLD_PREEMPTED, timedelta())
    )

    # Time to first touch: created -> first time anyone actually started it.
    # This measures F-001 and F-002 directly — how long work sits before anyone
    # picks it up — and is probably the most actionable single number for a lead.
    first_start = next(
        (t.occurred_at for t in transitions if t.to_state == State.IN_PROGRESS.value),
        None,
    )
    if first_start is not None:
        timeline.time_to_first_touch = working_duration(
            timeline.created_at, first_start, calendar
        )

    # ---- Who worked on it, and when ----
    participants = list(
        session.scalars(
            select(WorkItemParticipant)
            .where(WorkItemParticipant.work_item_id == work_item_id)
            .order_by(WorkItemParticipant.from_ts, WorkItemParticipant.id)
        )
    )
    for participant in participants:
        assigner = session.get(Person, participant.assigned_by_id)
        timeline.owners.append(
            OwnerSpell(
                person_name=participant.person.name,
                person_id=participant.person_id,
                assigned_by=assigner.name if assigner else "unknown",
                from_ts=participant.from_ts,
                to_ts=participant.to_ts,
                duration=(participant.to_ts or now) - participant.from_ts,
            )
        )

    # ---- What displaced it (BO-4) ----
    for event in transitions:
        if event.displaced_by_id is None:
            continue
        displacer = session.get(WorkItem, event.displaced_by_id)
        timeline.displacements.append(
            Displacement(
                occurred_at=event.occurred_at,
                displaced_by_id=event.displaced_by_id,
                displaced_by_title=displacer.title if displacer else "(removed)",
                by_person=event.changed_by.name,
            )
        )

    # ---- Field-level history (ADR-003 layer 2) ----
    timeline.field_changes = list(
        session.scalars(
            select(WorkItemAudit)
            .where(WorkItemAudit.work_item_id == work_item_id)
            .order_by(WorkItemAudit.occurred_at, WorkItemAudit.id)
        )
    )

    return timeline


def format_duration(delta: timedelta) -> str:
    """Human-readable duration. Precision degrades as magnitude grows.

    Nobody needs to know something took '3 days, 4 hours and 17 minutes'.
    Over-precise durations imply a measurement accuracy we do not have.
    """
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h".replace(".0h", "h")
    days = hours / 24
    return f"{days:.1f}d".replace(".0d", "d")


def state_label(state: State) -> str:
    return LABELS[state]
