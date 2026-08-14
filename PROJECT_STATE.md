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

Round 1 complete. **Round 2 — Work, People & Authority** is open, awaiting
answers. It re-asks what Round 1 left open and confronts the adoption question.

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

## ASSUMED (must be validated)

- A-001: ~~There is a real organization~~ → **CONFIRMED** as K-006.
- A-002: Work is Projects → Tasks — **WEAKENED.** Looks queue-shaped. Re-tested
  as Q2.3.
- A-003: Managers assign top-down — provisionally supported (verbal assignment).
  Re-tested as Q2.6.
- A-004: Effort is estimable — **NOT SUPPORTED.** No estimation happens today;
  it must be introduced as a new habit.
- A-005: This system owns tasks — **provisionally CONFIRMED**, because there is
  no existing system of record to mirror.
- A-006 (new): Someone in management will support and mandate this. **Unverified
  and load-bearing.** Q2.8.

## UNKNOWN

- U-002: Team size, number of clients/products, planning horizon. (Q2.5)
- U-006: Organization scale by role. (Q2.5)
- U-007: Who has authority to mandate use. (Q2.8)
- U-008: What developers gain from using it. (Q2.7)
- U-009: Whether requests are recorded anywhere at all today. (Q2.1)
- U-010: What decisions management actually makes weekly — the proxy stakeholder
  does not know. Needs a real manager. (Round 3)

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

## REJECTED

- (none yet)

## OPEN QUESTIONS

Round 2 deck: `docs/discovery/round-02-cards.html`. Twelve questions, four
marked as pivots.

## KNOWN ISSUES / RISKS

- R-001: Scope in the initial brief is very large. Mitigated by D-004 (wedge).
- R-002: ~~SoR conflict with Jira/ADO~~ → **CLOSED.** No existing system of
  record exists, so there is nothing to mirror or conflict with. Revisit only if
  the organization adopts Jira later.
- R-003: **Adoption risk — now the top risk.** New habit, stakeholders who did
  not request the system, an organization that tracks nothing today. Engineering
  quality cannot compensate. Every design decision should be weighed against
  "does this make recording cheaper or more expensive?"
- R-004: **Proxy stakeholder risk.** Our only business source is not the end
  user and has said they don't know how management decides. Requirements traced
  only to this source are marked TO VALIDATE until a real manager confirms them.

---

## NEXT ACTION

1. Answer Round 2 (`docs/discovery/round-02-cards.html`).
2. In parallel, and more valuable than any answer in the deck: get 30 minutes
   with one real manager. Question set to be provided.
3. Then Round 3 — defining what a "task" is in this organization, which is the
   precondition for the domain model.
