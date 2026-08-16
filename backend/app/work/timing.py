"""Turning "when did this actually happen?" into a moment (BR-004).

The stakeholder was explicit: *"if someone forgets to record it they can do it
by EOD for tracking."* So recording late is normal, not an exception, and the
product has always carried two timestamps for it — `occurred_at` (when the work
happened) and `recorded_at` (when someone typed it).

Until now only the service layer honoured that. The screens did not, so every
catch-up entry stamped the moment of typing. Under ADR-001 every number this
product shows is derived from these timestamps; a systematically wrong one does
not make the numbers vague, it makes them confidently wrong.

**The timezone problem, and why there is a hidden field for it.**
`<input type="datetime-local">` submits a *naive* wall-clock string —
`2026-08-16T09:30` — with no indication of which clock it was read from. A
server that assumed UTC would shift every entry by the user's offset: for a team
on IST (+05:30), 9:30am becomes 3:00pm, and a genuine morning entry can even
land in the future and be rejected outright. So the browser sends its offset
alongside, and we convert. Where the offset is missing the value is read as UTC
and said to be so, rather than silently guessing.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

#: How far back a recorded time may be dated.
#:
#: RULE-016. "Record it by EOD" needs hours, not weeks. Past a fortnight, a
#: backdated entry is far more likely a mistyped year or month than a real
#: catch-up — and one wild timestamp does more damage to a cycle-time
#: distribution than a dozen missing entries, because it silently drags the
#: average nobody is watching. Refusing is recoverable; a poisoned statistic is
#: not, because nobody knows to go looking for it.
MAX_BACKDATE = timedelta(days=14)

#: Tolerance for the gap between the browser's clock and the server's. Without
#: it, "now" submitted from a machine running a few seconds fast is refused as
#: being in the future, which would be baffling.
CLOCK_SKEW = timedelta(minutes=2)


class TimingError(Exception):
    """The stated time cannot be accepted, with a reason a user can act on."""


def parse_when(
    raw: str | None,
    offset_minutes: str | int | None = None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Read an optional "when did this happen" field.

    Returns `None` when nothing was stated, which the services already treat as
    "now" — so the fast path stays untouched and D-005 holds: a title alone is
    still enough to record something.

    `offset_minutes` is JavaScript's `Date.getTimezoneOffset()`: the minutes to
    **add** to local time to reach UTC (+05:30 reports -330).
    """
    if raw is None or not raw.strip():
        return None

    now = now or datetime.now(UTC)
    text = raw.strip()

    try:
        stated = datetime.fromisoformat(text)
    except ValueError:
        raise TimingError(
            "That does not look like a date and time. Leave it blank to record "
            "this as happening now."
        ) from None

    if stated.tzinfo is None:
        # A naive value is wall-clock time on the browser's clock. Convert it
        # using the offset that browser reported; assume UTC only if it did not.
        try:
            shift = int(offset_minutes) if offset_minutes not in (None, "") else 0
        except (TypeError, ValueError):
            shift = 0
        # Guard against a nonsense offset: real ones span UTC-12:00 to UTC+14:00.
        if not -840 <= shift <= 720:
            shift = 0
        stated = (stated + timedelta(minutes=shift)).replace(tzinfo=UTC)
    else:
        stated = stated.astimezone(UTC)

    if stated > now + CLOCK_SKEW:
        raise TimingError(
            "Work cannot be recorded as having happened in the future."
        )
    # Anything inside the skew window is genuinely "now"; clamp rather than
    # store a timestamp a few seconds ahead of the events that follow it.
    if stated > now:
        return now

    if now - stated > MAX_BACKDATE:
        days = (now - stated).days
        raise TimingError(
            f"That is {days} days ago. Recording is meant for catching up within "
            f"a fortnight — check the date, and if it really is that old, record "
            f"it now and say so in the description."
        )

    return stated


def was_backdated(occurred_at: datetime, recorded_at: datetime) -> bool:
    """Whether a record was entered noticeably after the fact.

    Used to label the timeline. A catch-up entry is legitimate, but a reader
    comparing two items deserves to know that one time was observed and the
    other remembered. Ten minutes is the threshold — below that the difference
    is the act of typing, not a delay worth reporting.
    """
    return recorded_at - occurred_at > timedelta(minutes=10)
