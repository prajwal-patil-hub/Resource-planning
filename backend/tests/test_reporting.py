"""Where the work goes, by client and by kind (BR-019).

The manager-facing report. Its central risk is not a wrong number but a
misread one: every percentage next to a client name invites being read as a
share of the team's cost, and under ADR-001 no such figure exists.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.flow.calendar import WorkingCalendar
from app.flow.reporting import build_client_reports, by_type_totals
from app.flow.statistics import MIN_SAMPLE, collect_samples
from app.models import Client, Team, WorkItemType
from app.work.lifecycle import State
from app.work.service import assign, create_work_item, transition

ALWAYS = WorkingCalendar(weekend_days=frozenset(), holidays=frozenset())


def _client(session, name):
    existing = session.scalar(select(Client).where(Client.name == name))
    if existing:
        return existing
    row = Client(name=name, active=True)
    session.add(row)
    session.flush()
    return row


def _type(session, name):
    existing = session.scalar(select(WorkItemType).where(WorkItemType.name == name))
    if existing:
        return existing
    row = WorkItemType(name=name, active=True, sort_order=99)
    session.add(row)
    session.flush()
    return row


def _finish(session, person, *, title, days, client=None, type_row=None, client_wait_days=0):
    start = datetime.now(UTC) - timedelta(days=days + 1)
    item = create_work_item(
        session, title=title, created_by_id=person.id, occurred_at=start,
        client_id=client.id if client else None,
        type_id=type_row.id if type_row else None,
    )
    assign(session, item=item, person_id=person.id, actor_id=person.id, occurred_at=start)
    transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
               occurred_at=start)
    if client_wait_days:
        transition(session, item=item, to_state=State.BLOCKED_ON_CLIENT, actor_id=person.id,
                   occurred_at=start)
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id,
                   occurred_at=start + timedelta(days=client_wait_days))
    transition(session, item=item, to_state=State.DONE, actor_id=person.id,
               occurred_at=start + timedelta(days=days))
    return item


def _report(session, **kw):
    return build_client_reports(session, collect_samples(session, ALWAYS), **kw)


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


def test_finished_work_is_attributed_to_its_client(session, person):
    acme = _client(session, "Acme Ltd")
    _finish(session, person, title="Their bug", days=2, client=acme)

    report = _report(session)
    row = next(r for r in report.reports if r.name == "Acme Ltd")

    assert row.finished == 1
    assert report.total_items == 1


def test_work_with_no_client_is_a_category_not_a_blank(session, person):
    """Internal work is real and often substantial. Hiding it under an empty
    label would conceal how much of the team's time never reaches a client."""
    _finish(session, person, title="Upgrade the build", days=1)

    row = _report(session).reports[0]

    assert row.client_id is None
    assert row.name == "No client — internal"


def test_share_is_a_share_of_items_and_says_so(session, person):
    acme = _client(session, "Acme Ltd")
    northwind = _client(session, "Northwind")
    for index in range(3):
        _finish(session, person, title=f"Acme {index}", days=1, client=acme)
    _finish(session, person, title="Northwind one", days=1, client=northwind)

    report = _report(session)
    acme_row = next(r for r in report.reports if r.name == "Acme Ltd")

    assert abs(acme_row.share_of(report.total_items) - 0.75) < 0.001
    explanation = acme_row.explanation(report.total_items)
    assert "3 of 4 finished item(s)" in explanation
    # The sentence that stops the number being misread as person-hours.
    assert "not person-hours" in explanation


def test_the_busiest_client_is_listed_first(session, person):
    quiet = _client(session, "Quiet Co")
    busy = _client(session, "Busy Co")
    _finish(session, person, title="One", days=1, client=quiet)
    for index in range(4):
        _finish(session, person, title=f"Many {index}", days=1, client=busy)

    assert _report(session).reports[0].name == "Busy Co"


# --------------------------------------------------------------------------
# The split that makes the page worth having (RULE-005)
# --------------------------------------------------------------------------


