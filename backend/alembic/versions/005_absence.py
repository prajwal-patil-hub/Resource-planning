"""Absence: authorship, approval, and the working-week setting.

The absence table and its no-overlap constraint have existed since 001 but were
unreachable — BO-3 (absence never silently stalls client work) was entirely
unmet. This makes it usable.

Revision ID: 005_absence
Revises: 004_auth
"""
from __future__ import annotations

from alembic import op

revision = "005_absence"
down_revision = "004_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE absence
            -- Who recorded it, as distinct from who approved it. A lead
            -- entering leave on someone's behalf is normal and must be visible.
            ADD COLUMN created_by_id bigint REFERENCES person(id),
            ADD COLUMN created_by_name text,
            ADD COLUMN approved_at timestamptz,
            -- Cancelled rather than deleted, consistent with everything else
            -- here: the record of a decision outlives the decision.
            ADD COLUMN cancelled_at timestamptz,
            ADD COLUMN cancelled_by_id bigint REFERENCES person(id)
        """
    )

    # The EXCLUDE constraint from 001 prevents ANY two absences overlapping for
    # one person — including a cancelled one blocking a new booking. Cancelled
    # rows must be excluded from the check or a corrected date range can never
    # be re-entered.
    op.execute("ALTER TABLE absence DROP CONSTRAINT IF EXISTS no_overlapping_absence")
    op.execute(
        """
        ALTER TABLE absence ADD CONSTRAINT no_overlapping_absence
            EXCLUDE USING gist (person_id WITH =, period WITH &&)
            WHERE (cancelled_at IS NULL)
        """
    )

    op.execute(
        """
        CREATE INDEX absence_by_person_live
            ON absence USING gist (person_id, period)
            WHERE cancelled_at IS NULL
        """
    )

    # Organization-wide settings. One row, enforced.
    #
    # This is deliberately a table rather than an environment variable: the
    # working week is a business fact the organization owns, not deployment
    # configuration, and it must be visible and changeable without a deploy.
    op.execute(
        """
        CREATE TABLE org_setting (
            id                smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            -- ISO weekday numbers that are NOT worked. 6=Saturday, 7=Sunday.
            -- TO VALIDATE: assumed Sat+Sun; the stakeholder has not confirmed
            -- whether this team works Saturdays.
            weekend_days      smallint[] NOT NULL DEFAULT '{6,7}',
            stale_after_days  smallint NOT NULL DEFAULT 3 CHECK (stale_after_days BETWEEN 1 AND 30)
        )
        """
    )
    op.execute("INSERT INTO org_setting (id) VALUES (1) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_setting")
    op.execute("DROP INDEX IF EXISTS absence_by_person_live")
    op.execute("ALTER TABLE absence DROP CONSTRAINT IF EXISTS no_overlapping_absence")
    op.execute(
        """
        ALTER TABLE absence ADD CONSTRAINT no_overlapping_absence
            EXCLUDE USING gist (person_id WITH =, period WITH &&)
        """
    )
    op.execute(
        """
        ALTER TABLE absence
            DROP COLUMN IF EXISTS created_by_id,
            DROP COLUMN IF EXISTS created_by_name,
            DROP COLUMN IF EXISTS approved_at,
            DROP COLUMN IF EXISTS cancelled_at,
            DROP COLUMN IF EXISTS cancelled_by_id
        """
    )
