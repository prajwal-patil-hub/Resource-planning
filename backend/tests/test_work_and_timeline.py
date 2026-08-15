"""Feature 1 behaviour, plus the time-in-state report (ADR-003).

The timeline tests use explicit `occurred_at` values rather than real elapsed
time, so the arithmetic is checked exactly instead of approximately.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.flow.load import load_for_team
from app.flow.timeline import build_timeline, format_duration
from app.work.lifecycle import IllegalTransition, State
from app.work.service import WorkItemError, assign, create_work_item, transition


# --------------------------------------------------------------------------
# Recording — the behaviour everything else depends on (BR-002, D-005)
# --------------------------------------------------------------------------


def test_title_alone_is_enough_to_record_work(session, person):
    item = create_work_item(session, title="Client says export is broken", created_by_id=person.id)

    assert item.id is not None
    assert item.state == State.NEW.value
    assert item.type_id is None and item.client_id is None and item.due_date is None


def test_blank_title_is_refused(session, person):
    with pytest.raises(WorkItemError, match="title"):
        create_work_item(session, title="   ", created_by_id=person.id)


def test_creation_records_its_own_event(session, person):
    """Without a creation transition the item has no history, and elapsed time
    from creation would be unmeasurable."""
    item = create_work_item(session, title="Something", created_by_id=person.id)
    tl = build_timeline(session, item.id)

    assert len(tl.transitions) == 1
    assert tl.transitions[0].from_state is None
    assert tl.transitions[0].to_state == State.NEW.value


def test_item_can_be_created_already_assigned(session, person, other_person):
    """C-007: whoever records the work may put a name on it."""
    item = create_work_item(
        session, title="Urgent fix", created_by_id=person.id, owner_id=other_person.id
    )
    tl = build_timeline(session, item.id)

    assert len(tl.owners) == 1
    assert tl.owners[0].person_name == "Priya"
    assert tl.owners[0].assigned_by == "Rahul"


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


def test_cannot_start_work_nobody_owns(session, person):
    """INV-6: something in progress must have someone accountable for it."""
    item = create_work_item(session, title="Orphan", created_by_id=person.id)

    with pytest.raises(WorkItemError, match="Assign an owner"):
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)


def test_illegal_transition_is_refused_with_a_useful_message(session, person):
    item = create_work_item(session, title="Jump", created_by_id=person.id)

    with pytest.raises(IllegalTransition) as exc:
        transition(session, item=item, to_state=State.IN_VERIFICATION, actor_id=person.id)

    assert "NEW" in str(exc.value)
    assert "allowed transitions" in str(exc.value)


def test_done_is_terminal(session, person):
    """D-011: reopening would give one item several cycle times."""
    item = create_work_item(session, title="Finish me", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)
    transition(session, item=item, to_state=State.DONE, actor_id=person.id)

    with pytest.raises(IllegalTransition):
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)


def test_resuming_clears_the_displacement(session, person):
    """A resumed item must not still claim to be displaced."""
    urgent = create_work_item(session, title="P0 outage", created_by_id=person.id)
    item = create_work_item(session, title="Planned CR", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)
    transition(
        session, item=item, to_state=State.ON_HOLD_PREEMPTED, actor_id=person.id,
        displaced_by_id=urgent.id,
    )
    assert item.displaced_by_id == urgent.id

    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)
    assert item.displaced_by_id is None


def test_backdated_change_cannot_precede_the_previous_one(session, person):
    """BR-004 allows end-of-day catch-up, but not an incoherent timeline."""
    base = datetime.now(UTC) - timedelta(days=2)
    item = create_work_item(
        session, title="Backdated", created_by_id=person.id, occurred_at=base
    )
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(
        session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
        occurred_at=base + timedelta(hours=5),
    )

    with pytest.raises(WorkItemError, match="dated before"):
        transition(
            session, item=item, to_state=State.DONE, actor_id=person.id,
            occurred_at=base + timedelta(hours=1),
        )


# --------------------------------------------------------------------------
# The report the stakeholder asked for (ADR-003)
# --------------------------------------------------------------------------


def test_time_in_state_is_computed_from_the_event_log(session, person, qa_person):
    """The full journey: recorded, queued, started, preempted, resumed,
    blocked on the client, verified, done — with the arithmetic checked."""
    t0 = datetime.now(UTC) - timedelta(days=10)
    urgent = create_work_item(session, title="P0 outage", created_by_id=person.id)

    item = create_work_item(
        session, title="Acme CR-42", created_by_id=person.id, occurred_at=t0
    )
    assign(session, item=item, person_id=person.id, actor_id=person.id)

    def move(state, hours, **kw):
        transition(
            session, item=item, to_state=state, actor_id=person.id,
            occurred_at=t0 + timedelta(hours=hours), **kw,
        )

    move(State.QUEUED, 1)                                        # NEW      1h
    move(State.IN_PROGRESS, 3)                                   # QUEUED   2h
    move(State.ON_HOLD_PREEMPTED, 5, displaced_by_id=urgent.id)  # ACTIVE   2h
    move(State.IN_PROGRESS, 9)                                   # ON HOLD  4h
    move(State.BLOCKED_ON_CLIENT, 10)                            # ACTIVE   1h
    move(State.IN_PROGRESS, 34)                                  # BLOCKED 24h
    move(State.IN_VERIFICATION, 35)                              # ACTIVE   1h
    move(State.IN_PROGRESS, 37)                                  # VERIFY   2h  (failed)
    move(State.IN_VERIFICATION, 38)                              # ACTIVE   1h
    move(State.DONE, 39)                                         # VERIFY   1h

    tl = build_timeline(session, item.id)

    assert tl.time_in_state[State.NEW] == timedelta(hours=1)
    assert tl.time_in_state[State.QUEUED] == timedelta(hours=2)
    # Active: 2 + 1 + 1 + 1 = 5h across four separate stints.
    assert tl.active_time == timedelta(hours=5)
    assert tl.time_in_state[State.ON_HOLD_PREEMPTED] == timedelta(hours=4)
    assert tl.waiting_on_client == timedelta(hours=24)
    assert tl.verification_time == timedelta(hours=3)

    # Waiting on us = unassigned + queued + set aside = 1 + 2 + 4.
    assert tl.waiting_on_us == timedelta(hours=7)

    assert tl.total_elapsed == timedelta(hours=39)
    # RULE-005: the client's 24 hours are not ours to answer for.
    assert tl.accountable_elapsed == timedelta(hours=15)

    assert tl.time_to_first_touch == timedelta(hours=3)
    assert tl.rework_count == 1
    assert tl.preemption_count == 1

    assert len(tl.displacements) == 1
    assert tl.displacements[0].displaced_by_title == "P0 outage"


def test_ownership_history_appears_in_the_timeline(session, person, other_person):
    item = create_work_item(session, title="Handover", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    assign(session, item=item, person_id=other_person.id, actor_id=person.id)

    tl = build_timeline(session, item.id)

    assert [o.person_name for o in tl.owners] == ["Rahul", "Priya"]
    assert tl.owners[0].to_ts is not None
    assert tl.owners[1].to_ts is None


def test_field_changes_are_captured_by_the_trigger(session, person):
    """ADR-003 layer 2: captured by the database, so no code path can miss it."""
    item = create_work_item(session, title="Typo in titel", created_by_id=person.id)

    item.title = "Typo in title"
    item.priority = 0
    session.flush()

    tl = build_timeline(session, item.id)
    changed = {c.field: (c.old_value, c.new_value) for c in tl.field_changes}

    assert changed["title"] == ("Typo in titel", "Typo in title")
    assert changed["priority"] == ("2", "0")


def test_recording_lag_is_measured(session, person):
    """R-006: the system can tell when its own data is drifting."""
    long_ago = datetime.now(UTC) - timedelta(hours=6)
    item = create_work_item(
        session, title="Recorded late", created_by_id=person.id, occurred_at=long_ago
    )

    tl = build_timeline(session, item.id)
    assert tl.max_recording_lag >= timedelta(hours=5, minutes=59)


# --------------------------------------------------------------------------
# Load (ADR-001) — items, not hours
# --------------------------------------------------------------------------


def test_load_counts_only_work_in_progress(session, person):
    """Fifteen queued items and one in progress is not overload — it is one
    thing being worked with a long queue, which needs a different response."""
    for index in range(4):
        item = create_work_item(session, title=f"Item {index}", created_by_id=person.id)
        assign(session, item=item, person_id=person.id, actor_id=person.id)
        if index < 2:
            transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)
        else:
            transition(session, item=item, to_state=State.QUEUED, actor_id=person.id)

    loads = {entry.name: entry for entry in load_for_team(session)}
    assert loads["Rahul"].load == 2
    assert len(loads["Rahul"].queued) == 2
    assert not loads["Rahul"].is_overloaded


def test_overload_is_relative_to_the_person(session, person):
    """RULE-007: never a single company-wide threshold."""
    person.normal_load = 1
    session.flush()

    for index in range(2):
        item = create_work_item(session, title=f"Load {index}", created_by_id=person.id)
        assign(session, item=item, person_id=person.id, actor_id=person.id)
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    entry = next(e for e in load_for_team(session) if e.name == "Rahul")
    assert entry.is_overloaded
    assert not entry.has_room
    # BR-020: the figure travels with its derivation.
    assert "normal level for Rahul is 1" in entry.explanation


def test_collaborators_do_not_carry_the_load(session, person, other_person):
    """RULE-003: accountability stays with exactly one person; others work
    under them."""
    item = create_work_item(session, title="Pair work", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    assign(
        session, item=item, person_id=other_person.id, actor_id=person.id,
        participation="COLLABORATOR",
    )
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    loads = {entry.name: entry for entry in load_for_team(session)}
    assert loads["Rahul"].load == 1
    assert loads["Priya"].load == 0


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "delta,expected",
    [
        (timedelta(seconds=42), "42s"),
        (timedelta(minutes=17), "17m"),
        (timedelta(hours=3, minutes=30), "3.5h"),
        (timedelta(hours=5), "5h"),
        (timedelta(days=2), "2d"),
        (timedelta(days=1, hours=12), "1.5d"),
    ],
)
def test_durations_do_not_imply_false_precision(delta, expected):
    """Nobody needs '3 days, 4 hours and 17 minutes' — and stating it would
    imply a measurement accuracy this system does not have."""
    assert format_duration(delta) == expected