def test_time_waiting_on_the_client_is_reported_separately(session, person):
    """A client whose work takes three weeks, two of which are their own
    silence, is a different conversation from one whose work takes three weeks
    of ours — and both looked identical before this."""
    slow = _client(session, "Slow To Reply")
    _finish(session, person, title="Needs their answer", days=10,
            client=slow, client_wait_days=7)

    row = next(r for r in _report(session).reports if r.name == "Slow To Reply")

    assert abs(row.total_elapsed - timedelta(days=10)) < timedelta(minutes=2)
    assert abs(row.theirs - timedelta(days=7)) < timedelta(minutes=2)
    assert abs(row.ours - timedelta(days=3)) < timedelta(minutes=2)
    assert row.their_share > 0.65


def test_a_responsive_client_shows_no_waiting_time(session, person):
    quick = _client(session, "Answers Fast")
    _finish(session, person, title="Straight through", days=4, client=quick)

    row = next(r for r in _report(session).reports if r.name == "Answers Fast")

    assert row.theirs == timedelta()
    assert row.their_share == 0.0


def test_the_overall_waiting_share_is_the_weighted_total(session, person):
    a = _client(session, "A")
    b = _client(session, "B")
    _finish(session, person, title="Waits", days=10, client=a, client_wait_days=5)
    _finish(session, person, title="Does not wait", days=10, client=b)

    report = _report(session)

    # 5 of 20 elapsed days were client wait.
    assert 0.2 < report.overall_their_share < 0.3


def test_the_split_never_exceeds_the_whole(session, person):
    acme = _client(session, "Acme Ltd")
    _finish(session, person, title="Mixed", days=6, client=acme, client_wait_days=2)

    row = _report(session).reports[0]

    assert row.ours + row.theirs <= row.total_elapsed + timedelta(seconds=2)
    assert 0.0 <= row.their_share <= 1.0


# --------------------------------------------------------------------------
# RULE-013 reaches here too
# --------------------------------------------------------------------------


def test_a_per_client_cycle_time_is_withheld_below_the_minimum_sample(session, person):
    """A median drawn from two items is an anecdote whether it sits on the
    forecasting page or this one."""
    acme = _client(session, "Acme Ltd")
    for index in range(2):
        _finish(session, person, title=f"Only two {index}", days=3, client=acme)

    row = _report(session).reports[0]

    assert row.finished == 2
    assert not row.cohort.is_sufficient


def test_a_per_client_cycle_time_appears_once_there_is_enough(session, person):
    acme = _client(session, "Acme Ltd")
    for index in range(MIN_SAMPLE):
        _finish(session, person, title=f"Plenty {index}", days=3, client=acme)

    row = _report(session).reports[0]

    assert row.cohort.is_sufficient
    assert abs(row.cohort.percentile(0.5) - timedelta(days=3)) < timedelta(minutes=5)


# --------------------------------------------------------------------------
# Open work — what a client is costing right now
# --------------------------------------------------------------------------


def test_open_work_is_counted_separately_from_history(session, person):
    """History says what a client has cost; open work says what they are
    costing now. A manager needs both and they are not the same question."""
    acme = _client(session, "Acme Ltd")
    _finish(session, person, title="Done for them", days=2, client=acme)
    create_work_item(session, title="Still going", created_by_id=person.id,
                     client_id=acme.id)

    row = next(r for r in _report(session).reports if r.name == "Acme Ltd")

    assert row.finished == 1
    assert row.open_now == 1


def test_a_client_with_only_open_work_still_appears(session, person):
    """Otherwise a client who has sent plenty and had nothing finished yet is
    invisible on the one page meant to show demand."""
    newcomer = _client(session, "Brand New")
    create_work_item(session, title="First job", created_by_id=person.id,
                     client_id=newcomer.id)

    row = next(r for r in _report(session).reports if r.name == "Brand New")

    assert row.finished == 0
    assert row.open_now == 1


# --------------------------------------------------------------------------
# Scoping (RULE-011)
# --------------------------------------------------------------------------


def test_the_report_is_scoped_to_the_teams_the_viewer_can_see(session, person, other_person):
    """A client report names commercial volumes, so it follows the same
    visibility rule as the work it is built from."""
    acme = _client(session, "Acme Ltd")
    _finish(session, person, title="Mine", days=1, client=acme)
    _finish(session, other_person, title="Theirs", days=1, client=acme)

    # Move the second person out of the team after the fact, the way someone
    # changing teams while holding work actually does.
    other_team = session.scalar(select(Team.id).where(Team.id != person.team_id).limit(1))
    other_person.team_id = other_team
    session.flush()

    everything = _report(session)
    scoped = _report(session, team_ids=[person.team_id])

    assert everything.total_items == 2
    assert scoped.total_items == 1


