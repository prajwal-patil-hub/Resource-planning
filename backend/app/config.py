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
    # RULE-013: refuse to forecast from fewer than this many comparable items.
    min_sample_for_forecast: int = 10

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg://rp@/resource_planning?host=/tmp/pgs&port=5433",
            ),
            stale_after_days=int(os.environ.get("STALE_AFTER_DAYS", "3")),
            min_sample_for_forecast=int(os.environ.get("MIN_SAMPLE_FOR_FORECAST", "10")),
        )


settings = Settings.from_env()
