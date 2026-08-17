"""Forecasting from history (BR-018, RULE-009, RULE-010, RULE-013, BO-6).

The module ADR-001 was written to make possible: nobody enters an estimate, so
the only honest answer to "when will this be done?" comes from how long
comparable work has actually taken.

The most important tests here are the ones asserting that it says **nothing**.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.flow.calendar import WorkingCalendar
from app.flow.statistics import (
    MIN_SAMPLE,
    Cohort,
    FlowStatistics,
    Sample,
    accountable_so_far,
    collect_samples,
    load_statistics,
    project,
)
from app.work.lifecycle import State
from app.work.service import assign, create_work_item, transition

#: No weekends, so a test asserting "3 working days" is not silently affected by
#: which day of the week it happens to run on.
ALWAYS = WorkingCalendar(weekend_days=frozenset(), holidays=frozenset())


def _sample(days: float, *, type_id=1, priority=2, item_id=0) -> Sample:
    return Sample(
        item_id=item_id,
        type_id=type_id,
        priority=priority,
        finished_at=datetime.now(UTC),
        elapsed=timedelta(days=days),
        accountable=timedelta(days=days),
    )


def _finish(session, person, *, title, days, type_id=None, priority=2, client_wait_days=0):
    """Record an item that was worked for `days` and then finished."""
    start = datetime.now(UTC) - timedelta(days=days + 1)
    item = create_work_item(
        session, title=title, created_by_id=person.id, type_id=type_id,
        priority=priority, occurred_at=start,
    )
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)
    if client_wait_days:
        transition(session, item=item, to_state=State.BLOCKED_ON_CLIENT, actor_id=person.id,
                   occurred_at=start)
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
                   occurred_at=start + timedelta(days=client_wait_days))
    transition(session, item=item, to_state=State.DONE, actor_id=person.id,
               occurred_at=start + timedelta(days=days))
    return item


# --------------------------------------------------------------------------
# RULE-013 — the refusal, which is the point of the module
# --------------------------------------------------------------------------


def test_it_refuses_to_forecast_from_too_little_history():
    """Forecasting from three finished items produces a confident number with
    nothing behind it. Saying so is the answer, not a failure to produce one."""
    stats = FlowStatistics([_sample(2) for _ in range(3)])

    forecast = stats.forecast(type_id=1, priority=2)

    assert not forecast.known
    assert forecast.typical == timedelta()
    assert "Not enough history" in forecast.reason


def test_the_refusal_says_how_much_more_is_needed(session):
    """A blank "unknown" invites people to assume the feature is broken. Saying
    "five more to go" makes it a countdown instead."""
    stats = FlowStatistics([_sample(2) for _ in range(3)])

    reason = stats.forecast(type_id=1, priority=2).reason

    assert f"{MIN_SAMPLE} are needed" in reason
    assert f"{MIN_SAMPLE - 3} more to go" in reason


def test_it_answers_once_there_is_enough(session):
    stats = FlowStatistics([_sample(2) for _ in range(MIN_SAMPLE)])

    assert stats.forecast(type_id=1, priority=2).known


def test_the_boundary_is_exact(session):
    assert not FlowStatistics([_sample(2)] * (MIN_SAMPLE - 1)).forecast(
        type_id=1, priority=2
    ).known
    assert FlowStatistics([_sample(2)] * MIN_SAMPLE).forecast(
        type_id=1, priority=2
    ).known


# --------------------------------------------------------------------------
# Percentiles, not averages
# --------------------------------------------------------------------------


def test_a_long_tail_does_not_drag_the_typical_figure():
    """The reason this uses percentiles at all. Cycle times are right-skewed:
    the mean sits above most items and below the tail, describing nothing that
    actually happens."""
    samples = [_sample(1) for _ in range(9)] + [_sample(60)]
    cohort = Cohort(basis="test", samples=samples)

    mean_days = sum(s.accountable.days for s in samples) / len(samples)

    assert cohort.percentile(0.5) == timedelta(days=1)
    assert mean_days > 6           # the average says a week
    assert cohort.percentile(0.5).days == 1   # the median says a day


def test_the_slowest_item_is_reported_rather_than_hidden():
    """Trimming the tail would make the numbers prettier and the planning
    worse — the slow ones are precisely what a lead needs to see coming."""
    cohort = Cohort(basis="test", samples=[_sample(1)] * 9 + [_sample(60)])

    assert cohort.percentile(1.0) == timedelta(days=60)


def test_percentiles_are_not_interpolated():
    """With eight observations, interpolating between the sixth and seventh
    manufactures precision the sample does not contain."""
    cohort = Cohort(basis="test", samples=[_sample(d) for d in range(1, 11)])

    # Nearest-rank: every result is an observation that actually occurred.
    observed = {timedelta(days=d) for d in range(1, 11)}
    for p in (0.5, 0.85, 1.0):
        assert cohort.percentile(p) in observed


def test_an_empty_cohort_returns_zero_rather_than_raising():
    assert Cohort(basis="none").percentile(0.5) == timedelta()


# --------------------------------------------------------------------------
# The cohort ladder — "comparable" is a judgement, so it is stated
# --------------------------------------------------------------------------


def test_the_narrowest_grouping_wins_when_it_has_enough_data():
    stats = FlowStatistics(
        [_sample(2, type_id=1, priority=1) for _ in range(MIN_SAMPLE)]
        + [_sample(9, type_id=1, priority=3) for _ in range(MIN_SAMPLE)]
    )

    forecast = stats.forecast(type_id=1, priority=1, type_name="Bug")

    assert forecast.cohort.basis == "Bug at P1"
    assert forecast.typical == timedelta(days=2)


def test_it_widens_the_grouping_rather_than_giving_up():
    """Narrowing improves relevance and destroys sample size. Walking outward
    to the first grouping with enough data keeps an answer available."""
    stats = FlowStatistics(
        [_sample(4, type_id=1, priority=1)]
        + [_sample(4, type_id=1, priority=3) for _ in range(MIN_SAMPLE)]
    )

    forecast = stats.forecast(type_id=1, priority=1, type_name="Bug")

    assert forecast.known
    assert forecast.cohort.basis == "Bug"


def test_it_falls_back_to_all_work_as_a_last_resort():
    stats = FlowStatistics([_sample(3, type_id=t) for t in range(MIN_SAMPLE + 2)])

    forecast = stats.forecast(type_id=99, priority=2, type_name="New kind")

    assert forecast.known
    assert forecast.cohort.basis == "all finished work"


def test_which_grouping_was_used_is_always_stated(session):
    """BR-020. An answer drawn from "all finished work" and one drawn from
    "Bug at P1" deserve different amounts of trust, and the reader cannot tell
    them apart unless told."""
    stats = FlowStatistics([_sample(3, type_id=1, priority=2) for _ in range(MIN_SAMPLE)])

    explanation = stats.forecast(type_id=1, priority=2, type_name="Bug").explanation

    assert "Bug at P2" in explanation
    assert f"{MIN_SAMPLE} finished item(s)" in explanation


# --------------------------------------------------------------------------
# RULE-010 — a range with a confidence, never a date
# --------------------------------------------------------------------------


def test_a_forecast_is_a_range_not_a_point():
    stats = FlowStatistics([_sample(d) for d in (1, 1, 2, 2, 3, 3, 4, 9)])

    forecast = stats.forecast(type_id=1, priority=2)

    assert forecast.typical < forecast.likely_within <= forecast.worst


def test_confidence_is_stated_and_grows_with_the_sample():
    small = FlowStatistics([_sample(2)] * MIN_SAMPLE).forecast(type_id=1, priority=2)
    large = FlowStatistics([_sample(2)] * 40).forecast(type_id=1, priority=2)

    assert "low" in small.confidence
    assert "good" in large.confidence


def test_no_forecast_anywhere_produces_a_date():
    """RULE-010, asserted structurally. Converting "about three working days
    left" into "Thursday" would hide the range inside a date and hand someone a
    promise the data never made."""
    stats = FlowStatistics([_sample(3)] * MIN_SAMPLE)
    forecast = stats.forecast(type_id=1, priority=2)
    projection = project(forecast, timedelta(days=1))

    for value in (forecast.typical, forecast.likely_within, forecast.worst,
                  projection.remaining):
        assert isinstance(value, timedelta)
    assert not isinstance(getattr(projection, "finish_date", None), date)


# --------------------------------------------------------------------------
# Measuring real history out of the event log
# --------------------------------------------------------------------------


def test_cycle_time_is_measured_from_recorded_events(session, person):
    _finish(session, person, title="Three day job", days=3)

    samples = collect_samples(session, ALWAYS)

    assert len(samples) == 1
    assert abs(samples[0].elapsed - timedelta(days=3)) < timedelta(minutes=1)


def test_time_waiting_on_the_client_is_not_counted_against_us(session, person):
    """RULE-005. The delay was theirs, and a cycle time that includes it makes
    the team look slow for someone else's silence."""
    _finish(session, person, title="They went quiet", days=6, client_wait_days=4)

    sample = collect_samples(session, ALWAYS)[0]

    assert abs(sample.elapsed - timedelta(days=6)) < timedelta(minutes=1)
    assert abs(sample.accountable - timedelta(days=2)) < timedelta(minutes=1)


