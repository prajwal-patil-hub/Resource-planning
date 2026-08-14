# PROJECT STATE

> Single source of truth for "where are we and why". Read this first at the
> start of every session. Keep it short — detail belongs in `/docs`.

**Last updated:** 2026-08-14
**Working name:** Resource Planning (developer workload & capacity platform)

---

## CURRENT PHASE

**Phase 0 — Product Discovery**

No coding. No architecture. No BRD yet.
We are interviewing to understand the business before anything else.

## CURRENT OBJECTIVE

Complete **Discovery Round 1: Problem & Business Objective**.
Establish what problem is really being solved, for whom, and what "better"
looks like in measurable terms.

---

## WHAT WE KNOW (KNOWN)

Sourced only from the initial project brief. Nothing validated yet.

- K-001: The intended product helps managers answer questions about developer
  workload, capacity, availability, assignment feasibility, and delivery risk.
- K-002: Deterministic business logic must own capacity/ETA/scheduling.
  AI is an interpretation and interaction layer only, never the source of truth.
- K-003: Preferred starting stack (subject to change if discovery contradicts it):
  Python + FastAPI, PostgreSQL, SQLAlchemy, Alembic, Next.js + TypeScript,
  Docker Compose, pytest, modular monolith.
- K-004: Explicitly out of scope for now: Kubernetes, Kafka, microservices,
  Redis, GraphQL — unless a demonstrated requirement justifies them.
- K-005: Integrations named as *eventual* (not initial): Jira, Azure DevOps,
  GitHub/GitLab, Google Calendar, Outlook, Slack/Teams, HR/leave systems.

## WHAT IS ASSUMED (ASSUMED — must be validated)

- A-001: There is a real organization with real managers who will use this.
  *Not yet confirmed — may be a learning/portfolio project.*
- A-002: Work is organized as Projects → Tasks. Real orgs may use epics,
  sprints, tickets, support queues, or no formal structure at all.
- A-003: Managers assign work to developers (top-down), rather than developers
  self-selecting work from a backlog.
- A-004: Effort is estimable in hours or days with useful accuracy.
- A-005: This system will *own* task data rather than mirror it from Jira/ADO.
  This is the single highest-impact unvalidated assumption.

## WHAT IS UNKNOWN (UNKNOWN)

- U-001: Is this a single-organization internal tool or a multi-tenant product?
- U-002: Team size, number of projects, planning horizon.
- U-003: How planning is done today and what specifically breaks.
- U-004: Whether the primary pain is *visibility* (who is on what) or
  *decision support* (who should take this) or *forecasting* (when will it ship).
- U-005: What success would be measured by.

## DECIDED

- D-001: Business-first sequence. Technology decisions are deferred until
  requirements justify them.
- D-002: Documentation lives in `/docs`; running context lives here.

## REJECTED

- (none yet)

## OPEN QUESTIONS

Tracked in `docs/discovery/00-discovery-log.md` — Round 1 is open and awaiting
answers.

## KNOWN ISSUES / RISKS

- R-001: Scope in the initial brief is very large (planning + integrations + AI).
  Risk of building broad and shallow. Discovery must find the narrow wedge.
- R-002: If an existing tool (Jira/ADO) already owns tasks, this product may be
  a *planning layer* rather than a *tracking system*. That changes the entire
  data model. Must be resolved before the domain model.

---

## NEXT ACTION

Answer Discovery Round 1 questions in
`docs/discovery/00-discovery-log.md` (or in conversation).
Then: summarize → challenge → Round 2 (Users & Stakeholders).
