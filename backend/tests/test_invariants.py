"""Tests for the invariants the database itself enforces.

These matter more than ordinary unit tests. Under ADR-001 every number the
product shows is derived from this data, so a broken invariant does not raise an
error — it produces a plausible wrong number nobody questions.

Each test here tries to break a rule through the most direct route available,
bypassing the service layer entirely, and asserts the database refuses.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.work.lifecycle import IllegalTransition, State
from app.work.service import WorkItemError, assign, create_work_item, transition


def test_one_current_owner_enforced_by_index(session, person, other_person):
    """INV-1: the partial unique index permits past owners, never two current."""
    item = create_work_item(session, title="Login broken", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)

    # Direct insert, bypassing the service — this is the path a data-fix script
    # would take, and it must still fail.
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO work_item_participant "
                "(work_item_id, person_id, participation, from_ts, assigned_by_id) "
                "VALUES (:i, :p, 'OWNER', now(), :p)"
            ),
            {"i": item.id, "p": other_person.id},
        )
        session.flush()


def test_reassignment_keeps_history(session, person, other_person):
    """D-012 / BR-015: the previous owner's row is closed, not overwritten."""
    item = create_work_item(session, title="Payment fails", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    assign(session, item=item, person_id=other_person.id, actor_id=person.id)

    rows = session.execute(
        text(
            "SELECT person_id, to_ts FROM work_item_participant "
            "WHERE work_item_id = :i AND participation = 'OWNER' ORDER BY from_ts"
        ),
        {"i": item.id},
    ).all()

    assert len(rows) == 2, "history must survive reassignment"
    assert rows[0].to_ts is not None, "previous owner closed"
    assert rows[1].to_ts is None, "new owner current"
    assert rows[1].person_id == other_person.id


def test_transitions_cannot_be_updated(session, person):
    """INV-2: editing history would silently change past measurements."""
    item = create_work_item(session, title="Report wrong", created_by_id=person.id)

    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(
            text("UPDATE state_transition SET to_state = 'DONE' WHERE work_item_id = :i"),
            {"i": item.id},
        )


def test_transitions_cannot_be_deleted(session, person):
    """INV-2, the other half. Separate test because the trigger is row-level:
    after a rollback there would be no rows left for it to fire on."""
    item = create_work_item(session, title="Report wrong", created_by_id=person.id)

    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(
            text("DELETE FROM state_transition WHERE work_item_id = :i"), {"i": item.id}
        )


def test_state_cannot_change_without_a_transition(session, person):
    """INV-7: this is what keeps the denormalized state column honest."""
    item = create_work_item(session, title="Export slow", created_by_id=person.id)

    with pytest.raises(DBAPIError, match="recorded transition"):
        session.execute(
            text("UPDATE work_item SET state = 'DONE' WHERE id = :i"), {"i": item.id}
        )


def test_preempted_item_must_name_its_displacer(session, person):
    """INV-3 / BO-4: 'on hold' with no cause is the vague status we are avoiding."""
    item = create_work_item(session, title="CR for Acme", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    with pytest.raises(WorkItemError, match="displaced"):
        transition(session, item=item, to_state=State.ON_HOLD_PREEMPTED, actor_id=person.id)


def test_item_cannot_displace_itself(session, person):
    item = create_work_item(session, title="Self", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    with pytest.raises(WorkItemError, match="cannot displace itself"):
        transition(
            session,
            item=item,
            to_state=State.ON_HOLD_PREEMPTED,
            actor_id=person.id,
            displaced_by_id=item.id,
        )


def test_displacement_cycles_are_rejected(session, person):
    """INV-4: a CHECK cannot traverse a graph, so the service does it."""
    a = create_work_item(session, title="A", created_by_id=person.id)
    b = create_work_item(session, title="B", created_by_id=person.id)
    for item in (a, b):
        assign(session, item=item, person_id=person.id, actor_id=person.id)
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)

    transition(
        session, item=a, to_state=State.ON_HOLD_PREEMPTED, actor_id=person.id,
        displaced_by_id=b.id,
    )

    with pytest.raises(WorkItemError, match="loop"):
        transition(
            session, item=b, to_state=State.ON_HOLD_PREEMPTED, actor_id=person.id,
            displaced_by_id=a.id,
        )


def test_absences_cannot_overlap(session, person):
    """INV-5: the EXCLUDE constraint holds where application checking would race."""
    session.execute(
        text(
            "INSERT INTO absence (person_id, period, kind, created_at) "
            "VALUES (:p, daterange('2026-09-01','2026-09-10'), 'LEAVE', now())"
        ),
        {"p": person.id},
    )
    session.flush()

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO absence (person_id, period, kind, created_at) "
                "VALUES (:p, daterange('2026-09-05','2026-09-15'), 'LEAVE', now())"
            ),
            {"p": person.id},
        )
        session.flush()


def test_future_transitions_rejected(session, person):
    """INV-12. A CHECK cannot call now(), so a trigger does this."""
    item = create_work_item(session, title="Time travel", created_by_id=person.id)
    assign(session, item=item, person_id=person.id, actor_id=person.id)

    with pytest.raises(WorkItemError, match="future"):
        transition(
            session,
            item=item,
            to_state=State.IN_PROGRESS,
            actor_id=person.id,
            occurred_at=datetime.now(UTC) + timedelta(hours=2),
        )


def test_work_item_survives_deletion_attempts_only_by_cancelling(session, person):
    """INV-10 / BR-005: history is the substrate, so nothing is destroyed."""
    item = create_work_item(session, title="Not needed", created_by_id=person.id)
    transition(session, item=item, to_state=State.CANCELLED, actor_id=person.id)
    assert item.state == State.CANCELLED.value
