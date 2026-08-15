# Discovery Log

Chronological record of the discovery interview: questions asked, answers given,
and what each answer settled or opened up.

Purpose: the conversation is not the source of truth. This file is.
When we later write the BRD, every business requirement should be traceable back
to an answer recorded here.

**Legend**

| Tag | Meaning |
|---|---|
| KNOWN | Stated by the stakeholder and taken as fact |
| ASSUMED | Inferred, not confirmed — must be validated |
| UNKNOWN | Identified gap, not yet asked or not yet answered |
| DECIDED | A choice we have deliberately made |
| REJECTED | A choice we have deliberately ruled out |
| TO VALIDATE | Believed true, needs evidence before we build on it |

---

## Round 1 — Problem & Business Objective

**Status:** ANSWERED — see outcomes below
**Date asked:** 2026-08-14
**Date answered:** 2026-08-14

### Why this round comes first

Every later artifact — requirements, domain model, database, API — is a
consequence of the problem definition. If the problem is stated wrongly, the
architecture will be correct engineering applied to the wrong thing. This is the
most expensive category of mistake in software, and the cheapest to avoid.

### Questions

#### Group A — The problem itself

- **Q1.1** Describe one specific, real occasion when planning went wrong.
  What happened, who was involved, what did it cost?
- **Q1.2** Which is the primary pain — pick one, don't say "all three":
  - (a) **Visibility** — nobody knows who is working on what right now
  - (b) **Decision support** — deciding who should take a new piece of work is slow or wrong
  - (c) **Forecasting** — we cannot say with confidence when work will be done
- **Q1.3** Why does this problem exist? Is it missing data, scattered data,
  stale data, no agreed process, or no time to do the analysis?

#### Group B — Who has the problem

- **Q1.4** Who feels this pain most acutely, by job title, and what do they do today
  when they feel it?
- **Q1.5** Is this for one organization you know, or a product intended for many
  organizations? (Determines whether we build for one workflow or configurable
  workflows — a very large architectural difference.)
- **Q1.6** How many people, teams, and concurrent projects are we planning for?

#### Group C — How it is solved today

- **Q1.7** What tool or artifact holds the plan today — spreadsheet, Jira, whiteboard,
  someone's memory? Describe it concretely.
- **Q1.8** What is the *system of record* for tasks today — where does a task
  officially live? Do you intend to replace that, or sit alongside it?
- **Q1.9** What breaks about the current approach? Be specific: what is slow,
  what is wrong, what is missing, what is manual?

#### Group D — Decisions and success

- **Q1.10** Name the top 3 decisions a manager makes weekly that this system should
  make faster or better.
- **Q1.11** If this works perfectly, what changes in the organization? What would you
  measure to prove it?
- **Q1.12** If we could ship only ONE screen or ONE answer, which one delivers the
  most value on day one?

### Answers (paraphrased, with source question)

| Q | Answer |
|---|---|
| Q1.1 | Work gets forgotten. We don't know what was assigned to whom, how much effort it takes, how to manage hours against tasks, or who covers for someone on leave and how long they'd take. Repeatedly behind schedule. |
| Q1.2 | No option selected. Stated: "mostly (b) decision support, a little (c) forecasting." |
| Q1.3 | Scattered data, lack of tracking, no time for analysis. |
| Q1.4 | Not answered by role. Stated instead: nobody does this today; assignment is manual; there is no tracking of anything. |
| Q1.5 | One organization. Development team, testing team, BA, management above. Wants to define hierarchy and rules, and optionally link people to teams — explicitly flagged as a "very big IF", not a core feature. |
| Q1.6 | No numbers given. Answered with a desired feature instead: define per-project team size, drag-and-drop hierarchy boxes top to bottom, add members by name, assign work later. |
| Q1.7 | No current tool. Considering building a local database; asked for a recommendation. |
| Q1.8 | Question not understood — to be re-asked in plain language as Q2.1/Q2.2. |
| Q1.9 | Work is assigned **verbally** when a client CR, bug report or email arrives. Four distinct failures described (see F-001..F-004 below). |
| Q1.10 | Only one decision named ("communicate orally, ask people to work in an organised manner"). Stated they do not know what decisions management makes; asked for help. |
| Q1.11 | Desired outcome: client pressure stops; managers organise and handle teams better. Asked for help defining measures. |
| Q1.12 | Asked for a recommendation. |

