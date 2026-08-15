"""The work item lifecycle.

The state machine from docs/08-domain-model.md section 5, expressed once.

INV-8 (only legal transitions) is enforced here rather than in the database,
because it needs the machine below. That is only safe because the trigger
`work_item_state_guarded` guarantees there is no other way to change state —
application enforcement is trustworthy exactly when there is one code path.
"""
from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    NEW = "NEW"
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD_PREEMPTED = "ON_HOLD_PREEMPTED"
    BLOCKED_ON_CLIENT = "BLOCKED_ON_CLIENT"
    IN_VERIFICATION = "IN_VERIFICATION"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


#: Legal transitions. Anything absent here is rejected.
ALLOWED: dict[State, frozenset[State]] = {
    State.NEW: frozenset({State.QUEUED, State.IN_PROGRESS, State.CANCELLED}),
    State.QUEUED: frozenset({State.IN_PROGRESS, State.BLOCKED_ON_CLIENT, State.CANCELLED}),
    State.IN_PROGRESS: frozenset(
        {
            State.ON_HOLD_PREEMPTED,
            State.BLOCKED_ON_CLIENT,
            State.IN_VERIFICATION,
            State.DONE,
            State.CANCELLED,
        }
    ),
    # Preemption is only reachable from IN_PROGRESS: work never started was not
    # displaced, it was queued. Allowing it from QUEUED would let the personal
    # backlog masquerade as displacement and inflate the BO-4 numbers.
    State.ON_HOLD_PREEMPTED: frozenset(
        {State.IN_PROGRESS, State.BLOCKED_ON_CLIENT, State.CANCELLED}
    ),
    State.BLOCKED_ON_CLIENT: frozenset({State.IN_PROGRESS, State.QUEUED, State.CANCELLED}),
    State.IN_VERIFICATION: frozenset({State.DONE, State.IN_PROGRESS, State.CANCELLED}),
    # INV-9: terminal. D-011 — rejected work becomes a new linked item, so no
    # item ever carries two cycle times.
    State.DONE: frozenset(),
    State.CANCELLED: frozenset(),
}

#: Only IN_PROGRESS counts toward a person's load. Someone with fifteen queued
#: items and one in progress is not overloaded — they are working on one thing
#: with a long queue, which is a different problem needing a different response.
LOAD_BEARING: frozenset[State] = frozenset({State.IN_PROGRESS})

#: RULE-005: waiting on the client does not count toward our accountability, and
#: is excluded from cycle time. This is what produces the evidence for
#: "eleven days, six of which we were waiting for your answer".
CLOCK_STOPPED: frozenset[State] = frozenset({State.BLOCKED_ON_CLIENT})

TERMINAL: frozenset[State] = frozenset({State.DONE, State.CANCELLED})

OPEN_STATES: frozenset[State] = frozenset(s for s in State) - TERMINAL

#: Human-facing labels. Kept beside the machine so a new state cannot be added
#: without someone deciding what to call it.
LABELS: dict[State, str] = {
    State.NEW: "Unassigned",
    State.QUEUED: "Queued",
    State.IN_PROGRESS: "In progress",
    State.ON_HOLD_PREEMPTED: "On hold",
    State.BLOCKED_ON_CLIENT: "Waiting on client",
    State.IN_VERIFICATION: "In verification",
    State.DONE: "Done",
    State.CANCELLED: "Cancelled",
}


class IllegalTransition(Exception):
    """Raised when a transition is not permitted by the lifecycle."""


def check_transition(current: State, target: State) -> None:
    """Raise IllegalTransition unless current -> target is allowed."""
    if target not in ALLOWED[current]:
        allowed = ", ".join(sorted(s.value for s in ALLOWED[current])) or "nothing"
        raise IllegalTransition(
            f"Cannot move from {current.value} to {target.value}. "
            f"From {current.value} the allowed transitions are: {allowed}."
        )
