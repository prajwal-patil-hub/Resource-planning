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

**Status:** OPEN — awaiting answers
**Date asked:** 2026-08-14

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

### Answers

_To be filled in._

### Outcomes of this round

_To be filled in: what became KNOWN, what contradictions surfaced, what new
UNKNOWNs opened._

---

## Concepts introduced in this round

See `docs/glossary.md` for: Product Discovery, Stakeholder, System of Record,
System of Engagement, Source of Truth, Wedge.
