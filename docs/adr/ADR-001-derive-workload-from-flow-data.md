# ADR-001 — Derive workload from flow data, not from typed effort

**Status:** PROPOSED — awaiting stakeholder confirmation
**Date:** 2026-08-14
**Supersedes:** nothing
**Related:** K-019, A-007 (rejected), D-003, D-004, R-006

---

## What an ADR is, and why this one exists

An **Architecture Decision Record** is a short document capturing one
significant decision: the situation that forced it, the options, the choice, and
what the choice costs you. One decision per file, numbered, never deleted — when
a decision is later reversed, a new ADR supersedes the old one and the old one
stays readable.

It exists because the reasoning behind a decision evaporates within weeks, while
the consequences last for years. Six months from now someone (probably you) will
look at this system and ask "why doesn't it track hours?" Without this file the
honest answer is "nobody remembers", and the usual next step is to add hours back
and rediscover why it didn't work.

This is the first ADR because it is the decision everything else rests on.

---

## Context

The original product brief asked for capacity, availability, overlap detection,
ETA calculation, "can X take this task", and an AI layer answering questions like
"who will be free next week". Every one of those is arithmetic over two numbers:

1. **estimated effort** — how long a task will take, entered before starting
2. **actual effort** — how long it really took, entered after finishing

Discovery Round 3 asked directly and pessimistically whether those two numbers
would ever be entered. The answer (Q3.6) was **(d) Honestly, neither** — neither
estimates nor actuals would be reliably recorded.

Supporting facts from discovery:

- K-009: no estimation or time recording happens today
- K-007: no tracking process exists at all — this creates a habit rather than
  replacing one
- K-016 / K-020: work is interrupt-driven; urgent client items preempt planned
  work, so any up-front estimate is invalidated by events outside the estimator's
  control
- K-023: clients set the deadlines, so the system's job is "will we make this
  date?" rather than "what date should we promise?"

This is not a discipline problem to be solved with reminders. Estimation is a
skill that takes teams months to develop and is famously unreliable even then,
and time logging is universally the first thing abandoned under pressure.
Designing a system that requires both, in an organization that does neither, is
designing for failure.

**The core risk being avoided:** a capacity engine fed by 40%-complete effort
data does not produce 40%-accurate answers. It produces confident, precise,
wrong answers — which is strictly worse than no answer, because people act on
them.

---

## Decision

**The system will compute workload, availability and forecasts from data captured
as a side-effect of doing the work — timestamps, state changes and counts — and
will never require typed effort.**

Three consequences follow directly:

1. **Load is measured in items, not hours.** "Rahul has 4 items in progress"
   rather than "Rahul has 26 hours assigned".
2. **Forecasts come from history, not estimates.** "P1 bugs have taken 1–4 days,
   80% within 3" rather than "this is estimated at 6 hours".
3. **Typed effort, if it ever appears, is optional enrichment.** It may improve
   accuracy where present. Nothing may depend on it being there.

The governing principle, which should be applied to every future feature:

> **Derive, don't ask.** If the system needs a number, first try to compute it
> from something the user already does. Only ask when it genuinely cannot be
> derived — and then make answering optional.

---

## Options considered

### Option A — Require estimates and actuals (the original brief)

Ask developers to estimate before and log time after.

- **For:** gives exact hour-level capacity maths; matches the original vision;
  familiar model.
- **Against:** the stakeholder has stated plainly the data will not be entered.
  Every downstream number would be wrong in an invisible, confident way. Adds
  friction at exactly the moment (task creation and completion) where D-005 says
  friction is most damaging.
- **Verdict: rejected.** It requires an input that does not exist.

### Option B — Require estimates only

Estimate up front; skip time logging.

- **For:** half the burden; enough for crude capacity maths.
- **Against:** Q3.6 says estimates specifically would not be entered either. And
  with no actuals, estimates never get corrected — the system cannot learn it is
  wrong, so error compounds silently.
- **Verdict: rejected.**

### Option C — Derive from flow data *(chosen)*

