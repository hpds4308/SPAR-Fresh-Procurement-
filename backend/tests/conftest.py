"""
Shared test fixtures.

Two tiers of tests live in this suite:

1. Pure unit tests (the pre-existing ones) — no live server, no real
   database, so they run anywhere with zero setup. FakeDB/FakeQuery below
   exist only for those.

2. DB-backed integration tests (added in this pass) — these exercise real
   service functions against a real, isolated Postgres database, never
   the dev/production one. See db_engine/db_session/client below.

DB-backed test database: DATABASE_URL is rewritten to "<original>_test"
before anything under app/ is imported (app.core.config.settings is a
module-level singleton read from the environment at import time, so this
must happen first or every later import would still see the real URL).
The test database is created if missing and migrated with the project's
own real Alembic chain — no separate/duplicated schema definition to
drift out of sync with production.
"""
import os
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_DB_URL = "postgresql+psycopg2://spar_user:spar_password@db:5432/spar_procurement"
_base_url = os.environ.get("DATABASE_URL", _DEFAULT_DB_URL)
_parts = urlsplit(_base_url)
_base_db_name = _parts.path.lstrip("/")
_TEST_DB_NAME = f"{_base_db_name}_test"
_TEST_DB_URL = urlunsplit((_parts.scheme, _parts.netloc, f"/{_TEST_DB_NAME}", _parts.query, _parts.fragment))
os.environ["DATABASE_URL"] = _TEST_DB_URL

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


class FakeQuery:
    """Mimics db.query(Model).filter(...).first() always finding nothing,
    so settings_service.get_setting() falls back to its .env-configured
    default — exactly the state a fresh install is in before Admin ever
    opens the Settings page."""

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class FakeDB:
    def query(self, *args, **kwargs):
        return FakeQuery()


# --------------------------------------------------------------------------
# DB-backed fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine():
    """
    Session-scoped: creates (if needed) and migrates the isolated
    "<db>_test" Postgres database, then yields an engine bound to it.
    Never touches the real database named in DATABASE_URL before this
    module's top-level rewrite.
    """
    admin_url = urlunsplit((_parts.scheme, _parts.netloc, f"/{_base_db_name}", "", ""))
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": _TEST_DB_NAME},
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_TEST_DB_NAME}"'))
    admin_engine.dispose()

    # Import lazily, after the DATABASE_URL override above has taken
    # effect — alembic/env.py reads app.core.config.settings.DATABASE_URL.
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(_TEST_DB_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """
    Function-scoped: one real Postgres transaction per test. Service code
    under test is free to call db.commit()/db.rollback() exactly like it
    does in production — a SAVEPOINT is re-opened after each one closes —
    and everything still unwinds via the outer transaction's rollback at
    the end of the test, so tests never leak rows into each other and
    never need per-test cleanup code.

    (This is SQLAlchemy's own documented pattern for joining a Session
    into an external transaction for tests.)
    """
    connection = db_engine.connect()
    outer_trans = connection.begin()
    Session = sessionmaker(bind=connection, future=True)
    session = Session()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    outer_trans.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """
    A real FastAPI TestClient wired to the app's actual routes, with only
    get_db overridden to hand out this test's isolated db_session instead
    of opening a fresh connection to the real database — every other
    dependency (auth, role checks, rate limiting) runs unmodified.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# --------------------------------------------------------------------------
# Factory fixtures — build the minimum realistic graph of rows a test
# needs (role, branch/supplier, product, user), mirroring what
# scripts/seed_master_data.py and scripts/seed_users.py set up for real,
# without depending on those scripts or the dev database's actual data.
# --------------------------------------------------------------------------


@pytest.fixture()
def roles(db_session):
    from app.models.user import Role

    codes = {"ADMIN": "Administrator", "BRANCH": "Branch", "SUPPLIER": "Supplier"}
    made = {}
    for code, name in codes.items():
        row = db_session.query(Role).filter(Role.code == code).first()
        if not row:
            row = Role(code=code, name=name)
            db_session.add(row)
            db_session.flush()
        made[code] = row
    db_session.commit()
    return made


@pytest.fixture()
def make_branch(db_session):
    from app.models.branch import Branch

    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = dict(branch_code=f"TB{n:03d}", branch_name=f"Test Branch {n}", status="ACTIVE")
        defaults.update(overrides)
        branch = Branch(**defaults)
        db_session.add(branch)
        db_session.commit()
        db_session.refresh(branch)
        return branch

    return _make


@pytest.fixture()
def make_supplier(db_session):
    from app.models.supplier import Supplier

    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = dict(supplier_code=f"TS{n:03d}", supplier_name=f"Test Supplier {n}", status="ACTIVE")
        defaults.update(overrides)
        supplier = Supplier(**defaults)
        db_session.add(supplier)
        db_session.commit()
        db_session.refresh(supplier)
        return supplier

    return _make


@pytest.fixture()
def make_product(db_session):
    from app.models.product import Product, ProductCategory, ProductUnit

    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        category = db_session.query(ProductCategory).first()
        if not category:
            category = ProductCategory(name="Test Category")
            db_session.add(category)
            db_session.flush()
        unit = db_session.query(ProductUnit).filter(ProductUnit.code == "KG").first()
        if not unit:
            unit = ProductUnit(code="KG")
            db_session.add(unit)
            db_session.flush()
        defaults = dict(
            product_code=f"TP{n:04d}",
            description=f"Test Product {n}",
            category_id=category.id,
            unit_id=unit.id,
            status="ACTIVE",
        )
        defaults.update(overrides)
        product = Product(**defaults)
        db_session.add(product)
        db_session.commit()
        db_session.refresh(product)
        return product

    return _make


@pytest.fixture()
def make_user(db_session, roles):
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    counter = {"n": 0}

    def _make(role="BRANCH", branch=None, supplier=None, password="TestPass123!", **overrides):
        counter["n"] += 1
        n = counter["n"]
        defaults = dict(
            username=f"testuser{n}",
            email=f"testuser{n}@example.test",
            password_hash=hash_password(password),
            branch_id=branch.id if branch else None,
            supplier_id=supplier.id if supplier else None,
            is_active=True,
        )
        defaults.update(overrides)
        user = User(**defaults)
        db_session.add(user)
        db_session.flush()
        db_session.add(UserRole(user_id=user.id, role_id=roles[role].id))
        db_session.commit()
        db_session.refresh(user)
        user.plain_password = password  # convenience for tests that need to log in
        return user

    return _make


@pytest.fixture()
def auth_headers():
    """Bearer-auth header dict from a real access token, for a given user."""
    from app.core.security import create_access_token

    def _headers(user):
        token = create_access_token(user.id)
        return {"Authorization": f"Bearer {token}"}

    return _headers
