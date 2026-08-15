# Database Design — Resource Planning

| | |
|---|---|
| **Document** | Database Design v1.0 |
| **Status** | DRAFT — for review |
| **Date** | 2026-08-15 |
| **Phase** | Phase 3 — Database Design |
| **Derives from** | `docs/08-domain-model.md` |
| **Target** | PostgreSQL 16, via SQLAlchemy + Alembic |

---

## 0. What this document is

The domain model said *what the business deals with*. This says *how it is
stored*, and — more importantly — **which business rules the database itself will
refuse to break**.

**The principle running through the whole document:** a rule enforced only in
application code is a rule that will eventually be broken, because there is
always a second code path — a script, a bug fix, a manual `UPDATE` at 11pm. A
rule enforced by the database cannot be broken by any path.

This matters more here than in most systems. Under ADR-001 every number the
product shows is *derived* from stored data. Corrupt data doesn't produce an
error message; it produces a plausible wrong number that nobody questions.

So the test applied to every invariant below is: **can the database enforce this
itself?** Where the answer is no, that is stated explicitly rather than assumed.

---

## 1. Concepts used here

### Primary key (PK)
**What:** the column that uniquely identifies a row.
**Why:** without it "the same row" has no meaning — you cannot reliably update or
reference anything.
**Here:** every table has one. See §2 for the choice of type.

### Foreign key (FK)
**What:** a column pointing at another table's primary key, which the database
enforces must exist.
**Why:** it makes "this work item belongs to a client that doesn't exist"
impossible rather than merely unlikely.
**Here:** every relationship in the domain model becomes an FK.

### Constraint
A rule the database enforces on every write, from any source.

| Kind | Enforces | Example here |
|---|---|---|
| `NOT NULL` | A value must be present | `work_item.title` |
| `UNIQUE` | No duplicates | `person.email` |
| `CHECK` | An expression must be true | Priority is 0–4 |
| `FOREIGN KEY` | The referenced row exists | `work_item.client_id` |
| `EXCLUDE` | No two rows conflict by a chosen operator | Absences must not overlap |

### Normalization
**What:** organizing tables so each fact is stored in exactly one place.
**Why:** if a fact is stored twice, the two copies eventually disagree, and
nothing tells you which is right.
**Example of the problem:** storing a client's name on every work item means
renaming the client requires updating thousands of rows, and any missed row is a
silent inconsistency. Storing `client_id` and keeping the name in one row fixes
it.
**Here:** the schema is normalized, with **one deliberate exception** — the
`work_item.state` column, explained in §4.3.

### Index
**What:** a lookup structure that lets the database find rows without scanning the
whole table.
**Why not index everything:** every index must be updated on write, so indexes
make writes slower and consume space. They are a trade, not a free win.
**Here:** every index in §6 is justified by a specific query. Speculative indexes
are omitted deliberately.

### Transaction
**What:** a group of statements that either all take effect or none do.
**Why:** without it, a crash halfway through leaves the database in a state your
rules say is impossible — for example, an item whose state says
`ON_HOLD_PREEMPTED` with no transition row explaining it.
**Here:** one aggregate change is one transaction (domain model §1).

### Migration
**What:** a versioned, ordered script that changes the schema, checked into git
alongside the code that needs it.
**Why:** schemas change. Without migrations, "which version is this database?"
becomes unanswerable, and environments silently diverge.
**Here:** Alembic. One migration per change; an applied migration is never edited.

---

## 2. Conventions

| Decision | Choice | Why |
|---|---|---|
| Primary key type | `bigint generated always as identity` | Small, fast, human-readable — "item #482" is usable in conversation and in a URL. A UUID would help only for offline creation or merging databases, neither of which applies. Trade-off: IDs are guessable, which is irrelevant for an internal tool behind authentication |
| Timestamps | `timestamptz` — **always** | `timestamp without time zone` stores a number with no meaning. Cycle time is the core metric here; measuring it across a daylight-saving boundary with naive timestamps produces silently wrong answers |
| Dates | `date` where no time is meaningful | Due dates and absences are whole days |
| Naming | `snake_case`, singular table names | Consistency only; no technical significance |
| Deletes | **None.** Nothing is ever deleted | INV-10, INV-11. History is the substrate |
| Enumerated values | `text` + `CHECK` for fixed sets; a table for extensible sets | See §2.1 |

