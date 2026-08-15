"""Seed the real team list and index team lookups.

Until now a single "Default" team existed, because no team structure had been
confirmed. Discovery named four groups (K-006, K-025): development, QA, BA and
management. Support and operations are added on the stakeholder's instruction.

Revision ID: 003_teams
Revises: 002_guards
"""
from __future__ import annotations

from alembic import op

revision = "003_teams"
down_revision = "002_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The existing "Default" team already owns rows; rename rather than replace,
    # so no person is orphaned and no history is disturbed.
    op.execute("UPDATE team SET name = 'Development' WHERE name = 'Default'")
    op.execute(
        """
        INSERT INTO team (name) VALUES
            ('QA'), ('Support'), ('Operations'), ('BA')
        ON CONFLICT (name) DO NOTHING
        """
    )
    # Filtering the board by team resolves through the owner's team, so this
    # lookup runs on every filtered page load.
    op.execute("CREATE INDEX IF NOT EXISTS person_by_team ON person (team_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS person_by_team")
    op.execute("DELETE FROM team WHERE name IN ('QA','Support','Operations','BA')")
    op.execute("UPDATE team SET name = 'Default' WHERE name = 'Development'")