### Failure modes described in Q1.9 (the most valuable material in this round)

| ID | Failure | What it implies the system must do |
|---|---|---|
| F-001 | Task assigned verbally, never recorded, then forgotten | Assignment must produce a durable record |
| F-002 | Person busy on other work, doesn't start it, nobody notices for 2 days | Work needs a status and a staleness signal |
| F-003 | Task actually took 15 minutes, but we only find out the next day | Actual effort must be captured, cheaply |
| F-004 | Assignee goes on leave; client believes work is progressing | Absence must be visible against assigned work |

### Outcomes of this round

**Became KNOWN**

- K-006: Single organization. Roles present: developers, testers, BA, management.
- K-007: **There is no current tool and no current process.** Work is assigned
  verbally. Nothing is tracked. This is not a digitization project — it is a
  process-creation project. Materially riskier and changes the sequencing.
- K-008: Work arrives **reactively** — client change requests, bug reports,
  emails — not as pre-planned project tasks.
- K-009: Effort is not estimated and actuals are not recorded today.
- K-010: The requester is a developer building this *for* management, on their
  own initiative. Management has not asked for it.

**Contradictions surfaced**

- C-001: **Stated pain vs described pain.** Q1.2 selected decision support and
  forecasting. Every failure in Q1.9 (F-001..F-004) is a *visibility and
  tracking* failure. Decision support and forecasting are computed **from** data
  that does not currently exist. Resolution: visibility is the necessary first
  layer; the stated goals are the second and third. Recorded as D-003.
- C-002: Q1.6 asked for scale; the answer described a drag-and-drop hierarchy
  builder. A solution was given in place of the problem. Scale remains UNKNOWN
  and is re-asked as Q2.5.
- C-003: Q1.5 says hierarchy and rules matter, but linking people to teams is a
  "very big IF". These are hard to separate — hierarchy is only meaningful if it
  controls something. Re-asked as Q2.11.

**Assumptions invalidated**

- A-002 (Projects → Tasks) — **weakened.** Work looks queue-shaped, not
  plan-shaped. Re-tested as Q2.3.
- A-004 (effort is estimable) — **not supported.** No estimation happens today.
  Estimates will have to be introduced as a new habit, not captured from
  existing practice.
- A-005 (we own tasks) — **provisionally confirmed**, because there is no
  existing system of record to integrate with. Nothing to mirror.

**New UNKNOWNs**

- U-006: Team and organization size (re-asked Q2.5).
- U-007: Who has authority to mandate use of the system (Q2.8).
- U-008: What developers gain from using it (Q2.7) — the adoption question.
- U-009: Whether requests are recorded anywhere at all today (Q2.1).

**New risks**

- R-003: **Adoption risk, now the top risk.** A system that creates a new habit,
  built for stakeholders who did not request it, in an organization that
  currently tracks nothing. Engineering quality cannot compensate for this.
- R-004: **Proxy stakeholder risk.** Our only source of business truth is not the
  end user and has stated they don't know how management decides. Requirements
  derived solely from this source must be marked TO VALIDATE.

---

## Round 2 — Work, People & Authority

**Status:** ANSWERED — see outcomes below
**Date asked:** 2026-08-14
**Date answered:** 2026-08-14
**Deck:** `round-02-cards.html`

Purpose: re-ask what Round 1 left open (scale, system of record) in plainer
language, test the two invalidated assumptions (queue vs plan), and confront the
two risks that now outrank everything technical — adoption and authority.

| Q | Topic |
|---|---|
| Q2.1 | Where a client CR or bug gets written down today *(pivot)* |
| Q2.2 | Who would type work into our system, and when |
| Q2.3 | Planned work vs reactive queue *(pivot)* |
| Q2.4 | Kinds of work, and which are worth tracking |
| Q2.5 | Real numbers: people per role, clients/products |
| Q2.6 | Who hands out work, and whether anyone can assign to anyone |
| Q2.7 | What a developer gains from the system *(pivot)* |
| Q2.8 | Who can mandate use, and whether they want it *(pivot)* |
| Q2.9 | Who notices today when a task stalls |
| Q2.10 | Whether developers may see each other's workload |
| Q2.11 | Whether hierarchy controls permissions or is display only |
| Q2.12 | What the analyst has misunderstood |