### 2.1 Why states are a CHECK constraint but work types are a table

Both look like "a list of allowed values". They are not the same kind of list.

**Work types** (bug, CR, observation, BA work) must be **user-extensible without a
code change** (K-014, BR-023). Adding one changes no logic — a new type just
groups differently. That is reference data: a table.

**States** (`NEW`, `IN_PROGRESS`, …) are fixed by the lifecycle. Adding a state is
never *only* data — it changes which transitions are legal, which states count
toward load, and which stop the clock. Making states editable would let someone
add a state the code has no rules for, and the system would silently mis-measure
it. A `CHECK` constraint is the honest expression: changing this requires a
migration *because* it requires a code change.

> **The general rule:** make a list extensible when adding an entry changes only
> data. Keep it fixed when adding an entry changes behaviour. Getting this
> backwards produces either constant migrations or configurable nonsense.

PostgreSQL `ENUM` types were considered and rejected — `ALTER TYPE ... ADD VALUE`
has awkward transactional behaviour in migrations, and `text` + `CHECK` is easier
to evolve for no practical loss.

---

## 3. Reference tables

```sql
CREATE TABLE role (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    -- ADR-002: roles are data, permissions are in code.
    -- New roles inherit one of the four built-in permission levels.
    permission_level text NOT NULL
        CHECK (permission_level IN ('DEVELOPER','TEAM_LEAD','MANAGER','ADMIN')),
    active      boolean NOT NULL DEFAULT true
);

CREATE TABLE team (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    active      boolean NOT NULL DEFAULT true
);

CREATE TABLE client (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    active      boolean NOT NULL DEFAULT true
);

CREATE TABLE work_item_type (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    active      boolean NOT NULL DEFAULT true,
    sort_order  smallint NOT NULL DEFAULT 100
);
```

> **`permission_level` is the ADR-002 seam.** Today it selects one of four
> behaviour sets defined in code. If per-role permission editing is ever needed,
> a `role_permission` table is added and this column becomes its default. Nothing
> that reads permissions has to change, because everything goes through the
> `access` module.

> **`active` rather than deletion, even for reference data.** A work type in use
> on 200 historical items cannot be deleted without either destroying those items
> or orphaning them. Deactivating removes it from the dropdown while leaving
> history intact.

---

## 4. Core tables

### 4.1 person

```sql
CREATE TABLE person (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text NOT NULL,
    email        text NOT NULL UNIQUE,
    role_id      bigint NOT NULL REFERENCES role(id),
    team_id      bigint REFERENCES team(id),
    reports_to_id bigint REFERENCES person(id),

    -- RULE-008: seeded default, tuned per person from observed history.
    normal_load  smallint NOT NULL DEFAULT 3
                 CHECK (normal_load BETWEEN 1 AND 20),

    active       boolean NOT NULL DEFAULT true,
    joined_on    date,
    left_on      date,

    CONSTRAINT person_not_own_manager CHECK (reports_to_id IS DISTINCT FROM id),
    CONSTRAINT person_dates_ordered
        CHECK (left_on IS NULL OR joined_on IS NULL OR left_on >= joined_on)
);
```

**`normal_load` defaults to 3** — this answers OPEN-4. Three is a starting guess,
chosen because it is low enough that the overload signal fires early (better than
firing late) and because RULE-008 says it gets tuned per person once four weeks of
real history exist. It is stored per person, not globally, because RULE-007
requires overload to be personal.

`reports_to_id` self-reference builds the hierarchy (K-017). The check prevents
someone reporting to themselves; **longer cycles (A→B→A) cannot be prevented by a
constraint** and are checked in application code — noted honestly in §7.

### 4.2 work_item

