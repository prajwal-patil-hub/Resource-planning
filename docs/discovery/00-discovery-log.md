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

**Status:** OPEN — awaiting answers
**Date asked:** 2026-08-14
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

### Answers

_To be filled in._

---

## Concepts introduced so far

See `docs/glossary.md` for: Product Discovery, Stakeholder, Source of Truth,
System of Record, System of Engagement, Wedge, Proxy Stakeholder, Work Intake,
Adoption Risk, Leading vs Lagging Indicator.
