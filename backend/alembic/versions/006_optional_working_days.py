"""Optional working days.

The stakeholder confirmed the team works Saturdays "but not always — it's
optional". A binary worked/not-worked flag cannot express that, and both
binary answers are wrong:

- Saturday counted as a working day punishes everyone who did NOT come in.
  A ticket sitting untouched over a Saturday nobody worked reads as a day lost.
- Saturday counted as non-working hides work that genuinely happened. Someone
  who came in on Saturday to fix a P0 gets no credit for it, and the item looks
  like it sat still.

So a day now has three states: worked, never worked, and **optional** — worked
only on the specific dates when someone actually worked.

Whether a particular optional day was worked is **derived from recorded
activity**, not asked (ADR-001). If work moved that day, the day was worked.

Revision ID: 006_optional_days
Revises: 005_absence
"""
from __future__ import annotations

from alembic import op

revision = "006_optional_days"
down_revision = "005_absence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE org_setting
            -- ISO weekday numbers worked only when activity is recorded.
            ADD COLUMN optional_days smallint[] NOT NULL DEFAULT '{6}'
        """
    )
    # Saturday moves out of "never worked" and into "optional"; Sunday stays.
    op.execute(
        """
        UPDATE org_setting
        SET weekend_days = '{7}', optional_days = '{6}'
        WHERE weekend_days @> '{6}' AND weekend_days @> '{7}'
        """
    )

    # Deriving "was this optional day worked?" scans transitions by calendar
    # date, which nothing indexed before.
    #
    # The cast is pinned to UTC deliberately. `occurred_at::date` on a
    # timestamptz depends on the session TimeZone, so it is not IMMUTABLE and
    # cannot be indexed — and more importantly, two servers configured
    # differently would disagree about which day a transition happened on.
    op.execute(
        """
        CREATE INDEX transitions_by_day
            ON state_transition (((occurred_at AT TIME ZONE 'UTC')::date))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS transitions_by_day")
    op.execute("UPDATE org_setting SET weekend_days = '{6,7}'")
    op.execute("ALTER TABLE org_setting DROP COLUMN IF EXISTS optional_days")