```sql
CREATE TABLE work_item (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- BR-002 / D-005: title is the ONLY required field at creation.
    title          text NOT NULL CHECK (length(trim(title)) > 0),
    description    text,

    type_id        bigint REFERENCES work_item_type(id),
    client_id      bigint REFERENCES client(id),

    -- RULE-006: P0..P4, stored numerically so ordering is meaningful.
    priority       smallint NOT NULL DEFAULT 2 CHECK (priority BETWEEN 0 AND 4),

    -- Denormalized cache of the latest transition. See §4.3.
    state          text NOT NULL DEFAULT 'NEW' CHECK (state IN (
                       'NEW','QUEUED','IN_PROGRESS','ON_HOLD_PREEMPTED',
                       'BLOCKED_ON_CLIENT','IN_VERIFICATION','DONE','CANCELLED')),

    -- RULE-014: client-given, never system-set. Null when none was given.
    due_date       date,

    -- INV-3: required while preempted. INV-4: cannot be itself.
    displaced_by_id bigint REFERENCES work_item(id),

    -- D-011: rejected work becomes a new item linked to the original.
    follow_up_of_id bigint REFERENCES work_item(id),

    created_by_id  bigint NOT NULL REFERENCES person(id),
    created_at     timestamptz NOT NULL DEFAULT now(),

    -- Optimistic locking (D-013).
    version        integer NOT NULL DEFAULT 1,

    CONSTRAINT preempted_names_its_displacer CHECK (
        state <> 'ON_HOLD_PREEMPTED' OR displaced_by_id IS NOT NULL),
    CONSTRAINT displacer_is_another_item CHECK (
        displaced_by_id IS DISTINCT FROM id),
    CONSTRAINT follow_up_is_another_item CHECK (
        follow_up_of_id IS DISTINCT FROM id)
);
```

**`preempted_names_its_displacer` is the most valuable constraint in the schema.**
It makes INV-3 — and therefore BO-4, explaining lateness with evidence —
structurally impossible to violate. Without it, "on hold" degrades into a vague
status meaning nothing, which is exactly what it means in every tool that doesn't
enforce this.

**Everything except `title`, `created_by_id` and `state` is nullable**, and that
is a business decision (BR-002) expressed in DDL. Each `NOT NULL` added here is a
field someone must fill before they can save — and the whole design rests on
saving being effortless.

### 4.3 The one deliberate denormalization

`work_item.state` duplicates information already in `state_transition`. This
breaks normalization knowingly.

**Why:** the most common query in the product — "show the team's open work" — would
otherwise need the latest transition per item on every page load. That is a
correlated subquery or window function over the largest table in the database,
for a screen that loads constantly.

**The cost:** two places can disagree. INV-7 says `state` must always equal the
latest transition's `to_state`.

**How the cost is contained:**

1. All state changes go through one application function that writes the
   transition and updates `state` **in the same transaction**.
2. A trigger (§5.3) blocks direct updates to `state`, so no other code path can
   set it without a transition.
3. A consistency check runs in the test suite and can be run against production:

```sql
-- Must return zero rows.
SELECT w.id, w.state, t.to_state
FROM work_item w
JOIN LATERAL (
    SELECT to_state FROM state_transition
    WHERE work_item_id = w.id
    ORDER BY occurred_at DESC, id DESC
    LIMIT 1
) t ON true
WHERE w.state <> t.to_state;
```

> **When denormalization is acceptable:** when the duplicated value is derivable
> from a single authoritative source, the derivation is enforced in one place, and
> a cheap check can prove they agree. All three hold here. Denormalizing without
> the third — a way to detect drift — is how databases quietly rot.

### 4.4 work_item_participant

```sql
CREATE TABLE work_item_participant (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_item_id  bigint NOT NULL REFERENCES work_item(id),
    person_id     bigint NOT NULL REFERENCES person(id),
    participation text NOT NULL CHECK (participation IN ('OWNER','COLLABORATOR')),

    -- D-012: time-bounded, so ownership history survives reassignment (BR-015).
    from_ts       timestamptz NOT NULL DEFAULT now(),
    to_ts         timestamptz,
    assigned_by_id bigint NOT NULL REFERENCES person(id),

    CONSTRAINT participation_period_ordered
        CHECK (to_ts IS NULL OR to_ts >= from_ts)
);

-- INV-1: at most ONE current owner per work item.
CREATE UNIQUE INDEX one_current_owner_per_item
    ON work_item_participant (work_item_id)
    WHERE participation = 'OWNER' AND to_ts IS NULL;
```