Capture state transitions with timestamps. Derive cycle time, throughput,
work-in-progress and historical distributions from them.

- **For:** the data is a byproduct of using the system at all, so it exists as
  long as anyone uses the product. Cycle time reflects reality *including*
  interruptions, waiting and preemption — which is precisely what estimates
  famously exclude and precisely what causes this organization's delays (K-016).
  Accuracy improves automatically as history accumulates.
- **Against:** needs a few weeks of history before forecasts mean anything.
  Cycle time is not effort — an item "in progress" for three days may be two
  hours of work, so it cannot answer "how many spare hours does Rahul have".
  Depends on state changes being recorded reasonably promptly (R-006).
- **Verdict: chosen.**

### Option D — Lightweight effort capture at completion

Instead of typing hours, one tap at close: *quick / normal / long*.

- **For:** near-zero friction; adds a coarse effort signal.
- **Against:** still an ask, still skippable, and coverage will be partial.
- **Verdict: deferred.** Worth adding later as optional enrichment under the
  "derive, don't ask" principle. Nothing may depend on it.

---

## What survives, and what does not

Mapping the original brief's questions against the chosen substrate:

| Original question | Status | How it is answered now |
|---|---|---|
| Who is working on what? | **Fully** | Assignment records |
| What is assigned to each developer? | **Fully** | Assignment records |
| Who is overloaded? | **Fully** | Items in progress vs their normal level |
| Who is under-utilized? | **Fully** | Same measure, other direction |
| Can X take this task? | **Fully** | Current load vs normal level, plus absence |
| Which work is at risk? | **Fully** | Open longer than similar items usually take, against a client due date |
| When will X be free? | **Approximately** | Historical cycle time of their open items |
| When will this task be done? | **Probabilistically** | "80% of P1 bugs finish within 3 days" |
| Expected project completion | **Probabilistically** | Throughput against remaining item count |
| Which client consumes most capacity? | **Fully** | Item counts and cycle time by client |
| Is the developer on leave? | **Fully** | Leave records (independent of this decision) |
| Best developer for a task? | **Partially** | History with similar work, current load — not skill-scored |
| How many hours capacity does X have? | **Not supported** | Requires effort data that will not exist |
| Will assigning this create an hour-level overlap? | **Redefined** | Overlap becomes "pushes them past their normal item load" |
| Precise ETA in hours | **Not supported** | Replaced by a probability range |

Two capabilities are genuinely lost; both were hour-precision answers. The
replacements are ranges rather than points — which is more honest anyway, since
an hour-precise date derived from guessed estimates was never actually precise.

---

## Consequences

**Positive**

- The system produces useful output from day one of use, with no setup, no
  estimation training, and no behaviour change beyond recording work.
- Its numbers improve on their own as history accumulates.
- It cannot produce the confidently-wrong capacity figures that are the main
  failure mode of tools in this category.
- It reduces, rather than adds to, the burden on the developers whose
  cooperation the whole system depends on (R-003).

**Negative**

- No output worth trusting for roughly 3–4 weeks, until enough items have
  completed to form a history. The Work Register (D-004) is useful immediately,
  which covers this gap.
- Forecasts are ranges with probabilities. Managers used to single dates may
  find this unsatisfying, and it will need explaining in the UI rather than
  hidden behind a number.
- Correctness now depends on state transitions being recorded promptly (R-006).
  Every state change must be one tap.
- "How many hours free is Rahul?" cannot be answered. If a stakeholder demands
  it, this ADR must be revisited rather than quietly worked around.

**Neutral**

- The database must store a full transition history per item (who, what state,
  when), not merely the current state. This is a modest amount of extra storage
  and the source of every derived metric.

---

## Revisit this decision if

- Effort data starts being entered voluntarily and consistently for 2+ months
- A stakeholder with authority requires hour-level capacity and accepts the cost
  of the data entry that makes it possible
- The organization grows past roughly 30–40 developers, where coarse item counts
  may stop being discriminating enough
- C-006 resolves the other way — i.e. Q3.7's "everything to be recorded" did mean
  recording time, not just recording the work item
