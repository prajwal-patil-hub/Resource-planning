"""Test fixtures.

Tests run against a real PostgreSQL database, not SQLite. That is not
fussiness: half the invariants in this system are enforced by PostgreSQL
features SQLite does not have — partial unique indexes, EXCLUDE constraints,
daterange, plpgsql triggers. Testing against SQLite would test a different
system and pass while the real one was broken.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://rp@/resource_planning_test?host=/tmp/pgs&port=5433",
)


@pytest.fixture(scope="session")
def engine():
    admin = create_engine(
        "postgresql+psycopg://rp@/postgres?host=/tmp/pgs&port=5433",
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS resource_planning_test"))
        conn.execute(text("CREATE DATABASE resource_planning_test"))
    admin.dispose()

    env = dict(os.environ, DATABASE_URL=TEST_DB_URL, PYTHONPATH=str(BACKEND))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"migrations failed:\n{result.stdout}\n{result.stderr}")

    eng = create_engine(TEST_DB_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    """A session in a transaction that is rolled back after each test.

    Keeps tests isolated without re-running migrations for every one.
    """
    connection = engine.connect()
    trans = connection.begin()
    factory = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        connection.close()


def _make_person(session: Session, name: str, email: str, role_code: str = "DEVELOPER"):
    from app.models import Person, Role

    role = session.scalar(
        text("SELECT id FROM role WHERE code = :c").bindparams(c=role_code)
    )
    person = Person(
        name=name,
        email=email,
        role_id=role,
        team_id=session.scalar(text("SELECT id FROM team LIMIT 1")),
        normal_load=3,
        active=True,
    )
    session.add(person)
    session.flush()
    return person


@pytest.fixture
def person(session):
    return _make_person(session, "Rahul", "rahul@example.com")


@pytest.fixture
def other_person(session):
    return _make_person(session, "Priya", "priya@example.com")


@pytest.fixture
def manager(session):
    """Someone with ASSIGN_ACROSS_TEAMS — the escape hatch for RULE-011."""
    return _make_person(session, "Meera", "meera@example.com", role_code="MANAGER")


@pytest.fixture
def qa_person(session):
    return _make_person(session, "Sana", "sana@example.com", role_code="QA")