### Answers (paraphrased)

| Q | Answer |
|---|---|
| Q2.1 | Requests arrive by **email**, or **verbally** when urgent. Nothing structured. |
| Q2.2 | **Developers themselves** create the record. A work item can be created **unassigned**. Assignment via a dropdown of people, with an "add new member" option. **Multiple people can be selected.** |
| Q2.3 | (c) Genuine mix — but qualified: "mostly new bugs or CRs rather than planned". Clients overload the team with bugs and CRs, "hence the time delays". |
| Q2.4 | All kinds exist. Work types must be **user-extendable** (e.g. add "BA work" later). |
| Q2.5 | "Around 10" — ambiguous, re-asked as Q3.10. |
| Q2.6 | Deflected to desired feature: configurable hierarchy controlling who can access and assign what. Current practice still unstated. |
| Q2.7 | "Tracking bugs and time management." |
| Q2.8 | No mandate yet — will **pitch to their manager**. Stated constraint: it must not be time-consuming to manage, nor hard to access and manage. |
| Q2.9 | The **team lead** or someone more senior notices. |
| Q2.10 | (c) Team-level, with the ability for the highest role to adjust who sees what and delegate that power downward. |
| Q2.11 | (a) Hierarchy controls permissions. |
| Q2.12 | Not sure yet. |

### Outcomes of this round

**Became KNOWN**

- K-011: Intake is email plus verbal escalation for urgent items. No structured
  intake exists.
- K-012: **Developers are the intended authors of work records**, not managers.
  Work items can exist in an unassigned state before anyone owns them.
- K-013: A work item may have **multiple assignees**. Person↔WorkItem is
  many-to-many, not a single owner field.
- K-014: Work types must be extensible by users at runtime — a reference table,
  not a fixed enum in code.
- K-015: The **Team Lead is the person who notices stalled work today**, making
  them the primary user of the day-one product, ahead of "management".
- K-016: The delay mechanism is now explicit: **unplanned client bugs and CRs
  displace planned work.** This is the causal story behind Round 1's F-002.
- K-017: Hierarchy is intended to control permissions, not merely display.
- K-018: Default visibility is team-level.

**Significance of K-012 (worth calling out)**

This substantially reduces R-003. The original adoption risk assumed managers
would have to chase developers for data. If developers create the record when
work reaches them, the record is a byproduct of receiving work rather than an
administrative task layered on top. The design consequence: **item creation must
be near-instant** — a title and nothing else should be enough to save.

**Contradictions surfaced**

- C-004: **Configurability vs. low management burden.** Q2.6, Q2.10 and Q2.11 all
  ask for configurable hierarchy and permissions. Q2.8 states the product must
  not be time-consuming or hard to manage. At ~10 people these goals are in
  direct conflict — a permission engine must be configured before anyone can use
  anything, and that setup cost lands on exactly the manager whose buy-in is
  being sought. Recommendation and decision point raised as Q3.12.
- C-005: Q2.3 selected "genuine mix" but the free text describes mostly reactive
  work. Treated as **mix, weighted reactive** until contradicted.

**Pattern noted (process observation, not a fault)**

Three questions about *how things work today* (Q1.6, Q2.6, and partly Q2.4) were
answered with *desired features* rather than current practice. Current
assignment practice therefore remains partly UNKNOWN. This is normal for a
technically-minded stakeholder, but it means feature requests are accumulating
faster than the business rules that justify them.

**Unresolved from this round**

- U-011: Do different work types need **different fields and steps**, or the same
  fields with a different label? Q2.4 said "all of them" without answering the
  behavioural half. Decides whether the model is one simple table or several
  shapes. (Q3.2)
- U-012: What "multiple people on a task" means operationally, and how load is
  attributed among them. (Q3.3, Q3.4)
