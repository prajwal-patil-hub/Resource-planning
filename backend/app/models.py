"""SQLAlchemy models.

These mirror docs/08-domain-model.md. The database enforces the invariants
(see the migrations); these classes give the application a typed view of them.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, DATERANGE
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------


class Role(Base):
    __tablename__ = "role"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    permission_level: Mapped[str] = mapped_column(Text)
    can_verify: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "team"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base):
    __tablename__ = "client"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkItemType(Base):
    __tablename__ = "work_item_type"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=100)


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


class Person(Base):
    __tablename__ = "person"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"))
    team_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("team.id"))
    reports_to_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("person.id"))
    normal_load: Mapped[int] = mapped_column(SmallInteger, default=3)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_on: Mapped[date | None] = mapped_column(Date)
    left_on: Mapped[date | None] = mapped_column(Date)

    # Credentials. Nullable because a person can exist in the directory before
    # they have a login — being in the org chart is not being a user.
    password_hash: Mapped[str | None] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_logins: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role] = relationship(lazy="joined")
    team: Mapped[Team | None] = relationship(lazy="joined")


class UserSession(Base):
    """A live login. A row rather than a self-contained cookie, so access can
    actually be revoked — see app/auth.py."""

    __tablename__ = "user_session"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text)
    person_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("person.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)


class Absence(Base):
    __tablename__ = "absence"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    person_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("person.id"))
    # daterange, so overlap is a first-class operation and the EXCLUDE
    # constraint can enforce INV-5 under concurrency.
    period: Mapped[object] = mapped_column(DATERANGE)
    kind: Mapped[str] = mapped_column(Text)
    approved_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("person.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("person.id"))
    created_by_name: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("person.id"))

    person: Mapped["Person"] = relationship(lazy="joined", foreign_keys=[person_id])

    @property
    def first_day(self) -> date:
        return self.period.lower

    @property
    def last_day(self) -> date:
        """The period is stored half-open, so the last day away is upper - 1."""
        from datetime import timedelta as _td

        return self.period.upper - _td(days=1)

    @property
    def is_approved(self) -> bool:
        return self.approved_by_id is not None


class OrgSetting(Base):
    """One row. Business facts the organization owns — not deployment config,
    so they live in the database and change without a deploy."""

    __tablename__ = "org_setting"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    weekend_days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    stale_after_days: Mapped[int] = mapped_column(SmallInteger, default=3)


class NonWorkingDay(Base):
    __tablename__ = "non_working_day"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(Text)


# --------------------------------------------------------------------------
# Work
# --------------------------------------------------------------------------


class WorkItem(Base):
    __tablename__ = "work_item"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    type_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("work_item_type.id"))
    client_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("client.id"))
    priority: Mapped[int] = mapped_column(SmallInteger, default=2)
    state: Mapped[str] = mapped_column(Text, default="NEW")
    due_date: Mapped[date | None] = mapped_column(Date)
    displaced_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("work_item.id"))
    follow_up_of_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("work_item.id"))
    created_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("person.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)

    type: Mapped[WorkItemType | None] = relationship(lazy="joined")
    client: Mapped[Client | None] = relationship(lazy="joined")

    # D-013: optimistic locking. SQLAlchemy bumps `version` on every UPDATE and
    # adds it to the WHERE clause; a stale write matches zero rows and raises
    # StaleDataError rather than silently overwriting someone else's change.
    __mapper_args__ = {"version_id_col": version}


class WorkItemParticipant(Base):
    __tablename__ = "work_item_participant"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("work_item.id"))
    person_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("person.id"))
    participation: Mapped[str] = mapped_column(Text)
    from_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("person.id"))

    person: Mapped[Person] = relationship(lazy="joined", foreign_keys=[person_id])


class StateTransition(Base):
    __tablename__ = "state_transition"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("work_item.id"))
    from_state: Mapped[str | None] = mapped_column(Text)
    to_state: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_by_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("person.id"))
    displaced_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("work_item.id"))
    note: Mapped[str | None] = mapped_column(Text)

    changed_by: Mapped[Person] = relationship(lazy="joined", foreign_keys=[changed_by_id])


class WorkItemAudit(Base):
    __tablename__ = "work_item_audit"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("work_item.id"))
    field: Mapped[str] = mapped_column(Text)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("person.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
