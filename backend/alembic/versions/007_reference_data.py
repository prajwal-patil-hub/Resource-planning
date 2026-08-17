"""Reference data integrity (BR-023, BR-024).

Adding a client or a work type has needed raw SQL until now. Opening that to
users exposes two gaps in the original schema that nobody could hit while the
only way in was a careful hand-written INSERT.

**1. Names were not unique, or were unique only by case.**
`client.name` and `team.name` carried a UNIQUE constraint, but a case-sensitive
one: "Acme" and "acme" could both exist. `work_item_type.name` and `role.name`
had none at all — only their `code` did — so two types both displayed as "Bug"
were possible.

Either produces the same failure, and it is a bad one: the client report splits
one client's work across two rows, each with half the history, and neither total
is right. Nothing in the reports can detect it, because from their point of view
these genuinely are two different clients.

**2. There was no way to say "stop offering this".**
Reference rows are referenced by work items forever, so they can never be
deleted — BR-005's "never destroyed, only cancelled" applies to them as much as
to work. `active` already existed for exactly this, and this migration simply
makes the guarantee explicit alongside the new uniqueness rules.

Revision ID: 007_reference_data
Revises: 006_optional_days
"""
from __future__ import annotations

from alembic import op

revision = "007_reference_data"
down_revision = "006_optional_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Case-insensitive uniqueness on every human-facing name. `lower(name)` is
    # immutable for text, so it can be indexed directly.
    #
    # These are added as indexes rather than table constraints because a
    # constraint cannot be expressed over an expression in PostgreSQL.
    for table in ("client", "team", "work_item_type", "role"):
        op.execute(
            f"CREATE UNIQUE INDEX {table}_name_ci ON {table} (lower(name))"
        )

    # The old case-sensitive constraints are now strictly weaker than the
    # indexes above and only serve to produce a worse error message.
    op.execute("ALTER TABLE client DROP CONSTRAINT IF EXISTS client_name_key")
    op.execute("ALTER TABLE team DROP CONSTRAINT IF EXISTS team_name_key")

    # Reference rows are pointed at by work items and people for the life of
    # the record, so deletion is not an operation this product offers. Blocking
    # it in the database means no future code path can quietly reintroduce it —
    # the same reasoning as the append-only trigger on state_transition.
    for table in ("client", "work_item_type", "role", "team"):
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION forbid_{table}_delete() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    '{table} rows are referenced by history and are deactivated, never deleted';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER {table}_no_delete
                BEFORE DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION forbid_{table}_delete();
            """
        )


def downgrade() -> None:
    for table in ("client", "work_item_type", "role", "team"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS forbid_{table}_delete()")
        op.execute(f"DROP INDEX IF EXISTS {table}_name_ci")
