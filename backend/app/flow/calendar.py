"""Working-time arithmetic (BR-014).

Elapsed time is currently measured in wall clock, which means a bug raised at
5pm on Friday and fixed at 9am on Monday reads as "2.7 days". That number is
true and useless: nobody was working for most of it.

**The distinction this module exists to make:**

| Measure | Includes weekends and holidays? | Answers |
|---|---|---|
| Calendar elapsed | Yes | What the client experienced |
| Working elapsed | No | How long we actually had to act |

Both are real. Reporting only calendar time makes the team look slow; reporting
only working time hides how long the client waited. The product shows calendar
time for what the client sees, and working time for what we answer for.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NonWorkingDay, OrgSetting


@dataclass(frozen=True)
class WorkingCalendar:
    """The organization's working week, loaded once per request.

    Held as a value object rather than queried per call: computing working time
    across a 90-day span would otherwise issue 90 queries.
    """

    #: ISO weekday numbers that are not worked (Monday=1 … Sunday=7).
    weekend_days: frozenset[int]
    holidays: frozenset[date]

    def is_working_day(self, day: date) -> bool:
        return day.isoweekday() not in self.weekend_days and day not in self.holidays

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
    weekend = frozenset(setting.weekend_days) if setting else frozenset({6, 7})
    holidays = frozenset(session.scalars(select(NonWorkingDay.day)).all())
    return WorkingCalendar(weekend_days=weekend, holidays=holidays)


def working_duration(
    start: datetime, end: datetime, calendar: WorkingCalendar
) -> timedelta:
    """Elapsed time between two moments, counting only working days.

    Whole days are counted whole — this deliberately does NOT model working
    hours (9–5). We have no data on when people actually work, and inventing
    an office-hours model would produce numbers that look precise and are not.
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