def test_unfinished_work_is_not_measured_as_if_it_were(session, person):
    """An open item has no cycle time yet. Including one would report a partial
    duration as a completed one and bias every percentile downward."""
    item = create_work_item(session, title="Still going", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    assert collect_samples(session, ALWAYS) == []


def test_weekends_are_excluded_from_measured_cycle_time(session, person):
    """BR-014. A job raised Friday and finished Monday must not read as three
    days of ours."""
    friday = datetime.now(UTC) - timedelta(days=14)
    while friday.isoweekday() != 5:
        friday -= timedelta(days=1)

    item = create_work_item(session, title="Over the weekend", created_by_id=person.id,
                            occurred_at=friday)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=friday)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=friday)
    transition(session, item=item, to_state=State.DONE, actor_id=person.id,
               occurred_at=friday + timedelta(days=3))   # the Monday

    weekdays_only = WorkingCalendar(weekend_days=frozenset({6, 7}), holidays=frozenset())
    sample = collect_samples(session, weekdays_only)[0]

    assert sample.elapsed < timedelta(days=2)


def test_statistics_load_from_a_live_database(session, person):
    for index in range(MIN_SAMPLE):
        _finish(session, person, title=f"Job {index}", days=2)

    stats = load_statistics(session, ALWAYS)
    forecast = stats.forecast(type_id=None, priority=2)

    assert forecast.known
    assert forecast.cohort.size == MIN_SAMPLE