**That partial unique index is worth understanding.** A plain `UNIQUE` on
`(work_item_id, participation)` would be wrong — it would forbid an item from ever
having had two owners *across time*, destroying the history the design exists to
keep. Adding `WHERE ... to_ts IS NULL` restricts uniqueness to *current* rows: any
number of past owners, never two at once.

This makes INV-1 impossible to violate even under concurrent writes, which
application-level checking cannot guarantee — two transactions can both read "no
current owner" and both insert.

`assigned_by_id` records **who** assigned. Per C-007, anyone may assign within
their team, so the mitigation for uncoordinated assignment is that every
assignment is attributable.

### 4.5 state_transition — the substrate

```sql
CREATE TABLE state_transition (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_item_id  bigint NOT NULL REFERENCES work_item(id),

    from_state    text CHECK (from_state IS NULL OR from_state IN (
                      'NEW','QUEUED','IN_PROGRESS','ON_HOLD_PREEMPTED',
                      'BLOCKED_ON_CLIENT','IN_VERIFICATION','DONE','CANCELLED')),
    to_state      text NOT NULL CHECK (to_state IN (
                      'NEW','QUEUED','IN_PROGRESS','ON_HOLD_PREEMPTED',
                      'BLOCKED_ON_CLIENT','IN_VERIFICATION','DONE','CANCELLED')),

    -- When it really happened vs when it was typed in (BR-004).
    occurred_at   timestamptz NOT NULL,
    recorded_at   timestamptz NOT NULL DEFAULT now(),

    changed_by_id bigint NOT NULL REFERENCES person(id),
    displaced_by_id bigint REFERENCES work_item(id),
    note          text,

    CONSTRAINT cannot_record_before_it_happened
        CHECK (occurred_at <= recorded_at),
    CONSTRAINT preemption_transition_names_displacer
        CHECK (to_state <> 'ON_HOLD_PREEMPTED' OR displaced_by_id IS NOT NULL)
);
```

**`occurred_at` vs `recorded_at`** is the schema's answer to R-006. Q3.7 allows
end-of-day catch-up, so a task finished at 11am may be recorded at 6pm. Cycle time
must use `occurred_at`, or a batch of evening updates makes everything look like
it took a day.

The gap between the two is also a **measurable health signal**:

```sql
-- Recording lag. If this grows, derived metrics are drifting (R-006).
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY recorded_at - occurred_at)
FROM state_transition
WHERE recorded_at > now() - interval '30 days';
```

> A system that can measure its own data quality can warn you before it starts
> lying to you. That is BR-020 applied to the system itself.

**`cannot_record_before_it_happened`** catches clock errors and bad backdating.
Note what it *cannot* do: a `CHECK` constraint may not call `now()`, because
constraints must be immutable — PostgreSQL revalidates them at unpredictable
times, and a rule whose truth changes with the clock would corrupt the table.
"`occurred_at` must not be in the future" (INV-12) therefore lives in application
code and the trigger in §5.2.

### 4.6 absence and non_working_day

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE absence (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id     bigint NOT NULL REFERENCES person(id),
    period        daterange NOT NULL,
    kind          text NOT NULL CHECK (kind IN ('LEAVE','HOLIDAY','OTHER')),
    approved_by_id bigint REFERENCES person(id),
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now(),

    -- INV-5: one person's absences must never overlap.
    CONSTRAINT no_overlapping_absence
        EXCLUDE USING gist (person_id WITH =, period WITH &&)
);

