"""
Sanity checks for the DB-backed fixture infrastructure itself (db_session
isolation, the client fixture's auth wiring) — not business logic. If
these fail, every other DB-backed test file's failures are suspect for
the wrong reason.
"""


def test_db_session_can_write_and_read(db_session, make_branch):
    branch = make_branch(branch_name="Fixture Smoke Branch")
    assert branch.id is not None
    assert branch.status == "ACTIVE"


def test_db_session_rolls_back_between_tests(db_session):
    from app.models.branch import Branch

    # If the previous test's commit had leaked past its transaction
    # rollback, this branch_name would already exist here.
    found = db_session.query(Branch).filter(Branch.branch_name == "Fixture Smoke Branch").first()
    assert found is None


def test_client_hits_real_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_client_rejects_unauthenticated_request(client):
    resp = client.get("/api/v1/orders/window")
    assert resp.status_code == 401


def test_client_authenticates_real_user(client, make_branch, make_user, auth_headers):
    branch = make_branch()
    user = make_user(role="BRANCH", branch=branch)
    resp = client.get("/api/v1/orders/window", headers=auth_headers(user))
    assert resp.status_code == 200
