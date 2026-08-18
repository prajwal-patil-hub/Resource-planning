"""Finding one piece of work among hundreds (Feature 9).

A record you cannot find again is barely a record, so this is the last thing
standing between the product's promise — nothing is forgotten — and it being
true in practice.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import Client, Team, WorkItemType
from app.work.lifecycle import State
from app.work.search import DEFAULT_LIMIT, search
from app.work.service import assign, create_work_item, transition


def _client(session, name):
    row = session.scalar(select(Client).where(Client.name == name))
    if row is None:
        row = Client(name=name, active=True)
        session.add(row)
        session.flush()
    return row


def _type(session, name):
    row = session.scalar(select(WorkItemType).where(WorkItemType.name == name))
    if row is None:
        row = WorkItemType(name=name, code=name.upper(), active=True, sort_order=99)
        session.add(row)
        session.flush()
    return row


def _item(session, person, title, *, owner=None, client=None, kind=None,
          description=None, done=False, priority=2):
    item = create_work_item(
        session, title=title, created_by_id=person.id, priority=priority,
        description=description,
        client_id=client.id if client else None,
        type_id=kind.id if kind else None,
        owner_id=owner.id if owner else None,
    )
    if done:
        assign(session, item=item, person_id=(owner or person).id, actor_id=person.id)
        transition(session, item=item, to_state=State.IN_PROGRESS, actor_id=person.id)
        transition(session, item=item, to_state=State.DONE, actor_id=person.id)
    return item


def _titles(results):
    return [hit.item.title for hit in results.hits]


# --------------------------------------------------------------------------
# The basics
# --------------------------------------------------------------------------


def test_a_word_from_the_title_finds_it(session, person):
    _item(session, person, "Invoice PDF shows the wrong tax")
    _item(session, person, "Session expires too early")

    assert _titles(search(session, "invoice")) == ["Invoice PDF shows the wrong tax"]


def test_matching_ignores_case(session, person):
    _item(session, person, "SSO login fails intermittently")

    assert search(session, "sso").count == 1
    assert search(session, "SSO").count == 1


def test_a_fragment_of_a_word_matches(session, person):
    """Somebody hunting for a half-remembered item types what they remember.
    "invoi" finding both "invoice" and "invoicing" is the point."""
    _item(session, person, "Invoicing run failed")

    assert search(session, "invoi").count == 1


def test_an_empty_query_finds_nothing_and_says_which_kind_of_nothing(session, person):
    """Distinct from a search that matched nothing. Returning every item for an
    empty box would look like a bug and bury the one thing being looked for."""
    _item(session, person, "Something")

    results = search(session, "   ")

    assert results.empty_query
    assert results.count == 0


def test_a_query_that_matches_nothing_is_not_the_same_as_an_empty_one(session, person):
    _item(session, person, "Something")

    results = search(session, "nothinglikethis")

    assert not results.empty_query
    assert results.count == 0


# --------------------------------------------------------------------------
# Words in any order — how people actually remember work
# --------------------------------------------------------------------------


def test_words_are_matched_in_any_order(session, person):
    """"acme invoice" must find "Invoice PDF is wrong — Acme". A phrase match
    would fail, and people remember a couple of salient words, not a title."""
    acme = _client(session, "Acme Corp")
    _item(session, person, "Invoice PDF is wrong", client=acme)

    assert search(session, "acme invoice").count == 1
    assert search(session, "invoice acme").count == 1


def test_every_word_has_to_match_something(session, person):
    """ANDing rather than ORing. Adding a word must narrow the list, or nobody
    can ever get from forty results to one."""
    acme = _client(session, "Acme Corp")
    _item(session, person, "Invoice PDF is wrong", client=acme)

    assert search(session, "acme invoice").count == 1
    assert search(session, "acme invoice missingword").count == 0


def test_the_words_may_match_different_fields(session, person, other_person):
    acme = _client(session, "Acme Corp")
    _item(session, person, "Export is slow", owner=other_person, client=acme)

    assert search(session, f"acme {other_person.name}").count == 1


# --------------------------------------------------------------------------
# What is searchable
# --------------------------------------------------------------------------


def test_the_client_name_is_searchable(session, person):
    acme = _client(session, "Acme Corp")
    _item(session, person, "Nothing obvious in the title", client=acme)

    assert search(session, "acme").count == 1


def test_the_kind_of_work_is_searchable(session, person):
    bug = _type(session, "Escalation")
    _item(session, person, "Plain title", kind=bug)

    assert search(session, "escalation").count == 1


def test_the_owner_is_searchable(session, person, other_person):
    _item(session, person, "Plain title", owner=other_person)

    assert search(session, other_person.name.lower()).count == 1


def test_the_description_is_searchable(session, person):
    """The details someone filled in later (D-005) are often the only place a
    distinguishing word appears."""
    _item(session, person, "Plain title", description="Caused by the nightly rollup job")

    assert search(session, "rollup").count == 1


def test_an_item_number_goes_straight_to_it(session, person):
    """People quote item numbers to each other constantly."""
    item = _item(session, person, "Some work")
    for index in range(3):
        _item(session, person, f"Other work {index}")

    assert search(session, str(item.id)).hits[0].item.id == item.id
    assert search(session, f"#{item.id}").hits[0].item.id == item.id


def test_a_number_also_still_matches_text(session, person):
    """"42" could be an item number or part of a reference in a title. Matching
    the id *as well as* the text rather than instead of it means neither
    reading loses."""
    numbered = _item(session, person, "CR-42 bulk import")

    found = search(session, "42")

    assert numbered.id in [hit.item.id for hit in found.hits]


# --------------------------------------------------------------------------
# Wildcards in user input — the bug this would otherwise have shipped with
# --------------------------------------------------------------------------


def test_a_percent_sign_is_not_a_wildcard(session, person):
    """Unescaped, searching "50%" matches every item in the database, which
    looks exactly like the search being broken."""
    _item(session, person, "Discount is 50% too high")
    _item(session, person, "Unrelated work")
    _item(session, person, "Also unrelated")

    assert _titles(search(session, "50%")) == ["Discount is 50% too high"]


def test_an_underscore_is_not_a_single_character_wildcard(session, person):
    _item(session, person, "Rename user_id column")
    _item(session, person, "Rename userxid column")

    assert _titles(search(session, "user_id")) == ["Rename user_id column"]


def test_a_backslash_does_not_break_the_query(session, person):
    _item(session, person, "Fix the C:\\temp path handling")

    assert search(session, "C:\\temp").count == 1


# --------------------------------------------------------------------------
# Closed work
# --------------------------------------------------------------------------


def test_finished_work_is_included_by_default(session, person):
    """"What did we do for them last month" is the main reason anyone searches.
    Hiding closed items would look exactly like finding nothing."""
    _item(session, person, "Finished last month", done=True)

    results = search(session, "finished")

    assert results.count == 1
    assert results.hits[0].is_closed


def test_finished_work_can_be_excluded_when_asked(session, person):
    _item(session, person, "Finished last month", done=True)

    assert search(session, "finished", include_closed=False).count == 0


def test_open_work_is_listed_before_finished_work(session, person):
    """Someone searching is usually trying to act on something. Finished work
    is context rather than the answer."""
    _item(session, person, "Export job done", done=True)
    _item(session, person, "Export job still going")

    assert _titles(search(session, "export job"))[0] == "Export job still going"


def test_urgent_work_is_listed_first_within_open_work(session, person):
    _item(session, person, "Export routine", priority=4)
    _item(session, person, "Export outage", priority=0)

    assert _titles(search(session, "export"))[0] == "Export outage"


# --------------------------------------------------------------------------
# Explaining itself (BR-020)
# --------------------------------------------------------------------------


def test_each_result_says_why_it_matched(session, person):
    """A result whose title does not obviously contain the query looks like a
    mistake until you can see it matched on the client instead."""
    acme = _client(session, "Acme Corp")
    _item(session, person, "Nothing obvious in the title", client=acme)

    hit = search(session, "acme").hits[0]

    assert hit.matched_on == ["client"]
    assert hit.why == "matched on client"


def test_matching_several_fields_reports_all_of_them(session, person, other_person):
    acme = _client(session, "Acme Corp")
    _item(session, person, "Acme export", owner=other_person, client=acme)

    hit = search(session, "acme").hits[0]

    assert "title" in hit.matched_on
    assert "client" in hit.matched_on


def test_an_item_found_by_number_says_so(session, person):
    item = _item(session, person, "Some work")

    hit = next(h for h in search(session, f"#{item.id}").hits if h.item.id == item.id)

    assert hit.matched_on[0] == "item number"


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------


def test_results_are_capped_and_the_remainder_is_counted(session, person):
    """A search returning four hundred rows has not answered the question, it
    has moved it. Saying how many were cut tells the reader to narrow rather
    than assume they saw everything."""
    for index in range(DEFAULT_LIMIT + 5):
        _item(session, person, f"Export job {index}")

    results = search(session, "export")

    assert results.count == DEFAULT_LIMIT
    assert results.cut == 5
    assert results.total == DEFAULT_LIMIT + 5


def test_a_smaller_limit_is_respected(session, person):
    for index in range(6):
        _item(session, person, f"Export job {index}")

    results = search(session, "export", limit=2)

    assert results.count == 2
    assert results.cut == 4


# --------------------------------------------------------------------------
# Scoping (RULE-011)
# --------------------------------------------------------------------------


def test_results_are_scoped_to_the_teams_the_viewer_can_see(session, person, other_person):
    _item(session, person, "Export mine", owner=person)
    _item(session, person, "Export theirs", owner=other_person)

    other_team = session.scalar(select(Team.id).where(Team.id != person.team_id).limit(1))
    other_person.team_id = other_team
    session.flush()

    assert search(session, "export").count == 2
    assert _titles(search(session, "export", team_ids=[person.team_id])) == ["Export mine"]


def test_unowned_work_is_always_findable(session, person):
    """Nobody has picked it up, so it belongs to everyone — the same rule the
    board uses."""
    _item(session, person, "Export nobody took")

    assert search(session, "export", team_ids=[person.team_id]).count == 1
