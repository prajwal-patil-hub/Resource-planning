"""Working-time arithmetic (BR-014).

Elapsed time measured in wall clock means a bug raised at 5pm on Friday and
fixed at 9am on Monday reads as "2.7 days". That number is true and useless:
nobody was working for most of it.

**The distinction this module exists to make:**

| Measure | Includes non-working days? | Answers |
|---|---|---|
| Calendar elapsed | Yes | What the client experienced |
| Working elapsed | No | How long we actually had to act |

Both are real. Reporting only calendar time makes the team look slow;
reporting only working time hides how long the client waited.

**Three kinds of day, not two.** The team works Saturdays sometimes. Treating
Saturday as a working day punishes everyone who did not come in; treating it as
non-working erases the work of whoever did. So an *optional* day counts only on
the specific dates when work was actually recorded — derived from the event log
rather than asked for (ADR-001).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Date, distinct, func, select
from sqlalchemy.orm import Session

from app.models import NonWorkingDay, OrgSetting, StateTransition


@dataclass(frozen=True)
class WorkingCalendar:
    """The organization's working week, loaded once per request.

    Held as a value object rather than queried per call: computing working time
    across a 90-day span would otherwise issue 90 queries.
    """

    #: ISO weekday numbers never worked (Monday=1 … Sunday=7).
    weekend_days: frozenset[int]
    holidays: frozenset[date]
    #: ISO weekday numbers worked only when someone actually worked.
    optional_days: frozenset[int] = frozenset()
    #: Specific optional dates known to have been worked.
    worked_optional: frozenset[date] = frozenset()

    def is_working_day(self, day: date) -> bool:
        if day.isoweekday() in self.weekend_days or day in self.holidays:
            return False
        if day.isoweekday() in self.optional_days:
            return day in self.worked_optional
        return True

    def day_kind(self, day: date) -> str:
        """For explaining a number back to a user (BR-020)."""
        if day in self.holidays:
            return "holiday"
        if day.isoweekday() in self.weekend_days:
            return "not worked"
        if day.isoweekday() in self.optional_days:
            return "optional — worked" if day in self.worked_optional else "optional — not worked"
        return "worked"

    def with_worked_days(self, days: frozenset[date] | set[date]) -> "WorkingCalendar":
        """A copy that also treats these optional dates as worked."""
        return replace(self, worked_optional=self.worked_optional | frozenset(days))

    def working_days_between(self, start: date, end: date) -> int:
        """Inclusive of both ends. Used for absence length."""
        if end < start:
            return 0
        return sum(
            1
            for offset in range((end - start).days + 1)
            if self.is_working_day(start + timedelta(days=offset))
        )

    def next_working_day(self, day: date) -> date:
        candidate = day
        # 30 is a generous ceiling; a longer run of non-working days would mean
        # the calendar itself is misconfigured, and looping forever would hide it.
        for _ in range(30):
            if self.is_working_day(candidate):
                return candidate
            candidate += timedelta(days=1)
        return candidate


def load_calendar(session: Session) -> WorkingCalendar:
    setting = session.get(OrgSetting, 1)
    return WorkingCalendar(
        weekend_days=frozenset(setting.weekend_days) if setting else frozenset({7}),
        optional_days=frozenset(setting.optional_days) if setting else frozenset({6}),
        holidays=frozenset(session.scalars(select(NonWorkingDay.day)).all()),
    )


def days_with_activity(
    session: Session, start: date, end: date, *, person_ids: list[int] | None = None
) -> set[date]:
    """Calendar dates on which work was recorded.

    This is what turns an optional day into a worked one. Deriving it from the
    event log rather than asking someone to tick "we worked this Saturday" is
    ADR-001 applied: the answer is already in data people produce by working.
    """
    # Pinned to UTC so the answer does not depend on the server's timezone,
    # and so the matching index can be used.
    day_of = func.cast(func.timezone("UTC", StateTransition.occurred_at), Date)
    query = select(distinct(day_of)).where(day_of.between(start, end))
    if person_ids:
        query = query.where(StateTransition.changed_by_id.in_(person_ids))
    return set(session.scalars(query).all())


def resolve_optional_days(
    session: Session,
    calendar: WorkingCalendar,
    start: date,
    end: date,
    *,
    person_ids: list[int] | None = None,
) -> WorkingCalendar:
    """Fill in which optional days in a range were actually worked.

    Scoped to specific people where possible: one person coming in on Saturday
    should not make that Saturday count against a colleague who did not.
    """
    if not calendar.optional_days or end < start:
        return calendar

    candidates = {
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).isoweekday() in calendar.optional_days
    }
    if not candidates:
        return calendar

    active = days_with_activity(session, start, end, person_ids=person_ids)
    return calendar.with_worked_days(candidates & active)


def working_duration(
    start: datetime, end: datetime, calendar: WorkingCalendar
) -> timedelta:
    """Elapsed time between two moments, counting only working days.

    Whole days are counted whole — this deliberately does NOT model working
    hours (9–5). We have no data on when people actually work, and inventing an
    office-hours model would produce numbers that look precise and are not.
    Excluding whole non-working days is the largest correction available from
    facts we actually have.
    """
    if end <= start:
        return timedelta()

    total = timedelta()
    day = start.date()
    last = end.date()

    while day <= last:
        if calendar.is_working_day(day):
            day_start = datetime.combine(day, time.min, tzinfo=UTC)
            day_end = day_start + timedelta(days=1)
            overlap_start = max(start, day_start)
            overlap_end = min(end, day_end)
            if overlap_end > overlap_start:
                total += overlap_end - overlap_start
        day += timedelta(days=1)

    return total
