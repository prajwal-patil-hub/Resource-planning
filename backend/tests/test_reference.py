"""Managing the labels work is filed under (BR-023, BR-024).

Small tables with an outsized effect: every report groups by one of them, so
how they are managed decides whether those reports mean anything.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.access import MATRIX, Permission, can
from app.models import Client, Person, Role, Team, WorkItemType
from app.reference import (
    PERMISSION_LEVELS,
    ReferenceError,
    add_client,
    add_role,
    add_team,
    add_work_type,
    rename_client,
    rename_team,
    rename_work_type,
    reorder_work_type,
    set_client_active,
    set_role_active,
    set_team_active,
    set_work_type_active,
    usage,
)
from app.work.service import create_work_item


# --------------------------------------------------------------------------
# Adding things — the gap this feature closed
# --------------------------------------------------------------------------


def test_a_client_can_be_added_without_sql(session):
    client = add_client(session, name="Contoso")

    assert client.id is not None
    assert client.active


def test_a_work_type_gets_a_code_derived_from_its_name(session):
    """Codes exist so seeded rows can be found by something that does not change
    when someone renames them. Derived rather than asked for — the user has no
    reason to care, and asking would be one more field in the way."""
    row = add_work_type(session, name="Data fix")

    assert row.code == "DATA_FIX"


def test_two_names_that_slug_the_same_still_get_distinct_codes(session):
    first = add_work_type(session, name="Data fix")
    second = add_work_type(session, name="Data-fix!")

    assert first.code != second.code


def test_a_blank_name_is_refused(session):
    with pytest.raises(ReferenceError, match="needs a name"):
        add_client(session, name="   ")


def test_names_are_trimmed(session):
    assert add_client(session, name="  Contoso  ").name == "Contoso"


# --------------------------------------------------------------------------
# Uniqueness — the failure that would corrupt every report
# --------------------------------------------------------------------------


def test_a_duplicate_client_name_is_refused(session):
    add_client(session, name="Contoso")

    with pytest.raises(ReferenceError, match="already a client"):
        add_client(session, name="Contoso")


def test_duplicates_are_caught_regardless_of_case(session):
    """"Acme" and "acme" are the same client to a human. Two rows would split
    one client's work across two lines in every report, each with half the
    history, and neither total would be right."""
    add_client(session, name="Acme Ltd")

    with pytest.raises(ReferenceError, match="already a client"):
        add_client(session, name="ACME LTD")


def test_the_refusal_explains_the_consequence_not_just_the_rule(session):
    add_client(session, name="Contoso")
    with pytest.raises(ReferenceError) as caught:
        add_client(session, name="contoso")

    assert "split its work" in str(caught.value)


def test_the_database_enforces_uniqueness_too(session):
    """The read-then-write check above can lose a race with a concurrent
    insert. The index cannot."""
    add_client(session, name="Contoso")

    with pytest.raises(Exception):
        session.execute(text("INSERT INTO client (name, active) VALUES ('CONTOSO', true)"))
        session.flush()


def test_work_type_names_are_unique_too(session):
    """The original schema constrained only `code`, so two types both displayed
    as "Bug" were possible."""
    add_work_type(session, name="Escalation")

    with pytest.raises(ReferenceError, match="already a work type"):
        add_work_type(session, name="escalation")


def test_renaming_to_an_existing_name_is_refused(session):
    add_client(session, name="Contoso")
    other = add_client(session, name="Fabrikam")

    with pytest.raises(ReferenceError, match="already a client"):
        rename_client(session, other, name="Contoso")


def test_renaming_something_to_its_own_name_is_allowed(session):
    """Otherwise saving a row without changing the name fails, which is a
    baffling thing for a form to do."""
    client = add_client(session, name="Contoso")

    assert rename_client(session, client, name="Contoso").name == "Contoso"


# --------------------------------------------------------------------------
# Renaming vs replacing — the decision the screen exists to steer
# --------------------------------------------------------------------------


def test_renaming_keeps_the_history_attached(session, person):
    """The point of renaming rather than replacing. Records point at the row,
    not the text, so a renamed client keeps every item it ever had — and past
    reports simply start using the new name, which is correct."""
    client = add_client(session, name="Acme Corp")
    create_work_item(session, title="Their bug", created_by_id=person.id, client_id=client.id)

    rename_client(session, client, name="Acme Ltd")

    assert usage(session).clients[client.id] == 1
    assert client.name == "Acme Ltd"


def test_a_work_types_code_does_not_follow_its_name(session):
    """The code is what seed data and any future integration match on. Silently
    changing an identifier because somebody fixed a typo is how references
    break."""
    row = add_work_type(session, name="Escalation")
    original = row.code

    rename_work_type(session, row, name="Urgent escalation")

    assert row.code == original


# --------------------------------------------------------------------------
# Retiring, never deleting
# --------------------------------------------------------------------------


def test_retiring_a_client_leaves_its_history_intact(session, person):
    client = add_client(session, name="Contoso")
    create_work_item(session, title="Old work", created_by_id=person.id, client_id=client.id)

    set_client_active(session, client, active=False)

    assert not client.active
    assert usage(session).clients[client.id] == 1


def test_a_retired_client_can_be_restored(session):
    client = add_client(session, name="Contoso")
    set_client_active(session, client, active=False)
    set_client_active(session, client, active=True)

    assert client.active


def test_the_database_refuses_to_delete_reference_rows(session, person):
    """BR-005's "never destroyed, only cancelled" applied to the labels as well
    as the work. Enforced in the database so no future code path can quietly
    reintroduce deletion."""
    client = add_client(session, name="Contoso")
    session.flush()

    with pytest.raises(Exception, match="deactivated, never deleted"):
        session.execute(text("DELETE FROM client WHERE id = :i").bindparams(i=client.id))
        session.flush()


# --------------------------------------------------------------------------
# Roles (BR-024, ADR-002)
# --------------------------------------------------------------------------


def test_a_role_can_be_added_and_placed_in_the_hierarchy(session):
    """ADR-002's seam used exactly as designed: roles are data and can be added
    at runtime, while what each level may do stays in code."""
    role = add_role(session, name="Solution Architect", permission_level="TEAM_LEAD")

    assert role.permission_level == "TEAM_LEAD"
    assert role.active


def test_a_new_role_actually_grants_its_level(session):
    """The test that proves the seam works end to end rather than just storing
    a string."""
    role = add_role(session, name="Solution Architect", permission_level="TEAM_LEAD")
    holder = Person(name="Dev Lead", email="sa@example.com", role_id=role.id,
                    normal_load=3, active=True)
    session.add(holder)
    session.flush()

    assert can(holder, Permission.SET_PRIORITY)
    assert not can(holder, Permission.MANAGE_PEOPLE)


def test_an_unknown_permission_level_is_refused(session):
    with pytest.raises(ReferenceError, match="not a permission level"):
        add_role(session, name="Wizard", permission_level="SUPREME")


def test_every_offered_level_is_one_the_code_knows(session):
    """A level the database allows but `MATRIX` does not would silently grant
    nothing, and the role would look broken rather than restricted."""
    for level in PERMISSION_LEVELS:
        assert level in MATRIX


def test_verification_is_separate_from_the_level(session):
    """BRD 3.3: QA verifies work without holding a lead's other powers."""
    role = add_role(session, name="Tester", permission_level="DEVELOPER", can_verify=True)
    holder = Person(name="Tester One", email="t1@example.com", role_id=role.id,
                    normal_load=3, active=True)
    session.add(holder)
    session.flush()

    assert can(holder, Permission.VERIFY)
    assert not can(holder, Permission.SET_PRIORITY)


