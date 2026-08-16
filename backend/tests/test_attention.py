"""The attention list (BR-007, BR-016, BR-017, BO-2).

The governing rule under test: everything on the list must need action. One
item that does not belong teaches people to skim, and a list people skim is
worse than no list — it gives the feeling of having checked without the fact.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.flow.attention import build_attention
from app.flow.calendar import WorkingCalendar
from app.people.absence import record_absence
from app.work.lifecycle import State
from app.work.service import assign, create_work_item, transition

CAL = WorkingCalendar(weekend_days=frozenset(), holidays=frozenset())


def _build(session, **kw):
    return build_attention(session, calendar=CAL, **kw)


def _item(session, person, title, *, owner=None, priority=2, state=None, due=None, ago=None):
    when = datetime.now(UTC) - (ago or timedelta(0))
    item = create_work_item(
        session, title=title, created_by_id=person.id, priority=priority,
        due_date=due, owner_id=(owner.id if owner else None), occurred_at=when,
    )
    if state and owner:
        route = {
            State.QUEUED: [State.QUEUED],
            State.IN_PROGRESS: [State.IN_PROGRESS],
            State.BLOCKED_ON_CLIENT: [State.QUEUED, State.BLOCKED_ON_CLIENT],
        }[state]
        for step in route:
            transition(session, item=item, to_state=step, actor_id=person.id, occurred_at=when)
    return item


# --------------------------------------------------------------------------
# What gets flagged
# --------------------------------------------------------------------------


def test_unowned_work_is_flagged(session, person):
    _item(session, person, "Someone mentioned this")
    assert [f.item.title for f in _build(session).unowned] == ["Someone mentioned this"]


def test_work_that_stopped_moving_is_flagged(session, person):
    _item(session, person, "Forgotten", owner=person, state=State.IN_PROGRESS,
          ago=timedelta(days=5))
    flags = _build(session, stale_after_days=3).stalled
    assert [f.item.title for f in flags] == ["Forgotten"]
    assert "working time" in flags[0].measure


def test_recently_moved_work_is_not_flagged(session, person):
    _item(session, person, "Moving along", owner=person, state=State.IN_PROGRESS,
          ago=timedelta(hours=6))
    assert _build(session, stale_after_days=3).stalled == []


def test_overdue_work_is_flagged(session, person):
    _item(session, person, "Late", owner=person, state=State.IN_PROGRESS,
          due=date.today() - timedelta(days=2))
    flags = _build(session).overdue
    assert [f.item.title for f in flags] == ["Late"]
    assert flags[0].severity == 0


def test_work_due_soon_and_not_started_is_flagged_before_it_is_late(session, person):
    """BR-017 is about warning while there is still time, not reporting failure."""
    _item(session, person, "Due tomorrow", owner=person, state=State.QUEUED,
          due=date.today() + timedelta(days=1))
    assert [f.item.title for f in _build(session).at_risk] == ["Due tomorrow"]


def test_work_due_far_ahead_is_not_flagged(session, person):
    _item(session, person, "Due in three weeks", owner=person, state=State.QUEUED,
          due=date.today() + timedelta(days=21))
    assert _build(session).at_risk == []


def test_work_in_progress_is_not_flagged_as_at_risk(session, person):
    """Someone is on it. A nudge would be noise."""
    _item(session, person, "Being worked on now", owner=person, state=State.IN_PROGRESS,
          due=date.today() + timedelta(days=1))
    assert _build(session).at_risk == []


def test_work_owned_by_someone_away_is_flagged(session, person, other_person):
    _item(session, person, "Owner on leave", owner=person, state=State.IN_PROGRESS)
    record_absence(
        session, person_id=person.id, start=date.today(),
        end=date.today() + timedelta(days=2), kind="LEAVE", created_by=other_person,
    )
    assert [f.item.title for f in _build(session).uncovered] == ["Owner on leave"]


# --------------------------------------------------------------------------
# What is deliberately NOT flagged — the rule that keeps the list readable
# --------------------------------------------------------------------------


def test_work_waiting_on_the_client_is_never_flagged_as_stalled(session, person):
    """It is not stalled by us, and nobody here can act on it."""
    _item(session, person, "Waiting for their reply", owner=person,
          state=State.BLOCKED_ON_CLIENT, ago=timedelta(days=20))
    assert _build(session, stale_after_days=3).stalled == []


def test_work_waiting_on_the_client_is_not_flagged_when_the_owner_is_away(session, person, other_person):
    _item(session, person, "Their move", owner=person, state=State.BLOCKED_ON_CLIENT)
    record_absence(
        session, person_id=person.id, start=date.today(),
        end=date.today() + timedelta(days=2), kind="LEAVE", created_by=other_person,
    )
    assert _build(session).uncovered == []


def test_finished_work_is_never_flagged(session, person):
    item = _item(session, person, "Done", owner=person, state=State.IN_PROGRESS,
                 ago=timedelta(days=30))
    transition(session, item=item, to_state=State.DONE, actor_id=person.id)
    assert _build(session, stale_after_days=3).total == 0


def test_nothing_wrong_produces_an_empty_list(session, person):
    _item(session, person, "All fine", owner=person, state=State.IN_PROGRESS)
    assert _build(session).total == 0


# --------------------------------------------------------------------------
# Ordering, explanation, scope
# --------------------------------------------------------------------------


def test_urgent_problems_sort_first(session, person):
    _item(session, person, "Routine unowned", priority=3)
    _item(session, person, "Urgent unowned", priority=0)
    assert _build(session).unowned[0].item.title == "Urgent unowned"


def test_every_flag_explains_itself(session, person):
    """BR-020 applies to a list of problems as much as to a number."""
    _item(session, person, "Nobody owns me", priority=0)
    flag = _build(session).unowned[0]

    assert flag.why
    assert flag.measure
    assert "ago" in flag.measure


def test_an_item_can_be_flagged_for_more_than_one_reason(session, person):
    """Unowned AND overdue is worse than either, and a lead needs both facts."""
    _item(session, person, "Nobody owns this and it is late",
          due=date.today() - timedelta(days=1))
    result = _build(session)

    assert len(result.unowned) == 1
    assert len(result.overdue) == 1
    assert result.total == 2


def test_the_team_filter_narrows_the_list(session, person, other_person):
    _item(session, person, "Mine", owner=person, state=State.IN_PROGRESS,
          due=date.today() - timedelta(days=1))
    other_person.team_id = None
    session.flush()
    _item(session, person, "Theirs", owner=other_person, state=State.IN_PROGRESS,
          due=date.today() - timedelta(days=1))

    scoped = _build(session, team_ids=[person.team_id])
    assert [f.item.title for f in scoped.overdue] == ["Mine"]
