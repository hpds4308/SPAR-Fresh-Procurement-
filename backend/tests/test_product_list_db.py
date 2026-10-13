"""
DB-backed tests for the admin Product List — Admin adds products and
removes / restores them. Removing only marks a product INACTIVE, so its
order and price history stays intact.
"""
import pytest
from pydantic import ValidationError

from app.core.errors import ConflictError, ValidationFailedError
from app.models.product import Product
from app.schemas.product import ProductCreate
from app.services import product_service


@pytest.fixture
def admin(make_user):
    return make_user(role="ADMIN")


def _payload(db_session, make_product, **overrides):
    ref = make_product()  # makes sure a category and the KG unit exist
    data = dict(
        product_code="NEW001",
        pos_code="00099999",
        description="  Rambutan   Red ",
        category_id=ref.category_id,
        unit_id=ref.unit_id,
    )
    data.update(overrides)
    return ProductCreate(**data)


def test_create_adds_active_product(db_session, admin, make_product):
    out = product_service.create(db_session, admin, _payload(db_session, make_product))

    assert out.description == "Rambutan Red"
    assert out.status == "ACTIVE"
    assert out.unit_code == "KG"
    row = db_session.get(Product, out.id)
    assert row.pos_code_flag is None


def test_create_without_pos_code_flags_it_missing(db_session, admin, make_product):
    out = product_service.create(db_session, admin, _payload(db_session, make_product, pos_code="  "))

    assert out.pos_code is None
    assert db_session.get(Product, out.id).pos_code_flag == "MISSING"


def test_duplicate_code_is_rejected(db_session, admin, make_product):
    make_product(product_code="DUP1")
    with pytest.raises(ConflictError):
        product_service.create(db_session, admin, _payload(db_session, make_product, product_code="dup1"))


def test_duplicate_of_removed_product_points_to_restore(db_session, admin, make_product):
    gone = make_product(product_code="OLD1", status="INACTIVE")
    with pytest.raises(ConflictError, match="Restore"):
        product_service.create(db_session, admin, _payload(db_session, make_product, product_code="OLD1"))
    assert gone.status == "INACTIVE"


def test_unknown_category_is_rejected(db_session, admin, make_product):
    with pytest.raises(ValidationFailedError):
        product_service.create(db_session, admin, _payload(db_session, make_product, category_id=999_999))


def test_blank_description_is_rejected():
    with pytest.raises(ValidationError):
        ProductCreate(product_code="X1", description="   ", category_id=1, unit_id=1)


def test_remove_and_restore_keep_the_row(db_session, admin, make_product):
    p = make_product()

    removed = product_service.remove(db_session, admin, p.id)
    assert removed.status == "INACTIVE"
    assert p.id in {r.id for r in product_service.list_all(db_session)}

    restored = product_service.restore(db_session, admin, p.id)
    assert restored.status == "ACTIVE"


def test_api_role_gates_and_branch_view(client, make_branch, make_user, make_product, auth_headers):
    admin = make_user(role="ADMIN")
    branch = make_user(role="BRANCH", branch=make_branch())
    ref = make_product()
    body = {"product_code": "API001", "description": "Api Fruit", "category_id": ref.category_id, "unit_id": ref.unit_id}

    assert client.get("/api/v1/products/all", headers=auth_headers(branch)).status_code == 403
    assert client.get("/api/v1/products/options", headers=auth_headers(branch)).status_code == 403
    assert client.post("/api/v1/products", json=body, headers=auth_headers(branch)).status_code == 403

    r = client.post("/api/v1/products", json=body, headers=auth_headers(admin))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert pid in {p["id"] for p in client.get("/api/v1/products", headers=auth_headers(branch)).json()}

    assert client.delete(f"/api/v1/products/{pid}", headers=auth_headers(branch)).status_code == 403
    r = client.delete(f"/api/v1/products/{pid}", headers=auth_headers(admin))
    assert r.status_code == 200 and r.json()["status"] == "INACTIVE"
    # Removed items drop off what branches order from, but stay on the admin list.
    assert pid not in {p["id"] for p in client.get("/api/v1/products", headers=auth_headers(branch)).json()}
    assert pid in {p["id"] for p in client.get("/api/v1/products/all", headers=auth_headers(admin)).json()}

    r = client.post(f"/api/v1/products/{pid}/restore", headers=auth_headers(admin))
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"
