"""Managing the things work is labelled with (BR-023, BR-024).

Clients, work types, roles and teams. Small tables with an outsized effect:
every report the product produces groups by one of them, so how they are managed
decides whether those reports mean anything.

**Three rules govern this module.**

**1. Deactivate, never delete.** A client with thirty finished items cannot be
removed without orphaning that history, and the reports would silently lose a
third of their totals. `active` controls whether something is *offered* for new
work; it never affects what already happened. This is BR-005 — "work is never
destroyed, only cancelled" — applied to the labels as well as the work, and the
database now enforces it with a trigger.

**2. Renaming is the right tool for a name change.** The identifier is what
records point at; the name is only a label. So renaming "Acme Corp" to
"Acme Ltd" makes every past report say "Acme Ltd", which is correct — it is the
same client. Creating a new client and switching to it would split one
relationship's history into two halves, and neither would be true. The screen
says this, because the instinct is usually the other way round.

**3. Naming things and changing who can do what are different powers.**
Adding a client is routine and a lead should not need an administrator for it.
Adding a role or a team changes what people are permitted to do, and that is
administration. They are gated separately rather than lumped together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import MATRIX
from app.models import Client, Person, Role, Team, WorkItem, WorkItemType

#: Permission levels a new role may be given. Deliberately the fixed set from
#: ADR-002 rather than a free-text field: permissions live in code, and a role
#: naming a level that `MATRIX` does not know would silently grant nothing.
PERMISSION_LEVELS = ("DEVELOPER", "TEAM_LEAD", "MANAGER", "ADMIN")

#: What each level actually means, for the person choosing one. A dropdown of
#: bare codes asks someone to pick blind and then blames them for the result.
LEVEL_DESCRIPTIONS = {
    "DEVELOPER": "Record and edit their own work, assign within their team, see their own team.",
    "TEAM_LEAD": "Everything a developer can, plus edit any item in the team, set priority, "
                 "verify, approve absence, and assign across teams.",
    "MANAGER": "Everything a team lead can, except verifying — plus visibility of every team.",
    "ADMIN": "Everything, including managing people, roles and teams.",
}


class ReferenceError(Exception):
    """A rule prevented the change, with a reason a user can act on."""


def _slug(name: str) -> str:
    """A stable code from a display name.

    Codes exist so that seeded rows can be found by something that does not
    change when someone renames them. Derived rather than asked for — the user
    has no reason to care, and asking would be one more field between them and
    the thing they actually wanted to do (D-005 applied beyond the composer).
    """
    code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    return code or "ITEM"


def _clean(name: str, what: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ReferenceError(f"A {what} needs a name.")
    if len(name) > 120:
        raise ReferenceError(f"That {what} name is too long — keep it under 120 characters.")
    return name


def _check_unique(session: Session, model, name: str, what: str, *, exclude_id: int | None = None) -> None:
    """Case-insensitive, because "Acme" and "acme" are the same client.

    Checked here for the message, and by a unique index for the truth: this read
    could lose a race with a concurrent insert, and the index cannot.
    """
    query = select(model.id).where(func.lower(model.name) == name.lower())
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if session.scalar(query) is not None:
        raise ReferenceError(
            f"There is already a {what} called “{name}”. Two with the same name "
            f"would split its work across two rows in every report, and neither "
            f"total would be right — rename the existing one instead."
        )


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------


def add_client(session: Session, *, name: str) -> Client:
    name = _clean(name, "client")
    _check_unique(session, Client, name, "client")
    row = Client(name=name, active=True)
    session.add(row)
    _flush(session, "client")
    return row


def rename_client(session: Session, client: Client, *, name: str) -> Client:
    name = _clean(name, "client")
    _check_unique(session, Client, name, "client", exclude_id=client.id)
    client.name = name
    _flush(session, "client")
    return client


def set_client_active(session: Session, client: Client, *, active: bool) -> Client:
    client.active = active
    session.flush()
    return client


# --------------------------------------------------------------------------
# Work types
# --------------------------------------------------------------------------


def add_work_type(session: Session, *, name: str, sort_order: int = 100) -> WorkItemType:
    name = _clean(name, "work type")
    _check_unique(session, WorkItemType, name, "work type")
    row = WorkItemType(
        name=name, code=_unique_code(session, WorkItemType, _slug(name)),
        active=True, sort_order=sort_order,
    )
    session.add(row)
    _flush(session, "work type")
    return row


def rename_work_type(session: Session, work_type: WorkItemType, *, name: str) -> WorkItemType:
    name = _clean(name, "work type")
    _check_unique(session, WorkItemType, name, "work type", exclude_id=work_type.id)
    # The code deliberately does NOT follow the name. It is what seed data and
    # any future integration match on, and silently changing an identifier
    # because someone fixed a typo is how references break.
    work_type.name = name
    _flush(session, "work type")
    return work_type


def set_work_type_active(session: Session, work_type: WorkItemType, *, active: bool) -> WorkItemType:
    work_type.active = active
    session.flush()
    return work_type


def reorder_work_type(session: Session, work_type: WorkItemType, *, sort_order: int) -> WorkItemType:
    work_type.sort_order = max(0, min(999, sort_order))
    session.flush()
    return work_type


# --------------------------------------------------------------------------
# Roles (BR-024, ADR-002)
# --------------------------------------------------------------------------


def add_role(session: Session, *, name: str, permission_level: str, can_verify: bool = False) -> Role:
    """Add a role and place it in the hierarchy.

    ADR-002's seam, used exactly as designed: roles are data and can be added at
    runtime, while what each one may do stays in code. A new role picks an
    existing permission level rather than a set of permissions, because a role
    granting an arbitrary combination would need a permissions editor — and that
    is deferred configurability, not a requirement anybody has stated.
    """
    name = _clean(name, "role")
    if permission_level not in PERMISSION_LEVELS:
        raise ReferenceError(
            f"“{permission_level}” is not a permission level. Choose one of: "
            f"{', '.join(PERMISSION_LEVELS)}."
        )
    # Belt and braces with the CHECK constraint: if a level is ever added to the
    # database that the code does not know, `can()` would grant nothing and the
    # role would look broken rather than restricted.
    if permission_level not in MATRIX:
        raise ReferenceError(
            f"The database allows “{permission_level}” but the application has no "
            f"rules for it, so anyone given it could do nothing. This is a bug, "
            f"not a configuration problem."
        )
    _check_unique(session, Role, name, "role")

    row = Role(
        name=name,
        code=_unique_code(session, Role, _slug(name)),
        permission_level=permission_level,
        can_verify=can_verify,
        active=True,
    )
    session.add(row)
    _flush(session, "role")
    return row


def update_role(
    session: Session, role: Role, *, name: str | None = None,
    permission_level: str | None = None, can_verify: bool | None = None,
) -> Role:
    if name is not None:
        name = _clean(name, "role")
        _check_unique(session, Role, name, "role", exclude_id=role.id)
        role.name = name
    if permission_level is not None:
        if permission_level not in PERMISSION_LEVELS:
            raise ReferenceError(f"“{permission_level}” is not a permission level.")
        role.permission_level = permission_level
    if can_verify is not None:
        role.can_verify = can_verify
    _flush(session, "role")
    return role


def set_role_active(session: Session, role: Role, *, active: bool, counts: dict | None = None) -> Role:
    """Deactivating a role that people still hold is refused.

    Not a nicety. `can()` reads permissions through the person's role, so
    everyone holding a deactivated role would keep whatever it grants while
    disappearing from the list of roles that exist — a permission that is in
    force and invisible. Move the people first, then retire the role.
    """
    if not active:
        holders = session.scalar(
            select(func.count(Person.id)).where(
                Person.role_id == role.id, Person.active.is_(True)
            )
        )
        if holders:
            raise ReferenceError(
                f"{holders} active person/people still have the “{role.name}” role. "
                f"Give them another role first — otherwise they keep its permissions "
                f"while the role itself no longer appears anywhere."
            )
    role.active = active
    session.flush()
    return role


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------


def add_team(session: Session, *, name: str) -> Team:
    name = _clean(name, "team")
    _check_unique(session, Team, name, "team")
    row = Team(name=name, active=True)
    session.add(row)
    _flush(session, "team")
    return row


def rename_team(session: Session, team: Team, *, name: str) -> Team:
    name = _clean(name, "team")
    _check_unique(session, Team, name, "team", exclude_id=team.id)
    team.name = name
    _flush(session, "team")
    return team


def set_team_active(session: Session, team: Team, *, active: bool) -> Team:
    """Same reasoning as roles: visibility is scoped by team (RULE-011), so a
    person in a retired team would be scoped to something that no longer
    appears in any filter."""
    if not active:
        members = session.scalar(
            select(func.count(Person.id)).where(
                Person.team_id == team.id, Person.active.is_(True)
            )
        )
        if members:
            raise ReferenceError(
                f"{members} active person/people are still in “{team.name}”. "
                f"Move them first — visibility is scoped by team, and they would "
                f"be scoped to a team that no longer appears in any filter."
            )
    team.active = active
    session.flush()
    return team


# --------------------------------------------------------------------------
# What is actually in use
# --------------------------------------------------------------------------


@dataclass
class Usage:
    """How much history each reference row carries.

    Shown next to every deactivate button, because "retire this client" is a
    very different decision at 0 items and at 300. The count is also the answer
    to "why can I not delete it".
    """

    clients: dict[int, int]
    work_types: dict[int, int]
    roles: dict[int, int]
    teams: dict[int, int]
    open_clients: dict[int, int]


def usage(session: Session) -> Usage:
    def counted(column, extra=None):
        query = select(column, func.count()).group_by(column)
        if extra is not None:
            query = query.where(extra)
        return {key: value for key, value in session.execute(query) if key is not None}

    from app.work.lifecycle import OPEN_STATES

    return Usage(
        clients=counted(WorkItem.client_id),
        work_types=counted(WorkItem.type_id),
        open_clients=counted(
            WorkItem.client_id,
            extra=WorkItem.state.in_([s.value for s in OPEN_STATES]),
        ),
        roles=counted(Person.role_id, extra=Person.active.is_(True)),
        teams=counted(Person.team_id, extra=Person.active.is_(True)),
    )


def _unique_code(session: Session, model, base: str) -> str:
    """Codes are unique in the database; two names can still slug the same."""
    candidate, suffix = base, 2
    while session.scalar(select(model.id).where(model.code == candidate)) is not None:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _flush(session: Session, what: str) -> None:
    """Turn a constraint violation into something a user can act on.

    The unique index is the real guarantee — the read-then-write check above can
    lose a race with a concurrent insert, and this is where that shows up.
    """
    try:
        session.flush()
    except IntegrityError as exc:
        raise ReferenceError(
            f"That {what} name is already taken. Two with the same name would "
            f"split its work across two rows in every report."
        ) from exc
