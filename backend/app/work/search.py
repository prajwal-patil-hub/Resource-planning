"""Finding one piece of work among hundreds.

The board and the table only help someone who already knows roughly where to
look. Past a few hundred items — which this team reaches inside a year — "the
invoice thing for Acme" becomes a scrolling exercise, and the product's own
promise (BR-001, nothing is forgotten) quietly stops being true in practice:
a record you cannot find again is barely a record.

**Why this is substring matching and not full-text search.**

PostgreSQL's `tsvector` machinery is the reflexive answer and it is the wrong
one here (working agreement 10: the simplest thing that meets the requirement).
The real numbers: roughly ten developers recording thirty to forty items a
month, so a few hundred rows in year one and a few thousand by year five. A
substring scan over a few thousand short titles is sub-millisecond, while
full-text search would add a maintained `tsvector` column, a trigger to keep it
current, and stemming behaviour that surprises people — searching "SSO" and
being shown "sso" is welcome, searching "invoicing" and silently also matching
"invoiced" is harder to explain when someone is hunting for one specific item.

**The seam, recorded so nobody has to re-derive it:** if `work_item` passes
roughly fifty thousand rows, or people start complaining that typos find
nothing, replace the `ilike` conditions built in `search()` with a `pg_trgm`
GIN index (handles both) or a `tsvector` column (handles neither typos nor
substrings, but ranks better). Nothing outside this module changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models import Client, Person, WorkItem, WorkItemParticipant, WorkItemType
from app.work.lifecycle import TERMINAL, State

#: Most results anyone will read. A search returning four hundred rows has not
#: answered the question; it has moved it. The count of what was cut is shown so
#: the reader knows to narrow rather than assuming they saw everything.
DEFAULT_LIMIT = 40

#: Matched against the whole query to spot "#42" or "42" — people quote item
#: numbers to each other constantly, and typing one should go straight there.
_ID_ONLY = re.compile(r"^#?(\d{1,9})$")


@dataclass
class Hit:
    """One result, with the reason it is one."""

    item: WorkItem
    owner_name: str | None
    client_name: str | None
    type_name: str | None
    #: Which fields the search terms were found in. BR-020 applied to a list:
    #: a result whose title does not obviously contain the query looks like a
    #: mistake until you can see it matched on the client or the owner.
    matched_on: list[str] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        return State(self.item.state) in TERMINAL

    @property
    def why(self) -> str:
        if not self.matched_on:
            return ""
        return "matched on " + ", ".join(self.matched_on)


@dataclass
class SearchResults:
    query: str
    terms: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    #: How many matched beyond the limit, so "40 results" is never mistaken for
    #: "all of them".
    cut: int = 0
    #: True when the query was empty — distinct from finding nothing.
    empty_query: bool = True

    @property
    def count(self) -> int:
        return len(self.hits)

    @property
    def total(self) -> int:
        return self.count + self.cut


def _escape(term: str) -> str:
    """Neutralise LIKE wildcards in user input.

    Without this, searching for "50%" matches every item in the database and
    searching for "a_b" matches "axb" — both baffling, and the first looks like
    the search is simply broken.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _terms(query: str) -> list[str]:
    """Split into words, each of which must match somewhere.

    ANDing the words rather than matching the phrase means "acme invoice" finds
    "Invoice PDF is wrong — Acme", which is how people actually remember work:
    a couple of salient words in no particular order.
    """
    return [word for word in re.split(r"\s+", query.strip()) if word]


