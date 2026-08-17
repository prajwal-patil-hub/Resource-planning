# PROJECT STATE

> Single source of truth for "where are we and why". Read this first at the
> start of every session. Keep it short — detail belongs in `/docs`.

**Last updated:** 2026-08-16
**Working name:** Resource Planning (developer workload & capacity platform)

---

## CURRENT PHASE

**Phase 4 — Implementation.** Features 1–7 built and running. 180 tests.

## CURRENT OBJECTIVE

Reference data management (BR-023, BR-024) — adding a client or work type still
needs SQL, and the new client report is only as good as whether items carry a
client at all.

**Status:** 180 tests passing against real PostgreSQL 16. ~96% of v1 scope;
**every business requirement is built**, 2 partially. All six business
objectives BO-1..BO-6 are met. Full audit in `docs/14-build-status.md`.

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
- K-028: The organization has **one manager**, who does managerial allocation.
  Withdraws the brief's "two managers assign simultaneously" edge case.
- K-029: **Anyone recording work may assign it** (C-007, resolved). Assignment is
  not reserved to the manager. Uncoordinated assignment is mitigated by
  visibility and attribution, not by permission.
- K-030: **Exactly one accountable owner per item, always.** Others working on
  it are collaborators, working under the owner (stakeholder, 2026-08-15).

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
- ~~OPEN-7 / C-007~~ → **RESOLVED 2026-08-15.** Anyone may assign within their
  team. BRD role matrix corrected. Cross-team assignment stays restricted
  (TO VALIDATE).
- ~~OPEN-4~~ → **CLOSED.** `normal_load` defaults to 3, tuned per person after
  four weeks of history.
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
- D-014: **`state` is deliberately denormalized** onto `work_item`, guarded by a
  trigger so it can only change alongside a recorded transition, plus a
  consistency query that proves it has not drifted.
- D-015: **Fixed lists are CHECK constraints; extensible lists are tables.**
  States are fixed (adding one changes behaviour); work types are extensible
  (adding one changes only data).
- D-016: **ADR-003 — the audit trail is the product, not a byproduct.** Three
  layers: state history, field history (captured by trigger so no code path can
  miss it), ownership history. **ACCEPTED.**
- D-017: **ADR-004 — frosted glass over a swappable background.** One CSS
  custom property (`--app-background`) controls the background; everything else
  reads from tokens. **ACCEPTED.**
- D-018: Elapsed time anchors on the **first event's `occurred_at`**, never the
  row's `created_at`. Backdated items otherwise compute negative durations.
- D-019: **Composer docked at the bottom**, not the top. Recording is the
  behaviour every metric depends on, so it sits where the hands already are.
- D-020: **Two views of one dataset** — Board (queue-shaped, for triage) and
  Table (row-per-item with sortable columns, for scanning and comparison).
  Same data, same composer; only the presentation differs.
- D-021: **Glass values are extracted, not eyeballed.** The reference
  tutorial's three inset shadows are used verbatim in geometry, with alpha
  scaled per surface size — full strength on small cards washes out text.
  Method and fidelity ledger in `docs/13-ui-extraction-prompt.md`.
- D-022: **Team filter resolves through the OWNER's team.** A work item has no
  team of its own; giving it one would be a second place for the same fact to
  live and drift.
- D-023: **Unowned work is never hidden by the team filter.** It belongs to no
  team, so filtering would make it vanish — recreating F-001, the exact problem
  the product exists to prevent. A filter that can hide unclaimed work is a bug.
- D-024: **Light theme is a re-lighting, not an inversion.** On a light ground
  white inner glows are invisible; depth comes from soft dark inner shadows plus
  a bright top highlight. Semantic colours are re-tuned for contrast, which is
  why they were kept separate from the glass palette.
- D-025: **Calendar time and working time are both reported, not one or the
  other.** Calendar elapsed is what the client waited; working elapsed excludes
  weekends and holidays and is what we answer for. Reporting only the first
  makes the team look slow; only the second hides how long the client waited.
- D-026: **Lists that demand action must contain nothing else.** The team
  filter never hides unowned work; cover detection never flags client-blocked
  work. Noise destroys the reason either list exists.
- D-027: **Focus mode** — board columns collapse to a left rail and one state
  gets the full width. The board answers "where is everything"; focus answers
  "what is in this column and what do I do about it".
- D-028: **The working week lives in the database, not configuration.** It is a
  business fact the organization owns and must change without a deploy.
  **RESOLVED 2026-08-16:** the team works Saturdays optionally. Sunday is never
  worked; Saturday is an optional day. See D-029.
- D-029: **A day has three states, not two: worked, optional, never.** The team
  works Saturdays sometimes. Counting Saturday as working punishes everyone who
  did not come in; counting it as non-working erases the work of whoever did.
  An optional day counts only on the dates when work was actually recorded —
  **derived from the event log, not asked for** (ADR-001), and resolved per
  person so one person's Saturday never counts against a colleague's.
- D-030: **Timestamp-to-date casts are pinned to UTC.** `occurred_at::date` on a
  timestamptz depends on the session timezone, so it is not immutable, cannot be
  indexed, and would make two differently-configured servers disagree about
  which day work happened on.
- D-031: **Everything on an action list must need action.** The attention view
  excludes client-blocked work from stalled and uncovered, and only flags
  at-risk items while there is still time to act. One item that does not belong
  teaches people to skim, and a list people skim is worse than no list.
- D-032: **Fix the input before building what consumes it.** Backdated recording
  (BR-004) and assign-time context (BR-016) come before forecasting (BR-018).
  Under ADR-001 every number is derived from recorded flow data, so a forecast
  built on systematically wrong timestamps is a confident false answer rather
  than a weak one.
