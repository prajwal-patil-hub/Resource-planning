"""Permissions.

ADR-002: roles are data so new ones can be added, but what a role may *do*
lives here in code for v1. This module is the seam — every permission decision
in the product goes through `can()`, so moving the matrix into the database
later changes this file and nothing that calls it.

The matrix below is BRD section 3.3, expressed once.
"""
from __future__ import annotations

from enum import StrEnum

from app.models import Person


class Permission(StrEnum):
    # Work
    CREATE_ITEM = "create_item"
    EDIT_OWN_ITEM = "edit_own_item"
    EDIT_ANY_ITEM_IN_TEAM = "edit_any_item_in_team"
    ASSIGN_IN_TEAM = "assign_in_team"
    ASSIGN_ACROSS_TEAMS = "assign_across_teams"
    SET_PRIORITY = "set_priority"
    VERIFY = "verify"
    # Visibility
    SEE_OWN_TEAM = "see_own_team"
    SEE_ALL_TEAMS = "see_all_teams"
    # People
    APPROVE_ABSENCE = "approve_absence"
    MANAGE_PEOPLE = "manage_people"


#: What each permission level may do. Levels are cumulative in practice but
#: written out in full — an inheritance chain hides exactly the question a
#: reader is trying to answer.
MATRIX: dict[str, frozenset[Permission]] = {
    "DEVELOPER": frozenset({
        Permission.CREATE_ITEM,
        Permission.EDIT_OWN_ITEM,
        # C-007: assignment within a team is open to everyone. The risk of
        # uncoordinated assignment is mitigated by visibility and attribution,
        # not by permission.
        Permission.ASSIGN_IN_TEAM,
        Permission.SEE_OWN_TEAM,
    }),
    "TEAM_LEAD": frozenset({
        Permission.CREATE_ITEM,
        Permission.EDIT_OWN_ITEM,
        Permission.EDIT_ANY_ITEM_IN_TEAM,
        Permission.ASSIGN_IN_TEAM,
        Permission.ASSIGN_ACROSS_TEAMS,
        Permission.SET_PRIORITY,
        Permission.VERIFY,
        Permission.SEE_OWN_TEAM,
        Permission.APPROVE_ABSENCE,
    }),
    "MANAGER": frozenset({
        Permission.CREATE_ITEM,
        Permission.EDIT_OWN_ITEM,
        Permission.EDIT_ANY_ITEM_IN_TEAM,
        Permission.ASSIGN_IN_TEAM,
        Permission.ASSIGN_ACROSS_TEAMS,
        Permission.SET_PRIORITY,
        Permission.SEE_OWN_TEAM,
        Permission.SEE_ALL_TEAMS,
        Permission.APPROVE_ABSENCE,
    }),
    "ADMIN": frozenset(Permission),
}


class Forbidden(Exception):
    """The signed-in person may not do this."""


def can(person: Person, permission: Permission) -> bool:
    if person is None or not person.active:
        return False
    granted = MATRIX.get(person.role.permission_level, frozenset())
    # `can_verify` is a per-role flag rather than a level, so QA can verify
    # without being given a lead's other powers (BRD section 3.3).
    if permission is Permission.VERIFY and person.role.can_verify:
        return True
    return permission in granted


def require(person: Person, permission: Permission) -> None:
    if not can(person, permission):
        raise Forbidden(
            f"{person.name if person else 'You'} cannot do this "
            f"({permission.value}). Ask a team lead or an admin."
        )


def visible_team_ids(person: Person, all_team_ids: list[int]) -> list[int]:
    """Which teams this person may see (RULE-011: team-level by default).

    Returning a list rather than a boolean means callers cannot forget to
    narrow — there is no "unfiltered" path to fall through to.
    """
    if can(person, Permission.SEE_ALL_TEAMS):
        return all_team_ids
    return [person.team_id] if person.team_id else []


def can_assign_to(actor: Person, target: Person) -> bool:
    """Whether `actor` may put work on `target` (RULE-011, cross-team limit).

    Visibility was already scoped by team, but the assign endpoint never
    re-checked it — so the rule held for what you could *see* and not for what
    you could *do*, which is the half that matters. A filtered dropdown is a
    convenience; it is not a control, because the form underneath it accepts any
    id someone cares to send.

    Deliberately permissive within a team (K-029): assignment is not reserved to
    a role, and uncoordinated assignment is handled by visibility and
    attribution rather than by permission. This blocks only the case the
    stakeholder actually flagged — reaching into another team.

    Note it checks `ASSIGN_ACROSS_TEAMS` rather than `SEE_ALL_TEAMS`: seeing
    another team's work and being able to hand them more of it are different
    powers, and a team lead has the second without the first.
    """
    if actor is None or target is None:
        return False
    if can(actor, Permission.ASSIGN_ACROSS_TEAMS):
        return True
    return actor.team_id is not None and actor.team_id == target.team_id