def search(
    session: Session,
    query: str,
    *,
    team_ids: list[int] | None = None,
    include_closed: bool = True,
    limit: int = DEFAULT_LIMIT,
) -> SearchResults:
    """Find work by title, description, client, kind, owner or number.

    Closed work is included by default and deliberately: "what did we do for
    them last month" is the main reason anyone searches, and hiding finished
    items would make the feature useless for its most common use while looking
    like it simply found nothing.
    """
    results = SearchResults(query=query or "")
    terms = _terms(results.query)
    if not terms:
        return results

    results.empty_query = False
    results.terms = terms

    def joined(selectable):
        """The same joins for the count and for the page of rows.

        Written once rather than twice because a filter applied to one and not
        the other would make "40 shown, 6 more" quietly wrong, and nothing would
        ever reveal it.
        """
        return (
            selectable
            .outerjoin(
                WorkItemParticipant,
                (WorkItemParticipant.work_item_id == WorkItem.id)
                & (WorkItemParticipant.participation == "OWNER")
                & (WorkItemParticipant.to_ts.is_(None)),
            )
            .outerjoin(Person, Person.id == WorkItemParticipant.person_id)
            .outerjoin(Client, Client.id == WorkItem.client_id)
            .outerjoin(WorkItemType, WorkItemType.id == WorkItem.type_id)
        )

    # A bare number is almost always somebody quoting an item they were told
    # about. Match the id as well as the text rather than instead of it — "42"
    # could equally be part of a ticket reference in a title.
    id_match = _ID_ONLY.match(results.query.strip())

    conditions = []
    for term in terms:
        pattern = f"%{_escape(term)}%"
        conditions.append(
            or_(
                WorkItem.title.ilike(pattern, escape="\\"),
                WorkItem.description.ilike(pattern, escape="\\"),
                Client.name.ilike(pattern, escape="\\"),
                WorkItemType.name.ilike(pattern, escape="\\"),
                Person.name.ilike(pattern, escape="\\"),
                cast(WorkItem.id, String).ilike(pattern, escape="\\"),
            )
        )
    text_match = and_(*conditions)

    filters = []
    if id_match:
        filters.append(or_(WorkItem.id == int(id_match.group(1)), text_match))
    else:
        filters.append(text_match)

    if not include_closed:
        filters.append(WorkItem.state.not_in([s.value for s in TERMINAL]))

    # RULE-011, the same scoping every other list uses. Unowned work is always
    # visible: nobody has picked it up, so it belongs to everyone.
    if team_ids is not None:
        filters.append(Person.team_id.is_(None) | Person.team_id.in_(team_ids))

    # The exact total, not just "there are more". A separate COUNT is one cheap
    # query, and "360 more — add a word" is the sentence that actually gets
    # someone from a useless result set to the item they wanted. Fetching
    # `limit + 1` rows instead would only ever be able to say "at least one".
    matched = session.scalar(
        joined(select(func.count()).select_from(WorkItem)).where(*filters)
    ) or 0

    rows = session.execute(
        joined(select(WorkItem, Person, Client, WorkItemType))
        .where(*filters)
        .order_by(
            # Open before closed. Somebody searching is usually trying to act on
            # something, and finished work is context rather than the answer.
            WorkItem.state.in_([s.value for s in TERMINAL]),
            WorkItem.priority,
            WorkItem.id.desc(),
        )
        .limit(limit)
    ).all()

    results.cut = max(0, matched - len(rows))

    lowered = [term.lower() for term in terms]
    for item, owner, client, work_type in rows:
        results.hits.append(
            Hit(
                item=item,
                owner_name=owner.name if owner else None,
                client_name=client.name if client else None,
                type_name=work_type.name if work_type else None,
                matched_on=_matched_fields(
                    lowered, item, owner, client, work_type,
                    by_id=bool(id_match) and item.id == int(id_match.group(1)),
                ),
            )
        )

    return results


def _matched_fields(terms, item, owner, client, work_type, *, by_id: bool) -> list[str]:
    """Which fields the query was found in.

    Computed here rather than in SQL because it is presentation, and because the
    rows are already loaded — asking the database to return six extra booleans
    per row to save a string comparison would be the wrong trade.
    """
    fields = {
        "title": item.title,
        "description": item.description,
        "client": client.name if client else None,
        "kind": work_type.name if work_type else None,
        "owner": owner.name if owner else None,
    }
    found = [
        label
        for label, value in fields.items()
        if value and any(term in value.lower() for term in terms)
    ]
    if by_id:
        found.insert(0, "item number")
    return found
