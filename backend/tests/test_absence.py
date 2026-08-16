"""Absence, the working calendar, and cover detection (BO-3, BR-012..BR-014)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.flow.calendar import WorkingCalendar
from app.flow.load import load_for_team
from app.people.absence import (
    AbsenceError,
    absences_for,
    absent_person_ids,
    approve,
    cancel,
    record_absence,
    uncovered_work,
    upcoming,
)
from app.work.lifecycle import State
from app.work.service import assign, create_work_item, transition

TODAY = date.today()


def _book(session, person, actor, *, start=None, end=None, **kw):
    return record_absence(
        session,
        person_id=person.id,
        start=start or TODAY,
        end=end or TODAY + timedelta(days=2),
        kind=kw.pop("kind", "LEAVE"),
        created_by=actor,
        **kw,
    )


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def test_absence_stores_the_last_day_inclusively(session, person, other_person):
    """The classic date-range bug. "Away Monday to Friday" must mean Friday is
    a day off, not the day back."""
    absence = _book(
        session, person, other_person,
        start=date(2026, 9, 7), end=date(2026, 9, 11),
    )

    assert absence.first_day == date(2026, 9, 7)
    assert absence.last_day == date(2026, 9, 11)
    # Stored half-open, so the upper bound is the first day back.
    assert absence.period.upper == date(2026, 9, 12)


def test_overlapping_absence_is_refused_with_a_usable_message(session, person, other_person):
    """INV-5, enforced by the EXCLUDE constraint rather than a read-then-write
    check that would lose the race."""
    _book(session, person, other_person, start=TODAY, end=TODAY + timedelta(days=4))

    with pytest.raises(AbsenceError, match="overlaps"):
        _book(session, person, other_person, start=TODAY + timedelta(days=2), end=TODAY + timedelta(days=6))


def test_two_people_may_be_away_at_the_same_time(session, person, other_person):
    _book(session, person, other_person)
    _book(session, other_person, person)

    assert len(absent_person_ids(session, TODAY)) == 2


def test_end_before_start_is_refused(session, person, other_person):
    with pytest.raises(AbsenceError, match="cannot be before"):
        _book(session, person, other_person, start=TODAY, end=TODAY - timedelta(days=1))


def test_cancelled_absence_frees_the_dates_again(session, person, other_person):
    """A corrected booking must be re-enterable. The EXCLUDE constraint is
    filtered on cancelled_at for exactly this reason."""
    first = _book(session, person, other_person, start=TODAY, end=TODAY + timedelta(days=4))
    cancel(session, first, other_person)

    corrected = _book(session, person, other_person, start=TODAY, end=TODAY + timedelta(days=2))
    assert corrected.id != first.id


def test_a_cancelled_absence_no_longer_counts_as_away(session, person, other_person):
    absence = _book(session, person, other_person)
    assert person.id in absent_person_ids(session, TODAY)

    cancel(session, absence, other_person)
    assert person.id not in absent_person_ids(session, TODAY)


def test_cancelling_keeps_the_record(session, person, other_person):
    """Cancelled, never deleted — consistent with everything else here."""
    absence = _book(session, person, other_person)
    cancel(session, absence, other_person)

    assert absence.cancelled_at is not None
    assert absence.cancelled_by_id == other_person.id
    assert len(absences_for(session, person.id, include_cancelled=True)) == 1
    assert len(absences_for(session, person.id)) == 0


def test_approval_is_recorded_with_who_and_when(session, person, other_person):
    absence = _book(session, person, other_person)
    assert not absence.is_approved

    approve(session, absence, other_person)
    assert absence.is_approved
    assert absence.approved_by_id == other_person.id
    assert absence.approved_at is not None


def test_a_cancelled_absence_cannot_be_approved(session, person, other_person):
    absence = _book(session, person, other_person)
    cancel(session, absence, other_person)

    with pytest.raises(AbsenceError, match="cancelled"):
        approve(session, absence, other_person)


def test_who_recorded_it_is_kept_separately_from_who_approved_it(session, person, other_person):
    """A lead entering leave on someone's behalf is normal and must be visible."""
    absence = _book(session, person, other_person)

    assert absence.created_by_id == other_person.id
    assert absence.created_by_name == other_person.name
    assert absence.approved_by_id is None


