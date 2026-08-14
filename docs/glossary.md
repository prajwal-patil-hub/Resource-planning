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

---

## Domain terms (to be defined together — currently ambiguous)

These are deliberately left undefined. Defining them precisely *is* a large part
of the business analysis work, and each definition has direct consequences for
the database and algorithms.

- **Capacity** — how much work a person can absorb in a period. Gross or net of
  meetings, support, and overhead? Measured in hours, points, or task slots?
- **Availability** — a point-in-time or forward-looking property? Does "available
  Tuesday" mean zero assigned work, or below a utilization threshold?
- **Allocation** — a commitment of a person's capacity to a project or task.
  Percentage-based or hours-based? Per day or per period?
- **Utilization** — assigned work ÷ capacity. Which capacity — gross or net?
  Is 100% the target, or is it a red flag?
- **Overlap / Conflict** — two claims on the same person at the same time. Is it
  an error, a warning, or a normal state to be visualized?
- **ETA** — expected completion date. Derived from effort + availability +
  dependencies, or manually stated by the assignee?
- **Best developer** — best by skill, speed, availability, cost, project
  familiarity, growth, or fairness? These frequently recommend different people.

_Do not use any of these terms in a requirement until it is defined above._