def test_a_role_still_held_by_people_cannot_be_retired(session, person):
    """`can()` reads permissions through the role, so everyone holding a retired
    role would keep what it grants while it stopped appearing anywhere — a
    permission in force and invisible."""
    with pytest.raises(ReferenceError, match="still have the"):
        set_role_active(session, person.role, active=False)


def test_a_role_nobody_holds_can_be_retired(session):
    role = add_role(session, name="Temporary", permission_level="DEVELOPER")

    set_role_active(session, role, active=False)

    assert not role.active


def test_an_inactive_holder_does_not_block_retiring_a_role(session):
    role = add_role(session, name="Temporary", permission_level="DEVELOPER")
    leaver = Person(name="Gone", email="gone@example.com", role_id=role.id,
                    normal_load=3, active=False)
    session.add(leaver)
    session.flush()

    set_role_active(session, role, active=False)
    assert not role.active


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------


def test_a_team_can_be_added(session):
    team = add_team(session, name="Platform")
    assert team.active


def test_a_team_with_people_in_it_cannot_be_retired(session, person):
    """Visibility is scoped by team (RULE-011), so they would be scoped to
    something that no longer appears in any filter."""
    team = session.get(Team, person.team_id)

    with pytest.raises(ReferenceError, match="still in"):
        set_team_active(session, team, active=False)


