# PROJECT STATE

> Single source of truth for "where are we and why". Read this first at the
> start of every session. Keep it short — detail belongs in `/docs`.

**Last updated:** 2026-08-15
**Working name:** Resource Planning (developer workload & capacity platform)

---

## CURRENT PHASE

**Phase 2 — Domain Model.** Discovery complete, BRD v1.0 drafted, domain model
v1.0 drafted. Still no coding.

## CURRENT OBJECTIVE

Review the domain model (`docs/08-domain-model.md`). Then Phase 3 — database
design, which is a direct translation of it.

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
- K-019: **Effort data will not be entered** — no estimates, no actuals (Q3.6,
  answered pessimistically as asked). The decisive finding of discovery.
- K-020: **Preemption is the core dynamic** — urgent work puts existing work on
  hold or transfers it. The system must record *what displaced what*.
- K-021: All work types share the same fields plus a type column. One work item
  table plus a type reference table. Closes U-011.
- K-022: Items are sometimes **blocked waiting on the client** — distinct from
  being preempted, and must not be merged with it.
- K-023: **Due dates are client-given inputs.** The product answers "will we make
  this date?", not "what date will this be?"
- K-024: Five priority levels, P0–P4.
- K-025: 10 developers, plus QA, BA and management. Headcount varies.
- K-026: Handover and splitting are rare, and happen as a consequence of
  preemption rather than independently.
- K-027: **A QA verification step exists** and is part of the lifecycle. QA also
  receives work directly from clients (Q3.1), so QA is both a verifier and a
  potential owner.
- K-028: **Assignment is centralized — one manager assigns.** Corrects the
  original brief's "two managers assign simultaneously" edge case, which is
  withdrawn. Raises C-007 against Q2.2 and the role matrix.

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
- A-007: Estimates and actual effort will be entered often enough to compute on
  — **REJECTED by K-019.** This invalidates the hour-arithmetic basis of the
  original brief. Superseded by ADR-001.

## UNKNOWN

Tracked as OPEN-1..OPEN-6 in `docs/03-brd.md` §11. Summary:

- ~~OPEN-1: is there a QA step?~~ → **CLOSED 2026-08-15, yes** (K-027).
- OPEN-2: who sets priority; does P0 preempt automatically?
- OPEN-3: should work group by client/product for reporting?
- OPEN-4: starting default for "normal load" per person.
- OPEN-5: does every item pass through verification; can it fail back?
- OPEN-6: what decisions management makes weekly — needs a manager.
- OPEN-7 / C-007: **who may assign work?** K-028 says one manager assigns; Q2.2
  said developers pick an assignee when creating an item; the role matrix lets
  Team Leads assign within team. Working assumption: anyone may take an unowned
  item themselves, but only the manager assigns work *to someone else*.
  Behavioural only — no structural impact. See domain model §13a.
- ~~C-006~~ → **RESOLVED 2026-08-15.** "Record everything by EOD" means the work
  item, not the time spent. ADR-001 unaffected.

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
- D-006: **ADR-001 — derive workload from flow data, not typed effort.**
  Load in items not hours; forecasts from history not estimates; typed effort
  optional enrichment only. Governing principle: *derive, don't ask.*
  **ACCEPTED 2026-08-15.**
- D-007: **ADR-002 — fixed roles on an extensible role table.** Roles are data
  and can be added; per-role permission editing is deferred.
  **ACCEPTED 2026-08-15.**
- D-008: Separate vision, stakeholder and business-process documents **skipped**.
  At this scale they would fragment rather than clarify — their content lives in
  BRD §1–§5. Will be split out only if they grow enough to need it.
- D-009: **Entity is `Person`, not `Developer`.** QA, BA and managers all own
  work (K-027). Role is a relationship, not an identity.
- D-010: **Entity is `WorkItem`, not `Task`.** "Task" implies plan-shaped
  decomposition; this work is queue-shaped (A-002 rejected).
- D-011: **`Done` is terminal.** A client rejecting delivered work creates a new
  linked item rather than reopening the old one — reopening would give a single
  item several cycle times and corrupt every historical metric.
- D-012: **Ownership is time-bounded**, not an `owner_id` field. Preserves
  ownership history through reassignment (BR-015) and covers all three
  multi-person scenarios from Q3.3 with one structure.
- D-013: **Optimistic locking** for concurrent edits to one work item.
  Notably *not* needed for concurrent assignment — nothing is reserved under
  ADR-001, so two assignments simply show as higher load, which is accurate.

## REJECTED

- Hour-based capacity, hour-based availability, hour-level overlap detection, and
  estimate-driven ETA. Not computable without effort data (K-019). Replacements
  defined in `docs/glossary.md` and ADR-001.

## DOCUMENTS

| Document | Status |
|---|---|
| `docs/discovery/00-discovery-log.md` | Complete — 3 rounds |
| `docs/glossary.md` | Living — terms defined before use |
| `docs/adr/ADR-001` | Accepted |
| `docs/adr/ADR-002` | Accepted |
| `docs/03-brd.md` | v1.0 draft — for review |
| `docs/08-domain-model.md` | **v1.0 draft — for review** |
| `docs/pitch/manager-brief.html` | Ready to use — supports ASM-2 |

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
- R-005: **Over-specification for scale.** Configurable permissions and
  delegated visibility rights requested for a ~15-person organization, against
  the same stakeholder's requirement that the product not be time-consuming to
  manage (C-004). Q3.12 was not answered; compromise proposed in ADR-002.
- R-006: **Data substrate risk.** With effort data gone, every derived number
  depends on state transitions being recorded promptly. Q3.7 explicitly permits
  end-of-day catch-up, which skews cycle-time measurement and makes "in progress
  right now" unreliable. Mitigation is a design constraint: every state change
  must be one tap, and EOD catch-up must be treated as normal.

---

## NEXT ACTION

1. **Resolve C-007 — who may assign work.** One sentence closes it. It is the
   only open item with a working assumption currently standing in for an answer.
2. **Pitch it.** Still outstanding. ASM-2 remains the only assumption whose
   failure ends the project, and the only one that costs 30 minutes to test.
3. Answer OPEN-2, OPEN-3, OPEN-5 — none block the database design.
4. Then Phase 3 — database design: tables, keys, constraints, indexes,
   migrations. A direct translation of the domain model.