# --------------------------------------------------------------------------
# Open work measured with the same ruler (RULE-009)
# --------------------------------------------------------------------------


def test_open_work_is_measured_the_same_way_finished_work_is(session, person):
    """Comparing calendar time against working time would make every open item
    look worse than the history it is judged by."""
    start = datetime.now(UTC) - timedelta(days=5)
    item = create_work_item(session, title="In flight", created_by_id=person.id,
                            occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)

    spent = accountable_so_far(session, ALWAYS)

    assert abs(spent[item.id] - timedelta(days=5)) < timedelta(minutes=2)


def test_client_wait_is_removed_from_open_work_too(session, person):
    start = datetime.now(UTC) - timedelta(days=5)
    item = create_work_item(session, title="Waiting on them", created_by_id=person.id,
                            occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.QUEUED, actor_id=person.id,
               occurred_at=start)
    transition(session, item=item, to_state=State.BLOCKED_ON_CLIENT, actor_id=person.id,
               occurred_at=start + timedelta(days=1))

    spent = accountable_so_far(session, ALWAYS)

    assert abs(spent[item.id] - timedelta(days=1)) < timedelta(minutes=2)


def test_an_item_past_the_85th_percentile_is_marked_overrunning():
    """RULE-009. It has outlasted 85% of comparable work, so whatever is
    happening is not the normal course of this kind of job."""
    stats = FlowStatistics([_sample(2)] * MIN_SAMPLE)
    forecast = stats.forecast(type_id=1, priority=2)

    projection = project(forecast, timedelta(days=9))

    assert projection.overrunning
    assert projection.remaining is None
    assert "behaving unlike the rest" in projection.explanation


def test_an_item_inside_its_history_reports_what_is_left():
    stats = FlowStatistics([_sample(5)] * MIN_SAMPLE)
    forecast = stats.forecast(type_id=1, priority=2)

    projection = project(forecast, timedelta(days=2))

    assert not projection.overrunning
    assert projection.remaining == timedelta(days=3)


def test_nothing_is_claimed_about_an_item_with_no_comparable_history():
    stats = FlowStatistics([_sample(2)] * 2)

    projection = project(stats.forecast(type_id=1, priority=2), timedelta(days=40))

    assert not projection.overrunning
    assert projection.remaining is None
    assert "Not enough history" in projection.explanation


# --------------------------------------------------------------------------
# Throughput
# --------------------------------------------------------------------------


def test_throughput_counts_finished_work_per_week(session, person):
    _finish(session, person, title="This week", days=1)

    weeks = load_statistics(session, ALWAYS).throughput(weeks=4)

    assert len(weeks) == 4
    assert sum(count for _, count in weeks) == 1


