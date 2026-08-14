# PROJECT STATE

> Single source of truth for "where are we and why". Read this first at the
> start of every session. Keep it short — detail belongs in `/docs`.

**Last updated:** 2026-08-14
**Working name:** Resource Planning (developer workload & capacity platform)

---

## CURRENT PHASE

**Phase 0 — Product Discovery**

No coding. No architecture. No BRD yet.

## CURRENT OBJECTIVE

Rounds 1 and 2 complete. **Round 3 — Work Items, Effort & Scope** is open and is
intended to be the final discovery round. It defines the work item precisely
enough to build a domain model.

---

## WHAT WE KNOW (KNOWN)

- K-001: The product helps managers understand developer workload, capacity,
  availability, assignment feasibility and delivery risk.
- K-002: Deterministic business logic owns capacity/ETA/scheduling. AI is an
  interpretation layer only, never the source of truth.
- K-003: Preferred starting stack (unchanged, still provisional): Python +
  FastAPI, PostgreSQL, SQLAlchemy, Alembic, Next.js + TypeScript, Docker
  Compose, pytest, modular monolith.
- K-004: Out of scope for now: Kubernetes, Kafka, microservices, Redis, GraphQL.
- K-005: Integrations (Jira, ADO, calendars, Slack, HR) are *eventual*, not
  initial. Round 1 makes them less urgent still — there is nothing to integrate
  with yet.
- K-006: Single organization. Roles present: developers, testers, BA,
  management.
- K-007: **No current tool, no current process.** Work is assigned verbally;
  nothing is tracked. This is process creation, not digitization.
- K-008: Work arrives **reactively** — client CRs, bug reports, emails — not as
  pre-planned project tasks.
- K-009: Effort is neither estimated up front nor recorded afterwards today.
- K-010: The requester is a developer building this for management on their own
  initiative. Management has not asked for it.
- K-011: Intake is email plus verbal escalation for urgent items.
- K-012: **Developers author the work records themselves**, and an item may be
  created unassigned. Materially reduces the adoption risk.
- K-013: A work item may have **multiple assignees** (many-to-many).
- K-014: Work types are user-extensible at runtime — reference data, not an enum.
- K-015: **Team Lead is the primary day-one user** — they are who notices stalled
  work today.
- K-016: Delay mechanism: unplanned client bugs and CRs displace planned work.
- K-017: Hierarchy controls permissions, not just display.
- K-018: Default visibility is team-level.

## ASSUMED (must be validated)

- A-001: ~~There is a real organization~~ → **CONFIRMED** as K-006.
- A-002: Work is Projects → Tasks — **REJECTED as the primary shape.** Q2.3
  confirms a mix weighted toward reactive client bugs and CRs. The model must be
  queue-first, with grouping by client/project as a secondary concern.
- A-003: Managers assign top-down — **REVISED.** Q2.2 says developers create the
  records; assignment is a separate later act. Creation and assignment are two
  distinct events, not one.
- A-004: Effort is estimable — **NOT SUPPORTED.** No estimation happens today;
  it must be introduced as a new habit.
- A-005: This system owns tasks — **provisionally CONFIRMED**, because there is
  no existing system of record to mirror.
- A-006: Someone in management will support and mandate this. **Still unverified
  and load-bearing** — the pitch has not happened yet.
- A-007 (new): Estimates and actual effort will be entered often enough to
  compute on. **Unverified and load-bearing** — every capacity, availability and
  ETA feature depends on it. Tested by Q3.6.

## UNKNOWN

- U-010: What decisions management actually makes weekly — the proxy stakeholder
  does not know. Needs a real manager, not another question to us.
- U-011: Whether work types need different fields/steps or only different
  labels. Decides whether the model is one table or several shapes. (Q3.2)
- U-012: What "multiple people on a task" means, and how load is attributed
  among them. (Q3.3, Q3.4)
- U-013: Whether effort data will realistically ever be entered. (Q3.6)
- U-014: Real headcount by role and number of clients. (Q3.10)

## DECIDED

- D-001: Business-first sequence. Technology deferred until requirements justify
  it.
- D-002: Documentation lives in `/docs`; running context lives here.
- D-003: **Visibility before decision support.** The stated goal (help managers
  decide who takes work) depends on data that does not exist. We build the
  record-keeping layer first, because everything else is computed from it.
  Rationale in `docs/discovery/00-discovery-log.md`, contradiction C-001.
- D-004: **Recommended wedge — the Work Register.** Every piece of work has a
  name, an owner, a status and a date, on one shared screen, with stale items
  and absent owners flagged. Directly addresses F-001..F-004. **Awaiting
  confirmation.**
- D-005: **Creating a work item must be near-instant** — a title alone must be
  enough to save it, with everything else optional and addable later. Follows
  from K-012: developers author records, so friction at creation destroys the
  data the whole system computes on.

## REJECTED

- (none yet)

## OPEN QUESTIONS

Round 3 deck: `docs/discovery/round-03-cards.html`. Twelve questions, four
pivots. Q3.6 (will effort data ever be entered?) gates every computational
feature in the product.

## KNOWN ISSUES / RISKS

- R-001: Scope in the initial brief is very large. Mitigated by D-004 (wedge).
- R-002: ~~SoR conflict with Jira/ADO~~ → **CLOSED.** No existing system of
  record exists, so there is nothing to mirror or conflict with. Revisit only if
  the organization adopts Jira later.
- R-003: **Adoption risk — downgraded to moderate** by K-012. Developers author
  records as a byproduct of receiving work, rather than managers chasing them for
  data. Still governs design: every decision is weighed against "does this make
  recording cheaper or more expensive?" See D-005.
- R-004: **Proxy stakeholder risk.** Our only business source is not the end
  user and has said they don't know how management decides. Requirements traced
  only to this source are marked TO VALIDATE until a real manager confirms them.
- R-005: **Over-specification for scale.** Configurable permissions,
  drag-and-drop hierarchy and delegated visibility rights are being requested for
  a ~10-person team, while the same stakeholder requires the product not be
  time-consuming to manage (contradiction C-004). The cost is not only build
  time — the setup burden lands on the very manager whose buy-in the project
  depends on. Resolution proposed in Q3.12.

---

## NEXT ACTION

1. Answer Round 3 (`docs/discovery/round-03-cards.html`) — final discovery round.
2. Still outstanding and still the highest-value action available: 30 minutes
   with one real manager, to close U-010 and verify A-006.
3. Then Phase 1 — the Business Requirements Document, with numbered traceable
   requirements derived from the discovery log.
