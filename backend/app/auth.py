"""Authentication: passwords, sessions, and the signed-in person.

Design notes worth knowing before changing anything here.

**Sessions are server-side rows, not self-contained signed cookies.** A signed
cookie cannot be revoked — deactivating someone leaves their cookie valid until
it expires. For a product whose entire value is an accurate record of who did
what, "we cannot revoke access" is the wrong trade.

**Only a hash of the session token is stored.** A database leak then does not
hand over live sessions.

**Failed-login state lives on the row, not in memory.** A restart is precisely
when an attacker would retry, so throttling that resets on restart is not
throttling.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Person, UserSession

SESSION_COOKIE = "rp_session"
SESSION_LIFETIME = timedelta(days=14)
#: Slide the expiry forward when someone is active, so a person using the
#: system daily is never logged out mid-week.
SESSION_REFRESH_AFTER = timedelta(hours=12)

MAX_FAILED_LOGINS = 8
LOCKOUT = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 10


class AuthError(Exception):
    """Login failed, for a reason the user is allowed to know."""


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(raw: str, hashed: str | None) -> bool:
    if not hashed:
        # Still spend the time. Returning immediately for an account with no
        # password makes account existence measurable by response time.
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"y", bcrypt.gensalt()))
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def check_password_quality(raw: str, *, name: str = "", email: str = "") -> None:
    """Reject the passwords that actually get chosen, not a rulebook.

    Composition rules (one capital, one digit, one symbol) push people toward
    `Password1!` and towards writing it down. Length plus a check against the
    obvious choices is more useful and less annoying — and friction matters
    everywhere in this product except here, where a little is correct.
    """
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    lowered = raw.lower()
    for banned in ("password", "12345678", "qwerty", "letmein", "welcome", "admin123"):
        if banned in lowered:
            raise AuthError("That contains a very common password. Pick something else.")
    if name and len(name) > 3 and name.lower() in lowered:
        raise AuthError("Don't use your own name in your password.")
    if email:
        local = email.split("@")[0].lower()
        if len(local) > 3 and local in lowered:
            raise AuthError("Don't use your email address in your password.")


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def start_session(session: Session, person: Person, *, user_agent: str = "") -> str:
    """Create a session and return the raw token for the cookie."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        UserSession(
            token_hash=_hash_token(token),
            person_id=person.id,
            created_at=now,
            expires_at=now + SESSION_LIFETIME,
            last_seen_at=now,
            user_agent=(user_agent or "")[:400],
        )
    )
    session.execute(
        update(Person).where(Person.id == person.id).values(last_login_at=now)
    )
    session.flush()
    return token


def person_for_token(session: Session, token: str | None) -> Person | None:
    if not token:
        return None
    now = datetime.now(UTC)
    row = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == _hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    if row is None:
        return None

    person = session.get(Person, row.person_id)
    if person is None or not person.active:
        # Deactivating someone ends their access immediately — the reason
        # sessions are rows rather than self-contained cookies.
        return None

    if now - row.last_seen_at > SESSION_REFRESH_AFTER:
        row.last_seen_at = now
        row.expires_at = now + SESSION_LIFETIME
        session.flush()
    return person


def end_session(session: Session, token: str | None) -> None:
    if not token:
        return
    session.execute(
        update(UserSession)
        .where(UserSession.token_hash == _hash_token(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def revoke_all_for(session: Session, person_id: int) -> None:
    """Used when someone is deactivated or their password changes."""
    session.execute(
        update(UserSession)
        .where(UserSession.person_id == person_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


def authenticate(session: Session, email: str, password: str) -> Person:
    now = datetime.now(UTC)
    person = session.scalar(
        select(Person).where(func.lower(Person.email) == (email or "").strip().lower())
    )

    if person is None:
        # Same message and comparable timing whether or not the account exists,
        # so login cannot be used to enumerate who works here.
        verify_password(password, None)
        raise AuthError("Email or password is not right.")

    if person.locked_until and person.locked_until > now:
        wait = int((person.locked_until - now).total_seconds() // 60) + 1
        raise AuthError(f"Too many attempts. Try again in about {wait} minute(s).")

    if not person.active:
        verify_password(password, None)
        raise AuthError("Email or password is not right.")

    if not verify_password(password, person.password_hash):
        person.failed_logins += 1
        if person.failed_logins >= MAX_FAILED_LOGINS:
            person.locked_until = now + LOCKOUT
            person.failed_logins = 0
        session.flush()
        raise AuthError("Email or password is not right.")

    person.failed_logins = 0
    person.locked_until = None
    session.flush()
    return person


def set_password(session: Session, person: Person, raw: str, *, must_change: bool = False) -> None:
    check_password_quality(raw, name=person.name, email=person.email)
    person.password_hash = hash_password(raw)
    person.must_change_password = must_change
    session.flush()


def anyone_can_sign_in(session: Session) -> bool:
    """False on a fresh install, which is what triggers first-run setup.

    BR-021 says the system must be usable immediately with no configuration
    step; creating the first administrator is the one unavoidable exception,
    so it is offered rather than documented.
    """
    return session.scalar(
        select(func.count(Person.id)).where(
            Person.password_hash.is_not(None), Person.active.is_(True)
        )
    ) > 0
