# Glossary

Terms are added here the moment they are first used anywhere in this project.
Nothing in `/docs` may use a term that is not defined here.

Format for each term: **what it is → why it exists → why it matters here.**

---

## Process & documentation terms

### Product Discovery
**What:** The phase before design and build, where you deliberately try to
understand the problem, the users, and the constraints — and equally, to find out
that your initial idea was wrong while it is still cheap to change.
**Why it exists:** The cost of changing a decision rises roughly by an order of
magnitude at each stage: conversation → document → design → code → production
data. Discovery front-loads the changes into the cheapest stage.
**Why it matters here:** The initial brief for this project contains at least
five unvalidated assumptions (see `PROJECT_STATE.md`). Each one, if wrong, would
invalidate part of the database schema.

### Stakeholder
**What:** Anyone affected by the system or whose approval/behaviour the system
depends on — not only the people who click buttons in it.
**Why it exists:** Systems fail for organizational reasons as often as technical
ones. A developer who resents being tracked will not keep task status accurate,
and the whole capacity model then rests on stale data.
**Why it matters here:** Developers are stakeholders even if managers are the
primary users. If developers get nothing from the system, its data will rot.

### Source of Truth
**What:** For a given fact, the one place that is authoritative. If two places
disagree, the source of truth wins by definition.
**Why it exists:** Copies of data drift. Without a designated authority, you get
irreconcilable conflicts and nobody knows which number to believe.
**Why it matters here:** The brief already states an important one: the
deterministic application, not the AI, is the source of truth for capacity and
scheduling. There is a second, unresolved one — is *this* system or Jira the
source of truth for tasks?

### System of Record (SoR)
**What:** The authoritative store where a business object officially lives and is
created/edited. E.g. an HR system is the SoR for employment status.
**Why it exists:** Organizations run many tools that all touch the same object.
Naming the SoR prevents duplicate, divergent copies.
**Why it matters here:** If Jira is the SoR for tasks, this product must *mirror*
tasks (read-mostly, sync, reconcile conflicts, tolerate being offline from Jira).
If this product is the SoR, it *owns* tasks (full CRUD, validation, lifecycle).
These are radically different systems with different schemas and failure modes.
This question must be answered before the domain model.

### System of Engagement (SoE)
**What:** The tool people actually work in day to day, which may not be the SoR.
**Why it exists:** Records need to be authoritative; interfaces need to be
pleasant. These goals conflict, so they are often separated.
**Why it matters here:** A likely shape for this product is "SoE for planning
decisions, not SoR for tasks" — managers plan here, work is tracked in Jira.

### Wedge
**What:** The narrowest version of the product that is genuinely useful to
someone on its own.
**Why it exists:** Broad-and-shallow products are useful to nobody. A wedge earns
the right to expand by being indispensable at one thing first.
**Why it matters here:** The brief describes ~18 manager questions, 7
integrations, and an AI layer. That is years of work. We need the one question
that, answered well, would make a manager open this every Monday.

### Proxy Stakeholder
**What:** Someone who speaks *about* the users rather than *as* one — a developer
describing what managers need, for example.
**Why it exists:** Real users are often unavailable, so teams settle for the
nearest informed person. Useful, but their knowledge has a known shape: strong on
mechanics, weaker on why decisions get made the way they do.
**Why it matters here:** Our only business source is building this for management
on their own initiative, and has said plainly they don't know how management
decides. That's honest and workable — but every requirement traced only to this
source must be marked **TO VALIDATE** until a real manager confirms it.

### Work Intake
**What:** How work enters the organization — the doorway before anything is
planned, estimated or assigned.
**Why it exists:** Planning models usually start at "we have a list of tasks" and
quietly assume the list appears by itself. In reality the intake shape determines
the whole system: a planned backlog behaves nothing like an unpredictable queue.
**Why it matters here:** Work here arrives as client change requests, bug reports
and emails, unpredictably. That is a **queue**, not a plan. A queue-shaped system
prioritizes triage, ownership and response time; a plan-shaped system prioritizes
breakdown, sequencing and dependencies. Building the wrong one wastes weeks.

### Adoption Risk
**What:** The risk that a system is built correctly and then not used, leaving
its data incomplete and therefore its outputs wrong.
**Why it exists:** Software that asks people to record things competes with their
actual job. If recording costs more than it returns, people stop — quietly, and
usually without telling anyone.
**Why it matters here:** Nothing is tracked today, so this system creates a new
habit rather than replacing an existing one. Worse, every number it eventually
produces — capacity, availability, ETA — is only as true as the data people
bothered to enter. A capacity engine fed by 60%-complete data doesn't give you
60%-correct answers; it gives you confident, wrong ones.

### Leading vs Lagging Indicator
**What:** A lagging indicator measures the outcome you want (fewer missed
deadlines). A leading indicator measures the behaviour that produces it (work
items having a recorded owner).
**Why it exists:** Lagging indicators are what matter but move slowly and are
influenced by everything. Leading indicators move immediately and tell you
whether the mechanism is working before the outcome has had time to change.
**Why it matters here:** "Client pressure stops" is the lagging goal and may take
months to shift. "% of work items with a recorded owner" moves within a week and
tells us early whether the system is being adopted at all.

### Architecture Decision Record (ADR)
**What:** A short document capturing one significant decision — the situation
that forced it, the options, the choice, and what the choice costs. One decision
per file, numbered, never deleted; a reversal gets a new ADR that supersedes the
old one, and the old one stays readable.
**Why it exists:** The reasoning behind a decision evaporates within weeks while
the consequences last for years. Without a record, the answer to "why is it built
this way?" becomes "nobody remembers", and teams re-litigate settled questions or
undo decisions without knowing what they were for.
**Why it matters here:** ADR-001 records why this system does not track hours.
That will look like an oversight to anyone who arrives later, and the file is
what stops someone helpfully adding hour tracking back in and rediscovering, over
several months, why it didn't work.

