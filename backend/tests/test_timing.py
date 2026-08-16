"""Recording context — backdating and assignment context (BR-004, BR-016).

Feature 5 exists because the service layer accepted a backdated `occurred_at`
and no screen ever sent one. Every catch-up entry stamped the moment of typing,
which under ADR-001 — where every number is derived from these timestamps —
does not make the numbers vague, it makes them confidently wrong.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.flow.load import assignment_options
from app.people.absence import record_absence
from app.work.lifecycle import State
from app.work.service import WorkItemError, assign, create_work_item, transition
from app.work.timing import MAX_BACKDATE, TimingError, parse_when, was_backdated

NOW = datetime(2026, 8, 16, 18, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Reading the field
# --------------------------------------------------------------------------


def test_blank_means_now_so_the_fast_path_is_untouched():
    """D-005: a title alone must still be enough. `None` flows through to the
    service, which stamps the current moment exactly as it did before."""
    assert parse_when("", now=NOW) is None
    assert parse_when(None, now=NOW) is None
    assert parse_when("   ", now=NOW) is None


def test_a_stated_time_is_read_in_the_browsers_timezone():
    """The bug this field would otherwise have shipped with.

    `datetime-local` submits naive wall-clock text. A server reading it as UTC
    would shift every entry from a team on IST by five and a half hours — and a
    genuine 9:30am entry would land in the future and be refused."""
    # IST is UTC+05:30, so getTimezoneOffset() reports -330.
    got = parse_when("2026-08-16T09:30", -330, now=NOW)

    assert got == datetime(2026, 8, 16, 4, 0, tzinfo=UTC)  # 09:30 IST


def test_a_missing_offset_is_read_as_utc_rather_than_guessed():
    got = parse_when("2026-08-16T09:30", None, now=NOW)
    assert got == datetime(2026, 8, 16, 9, 30, tzinfo=UTC)


def test_a_nonsense_offset_is_ignored_rather_than_applied():
    """Real offsets span UTC-12:00 to UTC+14:00. A tampered or broken value
    must not be allowed to move a timestamp days out of position."""
    got = parse_when("2026-08-16T09:30", 99999, now=NOW)
    assert got == datetime(2026, 8, 16, 9, 30, tzinfo=UTC)


def test_an_explicit_timezone_is_honoured():
    got = parse_when("2026-08-16T09:30:00+05:30", now=NOW)
    assert got == datetime(2026, 8, 16, 4, 0, tzinfo=UTC)


def test_the_future_is_refused():
    with pytest.raises(TimingError, match="future"):
        parse_when("2026-08-17T09:00", now=NOW)


def test_a_clock_a_few_seconds_fast_is_treated_as_now():
    """Otherwise someone pressing the button on a machine running slightly
    ahead of the server is told their work happens in the future."""
    got = parse_when((NOW + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S"), now=NOW)
    assert got == NOW


def test_something_dated_months_back_is_refused_with_the_reason(session):
    """RULE-016. Past a fortnight a backdated entry is far more likely a
    mistyped year than a real catch-up, and one wild timestamp does more damage
    to a cycle-time distribution than a dozen missing entries — because nobody
    knows to go looking for it."""
    stale = NOW - MAX_BACKDATE - timedelta(days=1)

    with pytest.raises(TimingError, match="fortnight"):
        parse_when(stale.strftime("%Y-%m-%dT%H:%M"), now=NOW)


def test_the_edge_of_the_window_is_still_accepted():
    edge = NOW - MAX_BACKDATE + timedelta(minutes=1)
    assert parse_when(edge.strftime("%Y-%m-%dT%H:%M"), now=NOW) is not None


def test_unparseable_text_says_what_to_do_about_it():
    with pytest.raises(TimingError, match="Leave it blank"):
        parse_when("yesterday afternoon", now=NOW)


def test_a_late_entry_is_marked_as_one():
    """BR-020 applied to time itself. A reader comparing two items deserves to
    know that one timestamp was observed and the other remembered."""
    assert was_backdated(NOW - timedelta(hours=9), NOW)
    assert not was_backdated(NOW - timedelta(seconds=40), NOW)


# --------------------------------------------------------------------------
# What backdating is actually for
# --------------------------------------------------------------------------


def test_end_of_day_catch_up_keeps_the_hour_the_work_started(session, person):
    """The stakeholder's own words: "if someone forgets to record it they can do
    it by EOD for tracking." This is that, end to end."""
    started = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    if started > datetime.now(UTC):
        started -= timedelta(days=1)

    item = create_work_item(
        session, title="Fixed the export at 9am", created_by_id=person.id,
        occurred_at=started,
    )

    first = item.transitions[0] if hasattr(item, "transitions") else None
    assert first is None or first.occurred_at == started


def test_the_two_timestamps_are_kept_separately(session, person):
    """ADR-003. `occurred_at` is when it happened; `recorded_at` is when someone
    typed it. Collapsing them into one would lose the ability to tell an
    accurate record from a remembered one."""
    from app.models import StateTransition
    from sqlalchemy import select

    started = datetime.now(UTC) - timedelta(hours=6)
    item = create_work_item(
        session, title="Caught up later", created_by_id=person.id, occurred_at=started,
    )

    row = session.scalar(
        select(StateTransition).where(StateTransition.work_item_id == item.id)
    )
    assert row.occurred_at == started
    assert row.recorded_at > row.occurred_at
    assert was_backdated(row.occurred_at, row.recorded_at)