- U-013: Whether estimates and actual effort would realistically ever be typed.
  Everything computational depends on this. (Q3.6)
- U-014: Real headcount by role. (Q3.10)

**Risk changes**

- R-003 (adoption): **downgraded** from critical to moderate, on K-012.
- R-004 (proxy stakeholder): **unchanged.** Still no manager contact. A-006
  remains unverified — the pitch has not happened.
- R-005 (new): **Over-specification for scale.** Configurable permissions,
  drag-and-drop hierarchy and delegated visibility rights are enterprise
  machinery being requested for a ten-person team. Cost is not just build time;
  it is the setup burden that lands on the very stakeholder whose approval the
  project depends on.

---

## Round 3 — Work Items, Effort & Scope

**Status:** ANSWERED — **discovery closed**
**Date asked:** 2026-08-14
**Date answered:** 2026-08-14
**Deck:** `round-03-cards.html`

Purpose: define the work item precisely enough to build a domain model, resolve
how multiple assignees affect load, and get an honest read on whether effort data
will ever exist. Intended as the **final discovery round**.

| Q | Topic |
|---|---|
| Q3.1 | Real lifecycle of one bug, including waiting states *(pivot)* |
| Q3.2 | Whether work types need different fields or just labels *(pivot)* |
| Q3.3 | What "multiple people on a task" actually means *(pivot)* |
| Q3.4 | How load is attributed across several assignees |
| Q3.5 | Split, merge and mid-flight handover |
| Q3.6 | Whether estimates and actuals would realistically be typed *(pivot)* |
| Q3.7 | Minimum unit of work worth recording |
| Q3.8 | Where deadlines originate — client-stated or calculated |
| Q3.9 | Priority levels, who sets them, whether urgent jumps the queue |
| Q3.10 | Real headcount by role, number of clients |
| Q3.11 | Whether work groups by client/product, and whether that drives decisions |
| Q3.12 | Fixed roles vs configurable permissions for v1 *(pivot, resolves C-004)* |

### Answers (paraphrased)

| Q | Answer |
|---|---|
| Q3.1 | Client mails, or comes to a developer's or QA's desk. Developer starts. Sometimes: "I'm on another task, I'll do this after." Sometimes the new task is urgent, so the old one is **put on hold or transferred to someone else**. When done, they mail the client back. |
| Q3.2 | (a) Same fields, plus a column identifying bug / CR / observation / etc. |
| Q3.3 | (c) Owner plus helpers — but (a) split and (d) handover also occur. All three have happened. |
| Q3.4 | Mostly equal, sometimes weighted by skill set. |
| Q3.5 | Usually no, but rarely yes. |
| Q3.6 | **(d) Honestly, neither.** Developers would not reliably type an estimate before, or actual time after. |
| Q3.7 | Everything should be recorded; if someone forgets, they can do it by end of day. |
| Q3.8 | **Clients give the deadlines.** |
| Q3.9 | Five levels: P0, P1, P2, P3, P4. Who sets them was not answered. |
| Q3.10 | **10 developers** (not 10 total). Headcount varies. |
| Q3.11 | Answered a different question: work is **sometimes pending from the client side**. Grouping by client left unanswered. |
| Q3.12 | Not selected. Wants to be able to add extra roles and place them within the hierarchy; "will be decided during the project phases". |

### Outcomes of this round

**The decisive finding — Q3.6**

- K-019: **Effort data will not be entered.** No estimates before, no actuals
  after. Confirmed deliberately and pessimistically, as asked.

Consequence: assumption **A-007 is REJECTED**, and with it the entire
hour-arithmetic basis of the original brief. Capacity in hours, hour-based
availability, hour-based overlap detection and estimate-driven ETA are **not
computable** and must not be specified. Anything built on them would produce
confident, wrong numbers — the worst possible outcome for a planning tool.

Resolution: **ADR-001** — derive workload from flow data (timestamps, counts,
history) rather than from typed effort. Nearly all of the originally requested
capabilities survive this change in a different form. See
`docs/adr/ADR-001-derive-workload-from-flow-data.md`.

**Other findings that became KNOWN**