# --------------------------------------------------------------------------
# Cover — the half of BO-3 that matters
# --------------------------------------------------------------------------


#: The lifecycle has no shortcuts — NEW cannot reach DONE or BLOCKED_ON_CLIENT
#: directly. Tests must walk a legal path, same as the UI does.
ROUTES = {
    State.NEW: [],
    State.QUEUED: [State.QUEUED],
    State.IN_PROGRESS: [State.IN_PROGRESS],
    State.BLOCKED_ON_CLIENT: [State.QUEUED, State.BLOCKED_ON_CLIENT],
    State.IN_VERIFICATION: [State.IN_PROGRESS, State.IN_VERIFICATION],
    State.DONE: [State.IN_PROGRESS, State.DONE],
}


def _open_item(session, person, title, priority=2, state=State.IN_PROGRESS):
    item = create_work_item(session, title=title, created_by_id=person.id, priority=priority)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    for step in ROUTES[state]:
        transition(session, item=item, to_state=step, actor_id=person.id)
    return item


def test_open_work_owned_by_an_absent_person_is_surfaced(session, person, other_person):
    _open_item(session, person, "Client waiting on this")
    _book(session, person, other_person)

    uncovered = uncovered_work(session)

    assert len(uncovered) == 1
    assert uncovered[0].person_name == person.name
    assert [i.title for i in uncovered[0].items] == ["Client waiting on this"]


def test_work_already_waiting_on_the_client_is_not_flagged(session, person, other_person):
    """If we are waiting for them, our absence is not what is holding it up.
    Flagging it would add noise to a list whose value is that everything on it
    needs action."""
    _open_item(session, person, "Waiting for their answer", state=State.BLOCKED_ON_CLIENT)
    _book(session, person, other_person)

    assert uncovered_work(session) == []


def test_finished_work_is_not_flagged(session, person, other_person):
    _open_item(session, person, "Already done", state=State.DONE)
    _book(session, person, other_person)

    assert uncovered_work(session) == []


def test_nobody_away_means_nothing_to_cover(session, person):
    _open_item(session, person, "In hand")
    assert uncovered_work(session) == []


def test_the_most_urgent_backlog_is_listed_first(session, person, other_person):
    _open_item(session, person, "Routine", priority=3)
    _open_item(session, other_person, "Outage", priority=0)
    _book(session, person, other_person)
    _book(session, other_person, person)

    uncovered = uncovered_work(session)
    assert uncovered[0].person_name == other_person.name
    assert uncovered[0].urgent_count == 1


def test_cover_explains_itself(session, person, other_person):
    """BR-020: the figure never travels without its derivation."""
    _open_item(session, person, "Something")
    _book(session, person, other_person, start=TODAY, end=TODAY + timedelta(days=2))

    calendar = WorkingCalendar(weekend_days=frozenset({6, 7}), holidays=frozenset())
    text = uncovered_work(session)[0].explanation(calendar)

    assert person.name in text
    assert "away until" in text
    assert "open item" in text


# --------------------------------------------------------------------------
# Load strip
# --------------------------------------------------------------------------


def test_someone_away_is_not_available_even_with_room(session, person, other_person):
    """Before this, the load strip's "away" state could never appear at all."""
    _book(session, person, other_person)

    entry = next(e for e in load_for_team(session) if e.person_id == person.id)
    assert entry.absent_today
    assert not entry.has_room
    assert entry.load == 0


def test_upcoming_absence_is_listed_within_the_horizon(session, person, other_person):
    _book(session, person, other_person, start=TODAY + timedelta(days=3), end=TODAY + timedelta(days=5))
    _book(session, other_person, person, start=TODAY + timedelta(days=40), end=TODAY + timedelta(days=42))

    ids = [a.person_id for a in upcoming(session, within_days=14)]
    assert person.id in ids
    assert other_person.id not in ids
