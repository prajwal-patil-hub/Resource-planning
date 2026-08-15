"""Triggers, indexes and seed data.

Triggers carry the rules SQL constraints cannot express. Every one of them exists
because the audit trail IS the data source (ADR-001, ADR-003) — a hole in it is
not a missing log line, it is a hole in the arithmetic.

Revision ID: 002_guards
Revises: 001_initial
"""
from __future__ import annotations

from alembic import op

revision = "002_guards"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # INV-2: transitions are append-only.
    #
    # Editing a past transition silently changes historical measurements — a
    # cycle time that was 3 days becomes 1 day, and no report shows that it
    # changed. This is not audit hygiene; it protects every number displayed.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_transition_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'state_transition is append-only (INV-2): % attempted on work_item %',
                TG_OP, COALESCE(OLD.work_item_id, NEW.work_item_id);
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER state_transition_is_immutable
            BEFORE UPDATE OR DELETE ON state_transition
            FOR EACH ROW EXECUTE FUNCTION forbid_transition_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'work_item_audit is append-only (ADR-003): % attempted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER work_item_audit_is_immutable
            BEFORE UPDATE OR DELETE ON work_item_audit
            FOR EACH ROW EXECUTE FUNCTION forbid_audit_mutation();
        """
    )

    # ------------------------------------------------------------------
    # INV-12: a transition cannot be dated into the future.
    #
    # A CHECK constraint may not call now() — constraints must be immutable, and
    # PostgreSQL revalidates them at unpredictable times. So this is a trigger.
    # One minute of tolerance absorbs harmless clock skew between app and db.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_future_occurrence() RETURNS trigger AS $$
        BEGIN
            IF NEW.occurred_at > now() + interval '1 minute' THEN
                RAISE EXCEPTION 'occurred_at cannot be in the future (INV-12): %',
                    NEW.occurred_at;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER transition_not_future
            BEFORE INSERT ON state_transition
            FOR EACH ROW EXECUTE FUNCTION reject_future_occurrence();
        """
    )

    # ------------------------------------------------------------------
    # INV-7: work_item.state may only change alongside a recorded transition.
    #
    # This is what keeps the D-014 denormalization honest. The transition service
    # sets app.transition_in_progress for its transaction; every other path —
    # including a manual UPDATE in psql — is rejected.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_bare_state_change() RETURNS trigger AS $$
        BEGIN
            IF NEW.state IS DISTINCT FROM OLD.state
               AND current_setting('app.transition_in_progress', true) IS DISTINCT FROM 'on'
            THEN
                RAISE EXCEPTION
                    'work_item.state may only change via a recorded transition (INV-7)';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER work_item_state_guarded
            BEFORE UPDATE ON work_item
            FOR EACH ROW EXECUTE FUNCTION forbid_bare_state_change();
        """
    )

    # ------------------------------------------------------------------
    # ADR-003 option B: field history captured by trigger, not by application
    # code. A log the application writes is only as complete as the code paths
    # that remember to call it; the first developer who writes an UPDATE for a
    # data fix creates a permanent invisible hole.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION capture_work_item_changes() RETURNS trigger AS $$
        DECLARE
            actor bigint := NULLIF(current_setting('app.actor_id', true), '')::bigint;
        BEGIN
            IF NEW.title IS DISTINCT FROM OLD.title THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'title', OLD.title, NEW.title, actor);
            END IF;
            IF NEW.description IS DISTINCT FROM OLD.description THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'description', OLD.description, NEW.description, actor);
            END IF;
            IF NEW.priority IS DISTINCT FROM OLD.priority THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'priority', OLD.priority::text, NEW.priority::text, actor);
            END IF;
            IF NEW.due_date IS DISTINCT FROM OLD.due_date THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'due_date', OLD.due_date::text, NEW.due_date::text, actor);
            END IF;
            IF NEW.client_id IS DISTINCT FROM OLD.client_id THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'client_id', OLD.client_id::text, NEW.client_id::text, actor);
            END IF;
            IF NEW.type_id IS DISTINCT FROM OLD.type_id THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'type_id', OLD.type_id::text, NEW.type_id::text, actor);
            END IF;
            IF NEW.state IS DISTINCT FROM OLD.state THEN
                INSERT INTO work_item_audit (work_item_id, field, old_value, new_value, changed_by_id)
                VALUES (NEW.id, 'state', OLD.state, NEW.state, actor);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER work_item_field_history
            AFTER UPDATE ON work_item
            FOR EACH ROW EXECUTE FUNCTION capture_work_item_changes();
        """
    )

    # ------------------------------------------------------------------
    # Indexes. Each justified by a query in docs/11-database-design.md section 6.
    #
    # Partial where possible: DONE and CANCELLED items will eventually be most of
    # the table and are never wanted by the screens people use daily.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE INDEX current_participation_by_person
            ON work_item_participant (person_id)
            WHERE to_ts IS NULL;

        CREATE INDEX open_work_items_by_state
            ON work_item (state)
            WHERE state NOT IN ('DONE','CANCELLED');

        CREATE INDEX transitions_by_item_recent
            ON state_transition (work_item_id, occurred_at DESC);

        CREATE INDEX transitions_by_target_state
            ON state_transition (to_state, occurred_at);

        CREATE INDEX open_work_items_by_client
            ON work_item (client_id)
            WHERE state NOT IN ('DONE','CANCELLED');

        CREATE INDEX open_work_items_by_due_date
            ON work_item (due_date)
            WHERE due_date IS NOT NULL AND state NOT IN ('DONE','CANCELLED');

        CREATE INDEX audit_by_item
            ON work_item_audit (work_item_id, occurred_at DESC);
        """
    )

    # ------------------------------------------------------------------
    # Seed data. The system must work immediately after installation with no
    # configuration (BR-021, CON-5).
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO role (code, name, permission_level, can_verify) VALUES
            ('DEVELOPER', 'Developer',  'DEVELOPER', false),
            ('QA',        'QA',         'DEVELOPER', true),
            ('TEAM_LEAD', 'Team Lead',  'TEAM_LEAD', true),
            ('MANAGER',   'Manager',    'MANAGER',   false),
            ('ADMIN',     'Admin',      'ADMIN',     true);

        INSERT INTO team (name) VALUES ('Default');

        INSERT INTO work_item_type (code, name, sort_order) VALUES
            ('BUG',         'Bug',            10),
            ('CR',          'Change Request', 20),
            ('OBSERVATION', 'Observation',    30),
            ('SUPPORT',     'Support',        40),
            ('OTHER',       'Other',          99);
        """
    )
    # 'Other' exists so classification is never a barrier to recording (D-005).


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS work_item_field_history ON work_item;
        DROP TRIGGER IF EXISTS work_item_state_guarded ON work_item;
        DROP TRIGGER IF EXISTS transition_not_future ON state_transition;
        DROP TRIGGER IF EXISTS work_item_audit_is_immutable ON work_item_audit;
        DROP TRIGGER IF EXISTS state_transition_is_immutable ON state_transition;
        DROP FUNCTION IF EXISTS capture_work_item_changes();
        DROP FUNCTION IF EXISTS forbid_bare_state_change();
        DROP FUNCTION IF EXISTS reject_future_occurrence();
        DROP FUNCTION IF EXISTS forbid_audit_mutation();
        DROP FUNCTION IF EXISTS forbid_transition_mutation();
        """
    )