- K-020: **Preemption is the core dynamic.** Urgent work arriving causes existing
  work to be put on hold or transferred. This is the mechanism behind K-016 and
  behind Round 1's F-002. The system must record *why* an item is on hold —
  specifically, which item displaced it.
- K-021: All work types share the same fields; type is a single classifying
  attribute. The model is **one work item table plus a type reference table** —
  the cheap outcome. Closes U-011.
- K-022: Work items are **blocked waiting on the client** at times. Externally
  blocked and internally preempted are different states with different meanings
  and must not be merged.
- K-023: **Due dates are client-given inputs**, not system outputs. The primary
  question the product answers is therefore "will we make this date?", not "what
  date will this be?" — a simpler and more valuable computation.
- K-024: Five priority levels, P0–P4.
- K-025: 10 developers, plus QA, BA and management. Total headcount larger than
  the earlier "around 10", still small. Headcount varies over time.
- K-026: Handover and splitting are rare but real, and occur as a *consequence of
  preemption* rather than independently.

**Contradiction surfaced**

- ~~C-006~~ **RESOLVED 2026-08-15.** Confirmed by the stakeholder: Q3.7's
  "everything to be recorded" refers to recording the **work item**, not the time
  spent. A-007 stays rejected; ADR-001 stands unamended.

**Lifecycle derived from Q3.1** (candidate, to be confirmed in the BRD)

| State | Meaning | Source |
|---|---|---|
| New | Recorded, no owner yet | K-012 |
| Queued | Owned, not started — "I'll do it after this one" | Q3.1 |
| In Progress | Actively being worked | Q3.1 |
| On Hold — preempted | Displaced by more urgent work; records what displaced it | K-020 |
| Blocked — waiting on client | Externally blocked, clock stops on our accountability | K-022 |
| Done | Client informed | Q3.1 |

Reassignment is an **event** that changes the owner, not a state.

**Gaps deliberately left open rather than invented**

- ~~O-001~~ **CLOSED 2026-08-15.** A QA verification step does exist and is part
  of the lifecycle (K-027). QA is therefore both a verifier and, per Q3.1, a
  possible owner of work arriving directly from clients. Sub-questions remain
  (does every item pass through it; can it fail back) — carried as OPEN-5.
- O-002: Who sets priority, and whether P0 automatically preempts, is unstated.
- O-003: Whether work should be groupable by client/product for reporting is
  still unanswered (Q3.11 answered a different question).
- O-004: Rule for how many items one person can hold before being "overloaded" —
  needs a starting value, to be tuned from real data.

**Risk changes**

- R-006 (new): **Data substrate risk.** With effort data gone, every derived
  number depends on state transitions being recorded promptly. If developers
  batch-update at end of day (which Q3.7 explicitly permits), cycle-time
  measurements skew and "in progress right now" becomes unreliable. Mitigation is
  a design problem: make state changes single-tap and visible, and treat EOD
  catch-up as normal rather than exceptional.
- R-005 (over-specification): **unresolved.** Q3.12 was not answered; the request
  for addable roles inside the hierarchy stands. Compromise proposed in ADR-002.

---

## Discovery closed

Three rounds, 36 questions. Sufficient to write business requirements. Remaining
gaps (O-001..O-004, U-010) are recorded and will be carried into the BRD as
explicitly marked open items rather than silently resolved.

---

## Concepts introduced so far

See `docs/glossary.md` for: Product Discovery, Stakeholder, Source of Truth,
System of Record, System of Engagement, Wedge, Proxy Stakeholder, Work Intake,
Adoption Risk, Leading vs Lagging Indicator.

---

## Post-discovery decisions

| Date | Decision |
|---|---|
| 2026-08-15 | ADR-001 **accepted** without amendment — flow data, not typed effort |
| 2026-08-15 | ADR-002 **accepted** without amendment — roles as data, permissions in code for v1 |
| 2026-08-15 | C-006 resolved — "record everything" means the work item |
| 2026-08-15 | O-001 closed — QA verification step confirmed (K-027) |

Discovery output is now carried forward in `docs/03-brd.md`. This log is closed
for new questions; it remains the evidence base every requirement traces back to.