### Cycle Time
**What:** Elapsed time from starting a piece of work to finishing it — wall clock,
including every interruption, pause and wait.
**Why it exists:** It's what you can actually measure without asking anyone
anything, since it's just the gap between two timestamps.
**Why it matters here:** It is not effort — an item "in progress" for three days
might be two hours of typing. But for predicting *when things will be done*,
cycle time is the better number precisely because it includes the interruptions
and waiting that really happen. Effort estimates fail mostly because they exclude
exactly those things, and in this organization interruptions are the dominant
cause of delay (K-016).

### Throughput
**What:** How many items get completed per unit of time — "we finish about nine
things a week."
**Why it exists:** It's the simplest possible measure of how fast a team actually
delivers, and needs no estimation.
**Why it matters here:** With throughput and a count of remaining work you can
forecast a completion range without a single estimate: 40 items left, ~9 a week,
so roughly 4–6 weeks. Cruder than a plan, and usually more accurate.

### Work in Progress (WIP)
**What:** The number of items a person or team has actively started but not
finished.
**Why it exists:** Starting more things doesn't finish more things. Past a
certain point extra concurrent work slows everything down — context switching
costs, and every started-but-unfinished item is value sitting idle.
**Why it matters here:** This is our replacement for hour-based capacity.
"Overloaded" becomes "carrying more items in progress than they normally
sustain", which needs only counting — no effort data, no estimates.

### Preemption
**What:** Urgent work displacing work already in progress.
**Why it exists as a named concept:** It's usually invisible. The displaced work
just quietly stops, and later looks like someone was slow.
**Why it matters here:** Q3.1 describes it directly — an urgent item arrives, and
the current task is put on hold or transferred. It is the mechanism behind this
organization's delays. Recording *which item displaced which* turns "why is this
late?" from an argument into a fact, including with clients.

### Reference Data (vs. a fixed enum)
**What:** Values stored as rows in a table (work types, roles, priorities) rather
than fixed in code.
**Why it exists:** Some lists are genuinely stable (a boolean is true or false)
and some grow with the business. Putting a growing list in code means a developer
and a deployment every time it grows.
**Why it matters here:** Work types must be user-extensible (K-014) and roles
should be addable (ADR-002), so both are reference data. Note the important
subtlety: making the *list* extensible is cheap; making the *behaviour attached
to each entry* configurable is expensive. ADR-002 grants the first and defers the
second.

### Configurability as deferred decision-making
**What:** Building a setting instead of making a choice.
**Why it exists:** Genuine uncertainty, or many customers who each need different
behaviour.
**Why it matters here:** It costs roughly 3–5× a fixed rule — the rule, plus
storage, plus an editing UI, plus validation, plus testing every combination —
and someone must configure it before anyone can use anything. With one
organization of ~15 people (K-025) there is no second customer to be flexible
for, and the setup burden lands on the manager whose buy-in the project depends
on (Q2.8). See ADR-002.

---

## Domain terms — now defined

These were deliberately left open at the start of discovery. ADR-001 settles most
of them, because the choice of substrate (flow data rather than typed effort)
determines what each can mean. Definitions are **PROPOSED** until ADR-001 is
confirmed.

### Capacity
**Definition:** the number of items a person can hold in progress at once while
still finishing things at their normal rate. Measured in **items, not hours**.
**Why not hours:** hour-based capacity requires effort data that will not be
entered (K-019). See ADR-001.
**Starting rule:** to be seeded with a default (open item O-004) and then tuned
per person from their own observed history.

### Load
**Definition:** how many items a person currently has in progress.
**Note:** an item counts against its **owner**. Collaborators are recorded and
visible but do not consume their own load in v1 — revisit if it distorts the
picture.

### Overloaded / Under-utilized
**Definition:** load above (or below) that person's normal sustained level.
Relative to the individual, not to a company-wide number, because people
genuinely differ and a single threshold would be wrong for most of them.

### Available
**Definition:** load is below their normal level, they are not on leave, and it
is a working day.
**Note:** availability is a *statement about now*, deliberately not a prediction.
"When will they be free" is a separate, probabilistic question.

### ETA
**Definition:** a **probability range** derived from how long similar items have
historically taken — "80% of P1 bugs have finished within 3 days" — not a single
calculated date.
**Why:** a single date computed from guessed estimates was never actually precise;
it only looked precise. See ADR-001.

### At risk
**Definition:** an item that is open longer than similar items usually take, and
has a client-given due date it is now unlikely to meet (K-023).
**Note:** this is the product's most valuable single signal, and it needs no
effort data at all — only history and a due date.

### Overlap
**Redefined:** not two tasks claiming the same hours. Instead: **assigning this
item would push the person past their normal load.** Hour-level overlap is not
computable without effort data.

### Blocked vs. On hold
**Blocked:** waiting on someone outside the team, usually the client (K-022). Our
accountability clock stops.
**On hold — preempted:** displaced by more urgent work (K-020). Our
accountability clock keeps running, and the record names the item that displaced
it.
**Why separate:** merging them would hide the difference between "the client
hasn't replied" and "we chose something else first" — which is exactly the
distinction that settles arguments about lateness.

### Best developer for a task
**Partially defined.** Candidate factors: history with similar work, current
load, absence, and familiarity with the client. Explicitly **not** skill-scored
in v1 — nobody maintains a skills matrix today, and an unmaintained one produces
worse recommendations than none.
**Status:** to be specified as an explicit ranked rule set, never as an opaque
score. A recommendation a manager cannot interrogate will not be trusted, and
should not be.

_Any requirement using these terms must mean exactly what is written here._
