"""Application configuration.

Single source for settings. Reads the environment, applies defaults that work
for local development so nothing needs configuring to run (BR-021, CON-5).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    # RULE-009 / BO-2: an item with no state change for this long is "stalled".
    stale_after_days: int = 3
    # NOTE: there is deliberately no setting for the forecasting minimum
    # sample. One existed, read MIN_SAMPLE_FOR_FORECAST, defaulted to 10, and was
    # wired to nothing — while the code enforced 8. A knob that does not turn
    # anything is worse than no knob: it invites someone to "fix" a forecast by
    # setting it to 3, and it lied about the number in force. ADR-005 argues 8
    # specifically, so it stays a reasoned constant in app/flow/statistics.py.
    #: Off for local HTTP development; MUST be on in production, or the session
    #: cookie travels in clear text.
    cookies_secure: bool = False

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg://rp@/resource_planning?host=/tmp/pgs&port=5433",
            ),
            stale_after_days=int(os.environ.get("STALE_AFTER_DAYS", "3")),
            cookies_secure=os.environ.get("COOKIES_SECURE", "0") == "1",
        )


settings = Settings.from_env()
