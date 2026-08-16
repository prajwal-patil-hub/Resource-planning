# Build Status — what is actually built

**Date:** 2026-08-16 (revised after Feature 5)
**Question answered:** "Is everything built?"
**Short answer:** Not yet, but close. Roughly **86%** of the v1 scope defined in
`03-brd.md`, up from 45% at the first audit.

This document exists because "is it done?" deserves a measured answer rather
than an impression. Every business requirement from the BRD is listed with its
real state, verified against the running code — not from memory.

**Status meanings**

| | |
|---|---|
| **Built** | Works end to end, has a test, reachable from the UI |
| **Partial** | Exists in the backend but unreachable, incomplete, or missing its UI |
| **Not built** | No implementation |

---

## Scorecard

| | Count | Was (first audit) |
|---|---|---|
| Built | 19 | 11 |
| Partial | 4 | 6 |
| Not built | 2 | 8 |
| **Total v1 business requirements** | **25** | 25 |

Of the seven domain services designed in `08-domain-model.md`, **four and a half
now exist**: `LoadService`, `AvailabilityService` (`people/absence.py` plus the
working calendar), `CoverService` (`uncovered_work`), `StalenessService`
(`flow/attention.py`), and the explanation half of `ExplanationService`.
`RiskService` exists in date-driven form only, and `FlowStatisticsService`
is still unwritten — which is why BO-6 remains the largest single gap.

**Test count:** 128, all passing against real PostgreSQL 16.

---

## Requirement by requirement

### Recording work

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-001 | Durable record of incoming work | **Built** | |
| BR-002 | Recording faster than telling a colleague | **Built** | Title-only composer |
| BR-003 | Recordable before it has an owner | **Built** | |
| BR-004 | Recording late is normal, not an error | **Built** | A "when did this happen?" control on the composer, the move form and the assign form, collapsed by default so the fast path is untouched. Reads the browser's timezone offset rather than assuming UTC. Refused beyond 14 days back or any time in the future (RULE-016). Backdated entries are labelled as such on the timeline |
| BR-005 | Work is never destroyed, only cancelled | **Built** | |

### Making work visible

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-006 | Exactly one accountable owner, or visibly unowned | **Built** | |
| BR-007 | Stalled work becomes visible without searching | **Built** | `/attention` — "Needs me" in the topbar. Counts working days only, and excludes client-blocked work so the list stays all-signal |
| BR-008 | Workload visible to the team | **Built** | |
| BR-009 | Displacement recorded with its cause | **Built** | |
| BR-010 | Waiting-on-client distinguishable from waiting-on-us | **Built** | |
| BR-011 | Work awaiting verification visible | **Built** | |

### People and availability

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-012 | Absence recordable and visible | **Built** | `/absence`. Last day is inclusive; overlaps refused by an `EXCLUDE` constraint rather than a read-then-write check; cancelled never deleted |
| BR-013 | Absent owner's work surfaced for cover | **Built** | Top of `/absence` and the "Owner is away" group on `/attention`. **BO-3 met** |
| BR-014 | Non-working days excluded from elapsed time | **Built** | Working calendar with **three** day states — worked, optional, never. Optional days (Saturdays) count only where activity was actually recorded, resolved per person |
| BR-015 | Reassignment preserves ownership history | **Built** | |

### Decision support

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-016 | See load and absence before assigning | **Built** | The assignee dropdown reads "Priya — 1 of 2, 1 waiting · free" and groups anyone away under "Away today — back 20 Aug". Each option carries its derivation on hover (BR-020). It does not rank and does not refuse: work is often queued for someone due back |
| BR-017 | Work at risk of missing its due date, flagged early | **Partial** | "Going to miss its date" is live on `/attention` — due within two working days and not started. It is driven by the due date alone; it does not yet use how long this kind of work has historically taken, which is the stronger form of the requirement |
| BR-018 | Timing as a range with confidence, never a false date | **Not built** | `FlowStatisticsService` unwritten. **BO-6 remains unmet** |
| BR-019 | Where effort goes, by client and by type | **Not built** | Data exists; no report |
| BR-020 | Every displayed number is explainable | **Partial** | Load, the timeline, cover, every attention flag and now every assignee option carry their derivation. The table and board columns still show bare counts |

