# Backend — Resource Planning

Feature 1: **record a work item**, built as a vertical slice — database,
business logic, API, UI, tests.

## Running it

```bash
docker compose up -d db                  # PostgreSQL 16
pip install -r requirements.txt
alembic upgrade head                     # schema + seed data
uvicorn app.api:app --reload             # http://127.0.0.1:8000
```

`DATABASE_URL` overrides the connection string; the default targets the
compose service above.

No configuration step exists by design (BR-021). Migrations seed five roles,
five work types and a default team, so the app is usable the moment it starts.

## Tests

```bash
pytest
```

Tests run against a **real PostgreSQL database**, not SQLite. That is not
fussiness — roughly half the invariants in this system are enforced by
PostgreSQL features SQLite does not have: partial unique indexes, `EXCLUDE`
constraints, `daterange`, and plpgsql triggers. Testing against SQLite would
test a different system, and pass while the real one was broken.

The suite creates and drops `resource_planning_test` itself.

## Layout

```
app/
  config.py          settings, with defaults that work unconfigured
  db.py              session per request; one transaction per aggregate change
  models.py          SQLAlchemy models mirroring docs/08-domain-model.md
  work/
    lifecycle.py     the state machine — one definition, used everywhere
    service.py       the ONLY code path that may change state
  flow/
    load.py          load in items, not hours (ADR-001)
    timeline.py      time-in-state report (ADR-003)
  web/               templates and the glass design system (ADR-004)
  api.py             HTTP API and server-rendered pages
alembic/versions/
  001_initial_schema.py        tables and constraints
  002_triggers_indexes_seed.py triggers, indexes, seed data
```

## Where the rules live

The guiding principle from `docs/11-database-design.md`: **a rule enforced only
in application code will eventually be broken**, because there is always a
second code path — a script, a data fix, a manual `UPDATE`. Nine of the domain
model's thirteen invariants are therefore enforced by the database itself.

| Rule | Enforced by |
|---|---|
| At most one current owner per item | Partial unique index |
| State transitions are immutable | Trigger + role grants |
| Preempted work must name what displaced it | `CHECK` constraint |
| Absences cannot overlap | `EXCLUDE USING gist` |
| `state` may only change with a recorded transition | Trigger |
| Field changes are captured | Trigger (cannot be bypassed) |
| Only legal transitions | `app/work/lifecycle.py` |
| No displacement cycles | `app/work/service.py` |

The four in application code all require traversing a graph or applying a state
machine, which SQL constraints genuinely cannot express. Each is reachable
through exactly one function — which is what makes application enforcement
trustworthy here.

## Two things to know before changing anything

**`state_transition` is append-only and load-bearing.** Every number the product
shows is computed from it. A trigger blocks `UPDATE` and `DELETE`. Editing
history would silently change past measurements, and no report would reveal it.

**`occurred_at` is not `recorded_at`.** Work can be recorded after the fact
(BR-004), so all elapsed-time arithmetic uses `occurred_at`. Using `recorded_at`
makes a batch of end-of-day updates look like everything took a day. The gap
between the two is itself reported as a data-quality signal.

## Authentication

First run has no users, so `/` sends you to `/setup` to create the first
administrator. That screen closes permanently once anyone can sign in — there is
still no configuration step (BR-021).

Two design points worth knowing:

**Sessions are rows in `user_session`, not self-contained signed cookies.** A
signed cookie cannot be revoked, so deactivating someone would leave their
access working until it expired. For a product whose entire value is an accurate
record of who did what, that is the wrong trade. Only a hash of the session token
is stored, so a database leak does not hand over live sessions.

**Permissions live in `app/access.py`**, per ADR-002 — one matrix, one `can()`
function. Moving them into the database later changes that file and nothing that
calls it.

Set `COOKIES_SECURE=1` in production or the session cookie travels in clear text.

## Known gaps

- Cross-team assignment is not yet enforced at the point of assignment (the
  permission exists and is checked for visibility, not for the assign action).
- No password reset by email — an admin resets it from `/people`.
