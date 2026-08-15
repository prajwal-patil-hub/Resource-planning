"""Initial schema: reference data, people, work items, transitions, audit.

Implements docs/11-database-design.md and ADR-003.

The guiding principle: a rule enforced only in application code will eventually
be broken, because there is always a second code path. Nine of the domain
model's thirteen invariants are enforced here, by the database itself.

Revision ID: 001_initial
Revises:
"""
from __future__ import annotations

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


# Fixed by the lifecycle (docs/08-domain-model.md section 5). Adding a state is
# never only data — it changes which transitions are legal, which count toward
# load, and which stop the clock. So it is a CHECK constraint, not a table:
# changing it requires a migration *because* it requires a code change.
STATES = (
    "NEW",
    "QUEUED",
    "IN_PROGRESS",
    "ON_HOLD_PREEMPTED",
    "BLOCKED_ON_CLIENT",
    "IN_VERIFICATION",
    "DONE",
    "CANCELLED",
)
STATE_LIST = ", ".join(f"'{s}'" for s in STATES)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # ------------------------------------------------------------------
    # Reference data. Extensible lists live in tables (K-014, BR-023).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE role (
            id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code text NOT NULL UNIQUE,
            name text NOT NULL,
            -- ADR-002 seam: roles are data, permissions are in code. If per-role
            -- permission editing is ever needed, a role_permission table is added
            -- and this becomes its default. Nothing that reads permissions changes.
            permission_level text NOT NULL
                CHECK (permission_level IN ('DEVELOPER','TEAM_LEAD','MANAGER','ADMIN')),
            can_verify boolean NOT NULL DEFAULT false,
            active boolean NOT NULL DEFAULT true
        )
        """
    )

    op.execute(
        """
        CREATE TABLE team (
            id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name   text NOT NULL UNIQUE,
            active boolean NOT NULL DEFAULT true
        )
        """
    )

    op.execute(
        """
        CREATE TABLE client (
            id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name   text NOT NULL UNIQUE,
            active boolean NOT NULL DEFAULT true
        )
        """
    )

    op.execute(
        """
        CREATE TABLE work_item_type (
            id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code       text NOT NULL UNIQUE,
            name       text NOT NULL,
            active     boolean NOT NULL DEFAULT true,
            sort_order smallint NOT NULL DEFAULT 100
        )
        """
    )

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE person (
            id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name          text NOT NULL CHECK (length(trim(name)) > 0),
            email         text NOT NULL UNIQUE,
            role_id       bigint NOT NULL REFERENCES role(id),
            team_id       bigint REFERENCES team(id),
            reports_to_id bigint REFERENCES person(id),
            -- RULE-008 / OPEN-4: seeded default, tuned per person from history.
            -- Personal, not global, because RULE-007 makes overload personal.
            normal_load   smallint NOT NULL DEFAULT 3
                          CHECK (normal_load BETWEEN 1 AND 20),
            -- INV-11: people are never deleted; history depends on them.
            active        boolean NOT NULL DEFAULT true,
            joined_on     date,
            left_on       date,
            CONSTRAINT person_not_own_manager
                CHECK (reports_to_id IS DISTINCT FROM id),
            CONSTRAINT person_dates_ordered
                CHECK (left_on IS NULL OR joined_on IS NULL OR left_on >= joined_on)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE absence (
            id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id      bigint NOT NULL REFERENCES person(id),
            period         daterange NOT NULL,
            kind           text NOT NULL CHECK (kind IN ('LEAVE','HOLIDAY','OTHER')),
            approved_by_id bigint REFERENCES person(id),
            note           text,
            created_at     timestamptz NOT NULL DEFAULT now(),
            -- INV-5. Doing this in application code loses the race when two
            -- requests arrive together; the database does not.
            CONSTRAINT no_overlapping_absence
                EXCLUDE USING gist (person_id WITH =, period WITH &&)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE non_working_day (
            day  date PRIMARY KEY,
            name text NOT NULL
        )
        """
    )

    # ------------------------------------------------------------------
    # Work
    # ------------------------------------------------------------------
    op.execute(
        f"""
        CREATE TABLE work_item (
            id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            -- BR-002 / D-005: title is the ONLY required field at creation.
            -- Every additional NOT NULL here is a tax on the recording behaviour
            -- that every metric in the product depends on.
            title           text NOT NULL CHECK (length(trim(title)) > 0),
            description     text,
            type_id         bigint REFERENCES work_item_type(id),
            client_id       bigint REFERENCES client(id),
            -- RULE-006: P0..P4, numeric so ordering is meaningful.
            priority        smallint NOT NULL DEFAULT 2 CHECK (priority BETWEEN 0 AND 4),
            -- Denormalized cache of the latest transition (D-014). Guarded by a
            -- trigger below so it cannot drift.
            state           text NOT NULL DEFAULT 'NEW' CHECK (state IN ({STATE_LIST})),
            -- RULE-014: client-given, never system-set.
            due_date        date,
            -- INV-3 + INV-4.
            displaced_by_id bigint REFERENCES work_item(id),
            -- D-011: rejected work becomes a new item linked to the original,
            -- so no item ever has two cycle times.
            follow_up_of_id bigint REFERENCES work_item(id),
            created_by_id   bigint NOT NULL REFERENCES person(id),
            created_at      timestamptz NOT NULL DEFAULT now(),
            -- D-013: optimistic locking.
            version         integer NOT NULL DEFAULT 1,
            -- The most valuable constraint in the schema: makes BO-4 —
            -- explaining lateness with evidence — structurally unavoidable.
            CONSTRAINT preempted_names_its_displacer
                CHECK (state <> 'ON_HOLD_PREEMPTED' OR displaced_by_id IS NOT NULL),
            CONSTRAINT displacer_is_another_item
                CHECK (displaced_by_id IS DISTINCT FROM id),
            CONSTRAINT follow_up_is_another_item
                CHECK (follow_up_of_id IS DISTINCT FROM id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE work_item_participant (
            id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            work_item_id   bigint NOT NULL REFERENCES work_item(id),
            person_id      bigint NOT NULL REFERENCES person(id),
            participation  text NOT NULL CHECK (participation IN ('OWNER','COLLABORATOR')),
            -- D-012: time-bounded, so ownership history survives reassignment.
            from_ts        timestamptz NOT NULL DEFAULT now(),
            to_ts          timestamptz,
            -- C-007: anyone may assign, so every assignment is attributable.
            assigned_by_id bigint NOT NULL REFERENCES person(id),
            CONSTRAINT participation_period_ordered
                CHECK (to_ts IS NULL OR to_ts >= from_ts)
        )
        """
    )

    # INV-1. Note the WHERE clause: a plain UNIQUE would forbid an item from ever
    # having had two owners across time, destroying the history we exist to keep.
    # Restricting uniqueness to current rows permits any number of past owners,
    # never two at once — and holds under concurrent writes, which application
    # checking cannot guarantee.
    op.execute(
        """
        CREATE UNIQUE INDEX one_current_owner_per_item
            ON work_item_participant (work_item_id)
            WHERE participation = 'OWNER' AND to_ts IS NULL
        """
    )

    # The substrate. Every metric in the product is computed from this table.
    op.execute(
        f"""
        CREATE TABLE state_transition (
            id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            work_item_id    bigint NOT NULL REFERENCES work_item(id),
            from_state      text CHECK (from_state IS NULL OR from_state IN ({STATE_LIST})),
            to_state        text NOT NULL CHECK (to_state IN ({STATE_LIST})),
            -- When it really happened vs when it was typed (BR-004).
            -- Cycle time must use occurred_at, or a batch of 6pm catch-up
            -- updates makes every item look like it took a day.
            occurred_at     timestamptz NOT NULL,
            recorded_at     timestamptz NOT NULL DEFAULT now(),
            changed_by_id   bigint NOT NULL REFERENCES person(id),
            displaced_by_id bigint REFERENCES work_item(id),
            note            text,
            CONSTRAINT cannot_record_before_it_happened
                CHECK (occurred_at <= recorded_at),
            CONSTRAINT preemption_transition_names_displacer
                CHECK (to_state <> 'ON_HOLD_PREEMPTED' OR displaced_by_id IS NOT NULL)
        )
        """
    )

    # ADR-003 layer 2: field-level history. State is not the only thing that
    # changes — priority, due dates and clients all change the meaning of every
    # metric computed afterwards.
    op.execute(
        """
        CREATE TABLE work_item_audit (
            id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            work_item_id  bigint NOT NULL REFERENCES work_item(id),
            field         text NOT NULL,
            old_value     text,
            new_value     text,
            changed_by_id bigint REFERENCES person(id),
            occurred_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    for table in (
        "work_item_audit",
        "state_transition",
        "work_item_participant",
        "work_item",
        "non_working_day",
        "absence",
        "person",
        "work_item_type",
        "client",
        "team",
        "role",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