### Operating constraints

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-021 | Usable immediately, no configuration | **Built** | |
| BR-022 | Useful output without estimates or timesheets | **Built** | |
| BR-023 | Work types extensible without a code change | **Partial** | Reference table exists; adding one needs SQL |
| BR-024 | Roles addable and placeable in the hierarchy | **Partial** | Same — table exists, no UI |
| BR-025 | Access governed by role and team | **Built** | bcrypt passwords, server-side revocable sessions (token hash stored, never the token), lockout after repeated failures, first-run bootstrap, permission matrix in `access.py`. Cross-team assignment is now refused at the point of assignment (RULE-017), and the load strip no longer leaks other teams |

---

## Gaps that are not business requirements but block a pilot

Closed since the first audit: authentication, editing a work item, people and
team management, backdated recording, assignment context, cross-team
enforcement. What is left:

| Gap | Why it blocks |
|---|---|
| **No forecasting** | BR-018. `FlowStatisticsService` is unwritten, so **BO-6 is the last unmet business objective**. Now unblocked: the timestamps it would read are finally trustworthy |
| **No reporting by client or type** | BR-019. The data exists; the manager-facing view does not |
| **No client or work-type management** | Adding either still requires SQL |
| **No self-service password reset** | A lead must reset for you |
| **No text search** | At a few hundred items, finding one becomes guesswork |
| **No deployment configuration** | No HTTPS, no backups, no process supervision, no restore procedure |
| **Background image not chosen** | ADR-004 left it as one CSS property; it is still the placeholder |

---

## What this means for the pitch

The stakeholder's position is recorded and accepted: the pitch happens when the
product is complete enough to justify a manager's time. **ASM-2 stays open and
load-bearing until then**, and that is a deliberate, informed choice rather than
an oversight.

One factual note for planning, not an argument: the app currently runs with
realistic demo data, so it *can* be shown at any point. Whether that is worth
doing is the stakeholder's call.

---

## Ordered plan to "complete enough to pilot"

Sequenced by dependency and by risk, not by ease.

| # | Feature | Closes | Status | Why this order |
|---|---|---|---|---|
| **1** | **Edit a work item** | BR-004 UI, D-005 | **Done** | The design's central promise was unkeepable. Smallest gap, largest contradiction |
| **2** | **Authentication and people management** | BR-025, BR-024 | **Done** | Until this existed, nothing in the audit trail was true |
| **3** | **Absence and non-working days** | BR-012, BR-013, BR-014 | **Done** | Unlocked BO-3, and stopped weekends inflating every duration |
| **4** | **Attention view — stalled, unowned, uncovered** | BR-007 | **Done** | Makes the system tell you rather than wait to be asked. The daily-use screen |
| **5** | **Recording context: backdating + assign-time load** | BR-004, BR-016, RULE-016, RULE-017 | **Done** | Both are one-screen changes, and the first protects the integrity of every number in features 6–7. Promoted above forecasting for that reason |
| **6** | **Flow statistics and forecasting** | BR-017, BR-018 | ← **next** | Needs ~3–4 weeks of history to mean anything, so build it early and let it fill. **Closes BO-6, the last unmet business objective** |
| **7** | **Reporting by client and type** | BR-019 | | The manager-facing view. Depends on 6 |
| **8** | **Reference data management** | BR-023 | | Small |
| **9** | **Search** | — | | Small |
| **10** | **Deployment, backups, restore** | — | | Last, but before any real data exists |

**Why 5 was promoted above forecasting.** The original plan put flow statistics
next. That order was wrong on reflection, and the reason is worth stating: ADR-001
committed this product to deriving every number from recorded flow data instead
of asking for estimates. A forecast built on timestamps that are systematically
wrong — because everyone recording at 6pm stamps 6pm — is not a weak forecast,
it is a confident false one, which is the exact failure ADR-001 was written to
avoid. Fix the input before building the thing that consumes it.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-16 | First audit, against BRD v1.1 and the running code |
| 1.1 | 2026-08-16 | Re-audited after Features 1–4. 11→17 built, 8→2 unbuilt. Plan re-ordered: recording context promoted above forecasting, with the reason recorded |
| 1.2 | 2026-08-16 | Feature 5 built. BR-004 and BR-016 closed; RULE-016 and RULE-017 added. 17→19 built. Two defects found while verifying and fixed: the load strip leaked every team's load to a single-team user, and cancelled absences still counted as away |