def test_a_backdated_transition_produces_the_real_elapsed_time(session, person):
    """The reason this feature came before forecasting. Without it, an item
    worked on all day reads as having taken seconds, and the cycle-time figure
    every forecast is built from is quietly wrong."""
    from app.flow.timeline import build_timeline

    morning = datetime.now(UTC) - timedelta(hours=8)
    item = create_work_item(
        session, title="All-day job", created_by_id=person.id, occurred_at=morning,
    )
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=morning)
    transition(
        session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
        occurred_at=morning + timedelta(minutes=5),
    )

    tl = build_timeline(session, item.id)
    assert tl.total_elapsed >= timedelta(hours=7)


def test_a_transition_cannot_predate_the_one_before_it(session, person):
    """Backdating is permitted; incoherence is not. A timeline that runs
    backwards cannot be explained to anyone (BR-020)."""
    item = create_work_item(session, title="Ordered", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)

    with pytest.raises(WorkItemError, match="dated before"):
        transition(
            session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
            occurred_at=datetime.now(UTC) - timedelta(days=3),
        )


# --------------------------------------------------------------------------
# Assignment context (BR-016)
# --------------------------------------------------------------------------


def _start(session, person, title):
    item = create_work_item(session, title=title, created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)
    return item


def test_each_option_carries_the_load_it_would_add_to(session, person, other_person):
    _start(session, person, "One")
    _start(session, person, "Two")

    option = next(o for o in assignment_options(session) if o.person_id == person.id)

    assert option.load == 2
    assert f"2 of {option.normal_load}" in option.label


def test_someone_away_says_so_and_says_when_they_are_back(session, person, other_person):
    """The failure this closes: a lead could hand work to someone the system
    already knew was on leave, and it would say nothing."""
    record_absence(
        session, person_id=person.id,
        start=date.today(), end=date.today() + timedelta(days=3),
        kind="LEAVE", created_by=other_person,
    )

    option = next(o for o in assignment_options(session) if o.person_id == person.id)

    assert option.is_away
    assert option.returns_on == date.today() + timedelta(days=4)
    assert "away until" in option.label
    assert not option.has_room


def test_an_absent_person_is_still_offered(session, person, other_person):
    """Deliberate. Work is often queued up for someone due back tomorrow, and
    refusing would be wrong the first time anyone tried it. State the fact;
    let the person choosing decide."""
    record_absence(
        session, person_id=person.id, start=date.today(), end=date.today(),
        kind="LEAVE", created_by=other_person,
    )

    assert person.id in {o.person_id for o in assignment_options(session)}


def test_options_are_alphabetical_not_ranked_by_spare_capacity(session, person, other_person):
    """Sorting by availability would quietly turn a fact into an instruction,
    and would move names around under a reader looking for one they already have
    in mind."""
    _start(session, person, "Busy")

    names = [o.name for o in assignment_options(session)]
    assert names == sorted(names)


def test_every_option_explains_its_own_number(session, person):
    """BR-020: no figure travels without its derivation."""
    _start(session, person, "One")

    option = next(o for o in assignment_options(session) if o.person_id == person.id)

    assert "1 item(s) in progress" in option.explanation
    assert person.name in option.explanation


def test_a_cancelled_absence_does_not_leave_someone_marked_away(session, person, other_person):
    """Found while building this: the load strip's absence check did not filter
    cancelled rows, so cancelling leave left the person showing as away."""
    from app.people.absence import cancel

    absence = record_absence(
        session, person_id=person.id, start=date.today(), end=date.today(),
        kind="LEAVE", created_by=other_person,
    )
    cancel(session, absence, other_person)

    option = next(o for o in assignment_options(session) if o.person_id == person.id)
    assert not option.is_away


# --------------------------------------------------------------------------
# Cross-team assignment (RULE-011)
# --------------------------------------------------------------------------


def test_work_cannot_be_pushed_onto_another_team(session, person, other_person):
    """Visibility was already scoped by team; the assign endpoint never
    re-checked it. A filtered dropdown is a convenience, not a control — the
    form beneath it accepts any id that is posted."""
    from app.models import Team

    outsider = other_person
    outsider.team_id = session.scalar(
        __import__("sqlalchemy").select(Team.id).where(Team.id != person.team_id).limit(1)
    )
    session.flush()

    item = create_work_item(session, title="Ours", created_by_id=person.id)

    with pytest.raises(WorkItemError, match="another team"):
        assign(session, item=item, person_id=outsider.id, actor_id=person.id)


def test_someone_who_can_see_every_team_may_assign_across_them(session, person, manager):
    """The escape hatch is a permission, not an exception in the code."""
    from app.models import Team

    person.team_id = session.scalar(
        __import__("sqlalchemy").select(Team.id).where(Team.id != manager.team_id).limit(1)
    )
    session.flush()

    item = create_work_item(session, title="Cross-team", created_by_id=manager.id)
    participant = assign(session, item=item, person_id=person.id, actor_id=manager.id)

    assert participant.person_id == person.id
