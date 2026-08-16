"""Authentication: credentials on person, and a revocable session table.

Until now every record claimed to be created by person #1. The audit trail —
which under ADR-001 is the product's entire data source — was therefore
attributable to nobody. This migration is what makes it true.

Revision ID: 004_auth
Revises: 003_teams
"""
from __future__ import annotations

from alembic import op

revision = "004_auth"
down_revision = "003_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE person
            -- Nullable: a person can exist in the directory before they have a
            -- login. Someone recorded in the org chart is not yet a user.
            ADD COLUMN password_hash text,
            ADD COLUMN must_change_password boolean NOT NULL DEFAULT false,
            ADD COLUMN last_login_at timestamptz,
            -- Throttling state. Kept on the row rather than in memory so it
            -- survives a restart, which is exactly when an attacker would retry.
            ADD COLUMN failed_logins smallint NOT NULL DEFAULT 0,
            ADD COLUMN locked_until timestamptz
        """
    )

    # Server-side sessions rather than a self-contained signed cookie.
    #
    # A signed cookie cannot be revoked: deactivating someone leaves their
    # cookie working until it expires. For a system whose whole value is an
    # accurate record of who did what, "we cannot revoke access" is the wrong
    # trade. A row per session also makes "who is logged in" answerable.
    op.execute(
        """
        CREATE TABLE user_session (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            -- The cookie carries a random token; only its hash is stored, so a
            -- database leak does not hand over live sessions.
            token_hash  text NOT NULL UNIQUE,
            person_id   bigint NOT NULL REFERENCES person(id),
            created_at  timestamptz NOT NULL DEFAULT now(),
            expires_at  timestamptz NOT NULL,
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            revoked_at  timestamptz,
            user_agent  text,
            CONSTRAINT session_period_ordered CHECK (expires_at > created_at)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX live_sessions_by_person
            ON user_session (person_id)
            WHERE revoked_at IS NULL
        """
    )

    # Email is the login identifier, so it must match case-insensitively.
    # Without this, "Rahul@x.com" and "rahul@x.com" are two accounts.
    op.execute("UPDATE person SET email = lower(email)")
    # This is a UNIQUE *constraint*, so it must be dropped as one — DROP INDEX
    # refuses and tells you to drop the constraint instead.
    op.execute("ALTER TABLE person DROP CONSTRAINT IF EXISTS person_email_key")
    op.execute("CREATE UNIQUE INDEX person_email_unique ON person (lower(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS person_email_unique")
    op.execute("ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)")
    op.execute("DROP TABLE IF EXISTS user_session")
    op.execute(
        """
        ALTER TABLE person
            DROP COLUMN IF EXISTS password_hash,
            DROP COLUMN IF EXISTS must_change_password,
            DROP COLUMN IF EXISTS last_login_at,
            DROP COLUMN IF EXISTS failed_logins,
            DROP COLUMN IF EXISTS locked_until
        """
    )
