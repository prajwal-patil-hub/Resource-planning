# ADR-003 — The audit trail is the product, not a byproduct

**Status:** ACCEPTED
**Date:** 2026-08-15 — requested directly by the stakeholder
**Related:** ADR-001, INV-2, BO-4, BR-020, F-002, F-003, K-020

---

## Context

The stakeholder asked for:

> "audit trails and also a report part where we can see each task took how much
> time and the time stamps and when was it on hold, who worked on it at what
> time and anything that I missed"

In most systems an audit trail is a compliance afterthought — a log nobody reads
until something goes wrong. Here it is the opposite. Under ADR-001 the
`state_transition` table **is** the data source for every metric the product
produces. The audit trail and the product are the same thing viewed from two
angles.

That reframing has a practical consequence: audit completeness is not a
nice-to-have that can be trimmed under time pressure. A missing transition is not
a missing log line — it is a hole in the arithmetic.

---

## Decision

**Every change to a work item is recorded as an immutable event, and the item's
full history is a first-class, user-facing screen — not a debugging tool.**

Three layers:

### Layer 1 — State history (`state_transition`)

Already designed. Records every lifecycle movement with `occurred_at`,
`recorded_at`, who made it, and what displaced it.

### Layer 2 — Field history (`work_item_audit`)

New. State is not the only thing that changes. Priority gets raised, due dates
move, clients reassign, titles get corrected. Each of those changes the meaning of
every metric computed afterwards, and each is a question someone will eventually
ask ("who moved this to P0?").

```
work_item_audit(work_item_id, field, old_value, new_value,
                changed_by, occurred_at, recorded_at)
```

Append-only, same as transitions.

### Layer 3 — Ownership history (`work_item_participant`)

Already designed as time-bounded rows (D-012), which makes "who worked on it at
what time" answerable directly.

---

## The report: time-in-state per item

The stakeholder asked how much time a task took and when it was on hold. Both
derive from Layer 1 by walking consecutive transitions and taking the gaps.

For each item the report gives:

| Measure | Meaning | Why it matters |
|---|---|---|
| **Total elapsed** | Creation → Done | The number the client experiences |
| **Time in each state** | Sum of gaps per state | Where the time actually went |
| **Active time** | Time in `IN_PROGRESS` | The closest honest proxy for effort we have without timesheets |
| **Waiting on us** | `QUEUED` + `ON_HOLD_PREEMPTED` | Delay we caused |
| **Waiting on client** | `BLOCKED_ON_CLIENT` | Delay the client caused — excluded from our accountability (RULE-005) |
| **In verification** | `IN_VERIFICATION` | QA queue time, otherwise invisible |
| **Rework count** | `IN_VERIFICATION → IN_PROGRESS` transitions | Quality signal that costs nothing to collect |
| **Times preempted** | Count of `→ ON_HOLD_PREEMPTED` | How often this was set aside |
| **Displaced by** | The items that preempted it | BO-4 — the evidence for lateness |
| **Owners over time** | Participant rows | Who held it, when, who assigned them |
| **Recording lag** | `recorded_at − occurred_at` | Confidence qualifier on everything above (R-006) |

### Things the stakeholder did not ask for, which the same data gives free

They said "and anything that I missed". These cost nothing extra because the
events are already being recorded:

1. **Time to first touch** — creation → first `IN_PROGRESS`. Directly measures
   F-001 and F-002: how long work sits before anyone starts it. Likely the single
   most actionable number for a team lead.
2. **Rework rate by type and by client** — which clients' requirements arrive
   unclear enough to fail verification.
3. **Preemption chains** — item A displaced B, B displaced C. Shows a cascade of
   disruption from one urgent request, which is invisible today.
4. **Who displaces whose work** — attribution for the pattern, not blame for the
   instance.
5. **Client responsiveness** — average `BLOCKED_ON_CLIENT` duration per client.
   Turns "the client is slow" from a complaint into a number.
6. **Recording lag trend** — whether the data underneath every other figure is
   getting better or worse.

> Every one of these follows from the same event log. This is the compounding
> return on ADR-001: record the events properly once, and questions nobody has
> asked yet are already answerable.

---

## Options considered

### Option A — Log table written by application code

A generic `audit_log` the service writes to alongside each change.

- **For:** simple, familiar.
- **Against:** it is only as complete as the code paths that remember to call it.
  The first developer who writes an `UPDATE` for a data fix creates a permanent,
  invisible hole. For a compliance log that is unfortunate; here it corrupts the
  metrics.
- **Verdict: rejected.**

### Option B — Database triggers capture changes automatically *(chosen)*

A trigger on `work_item` writes field-level changes to `work_item_audit`.

- **For:** cannot be bypassed. Any path that changes the row — application, script,
  manual `psql` — is captured. Given that the audit trail *is* the data source,
  "cannot be bypassed" is the requirement, not a bonus.
- **Against:** logic in the database, which is harder to test and less visible than
  application code. Mitigated by keeping the trigger tiny and testing it directly.
- **Verdict: chosen.**

### Option C — Full event sourcing

Store only events; derive all current state by replay.

- **For:** the purest expression of ADR-001; perfect history by construction.
- **Against:** substantially more machinery — projections, rebuilds, versioned
  event schemas. For fifteen people this is a large tax for a marginal gain over
  Option B, and it would slow the first useful screen by weeks.
- **Verdict: rejected as over-engineering** (working agreement 10).

---

## Consequences

**Positive**

- "Why is this late?" becomes a screen rather than an argument (BO-4).
- Satisfies BR-020 — every derived number can be traced to the events that
  produced it.
- Data-quality is itself measurable via recording lag.
- Six additional insights come free from data already being captured.

**Negative**

- Two more append-only tables that grow forever. At this scale, negligible —
  perhaps 50k rows in five years.
- Trigger logic sits in migrations, so changing what is audited requires a
  migration.
- Field history captures *what* changed, never *why*. An optional note is offered
  on transitions; it must never be mandatory (D-005 — friction).

**Neutral**

- Rows are never deleted, so a person who leaves remains referenced in history.
  Consistent with INV-11.

---

## Revisit if

- Audit tables grow past roughly 10 million rows, where partitioning starts to pay
- A legal or contractual retention requirement appears — none exists today
- Users start asking *why* a change was made often enough to justify making the
  note mandatory, which would have to be weighed against recording friction
