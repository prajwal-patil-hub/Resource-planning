# ADR-002 — Ship fixed roles on an extensible role table

**Status:** ACCEPTED
**Date proposed:** 2026-08-14
**Date accepted:** 2026-08-15 — stakeholder approved without amendment
**Related:** C-004, R-005, K-017, K-018, Q3.12

---

## Context

The stakeholder has asked three separate times for configurable hierarchy and
permissions (Q2.6, Q2.10, Q2.11), and in Q3.12 declined to choose fixed roles,
adding that they want to add extra roles and place them within the hierarchy,
with the details "decided during the project phases".

The same stakeholder stated in Q2.8 that the product must not be time-consuming
or hard to manage — the condition on which they intend to pitch it to their
manager.

These pull in opposite directions (contradiction C-004). A configurable
permission system must be configured before anyone can use anything, and that
setup cost lands on the very person whose approval the project depends on.

Scale context: 10 developers plus QA, BA and management (K-025). One
organization, not a multi-tenant product (K-006).

**The underlying trade-off:** configurability is deferred decision-making. It
costs roughly 3–5× a fixed rule — the rule, plus storage for it, plus an editing
UI, plus validation, plus testing every combination. That price is worth paying
when you have many customers who each need different behaviour. With one
organization of this size, there is no second customer to be flexible for.

However, "headcount varies" (K-025) and the org is genuinely evolving, so a
design that makes adding a role *impossible* would also be wrong.

---

## Decision

**Store roles as data in a table, seeded with four roles. Attach permissions to
role in code, not in the database, for version one.**

Seeded roles: **Developer, Team Lead, Manager, Admin.**

This splits the request in two and grants the cheap half immediately:

| Capability | v1 | Why |
|---|---|---|
| Add a new role (e.g. "QA Lead", "BA") | **Yes** — insert a row | Cheap. Roles are reference data, like work types (K-021) |
| Place a role in the reporting hierarchy | **Yes** | Hierarchy is already editable — who reports to whom |
| Edit which permissions a role has, from a UI | **No** — deferred | This is the expensive part and nobody has yet needed it |
| Delegate permission-granting downward | **No** — deferred | Requested in Q2.10 but no concrete case given |

A new role added in v1 inherits a permission set chosen from the four built-in
levels. That covers "add a QA Lead who sees what a Team Lead sees" — which is
the realistic near-term need — without building a permission editor.

---

## Options considered

### Option A — Four hardcoded roles, no role table

- **For:** simplest possible; fastest to build.
- **Against:** adding "QA Lead" later needs a code change and a migration. The
  stakeholder has explicitly said the org changes shape. Too rigid.
- **Verdict: rejected.**

### Option B — Full configurable permission engine

Roles, permissions, grants, delegation, all editable at runtime.

- **For:** exactly what was asked for; never blocked by a missing rule.
- **Against:** several weeks of work before a single useful screen exists;
  requires setup before first use, directly violating the Q2.8 constraint; the
  most complex part of the product would be the part serving 10 people who all
  know each other. Highest-cost answer to the least-evidenced need.
- **Verdict: rejected for v1.**

### Option C — Roles as data, permissions in code *(chosen)*

- **For:** grants the frequently-requested half (add roles, place them in the
  hierarchy) at near-zero cost; defers the expensive half until a real case
  appears; leaves a clean seam — the permission engine can later read from the
  database without changing anything that calls it.
- **Against:** does not fully satisfy the stated request. Changing what a role
  may *do* still needs a developer.
- **Verdict: chosen.**

---

## Consequences

**Positive**

- No configuration required before first use. The system works the moment it is
  installed, which is the condition the pitch depends on.
- Adding a role is a row, available immediately.
- The seam is identified in advance: permission checks go through one module, so
  moving permissions from code to database later is a contained change, not a
  rewrite.

**Negative**

- Changing a role's permissions requires a code change in v1.
- Delegated permission-granting (Q2.10) is not available.
- This does not match what was asked for, and the stakeholder may reject it.

**Neutral**

- Default visibility remains team-level (K-018) regardless of this decision.

---

## Revisit this decision if

- A real case appears where two people with the same role need different
  permissions
- The product is ever offered to a second organization — at which point
  configurability stops being deferred decision-making and becomes a genuine
  requirement
- Permission changes start being requested more than roughly once a month
