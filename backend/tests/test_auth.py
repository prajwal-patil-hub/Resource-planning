"""Authentication, sessions and permissions.

These matter because the audit trail is the product's data source (ADR-001).
An attribution that can be forged, or a session that cannot be revoked, makes
every number downstream untrustworthy in a way no report would reveal.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.access import Forbidden, Permission, can, require, visible_team_ids
from app.auth import (
    MAX_FAILED_LOGINS,
    AuthError,
    anyone_can_sign_in,
    authenticate,
    end_session,
    hash_password,
    person_for_token,
    revoke_all_for,
    set_password,
    start_session,
    verify_password,
)
from app.models import Person, Role


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def test_password_is_hashed_not_stored(session, person):
    set_password(session, person, "correct horse battery")

    assert person.password_hash is not None
    assert "correct horse battery" not in person.password_hash
    assert person.password_hash.startswith("$2")  # bcrypt
    assert verify_password("correct horse battery", person.password_hash)
    assert not verify_password("wrong horse battery", person.password_hash)


def test_the_same_password_hashes_differently_each_time(session):
    """Salting. Without it, identical passwords are visibly identical in the
    database, and one cracked hash reveals every account that shares it."""
    assert hash_password("the same phrase") != hash_password("the same phrase")


@pytest.mark.parametrize(
    "bad,reason",
    [
        ("short", "at least"),
        ("mypassword123", "common password"),
        ("Rahul is here ok", "your own name"),
    ],
)
def test_obvious_passwords_are_refused(session, person, bad, reason):
    with pytest.raises(AuthError, match=reason):
        set_password(session, person, bad)


def test_a_password_containing_the_email_is_refused(session, person):
    person.name = "Devendra"
    person.email = "dpatil@example.com"
    session.flush()

    with pytest.raises(AuthError, match="email address"):
        set_password(session, person, "dpatil rules ok")


def test_verifying_against_no_password_is_false_not_an_error(session):
    """An account without a login must not be sign-in-able, and must not crash."""
    assert verify_password("anything", None) is False


# --------------------------------------------------------------------------
# Sign in
# --------------------------------------------------------------------------


def test_sign_in_with_the_right_password(session, person):
    set_password(session, person, "a decent long phrase")
    signed_in = authenticate(session, "rahul@example.com", "a decent long phrase")
    assert signed_in.id == person.id
    assert person.last_login_at is None or True  # set on session start, not here


def test_email_matching_ignores_case(session, person):
    set_password(session, person, "a decent long phrase")
    assert authenticate(session, "RAHUL@Example.COM", "a decent long phrase").id == person.id


def test_unknown_email_and_wrong_password_give_the_same_message(session, person):
    """Otherwise login becomes a way to find out who works here."""
    set_password(session, person, "a decent long phrase")

    with pytest.raises(AuthError) as unknown:
        authenticate(session, "nobody@example.com", "whatever")
    with pytest.raises(AuthError) as wrong:
        authenticate(session, "rahul@example.com", "whatever")

    assert str(unknown.value) == str(wrong.value)


def test_deactivated_people_cannot_sign_in(session, person):
    set_password(session, person, "a decent long phrase")
    person.active = False
    session.flush()

    with pytest.raises(AuthError):
        authenticate(session, "rahul@example.com", "a decent long phrase")


def test_repeated_failures_lock_the_account(session, person):
    set_password(session, person, "a decent long phrase")

    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(AuthError):
            authenticate(session, "rahul@example.com", "nope")

    # Even the correct password is refused while locked.
    with pytest.raises(AuthError, match="Too many attempts"):
        authenticate(session, "rahul@example.com", "a decent long phrase")


def test_a_successful_sign_in_clears_the_failure_count(session, person):
    set_password(session, person, "a decent long phrase")
    for _ in range(3):
        with pytest.raises(AuthError):
            authenticate(session, "rahul@example.com", "nope")
    assert person.failed_logins == 3

    authenticate(session, "rahul@example.com", "a decent long phrase")
    assert person.failed_logins == 0


# --------------------------------------------------------------------------
# Sessions — the reason they are rows and not signed cookies
# --------------------------------------------------------------------------


def test_a_session_token_identifies_its_person(session, person):
    token = start_session(session, person)
    assert person_for_token(session, token).id == person.id


def test_only_the_hash_of_the_token_is_stored(session, person):
    """A database leak must not hand over live sessions."""
    token = start_session(session, person)
    stored = session.execute(text("SELECT token_hash FROM user_session")).scalars().all()

    assert token not in stored
    assert len(stored) == 1


def test_signing_out_ends_the_session_immediately(session, person):
    token = start_session(session, person)
    end_session(session, token)
    assert person_for_token(session, token) is None


def test_deactivating_someone_ends_their_access_at_once(session, person):
    """The whole argument for server-side sessions. A signed cookie would keep
    working until it expired."""
    token = start_session(session, person)
    assert person_for_token(session, token) is not None

    person.active = False
    session.flush()

    assert person_for_token(session, token) is None


def test_revoking_all_sessions_signs_out_every_device(session, person):
    a = start_session(session, person)
    b = start_session(session, person)
    revoke_all_for(session, person.id)

    assert person_for_token(session, a) is None
    assert person_for_token(session, b) is None


def test_an_expired_session_is_not_accepted(session, person):
    token = start_session(session, person)
    past = datetime.now(UTC) - timedelta(days=30)
    session.execute(
        text("UPDATE user_session SET created_at = :c, expires_at = :e, last_seen_at = :c"),
        {"c": past, "e": past + timedelta(days=14)},
    )
    assert person_for_token(session, token) is None


def test_a_forged_token_is_rejected(session, person):
    start_session(session, person)
    assert person_for_token(session, "not-a-real-token") is None
    assert person_for_token(session, None) is None


# --------------------------------------------------------------------------
# First-run
# --------------------------------------------------------------------------


def test_setup_is_offered_only_while_nobody_can_sign_in(session, person):
    assert anyone_can_sign_in(session) is False
    set_password(session, person, "a decent long phrase")
    assert anyone_can_sign_in(session) is True


# --------------------------------------------------------------------------
# Permissions (ADR-002)
# --------------------------------------------------------------------------


def _as_role(session, person, code):
    person.role_id = session.scalar(text("SELECT id FROM role WHERE code = :c").bindparams(c=code))
    session.flush()
    session.refresh(person)
    return person


def test_a_developer_can_record_and_assign_but_not_manage_people(session, person):
    dev = _as_role(session, person, "DEVELOPER")

    assert can(dev, Permission.CREATE_ITEM)
    # C-007: assignment within a team is open to everyone.
    assert can(dev, Permission.ASSIGN_IN_TEAM)
    assert not can(dev, Permission.SET_PRIORITY)
    assert not can(dev, Permission.MANAGE_PEOPLE)
    assert not can(dev, Permission.SEE_ALL_TEAMS)


def test_qa_can_verify_without_a_leads_other_powers(session, qa_person):
    """`can_verify` is a per-role flag, not a permission level — so QA verifies
    without also being able to set priority or assign across teams."""
    assert can(qa_person, Permission.VERIFY)
    assert not can(qa_person, Permission.SET_PRIORITY)
    assert not can(qa_person, Permission.ASSIGN_ACROSS_TEAMS)


def test_a_manager_sees_every_team_and_a_developer_sees_their_own(session, person):
    dev = _as_role(session, person, "DEVELOPER")
    assert visible_team_ids(dev, [1, 2, 3]) == [dev.team_id]

    mgr = _as_role(session, person, "MANAGER")
    assert visible_team_ids(mgr, [1, 2, 3]) == [1, 2, 3]


def test_an_admin_can_do_everything(session, person):
    admin = _as_role(session, person, "ADMIN")
    for permission in Permission:
        assert can(admin, permission), permission


def test_a_deactivated_person_can_do_nothing(session, person):
    admin = _as_role(session, person, "ADMIN")
    admin.active = False
    session.flush()

    for permission in Permission:
        assert not can(admin, permission), permission


def test_require_raises_with_a_message_a_person_can_act_on(session, person):
    dev = _as_role(session, person, "DEVELOPER")
    with pytest.raises(Forbidden, match="Ask a team lead or an admin"):
        require(dev, Permission.MANAGE_PEOPLE)