CREATE TABLE non_working_day (
    day     date PRIMARY KEY,
    name    text NOT NULL
);
```

**The `EXCLUDE` constraint is PostgreSQL doing work you would otherwise write
badly.** "No two absences for the same person may overlap" is genuinely awkward in
application code — you must query existing rows, compare ranges, and handle the
race where two requests are submitted simultaneously. `EXCLUDE USING gist` states
the rule directly: no two rows may have the same `person_id` (`WITH =`) *and*
overlapping `period` (`WITH &&`). The database enforces it under concurrency.

`daterange` is used rather than two date columns because it makes overlap a
first-class operation. `[start, end)` — inclusive start, exclusive end — is the
PostgreSQL default and avoids the off-by-one errors that plague date ranges.

`non_working_day` holds public holidays; weekends are computed rather than stored.
Per-person working patterns are **not** modelled — nobody asked for them, and
adding them later is additive.

---

## 5. Triggers — rules SQL constraints cannot express

### 5.1 Append-only transitions (INV-2)

```sql
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
```

Every metric in the product is computed from this table. Editing a past
transition silently changes historical measurements — a cycle time that was 3 days
becomes 1 day, and no report shows that it changed. This is not an audit-trail
nicety; it protects every number the system displays.

Application database roles should also be denied `UPDATE`/`DELETE` on this table.
Two independent mechanisms for the one rule that cannot be allowed to fail.

### 5.2 Transitions cannot be dated into the future (INV-12)

```sql
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
```

The one-minute tolerance absorbs harmless clock skew between the application
server and the database rather than rejecting legitimate writes.

### 5.3 `state` may only change alongside a transition (INV-7)

```sql
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
```

The transition service sets `app.transition_in_progress` for the duration of its
transaction. Any other code path — including a manual `UPDATE` — is rejected.

This keeps the §4.3 denormalization honest: `state` cannot drift, because there is
exactly one way to change it.

### 5.4 What is *not* enforced in the database

Stated plainly, because unstated gaps become assumed guarantees.

| Rule | Why the database cannot do it | Where it lives |
|---|---|---|
| INV-8 — only legal transitions | Needs the state machine; a CHECK over `from_state`/`to_state` pairs is possible but would duplicate logic that must live in code anyway, and drift from it | Application: one transition service |
| INV-4 — no displacement *cycles* | Recursive check; a constraint cannot traverse the graph | Application, on write |
| Hierarchy cycles (A→B→A) | Same | Application, on write |
| RULE-013 — minimum sample before forecasting | A query-time rule, not a storage rule | `FlowStatisticsService` |

> **The discipline that makes this safe:** each of these has exactly one code path
> that can perform the operation. INV-8 is enforceable in code only because the
> §5.3 trigger guarantees there is no other way to change state.

---

## 6. Indexes, each justified by a query

At ~10 developers producing perhaps a few thousand items a year, this database is
small — every table would fit in memory for years. **These indexes are about
designing correctly, not about current performance need.** Adding them later is
easy; the value now is knowing which queries the schema must serve.

| Index | Query it serves |
|---|---|
| `work_item_participant (person_id) WHERE to_ts IS NULL` | "What does this person currently hold?" — the load calculation, run on every board render |
| `work_item (state) WHERE state NOT IN ('DONE','CANCELLED')` | The team board — open work only. Partial, because closed items grow without bound and are never on the board |
| `state_transition (work_item_id, occurred_at DESC)` | Latest transition per item — staleness detection, and the INV-7 consistency check |
| `state_transition (to_state, occurred_at)` | Throughput and cycle-time statistics by period |
| `work_item (client_id) WHERE state NOT IN ('DONE','CANCELLED')` | Open work per client (BR-019) |
| `work_item (due_date) WHERE due_date IS NOT NULL AND state NOT IN ('DONE','CANCELLED')` | At-risk detection (BR-017) — only open items with a date can be at risk |
| `absence USING gist (person_id, period)` | Created automatically by the EXCLUDE constraint; also serves "who is away next week?" |

> **Why so many are partial.** `DONE` and `CANCELLED` items will eventually be
> most of the table and are never wanted by the screens people use daily. A
> partial index stays small and stays in memory. This is the single highest-value
> indexing habit in a system with an ever-growing history table.

---

## 7. Seed data

The system must work immediately after installation, with no configuration
(BR-021, CON-5). Migrations therefore seed:

| Table | Seeded with |
|---|---|
| `role` | Developer, QA, Team Lead, Manager, Admin — QA at `DEVELOPER` permission level plus verification rights |
| `work_item_type` | Bug, Change Request, Observation, Support, Other |
| `team` | A single "Default" team, so nobody must create one before recording work |
| `non_working_day` | Empty — holidays are country-specific and added when known |

`Other` exists so that classification is never a barrier to recording. Under D-005
a person must be able to save an item without deciding what kind it is.

---

## 8. Migrations

**Alembic**, one migration per change, checked in with the code that needs it.

Rules:

1. **Never edit an applied migration.** Once it has run anywhere, it is history.
   Fix forward with a new one.
2. **Every migration has a `downgrade`** — even if it only drops what was added.
   Writing it forces you to notice destructive changes.
3. **Data migrations are separate from schema migrations.** Mixing them makes
   failures hard to reason about and rollbacks unsafe.
4. **Adding a `NOT NULL` column to a populated table is three migrations:** add
   nullable → backfill → add the constraint. Doing it in one locks the table and
   fails on existing rows.

Initial migration sequence:

| # | Contents |
|---|---|
| 001 | Extensions (`btree_gist`), reference tables, seed data |
| 002 | `person`, `absence`, `non_working_day` |
| 003 | `work_item`, `work_item_participant`, `state_transition` |
| 004 | Triggers and functions |
| 005 | Indexes |

Splitting them this way means a failure is traceable to one concern.

---

## 9. Invariant coverage

The scorecard for this document: which business rules the database itself refuses
to break.

| Invariant | Enforced by | Where |
|---|---|---|
| INV-1 one current owner | **Database** | Partial unique index §4.4 |
| INV-2 transitions append-only | **Database** | Trigger §5.1 + role grants |
| INV-3 preempted names displacer | **Database** | CHECK §4.2, §4.5 |
| INV-4 no self-displacement | **Database** | CHECK §4.2 |
| INV-4 no displacement cycles | Application | §5.4 |
| INV-5 no overlapping absences | **Database** | EXCLUDE §4.6 |
| INV-6 cannot leave NEW unowned | Application | Transition service |
| INV-7 state mirrors latest transition | **Database** (guard) + application (write) | Trigger §5.3, check §4.3 |
| INV-8 only legal transitions | Application | Transition service |
| INV-9 DONE/CANCELLED terminal | Application | Transition service |
| INV-10 items never deleted | **Database** | No delete path; grants |
| INV-11 people never deleted | **Database** | `active` flag; grants |
| INV-12 occurred_at not future | **Database** | Trigger §5.2 |

**Nine of thirteen are enforced by the database itself.** The four that are not
all require traversing a graph or applying a state machine, which SQL constraints
genuinely cannot express — and each is reachable through exactly one code path,
which is what makes application enforcement trustworthy here.

---

## 10. What is deliberately not done

| Not done | Why |
|---|---|
| Table partitioning | `state_transition` might reach ~50k rows in five years. Partitioning solves a problem two orders of magnitude away |
| Materialized views for metrics | Compute directly first. Add caching when a real query is measurably slow, not before |
| Full-text search on titles | `ILIKE` is fine at this volume. Add `tsvector` when it isn't |
| Audit columns on every table | `state_transition` already records the history that matters. Blanket audit columns add noise |
| Soft-delete flags on work items | `CANCELLED` is a real state with business meaning; a `deleted` flag would be a second, weaker way to say the same thing |
| Separate read replicas, connection pooling beyond defaults | Fifteen users |

> Each of these is a legitimate technique that would be right at a different
> scale. Applying them now would add operational complexity nobody can justify —
> and every one of them is straightforward to add when a measurement, rather than
> a worry, calls for it.

---

## 11. Open items

| ID | Question | Impact |
|---|---|---|
| **OPEN-2** | Who sets priority; does P0 auto-preempt? | None on schema — `priority` exists either way. Affects the transition service |
| **OPEN-3** | Group work by product as well as client? | Additive — a `product` table and a nullable FK |
| **OPEN-4** | ~~Default normal load~~ | **CLOSED** — 3, tuned per person after four weeks (§4.1) |
| **OPEN-5** | Does every item pass through verification? | None on schema. A per-type rule in the transition service if mandatory |

---

## 12. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-15 | Initial design from domain model v1.2. OPEN-4 closed |
