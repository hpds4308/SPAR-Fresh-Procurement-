"""
QA suite fixtures.

Reuses the application's own DB-backed fixtures (client, make_user,
make_branch, make_product, db_session, ...) from backend/tests/conftest.py
WITHOUT modifying anything under backend/. Nothing in here touches the real
database: the imported conftest rewrites DATABASE_URL to "<db>_test" before
any app module is imported.

Convention used across this suite
---------------------------------
* A test that PASSES documents behaviour that is correct today.
* A test marked  @pytest.mark.xfail(strict=True, reason="BUG-xx ...")  pins a
  CONFIRMED defect from qa/QA_REPORT.md. It is green (xfailed) today and turns
  red (XPASS-strict) the moment the bug is fixed, which is the cue to delete
  the marker and keep the test as a regression guard.
* A test marked  xfail(strict=False, reason="RISK-xx ...")  pins a suspected
  risk / design question that needs a product decision.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Re-export the project's fixtures (client, make_*, db_session, auth_headers ...).
from tests.conftest import *  # noqa: F401,F403,E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """slowapi keeps counters in process memory; without this, tests that log
    in repeatedly would trip the 10/minute login limit and fail for the wrong
    reason."""
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def client_no_raise(db_session):
    """Like the app's `client` fixture, but unhandled server exceptions come
    back as real HTTP 500 responses (what a browser would see) instead of being
    re-raised into the test."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def open_order_window(db_session, make_user):
    """Force the branch ordering cutoff to 23:59 so order tests don't depend
    on the wall-clock time they run at (same approach the app's own tests use)."""
    from app.models.system import SystemSetting

    def _open(any_user_id: int):
        row = db_session.query(SystemSetting).filter(SystemSetting.key == "branch_order_deadline").first()
        if row:
            row.value = "23:59"
        else:
            db_session.add(SystemSetting(key="branch_order_deadline", value="23:59", updated_by=any_user_id))
        db_session.commit()

    return _open
