# Business Requirements Document — Resource Planning

| | |
|---|---|
| **Document** | BRD v1.0 |
| **Status** | DRAFT — for review |
| **Date** | 2026-08-15 |
| **Phase** | Phase 1 — Business Requirements |
| **Source** | `docs/discovery/00-discovery-log.md` (3 rounds, 36 questions) |
| **Decisions in force** | ADR-001 (accepted), ADR-002 (accepted) |

---

## 0. What this document is, and what it is not

A **Business Requirements Document** states *what the business needs and why*, in
business language. It deliberately contains no screens, no field lists, no
database tables and no API designs.

**Why the separation matters.** A requirement written as a solution ("add a
dropdown for status") cannot be challenged, because it hides the need behind an
implementation. Written as a need ("work that has stopped progressing must become
visible without anyone looking for it"), it can be questioned, tested, and solved
several different ways. It also survives redesigns: screens change, the business
need doesn't.

**What comes next, and where it lives:**

| Level | Question it answers | Document |
|---|---|---|
| Business requirement (BR) | What does the business need? | This document |
| Functional requirement (FR) | What must the system do? | `05-srs.md` |
| Technical design | How is it built? | `10-technical-design.md` |

Every FR written later must trace back to a BR here. Anything that cannot is
either a missing business requirement or a feature nobody needs.

**Identifier scheme used throughout:**

| Prefix | Meaning |
|---|---|
| `BO-n` | Business objective |
| `BR-n` | Business requirement |
| `RULE-n` | Business rule — always true, constrains behaviour |
| `CON-n` | Constraint — a fact we must design within |
| `ASM-n` | Assumption — believed, not proven; each has a validation plan |
| `OPEN-n` | Known gap, deliberately unresolved |
| `F-n` | Observed failure from discovery, the evidence base |

---

## 1. Problem statement

A software team of roughly 10 developers plus QA, BA and management delivers
change requests and bug fixes for external clients. Work arrives by email or
verbally, is assigned verbally, and is recorded nowhere.

Four failures follow directly, all observed and reported during discovery:

| ID | Observed failure | Consequence |
|---|---|---|
| **F-001** | Work assigned verbally, never recorded, then forgotten | Client chases; team learns of its own commitment from the client |
| **F-002** | Person is busy on other work, doesn't start it, nobody notices for two days | Delay discovered only when it is already a delay |
| **F-003** | Work that took 15 minutes is only reported the following day | No basis for knowing how long anything actually takes |
| **F-004** | Assignee goes on leave; client believes work is progressing | Silent stall, and a credibility cost when it surfaces |

Underneath all four is a single mechanism, identified in discovery and central to
this document:

> **Unplanned urgent work displaces planned work, invisibly.**
> A client's P0 bug arrives, a developer sets aside the CR they were working on,
> and nothing records that this happened. The CR is later described as "late"
> when it was in fact *displaced* — often by the same client's own urgent request.

The organization currently cannot answer, at any moment: who is working on what,
what has stalled, what is at risk, or why anything is late.

**This is not a tooling gap in an existing process. There is no process.** The
system must therefore create a habit rather than digitize one, which makes ease
of recording the single most important design property in this document.

---

## 2. Business objectives

Ordered by priority. Later objectives depend on data produced by earlier ones.

| ID | Objective | Addresses | Measure |
|---|---|---|---|
| **BO-1** | No committed work is forgotten | F-001 | % of incoming requests with a record within 1 working day |
| **BO-2** | Stalled work is noticed by us before the client notices | F-002 | Count of items with no progress for > 3 days, trending down |
| **BO-3** | Absence never silently stalls client work | F-004 | Count of items whose owner is absent and which have no cover |
| **BO-4** | Lateness can be explained with evidence | F-002, K-020 | % of overdue items with a recorded cause (preempted / blocked on client) |
| **BO-5** | Overload is visible before it causes failure | F-002 | Count of people above their normal load, trending down |
| **BO-6** | Delivery timing can be forecast honestly | F-003, K-023 | Forecast range vs actual, reviewed monthly |

**BO-1 is the foundation.** Every other objective is computed from data that only
exists if BO-1 is met. If BO-1 fails, the product fails regardless of how well
everything else is built.

---

## 3. Stakeholders and personas

### 3.1 Stakeholder register

| Stakeholder | Interest | Influence | Current stance |
|---|---|---|---|
| Developer | Does the work; must record it | **High** — data quality depends entirely on them | Unknown, unconsulted |
| QA | Receives work directly; verifies before delivery | High | Unknown, unconsulted |
| Team Lead | Notices stalled work today; primary user | High | Unknown, unconsulted |
| Manager | Needs delivery visibility; must mandate use | **Decisive** | **Has not been asked** — see ASM-2 |
| BA | Handles client communication and requirements | Medium | Unknown |
| Client | Raises work, sets deadlines, chases | External | Not a user of the system |
| Project sponsor (this project) | Building it on own initiative | — | Committed |

> **Note on stakeholder consultation.** All requirements in this document derive
> from a single source: the project sponsor, who is a developer building this for
> management rather than a manager themselves, and who stated during discovery
> that they do not know what decisions management makes weekly. Requirements are
> marked **TO VALIDATE** where they rest on that inference. This is recorded as
> risk R-004 and is the largest non-technical risk in the project.

### 3.2 Personas

**Developer — "I was told about it on Tuesday"**
Receives work by email or someone stopping at their desk. Juggles several items,
frequently interrupted by urgent client issues. Does not estimate, does not log
time, and will not start doing either. Forgets things not because of carelessness
but because the commitment was never written anywhere.
*Needs:* a place to put work in five seconds; a defensible answer to "why isn't
this done" — namely, what displaced it.
*Will abandon the system if:* recording anything takes longer than telling
someone.

**QA — "it also comes to my desk"**
Receives work directly from clients, and verifies developers' work before it goes
back to the client. Sits at a point where things queue invisibly.
*Needs:* to see what is waiting for verification, and to send work back when it
fails.

**Team Lead — the primary user**
The person who notices today, by memory and conversation, that something has
stalled. Everything they do manually is what this product automates.
*Needs:* one screen showing all work, who owns it, what has stopped moving, and
who is carrying too much.
*Decides:* who takes new work, what gets displaced, what the client is told.

**Manager — the approver**
Has not asked for this system and has not yet seen it. Will judge it on whether
it creates work for them.
*Needs:* delivery risk and client-level effort distribution, without configuring
anything.
*Will reject it if:* using it requires setup, administration, or chasing people.

### 3.3 Role–permission matrix

Per **ADR-002**: four roles seeded, stored as data so more can be added; the
permissions themselves are fixed in code for v1.

| Action | Developer | QA | Team Lead | Manager | Admin |
|---|:---:|:---:|:---:|:---:|:---:|
| Create work item | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edit item they own | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edit any item in own team | — | — | ✓ | ✓ | ✓ |
| Assign work to self | ✓ | ✓ | ✓ | ✓ | ✓ |
| Assign work to others in own team | ✓ | ✓ | ✓ | ✓ | ✓ |
| Assign across teams | — | — | ✓ | ✓ | ✓ |
| Move own item through states | ✓ | ✓ | ✓ | ✓ | ✓ |
| Mark verification passed / failed | — | ✓ | ✓ | — | ✓ |
| Set priority | — | — | ✓ | ✓ | ✓ |
| Record own absence | ✓ | ✓ | ✓ | ✓ | ✓ |
| Approve absence | — | — | ✓ | ✓ | ✓ |
| See own work | ✓ | ✓ | ✓ | ✓ | ✓ |
| See own team's work and load | ✓ | ✓ | ✓ | ✓ | ✓ |
| See all teams | — | — | — | ✓ | ✓ |
| See cross-client reporting | — | — | ✓ | ✓ | ✓ |
| Manage people, teams, roles | — | — | — | — | ✓ |

Notes:

- Team-level visibility is the default (K-018). A developer sees their whole
  team's load, not just their own — this is deliberate: hiding it would prevent
  the team self-balancing, which is one of the cheapest benefits available.
- QA is a **seeded additional role** under ADR-002, distinguished from Developer
  only by verification rights.
- **Assignment within a team is open to everyone** (C-007, resolved 2026-08-15).
  A developer recording work may put a colleague's name on it. The risk of
  uncoordinated assignment is mitigated by visibility rather than permission —
  load is visible team-wide before you assign, and every assignment records who
  made it. Restrict later only if the data shows a real problem.
- **Cross-team assignment stays restricted** to Team Lead and above. **TO
  VALIDATE** — assigning into a team whose load you cannot see is the case that
  actually needs a gate. May be moot if the organization runs as one team.
- **TO VALIDATE:** the split between Team Lead and Manager is inferred, not
  stated. One conversation with a manager may collapse these into one role.

---

## 4. Current state (as-is)

```
Client
  │  email, or walks to a developer's or QA's desk
  ▼
Developer / QA hears about it
  │
  ├─ starts it now
  │
  ├─ "I'm on something else, I'll do it after"     ← queue exists only in their head
  │
  └─ urgent item arrives
        ├─ current work put on hold                ← displacement not recorded
        └─ or transferred to someone else          ← handover not recorded
  │
  ▼
Work is done
  │
  ▼
QA verifies
  │
  ▼
Reply to client
```

**Where it breaks:**

| Point | Failure |
|---|---|
| "Hears about it" | No record exists → F-001 |
| "I'll do it after" | An invisible personal queue nobody else can see → F-002 |
| "Put on hold" | The reason for the delay is lost → BO-4 impossible |
| "Transferred" | Ownership history lost |
| Throughout | Absence is not connected to work → F-004 |

---

## 5. Future state (to-be)

### 5.1 Principle governing the whole design

> **Derive, don't ask** (ADR-001).
> If the system needs a number, compute it from something the user already does.
> Ask only when it cannot be derived — and then make answering optional.

The only thing anyone is asked to do is **record work and move it through
states**. Every metric in this document is computed from those two actions.

### 5.2 Work item lifecycle

| State | Meaning | Accountability clock |
|---|---|---|
| **New** | Recorded, no owner yet | Running |
| **Queued** | Owned, not started — the personal queue, made visible | Running |
| **In Progress** | Actively being worked | Running |
| **On Hold — preempted** | Displaced by more urgent work; **records which item displaced it** | Running |
| **Blocked — on client** | Waiting for the client; we cannot proceed | **Stopped** |
| **In Verification** | With QA | Running |
| **Done** | Verified and client informed | Ended |
| **Cancelled** | No longer required; retained, never deleted | Ended |

Transitions of note:

- **In Verification → In Progress** when verification fails (rework loop).
- **Reassignment is an event, not a state.** The owner changes; the item's state
  and its full history are preserved.
- **On Hold — preempted** must name the displacing item. This is what makes BO-4
  possible, and it is the single most valuable field in the system.

The distinction between *On Hold — preempted* and *Blocked — on client* is
deliberate and must not be collapsed. One means "we chose something else first";
the other means "you haven't replied". Merging them would erase precisely the
evidence needed to discuss lateness with a client.

### 5.3 How workload is measured

Per ADR-001, in **items, not hours**:

- **Load** = number of items a person currently has In Progress.
- **Normal level** = that person's own historically sustained load, seeded with a
  default and tuned from observed data (OPEN-4).
- **Overloaded** = above their normal level. **Available** = below it, not
  absent, and a working day.
- **Cycle time** = elapsed time from first entering In Progress to Done,
  including interruptions — because interruptions are this organization's
  dominant cause of delay.
- **At risk** = open longer than similar items typically take, with a client due
  date approaching.

---

## 6. Business requirements

Each requirement states a business need. Solutions are deliberately excluded.

### Recording work

| ID | Requirement | Traces to | Priority |
|---|---|---|---|
| **BR-001** | Every piece of incoming work must have a durable record, independent of anyone's memory | F-001, BO-1 | Must |
| **BR-002** | Creating that record must be faster than telling a colleague about it | R-003, D-005 | Must |
| **BR-003** | A work item must be recordable before it has an owner | K-012 | Must |
| **BR-004** | Recording work late (e.g. at end of day) must be normal and supported, not an error | Q3.7 | Must |
| **BR-005** | Work items must never be destroyed; unwanted work is cancelled and retained | ADR-001 | Must |

### Making work visible

| ID | Requirement | Traces to | Priority |
|---|---|---|---|
| **BR-006** | Every work item must have exactly one accountable person, or be visibly unowned | F-001, BO-1 | Must |
| **BR-007** | Work that has stopped progressing must become visible without anyone searching for it | F-002, BO-2 | Must |
| **BR-008** | A person's current workload must be visible to their team | F-002, BO-5, K-018 | Must |
| **BR-009** | Planned work displaced by urgent work must be recorded as displaced, identifying what displaced it | K-020, BO-4 | Must |
| **BR-010** | Work waiting on the client must be distinguishable from work waiting on us | K-022, BO-4 | Must |
| **BR-011** | Work awaiting verification must be visible as a distinct state | K-027 | Must |

### People and availability

| ID | Requirement | Traces to | Priority |
|---|---|---|---|
| **BR-012** | Planned absence must be recordable and visible against that person's open work | F-004, BO-3 | Must |
| **BR-013** | Work owned by an absent person must be surfaced for cover | F-004, BO-3 | Must |
| **BR-014** | Non-working days must be excluded from all elapsed-time measures | — | Should |
| **BR-015** | Reassigning work must preserve the full ownership history | K-026 | Must |

### Decision support

| ID | Requirement | Traces to | Priority |
|---|---|---|---|
| **BR-016** | Before assigning work, the assigner must be able to see the candidate's current load and absence | BO-5 | Must |
| **BR-017** | Work at risk of missing a client-given due date must be identified before that date | K-023, BO-6 | Must |
| **BR-018** | Delivery timing must be expressed as a range with stated confidence, never a false single date | ADR-001, BO-6 | Must |
| **BR-019** | The system must show where the organization's effort is going, by client and by work type | BO-6 | Should |
| **BR-020** | Any figure the system displays must be explainable — a user must be able to see what it was derived from | R-006 | Must |

> **On BR-020.** A number a manager cannot interrogate will not be trusted, and
> should not be. Because every metric here is derived rather than entered, the
> derivation must be inspectable — otherwise the first surprising number destroys
> confidence in all the others.

### Operating constraints as requirements

| ID | Requirement | Traces to | Priority |
|---|---|---|---|
| **BR-021** | The system must be usable immediately after installation, with no configuration step | Q2.8, ADR-002 | Must |
| **BR-022** | The system must produce useful output without requiring effort estimates or time logging | K-019, ADR-001 | Must |
| **BR-023** | Work types must be extensible by users without a code change | K-014, K-021 | Must |
| **BR-024** | New roles must be addable and placeable in the hierarchy without a code change | ADR-002 | Should |
| **BR-025** | Access to work and workload data must be governed by role and team | K-017, K-018 | Must |

---

## 7. Business rules

Rules are always true and constrain system behaviour. Where a rule is not yet
decided it is marked OPEN rather than guessed.

| ID | Rule |
|---|---|
| **RULE-001** | A work item may exist with no owner. It is then in state New and counts against no one. |
| **RULE-002** | An assigned work item has exactly one accountable owner. Additional participants are collaborators. |
| **RULE-003** | Load counts against the owner only. Collaborators are visible but do not carry the item in their own load in v1. |
| **RULE-004** | An item placed On Hold — preempted must identify the item that displaced it. |
| **RULE-005** | Time spent Blocked — on client does not count toward our accountability for lateness. Time spent On Hold — preempted does. |
| **RULE-006** | Priority levels are P0, P1, P2, P3, P4, where P0 is most urgent. |
| **RULE-007** | A person is overloaded when their in-progress count exceeds their own normal level — never a single organization-wide threshold. |
| **RULE-008** | A person's normal level starts from a seeded default and is adjusted from their observed history. |
| **RULE-009** | An item is at risk when its elapsed time exceeds the typical cycle time for similar items and its due date has not passed. |
| **RULE-010** | Forecasts are expressed as ranges with a stated confidence. The system must not present a derived date as certain. |
| **RULE-011** | Default visibility is team-level. |
| **RULE-012** | Reassignment changes the owner and is recorded as an event. Prior ownership is retained. |
| **RULE-013** | The system must not forecast from fewer than a defined minimum of comparable completed items; below that it must say it does not yet know. |
| **RULE-014** | Due dates originate from the client. The system evaluates them; it does not set them. |
| **RULE-015 (OPEN)** | Who may set priority, and whether P0 triggers preemption automatically or a human always decides — see OPEN-2. |
| **RULE-016** | Work may be recorded as having happened up to 14 days in the past, and never in the future. Beyond that window the entry is refused with its reason. |
| **RULE-017** | A person may only be assigned work from a team they are permitted to assign into. The check is enforced at the point of assignment, not only in the list of names offered. |
| **RULE-018** | No report presents elapsed item time as effort, cost, capacity or person-hours. The product holds no effort data and must never imply that it does. |
| **RULE-019** | A measurement may be shown at any sample size; an inference drawn from it may not. Emphasis, ranking and percentiles wait for the minimum sample (RULE-013); a directly measured quantity does not. |
| **RULE-020** | Reference data — clients, work types, roles, teams — is retired, never deleted, and names are unique regardless of case. |
| **RULE-021** | A role or team still held by active people cannot be retired. |

> **On RULE-013.** Forecasting from three completed items produces a confident
> number with no basis. Refusing to answer until there is enough history is a
> feature, not a limitation, and protects the credibility of every other figure.

> **On RULE-016.** "Record it by EOD" needs hours, not weeks. Past a fortnight a
> backdated entry is far more likely a mistyped year or month than a real
> catch-up — and one wild timestamp does more damage to a cycle-time
> distribution than a dozen missing entries, because it silently drags an
> average nobody is watching. A refusal is recoverable; a poisoned statistic is
> not, because nobody knows to go looking for it.

> **On RULE-017.** Visibility was already scoped by team, but a filtered
> dropdown is a convenience and not a control — the form beneath it accepts any
> identifier that is posted. The rule held for what someone could *see* and was
> silent on what they could *do*, which is the half that matters.

> **On RULE-018.** ADR-001 removed effort data from the product permanently, so
> "where the work goes" can only be answered in items and elapsed duration. Two
> items open across the same week contribute two item-weeks while costing the
> team one week — a percentage next to a client's name is a share of *demand*,
> never of cost. A manager will read it as cost unless told plainly, so the
> report says so in its own first paragraph rather than in a footnote.

> **On RULE-019.** The distinction that keeps the reports honest without making
> them useless. "Of the 12 days these items were alive, 7 were spent waiting on
> the client" is true however few items there are, and withholding it would be
> false caution. "This client is slow" is an inference about their habits, and
> that needs a sample. So the figure is always shown and the emphasis is not.

> **On RULE-020.** Two rows for one client is the worst failure available to the
> reports: each carries half the history, every total is wrong, and nothing in
> the product can detect it — from the reports' point of view these genuinely
> are two different clients. Case-insensitive uniqueness closes the common
> version ("Acme" and "acme"). Retiring rather than deleting is the same
> principle as BR-005 applied to the labels: a client with thirty finished items
> cannot be removed without those thirty items losing their history. Renaming is
> therefore the correct tool for a name change, and the screen says so, because
> the instinct is usually to create a new one.

> **On RULE-021.** `can()` reads permissions through the person's role, so
> everyone holding a retired role would keep whatever it grants while the role
> stopped appearing anywhere — a permission in force and invisible. The same
> applies to teams, which scope visibility under RULE-011.

---

## 8. Scope

### 8.1 In scope for v1

- Recording work items, with type, priority, client-given due date, and owner
- The full lifecycle in §5.2, including preemption and client-blocked states
- QA verification, including the rework loop
- Team-level visibility of work and load
- Absence recording and its effect on open work
- Stalled-work and at-risk detection
- Load measurement in items, with per-person normal levels
- Historical cycle time and throughput, once sufficient history exists
- Reporting by client and by work type
- Four seeded roles on an extensible role table

### 8.2 Explicitly out of scope for v1

Each of these was requested at some point. Each is excluded for a stated reason,
not by oversight.

| Excluded | Reason |
|---|---|
| Hour-based capacity, timesheets, effort estimates | Not computable — the data will not be entered (K-019, ADR-001) |
| Precise single-date ETA | Would be false precision derived from data we do not have |
| Jira / Azure DevOps / GitHub integration | Nothing to integrate with — no existing system of record (R-002 closed) |
| Calendar, Slack/Teams, HR system integration | No demonstrated requirement yet; each adds a dependency and a failure mode |
| AI natural-language interface | Deliberately deferred. It must sit above a working deterministic system, and that system does not exist yet |
| Skills matrix and skill-based assignment | Nobody maintains a skills matrix today. An unmaintained one produces worse recommendations than none |
| Task dependency graphs | Splitting and handover are rare (K-026). Would add significant complexity for a rare case |
| Configurable permission editing, delegated rights | ADR-002 — expensive, and no concrete case given |
| Drag-and-drop org chart builder | Requested as a feature; the underlying need (hierarchy controls permissions) is met by ADR-002 at a fraction of the cost |
| Multi-tenancy | Single organization (K-006) |
| Client-facing access | Clients are not users |

> **Why "out of scope" is written this way.** Recording the *reason* means the
> decision can be revisited on evidence rather than re-argued from scratch. If a
> reason stops being true — for example, if the team adopts Jira — the exclusion
> should be reconsidered immediately.

---

## 9. Constraints

| ID | Constraint | Consequence |
|---|---|---|
| **CON-1** | ~10 developers plus QA, BA, management; headcount varies | Simplicity beats scalability. Anything requiring a dedicated administrator is wrong |
| **CON-2** | No effort data will be entered | All computation must derive from flow data (ADR-001) |
| **CON-3** | No existing tool or process to build on | The product must create a habit; ease of recording is the dominant design criterion |
| **CON-4** | No mandate yet; adoption is voluntary until management approves | The system must be worth using before anyone is told to use it |
| **CON-5** | Must work with zero configuration | Rules ship as defaults, not as setup questions (BR-021) |
| **CON-6** | Single organization, not a product for sale | Configurability is deferred decision-making, not flexibility |
| **CON-7** | Work arrives unpredictably and interrupts planned work | The model must be queue-first; planning is secondary |

---

## 10. Assumptions

Each assumption has a validation plan. Unvalidated assumptions are not facts and
must not be treated as such downstream.

| ID | Assumption | Risk if wrong | How to validate |
|---|---|---|---|
| **ASM-1** | Developers will record work when it reaches them | Total failure — every metric depends on it | Watch the recording rate in the first two weeks of real use |
| **ASM-2** | A manager will support and mandate this | Project has no route to adoption | **Pitch it. Not yet done.** Highest-value outstanding action |
| **ASM-3** | State changes are recorded promptly enough for cycle time to be meaningful | Metrics skew; "in progress now" becomes unreliable | Compare state-change timestamps against working hours after 3 weeks |
| **ASM-4** | Item count is a good enough proxy for load at this team size | Load figures mislead | Review against observed overload after one month |
| **ASM-5** | This system owns work items; no other system of record emerges | Model becomes a mirror, with sync and drift problems | Revisit if the organization adopts Jira or similar |
| **ASM-6** | Team Lead and Manager are genuinely distinct roles here | Two roles where one would do; unnecessary complexity | Confirm with a manager (same conversation as ASM-2) |

---

## 11. Open items

Deliberately unresolved. Recorded rather than guessed.

| ID | Question | Blocks | Owner |
|---|---|---|---|
| **OPEN-1** | ~~Is there a QA verification step?~~ | — | **CLOSED 2026-08-15 — yes. Recorded as K-027 and reflected in §5.2** |
| **OPEN-2** | Who may set priority, and does P0 preempt automatically or does a human always decide? | RULE-015; preemption behaviour | Stakeholder |
| **OPEN-3** | Should work be groupable by client/product for reporting? | BR-019 | Stakeholder |
| **OPEN-4** | Starting default for "normal load" per person | RULE-008 | Analyst — propose a value, tune from data |
| **OPEN-5** | Does every item pass through verification, or only some types? Can verification fail and return the item? | Lifecycle completeness | Stakeholder |
| **OPEN-6** | What decisions does management actually make weekly? | Whether BO-4..BO-6 target the right decisions | **Requires a manager, not another question to the sponsor** |

---

## 12. Success measures

Leading indicators move within days and tell us whether the mechanism works.
Lagging indicators are what actually matters but move slowly.

**Leading**

| Measure | Target | Why |
|---|---|---|
| % of incoming work recorded within 1 working day | > 80% by week 4 | If this fails nothing else matters (BO-1) |
| Items with no state change for > 3 days | Trending down | BO-2 working |
| % of overdue items with a recorded cause | > 70% | BO-4 working |
| People above normal load | Trending down | BO-5 working |

**Lagging**

| Measure | Why |
|---|---|
| Client escalations per month | The sponsor's own stated goal: "pressure from client would stop" |
| % of client due dates met | The outcome the business cares about |
| Median cycle time by work type | Whether delivery is genuinely improving |

> **Read the leading indicators first.** If the recording rate is below 50% at
> week four, the correct response is to reduce friction in recording — not to add
> features. Every number downstream is a function of that one.

---

## 13. Traceability

Evidence → objective → requirement. Functional requirements will attach to this
chain in the SRS.

| Failure | Objective | Business requirements |
|---|---|---|
| F-001 forgotten work | BO-1 | BR-001, BR-002, BR-003, BR-006 |
| F-002 stalled unnoticed | BO-2, BO-5 | BR-007, BR-008, BR-009, BR-016 |
| F-003 unknown duration | BO-6 | BR-018, BR-022 |
| F-004 absence stalls work | BO-3 | BR-012, BR-013 |
| K-020 invisible preemption | BO-4 | BR-009, BR-010 |
| K-023 client due dates | BO-6 | BR-017, RULE-014 |
| K-027 QA step | — | BR-011 |
| R-003 adoption risk | BO-1 | BR-002, BR-004, BR-021 |
| R-006 substrate risk | all | BR-020 |

---

## 14. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-15 | Initial draft from discovery rounds 1–3, ADR-001, ADR-002. OPEN-1 closed same day (QA step confirmed) |
| 1.1 | 2026-08-15 | Role matrix §3.3 corrected: Developer and QA may assign within their own team (C-007). OLD: assignment restricted to Team Lead and above. REASON: stakeholder confirmed developers can name an assignee when recording work, consistent with Q2.2. IMPACT: one rule in the `access` module; no change to entities, tables, or the domain model's structure |
