# Build Status — what is actually built

**Date:** 2026-08-16
**Question answered:** "Is everything built?"
**Short answer:** No. Roughly **45%** of the v1 scope defined in `03-brd.md`.

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

| | Count |
|---|---|
| Built | 11 |
| Partial | 6 |
| Not built | 8 |
| **Total v1 business requirements** | **25** |

Of the seven domain services designed in `08-domain-model.md`, **one and a half
exist**: `LoadService`, and the explanation half of `ExplanationService`.
`RiskService`, `StalenessService`, `FlowStatisticsService`, `AvailabilityService`
and `CoverService` are unwritten.

---

## Requirement by requirement

### Recording work

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-001 | Durable record of incoming work | **Built** | |
| BR-002 | Recording faster than telling a colleague | **Built** | Title-only composer |
| BR-003 | Recordable before it has an owner | **Built** | |
| BR-004 | Recording late is normal, not an error | **Partial** | The API accepts a backdated time; **the UI has no way to enter one**. A developer catching up at 6pm cannot say when it actually happened — so every catch-up entry silently records the wrong time, which is precisely what the two-timestamp design was built to avoid |
| BR-005 | Work is never destroyed, only cancelled | **Built** | |

### Making work visible

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-006 | Exactly one accountable owner, or visibly unowned | **Built** | |
| BR-007 | Stalled work becomes visible without searching | **Partial** | A `stalled` flag shows in the table view only. Nothing surfaces it to a lead who has not gone looking — which is the actual requirement (BO-2) |
| BR-008 | Workload visible to the team | **Built** | |
| BR-009 | Displacement recorded with its cause | **Built** | |
| BR-010 | Waiting-on-client distinguishable from waiting-on-us | **Built** | |
| BR-011 | Work awaiting verification visible | **Built** | |

### People and availability

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-012 | Absence recordable and visible | **Not built** | Table and the overlap constraint exist; there is no way to enter absence. The load strip's "away" state can therefore never appear |
| BR-013 | Absent owner's work surfaced for cover | **Not built** | `CoverService` unwritten. **BO-3 is entirely unmet** |
| BR-014 | Non-working days excluded from elapsed time | **Not built** | Table exists and is empty; weekends and holidays currently inflate every duration |
| BR-015 | Reassignment preserves ownership history | **Built** | |

### Decision support

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-016 | See load and absence before assigning | **Partial** | Load is on the strip, not at the moment of assignment. The assign dropdown shows names with no context |
| BR-017 | Work at risk of missing its due date, flagged early | **Not built** | `RiskService` unwritten. Overdue is shown; *at risk before the date* is not |
| BR-018 | Timing as a range with confidence, never a false date | **Not built** | `FlowStatisticsService` unwritten. **BO-6 is entirely unmet** |
| BR-019 | Where effort goes, by client and by type | **Not built** | Data exists; no report |
| BR-020 | Every displayed number is explainable | **Partial** | Load carries its derivation, the timeline carries per-measure notes. Not yet systematic |

### Operating constraints

| ID | Requirement | Status | Note |
|---|---|---|---|
| BR-021 | Usable immediately, no configuration | **Built** | |
| BR-022 | Useful output without estimates or timesheets | **Built** | |
| BR-023 | Work types extensible without a code change | **Partial** | Reference table exists; adding one needs SQL |
| BR-024 | Roles addable and placeable in the hierarchy | **Partial** | Same — table exists, no UI |
| BR-025 | Access governed by role and team | **Not built** | No authentication at all. The `access` module is a stub |

---

## Gaps that are not business requirements but block a pilot

| Gap | Why it blocks |
|---|---|
| **No authentication** | Every record claims to be created by person #1. Nothing is attributable, so the audit trail — the product's whole foundation — is currently fiction |
| **No way to edit a work item** | Title, priority, client, type and due date cannot be changed after creation. This contradicts D-005 directly: the design says "everything else is optional and addable later", and there is no later. It also means the field-history trigger built for ADR-003 **can never fire from the UI** |
| **No people or team management** | Adding a person requires SQL |
| **No client or work-type management** | Same |
| **No text search** | At a few hundred items, finding one becomes guesswork |
| **No deployment configuration** | No HTTPS, no backups, no process supervision, no restore procedure |

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

| # | Feature | Closes | Why this order |
|---|---|---|---|
| **1** | **Edit a work item** | BR-004 UI, D-005 | The design's central promise is currently unkeepable. Smallest gap, largest contradiction |
| **2** | **Authentication and people management** | BR-025, BR-024 | Until this exists, nothing in the audit trail is true. Everything downstream inherits that |
| **3** | **Absence and non-working days** | BR-012, BR-013, BR-014 | Unlocks BO-3 entirely, and stops weekends inflating every duration |
| **4** | **Attention view — stalled, unowned, uncovered** | BR-007, BR-016 | Makes the system tell you rather than wait to be asked. This is the daily-use screen |
| **5** | **Flow statistics and risk** | BR-017, BR-018 | Needs ~3–4 weeks of history to mean anything, so build it early and let it fill |
| **6** | **Reporting by client and type** | BR-019 | The manager-facing view. Depends on 5 |
| **7** | **Reference data management** | BR-023 | Small |
| **8** | **Search** | — | Small |
| **9** | **Deployment, backups, restore** | — | Last, but before any real data exists |

Items 1–4 are what a pilot genuinely needs. Items 5–6 are what make it worth
keeping after the first month.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-16 | First audit, against BRD v1.1 and the running code |