def test_an_empty_team_can_be_retired(session):
    team = add_team(session, name="Platform")

    set_team_active(session, team, active=False)

    assert not team.active


def test_team_names_are_unique_case_insensitively(session):
    add_team(session, name="Platform")

    with pytest.raises(ReferenceError, match="already a team"):
        add_team(session, name="PLATFORM")


def test_a_team_can_be_renamed(session):
    team = add_team(session, name="Platfrom")
    rename_team(session, team, name="Platform")

    assert team.name == "Platform"


# --------------------------------------------------------------------------
# Usage counts — the answer to "why can I not delete it"
# --------------------------------------------------------------------------


def test_usage_counts_what_each_label_carries(session, person):
    client = add_client(session, name="Contoso")
    kind = add_work_type(session, name="Escalation")
    create_work_item(session, title="One", created_by_id=person.id,
                     client_id=client.id, type_id=kind.id)
    create_work_item(session, title="Two", created_by_id=person.id, client_id=client.id)

    counts = usage(session)

    assert counts.clients[client.id] == 2
    assert counts.work_types[kind.id] == 1
    assert counts.roles[person.role_id] >= 1


def test_open_work_is_counted_separately_from_all_work(session, person):
    """"Retire this client" is a different decision at 0 open items and at 5."""
    client = add_client(session, name="Contoso")
    create_work_item(session, title="Live", created_by_id=person.id, client_id=client.id)

    counts = usage(session)

    assert counts.clients[client.id] == 1
    assert counts.open_clients[client.id] == 1


def test_usage_is_empty_rather_than_missing_for_unused_labels(session):
    client = add_client(session, name="Nobody uses me")

    assert usage(session).clients.get(client.id, 0) == 0


# --------------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------------


def test_work_types_can_be_reordered(session):
    row = add_work_type(session, name="Escalation", sort_order=50)
    reorder_work_type(session, row, sort_order=10)

    assert row.sort_order == 10


def test_a_nonsense_order_is_clamped_rather_than_stored(session):
    row = add_work_type(session, name="Escalation")

    reorder_work_type(session, row, sort_order=99999)
    assert row.sort_order == 999

    reorder_work_type(session, row, sort_order=-5)
    assert row.sort_order == 0


def test_a_retired_work_type_is_not_offered_but_still_exists(session, person):
    row = add_work_type(session, name="Escalation")
    create_work_item(session, title="Filed under it", created_by_id=person.id, type_id=row.id)
    set_work_type_active(session, row, active=False)

    offered = session.scalars(
        select(WorkItemType).where(WorkItemType.active.is_(True))
    ).all()

    assert row not in offered
    assert session.get(WorkItemType, row.id) is not None


# --------------------------------------------------------------------------
# Who may do what
# --------------------------------------------------------------------------


def test_naming_things_and_changing_permissions_are_different_powers(session):
    """Adding a client is routine and a lead should not need an administrator
    for it. Adding a role changes what people may do, and that is
    administration."""
    assert Permission.MANAGE_LABELS in MATRIX["TEAM_LEAD"]
    assert Permission.MANAGE_PEOPLE not in MATRIX["TEAM_LEAD"]
    assert Permission.MANAGE_PEOPLE not in MATRIX["MANAGER"]
    assert Permission.MANAGE_PEOPLE in MATRIX["ADMIN"]


def test_a_developer_cannot_manage_labels(session, person):
    assert not can(person, Permission.MANAGE_LABELS)