def test_throughput_reports_quiet_weeks_as_zero_rather_than_omitting_them(session, person):
    """A gap silently dropped from a chart reads as "no data" instead of "no
    work finished", and those mean opposite things."""
    weeks = load_statistics(session, ALWAYS).throughput(weeks=6)

    assert [count for _, count in weeks] == [0, 0, 0, 0, 0, 0]


# --------------------------------------------------------------------------
# The attention view, now reading history (BR-017)
# --------------------------------------------------------------------------


def test_the_attention_view_stays_silent_without_history(session, person):
    """RULE-013 reaching all the way to the screen. A quiet list is the correct
    output of a system that does not yet know."""
    from app.flow.attention import build_attention

    start = datetime.now(UTC) - timedelta(days=40)
    item = create_work_item(session, title="Very old", created_by_id=person.id,
                            occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)

    result = build_attention(
        session, calendar=ALWAYS, stats=FlowStatistics([_sample(2)] * 2)
    )

    assert result.overrunning == []


def test_the_attention_view_flags_work_outlasting_its_history(session, person):
    from app.flow.attention import build_attention

    for index in range(MIN_SAMPLE):
        _finish(session, person, title=f"Normal {index}", days=1)

    start = datetime.now(UTC) - timedelta(days=20)
    item = create_work_item(session, title="Dragging on", created_by_id=person.id,
                            occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)
    # Moved just now, so it is long-running rather than stalled — the two are
    # deliberately not reported together.
    transition(session, item=item, to_state=State.IN_VERIFICATION, actor_id=person.id)

    result = build_attention(
        session, calendar=ALWAYS, stats=load_statistics(session, ALWAYS)
    )

    titles = [f.item.title for f in result.overrunning]
    assert "Dragging on" in titles
    assert all(f.detail for f in result.overrunning), "BR-020: the workings travel with it"


def test_client_blocked_work_is_never_flagged_as_overrunning(session, person):
    """The governing rule of the attention view holds here too: it is not
    stalled by us, and nobody here can act on it."""
    from app.flow.attention import build_attention

    for index in range(MIN_SAMPLE):
        _finish(session, person, title=f"Normal {index}", days=1)

    start = datetime.now(UTC) - timedelta(days=20)
    item = create_work_item(session, title="Their move", created_by_id=person.id,
                            occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.QUEUED, actor_id=person.id,
               occurred_at=start)
    transition(session, item=item, to_state=State.BLOCKED_ON_CLIENT, actor_id=person.id,
               occurred_at=start)

    result = build_attention(
        session, calendar=ALWAYS, stats=load_statistics(session, ALWAYS)
    )

    assert "Their move" not in [f.item.title for f in result.overrunning]


def test_a_stalled_item_is_not_also_reported_as_overrunning(session, person):
    """D-031. Both facts are true, and the second adds nothing: "nothing has
    happened for four weeks" already explains why it has outrun its history,
    and it is the more actionable of the two. Two rows saying one thing is how
    a list stops being read."""
    from app.flow.attention import build_attention

    for index in range(MIN_SAMPLE):
        _finish(session, person, title=f"Normal {index}", days=1)

    start = datetime.now(UTC) - timedelta(days=25)
    item = create_work_item(session, title="Untouched for weeks", created_by_id=person.id,
                            occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)

    result = build_attention(
        session, calendar=ALWAYS, stale_after_days=3,
        stats=load_statistics(session, ALWAYS),
    )

    assert [f.item.title for f in result.stalled] == ["Untouched for weeks"]
    assert result.overrunning == []


def test_work_that_is_moving_but_overrunning_is_still_flagged(session, person):
    """The suppression above must not swallow the case the flag exists for:
    an item being actively worked that has simply taken far longer than
    anything comparable."""
    from app.flow.attention import build_attention

    for index in range(MIN_SAMPLE):
        _finish(session, person, title=f"Normal {index}", days=1)

    start = datetime.now(UTC) - timedelta(days=25)
    item = create_work_item(session, title="Worked on daily, still going",
                            created_by_id=person.id, occurred_at=start)
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)
    # Moved recently, so it is not stalled — only long-running. (A preemption
    # would need a displacing item named, which is a different rule.)
    transition(session, item=item, to_state=State.IN_VERIFICATION, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    result = build_attention(
        session, calendar=ALWAYS, stale_after_days=3,
        stats=load_statistics(session, ALWAYS),
    )

    assert result.stalled == []
    assert [f.item.title for f in result.overrunning] == ["Worked on daily, still going"]
