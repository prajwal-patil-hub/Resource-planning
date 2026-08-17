# ADR-005 — Forecast from percentiles of past work, and refuse below a minimum sample

**Status:** ACCEPTED
**Date:** 2026-08-16
**Supersedes:** nothing
**Depends on:** ADR-001 (derive workload from flow data, not typed effort)

---

## What an ADR is

An *Architecture Decision Record* is one file per significant decision. It
captures the context at the time, the options that were genuinely considered,
what was chosen, what that costs, and what would make us revisit it. It is never
edited to look wiser later and never deleted — a decision that turned out badly
is more useful to a future reader than one quietly removed.

---

## Context

ADR-001 established the governing constraint: **nobody will enter an estimate**
(K-019). No story points, no hours, no "this'll take three days". That decision
is what makes this product buildable at all, because it asks nothing of people
beyond recording that work exists and moving it along.

It also leaves an obligation. BO-6 — the business objective this closes — says
the product must answer *"when will this be done?"* in a form a client can be
told. With no estimates, the only material available is the record of how long
comparable work has actually taken.

That raises three questions this ADR answers:

1. **Which statistic** describes "how long work takes"?
2. **What shape** should the answer take — a date, a range, something else?
3. **What happens when there is not enough history**, which is the state the
   product will be in for its first month of use?

---

## Terms used here

- **Cycle time** — how long one item took from first recorded to finished,
  counting only working time and excluding stretches spent waiting on the
  client. Distinct from *lead time*, which is what the client experienced.
- **Percentile** — the value below which a given share of observations fall.
  The 85th percentile of cycle time is the duration that 85% of finished items
  came in under.
- **Right-skewed** — a distribution where most values cluster low and a few
  stretch far high. Cycle times are almost always right-skewed.
- **Cohort** — the set of past items being treated as comparable to the one
  being forecast.

---

## Decision 1 — percentiles, not averages

**Chosen:** report the median (50th) and the 85th percentile, and show the
slowest observation alongside them.

The mean is the intuitive choice and the wrong one. Cycle times are
right-skewed: most items finish quickly, a few drag on for weeks because the
client went quiet or the fix turned out to sit under something else. A single
60-day item among nine 1-day items produces a mean of 6.9 days — a number
higher than 90% of the work and lower than the outlier. It describes nothing
that ever happened.

The median survives that outlier untouched. The 85th percentile moves with the
tail without being captured by it, which is exactly the property a planning
number needs.

| Option | Why not |
|---|---|
| Mean cycle time | One slow item distorts it; the result describes no real case |
| Mean plus standard deviation | Assumes a normal distribution the data does not have. A "mean ± 2σ" range on skewed data produces negative lower bounds |
| Median alone | Half of all work exceeds it. Planning against it guarantees missing half the time |
| **Median and 85th percentile** | **Chosen.** One number for "usually", one to plan against, both real observations |

**Nearest-rank, not interpolated.** With eight observations, interpolating
between the sixth and seventh manufactures a precision the sample does not
contain. Every percentile this product reports is a duration that some real item
actually took.

---

## Decision 2 — a range with a stated confidence, never a date

**Chosen:** the product never converts a forecast into a calendar date.

RULE-010 already required ranges; this makes it structural. "About three
working days left" is not turned into "Thursday" anywhere in the system, and
there is a test asserting no forecast field is ever a date.

The reason is what the two forms do to a reader. A range invites judgement and
can be checked afterwards: *"85% of work like this finished within four working
days"* is either true of the next twenty items or it is not. A date invites
belief, and when it slips there is nothing to inspect — only a broken promise.
Given K-023, where due dates arrive **from** clients rather than being set by
us, the product's job is to evaluate a date somebody else chose, not to invent
one of its own.

Confidence is stated in words tied to sample size — "low, treat as indicative",
"fair", "good" — rather than as a percentage. A percentage would imply an
interval calculation this sample size cannot support, which would be the same
false precision in different clothing.

---

## Decision 3 — refuse below a minimum sample (RULE-013)

**Chosen:** with fewer than **8** comparable finished items, the product says it
does not yet know, states how many more are needed, and offers no number.

This is the decision most likely to be argued with, so the reasoning is worth
setting out plainly.

A forecast from three items is an anecdote wearing a statistic's clothes. It
will look identical to a well-founded one — same layout, same confident
typography — and the reader has no way to tell them apart. The first time it is
badly wrong, the damage is not confined to that number: it discredits the load
figures, the cycle-time report, and the attention list, none of which deserved
it. BR-020 exists because a number a lead cannot interrogate will not be
trusted; a number that was never interrogable in the first place is worse.

Eight is chosen because it is the point where the 85th percentile stops being
the single slowest observation and becomes the second-slowest — so one unusual
item can no longer define the entire upper bound on its own. For a team
recording twenty to forty items a month it is reachable within three to four
weeks.

**Consequence accepted:** the product ships with this feature visibly empty and
fills itself over the first month. That is a real cost at pitch time, and it is
the right trade. A system that admits what it does not know earns the right to
be believed about what it does.

---

## Decision 4 — widen the cohort rather than give up

"Comparable" is a judgement. Narrowing it (same type *and* same priority)
improves relevance and destroys sample size; widening it does the reverse.
Rather than pick one compromise, the product walks a ladder:

1. same work type, same priority
2. same work type
3. all finished work

It stops at the first rung with enough data, **and always says which rung it
landed on**. An answer drawn from "Bug at P1" and one drawn from "all finished
work" warrant different amounts of trust, and the reader cannot tell them apart
unless told.

---

## Consequences

**Good**
- Answers cost nobody any effort to produce — they are a byproduct of recording,
  exactly as ADR-001 intended.
- The numbers improve on their own as the team uses the system.
- Every figure is traceable to the items it came from (BR-020).
- The product cannot produce a confidently wrong date, because it produces no
  dates.

**Bad, and accepted**
- Empty for the first three to four weeks of real use.
- Cannot forecast a genuinely novel kind of work — it will fall back to "all
  finished work" and say so, which is honest but blunt.
- Cycle time from the event log inherits whatever the log gets wrong. This is
  precisely why backdated recording (BR-004) was built **before** this feature
  rather than after — see D-032.

**Load-bearing assumption**
- That recording is consistent enough for the sample to represent reality. If
  half the work never gets recorded, these numbers describe the recorded half
  only. Nothing in the statistics can detect that, which is why recording
  friction (rule 14) remains the risk the whole product is judged against.

---

## What would make us revisit this

- **Sample size stops being the constraint.** With a year of history, a proper
  interval estimate becomes defensible and the word-based confidence could be
  replaced with a calculated one.
- **The team starts estimating anyway.** If estimates ever arrive voluntarily
  and prove accurate, they become a second signal to weigh against history —
  never a replacement for it, per ADR-001.
- **Cycle time turns out to be multi-modal** — for instance if "bug" covers both
  ten-minute config fixes and three-week investigations. The fix then is a
  better cohort key, not a better statistic.
- **Someone asks for a date and will not accept a range.** That is a real
  conversation to have with a stakeholder, not something to resolve by quietly
  adding a date field.