- D-033: **Backdating is bounded, not free** (RULE-016). Up to 14 days back,
  never forward. Past a fortnight a backdated entry is more likely a mistyped
  year than a real catch-up, and one wild timestamp drags an average nobody is
  watching. A refusal is recoverable; a poisoned statistic is not.
- D-034: **The browser reports its timezone offset; the server never guesses
  one.** `datetime-local` submits naive wall-clock text, so reading it as UTC
  would shift every entry from an IST team by five and a half hours and push
  genuine morning entries into the future. No org-timezone setting was added —
  that is configurability standing in for a fact already available (rule 10).
- D-035: **Assignment context states facts and does not rank.** The dropdown
  shows load and absence but keeps alphabetical order and refuses nobody.
  Sorting by spare capacity would turn a fact into an instruction, and blocking
  an absent person would be wrong the first time anyone queued up work for
  someone due back tomorrow.
- D-036: **Scoping rules are enforced at the write, not only in the widget**
  (RULE-017). A filtered dropdown is a convenience; the form beneath it accepts
  any identifier posted to it.
- D-037: **ADR-005 — forecast from percentiles of past work, and refuse below a
  minimum sample.** Median and 85th percentile rather than a mean, because cycle
  times are right-skewed and the mean describes no real case. Nearest-rank, not
  interpolated. Never converted into a date. Nothing offered at all below 8
  comparable finished items. **ACCEPTED 2026-08-16.**
- D-038: **The cohort ladder is walked, and which rung was used is stated.**
  Type-and-priority, then type, then all work; stop at the first with enough
  data. An answer from "Bug at P1" and one from "all finished work" deserve
  different trust, and a reader cannot tell them apart unless told.
- D-039: **A stalled item is not also reported as overrunning.** Both are true
  and the second adds nothing — "nothing has happened for four weeks" already
  explains why it outran its history, and it is the more actionable of the two.
  Two rows saying one thing is the noise D-031 forbids.
- D-040: **No report presents elapsed item time as effort or cost** (RULE-018).
  ADR-001 removed effort data permanently, so "where the work goes" is answered
  in items and duration. Two items open across one week are two item-weeks and
  one week of the team; a percentage beside a client's name is a share of
  demand, never of cost, and the page says so in its own first paragraph.
- D-041: **A measurement may be shown at any sample size; an inference from it
  may not** (RULE-019). "7 of these 12 days were client wait" is true however
  few items there are. "This client is slow" is a claim about their habits and
  needs the sample RULE-013 requires. So the figure always shows and the
  warning colour waits.
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
| `docs/08-domain-model.md` | v1.2 draft — for review |
| `docs/11-database-design.md` | **v1.0 draft — for review** |
| `docs/adr/ADR-003` | Accepted — audit trail and item timeline |
| `docs/adr/ADR-004` | Accepted — glass UI, swappable background |
| `docs/pitch/manager-brief.html` | Ready to use — supports ASM-2 |
| `docs/13-ui-extraction-prompt.md` | Reusable UI extraction prompt + applied spec |
| `backend/` | **Feature 1 implemented — 33 tests passing** |

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

## BUILD COMPLETENESS

**~84% of the v1 BRD scope.** BR-007 and BR-017 now built; BO-2 and BO-3 fully
met. Remaining: BR-018 (probability ranges — needs history) and BR-019
(reporting by client and type). Full requirement-by-requirement audit in
`docs/14-build-status.md`. 11 requirements built, 6 partial, 8 not built.
Five of seven designed domain services are unwritten.

## KNOWN GAPS IN THE BUILD

- ~~No authentication~~ → **BUILT 2026-08-16.** Sessions, password policy,
  lockout, first-run setup, people management, permission matrix.
- Cross-team assignment is not enforced at the point of assignment.
- No self-service password reset — an admin resets from `/people`.
- Background image not chosen — one CSS property, deliberately deferred.
- ~~No absence entry~~ → **BUILT.** Booking, approval, cancellation, cover
  detection, holidays and an editable working week.
- No stalled-work surfacing beyond a flag in the table (BO-2 partial).
- No forecasting or risk detection (BO-6 entirely unmet).
- ~~Weekends and holidays not excluded~~ → **BUILT** (D-025).

## NEXT ACTION

Stakeholder decision recorded 2026-08-16: **the pitch happens once the product
is complete enough to justify a manager's time.** ASM-2 stays open and
load-bearing by informed choice, not oversight.

Ordered build plan in `docs/14-build-status.md`:

1. ~~Edit a work item~~ — **DONE 2026-08-16**
2. ~~Authentication and people management~~ — **DONE 2026-08-16**
3. ~~Absence and non-working days~~ — **DONE 2026-08-16**
4. ~~Attention view~~ — **DONE 2026-08-16** (/attention)
5. ~~Recording context — backdating + assign-time load~~ — **DONE 2026-08-16**
   (BR-004, BR-016, RULE-016, RULE-017)
6. ~~Flow statistics and forecasting~~ — **DONE 2026-08-16**
   (BR-017, BR-018, RULE-009/010/013; ADR-005. Closes BO-6)
7. ~~Reporting by client~~ — **DONE 2026-08-16** (BR-019, RULE-018/019)
8. **Reference data management** ← next (BR-023, BR-024)
9. Search
10. Deployment, backups, restore

Items 1–5 are what a pilot needs. 6–7 are what make it worth keeping.

**Why 5 was promoted above forecasting (D-032).** ADR-001 committed the product
to deriving every number from recorded flow data. A forecast built on timestamps
that are systematically wrong — because someone recording at 6pm stamps 6pm — is
not a weak forecast but a confident false one, which is the failure ADR-001
exists to prevent. Fix the input before building what consumes it.