def test_unowned_open_work_stays_visible_in_a_narrowed_view(session, person):
    """Consistent with the board: work nobody has picked up is everyone's
    problem, and hiding it from a narrowed view would hide the worst case.

    Note this can only apply to *open* work. A finished item always had an
    owner — INV-6 forbids work being in progress with nobody accountable, and
    DONE is only reachable through it."""
    acme = _client(session, "Acme Ltd")
    create_work_item(session, title="Nobody took it", created_by_id=person.id,
                     client_id=acme.id)

    scoped = _report(session, team_ids=[person.team_id])

    assert scoped.scoped is True
    assert next(r for r in scoped.reports if r.name == "Acme Ltd").open_now == 1


def test_open_work_is_scoped_the_same_way_finished_work_is(session, person, other_person):
    """Otherwise one row would put two different populations side by side —
    finished counts narrowed to your teams, open counts spanning the whole
    organisation — which is worse than either alone."""
    acme = _client(session, "Acme Ltd")
    other_team = session.scalar(select(Team.id).where(Team.id != person.team_id).limit(1))

    item = create_work_item(session, title="Owned elsewhere", created_by_id=person.id,
                            client_id=acme.id, owner_id=other_person.id)
    other_person.team_id = other_team
    session.flush()

    everything = _report(session)
    scoped = _report(session, team_ids=[person.team_id])

    assert next(r for r in everything.reports if r.name == "Acme Ltd").open_now == 1
    assert not any(r.name == "Acme Ltd" and r.open_now for r in scoped.reports)


def test_an_unscoped_report_says_it_is_unscoped(session, person):
    """The page renders a warning when the totals are partial, so the flag has
    to be right or the warning appears when it should not."""
    assert _report(session).scoped is False


# --------------------------------------------------------------------------
# By kind of work
# --------------------------------------------------------------------------


def test_work_is_also_broken_down_by_kind(session, person):
    bug = _type(session, "Bug")
    change = _type(session, "Change Request")
    for index in range(3):
        _finish(session, person, title=f"Bug {index}", days=1, type_row=bug)
    _finish(session, person, title="A CR", days=5, type_row=change)

    samples = collect_samples(session, ALWAYS)
    rows = by_type_totals(samples, {bug.id: "Bug", change.id: "Change Request"})

    assert rows[0][0] == "Bug"
    assert rows[0][1] == 3
    assert rows[1][1] == 1


def test_the_mix_shows_what_a_client_actually_sends(session, person):
    """A client sending mostly bugs is a different relationship from one
    sending mostly change requests, whatever the totals say."""
    acme = _client(session, "Acme Ltd")
    bug = _type(session, "Bug")
    change = _type(session, "Change Request")
    for index in range(3):
        _finish(session, person, title=f"Bug {index}", days=1, client=acme, type_row=bug)
    _finish(session, person, title="One CR", days=2, client=acme, type_row=change)

    row = next(r for r in _report(session).reports if r.name == "Acme Ltd")

    assert row.mix["Bug"] == 3
    assert row.mix["Change Request"] == 1
    assert row.mix_summary.startswith("Bug ×3")


def test_an_empty_report_does_not_divide_by_zero(session):
    report = _report(session)

    assert report.total_items == 0
    assert report.overall_their_share == 0.0


def test_the_waiting_figure_is_shown_however_small_the_sample(session, person):
    """A measurement, not an inference. "Of the 12 days these items were alive,
    7 were client wait" is simply true whatever the count — unlike a percentile,
    which estimates a distribution and needs RULE-013."""
    acme = _client(session, "Acme Ltd")
    _finish(session, person, title="Only one", days=10, client=acme, client_wait_days=6)

    row = next(r for r in _report(session).reports if r.name == "Acme Ltd")

    assert not row.cohort.is_sufficient      # too few for a cycle time
    assert row.their_share > 0.5             # but the split is still real
