"""
DB-backed tests for the admin Product List — Admin adds products and
removes / restores them. Removing only marks a product INACTIVE, so its
order and price history stays intact.
"""
import pytest
from pydantic import ValidationError

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
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


# ---- Editing ----


def test_update_changes_details_in_place(db_session, admin, make_product):
    p = make_product(product_code="ED1", pos_code="00011111")
    payload = _payload(db_session, make_product, product_code="ED1-NEW", pos_code=None, description=" Mango  TJC ")

    out = product_service.update(db_session, admin, p.id, payload)

    assert out.id == p.id
    assert out.product_code == "ED1-NEW"
    assert out.description == "Mango TJC"
    row = db_session.get(Product, p.id)
    assert row.pos_code is None and row.pos_code_flag == "MISSING"


def test_update_keeps_existing_pos_flag_when_pos_code_unchanged(db_session, admin, make_product):
    p = make_product(product_code="ED2", pos_code="00022222")
    p.pos_code_flag = "NA"
    db_session.commit()

    product_service.update(db_session, admin, p.id, _payload(db_session, make_product, product_code="ED2", pos_code="00022222"))

    assert db_session.get(Product, p.id).pos_code_flag == "NA"


def test_update_rejects_code_of_another_product(db_session, admin, make_product):
    make_product(product_code="TAKEN")
    p = make_product(product_code="MINE")
    with pytest.raises(ConflictError):
        product_service.update(db_session, admin, p.id, _payload(db_session, make_product, product_code="taken"))


def test_update_can_keep_own_code(db_session, admin, make_product):
    p = make_product(product_code="SAME1")
    out = product_service.update(db_session, admin, p.id, _payload(db_session, make_product, product_code="same1"))
    assert out.product_code == "same1"


# ---- Photos ----


def _png(w: int, h: int) -> bytes:
    import struct

    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00" + b"\x00" * 64


def _jpeg(w: int, h: int) -> bytes:
    import struct

    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\x00" * 9
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def test_set_image_accepts_1080_square_and_versions_it(db_session, admin, make_product):
    p = make_product()
    out = product_service.set_image(db_session, admin, p.id, _jpeg(1080, 1080), _jpeg(240, 240))

    assert out.image_version
    data, ctype = product_service.get_image(db_session, p.id, thumb=False)
    assert ctype == "image/jpeg" and data.startswith(b"\xff\xd8")
    refs = {r.product_id: r for r in product_service.image_refs(db_session)}
    assert refs[p.id].version == out.image_version
    assert refs[p.id].product_code == p.product_code


@pytest.mark.parametrize("w,h", [(1080, 1079), (1920, 1080), (500, 500)])
def test_set_image_rejects_other_sizes(db_session, admin, make_product, w, h):
    p = make_product()
    with pytest.raises(ValidationFailedError, match="1080 x 1080"):
        product_service.set_image(db_session, admin, p.id, _png(w, h), _png(240, 240))


def test_set_image_rejects_non_images_and_bad_thumbs(db_session, admin, make_product):
    p = make_product()
    with pytest.raises(ValidationFailedError, match="isn't a photo"):
        product_service.set_image(db_session, admin, p.id, b"<svg></svg>", _png(240, 240))
    with pytest.raises(ValidationFailedError, match="thumbnail"):
        product_service.set_image(db_session, admin, p.id, _png(1080, 1080), _png(1080, 1080))


def test_remove_image(db_session, admin, make_product):
    p = make_product()
    product_service.set_image(db_session, admin, p.id, _png(1080, 1080), _png(240, 240))
    out = product_service.remove_image(db_session, admin, p.id)
    assert out.image_version is None
    with pytest.raises(NotFoundError):
        product_service.get_image(db_session, p.id, thumb=True)


# ---- Imported items: counted in cases, with Admin's case size ----

def _imported_category(db_session):
    from app.models.product import ProductCategory

    return db_session.query(ProductCategory).filter_by(name="Imported Fruit").one()


def test_imported_item_goes_per_case_with_its_kg(db_session, admin, make_product):
    imported = _imported_category(db_session)
    # Whatever unit the form sent, Imported items are saved per case.
    out = product_service.create(
        db_session, admin, _payload(db_session, make_product, category_id=imported.id, case_kg=12.5)
    )

    assert out.category_name == "Imported Fruit"
    assert out.unit_code == "case"
    assert out.case_kg == 12.5
    refs = {r.product_id: r for r in product_service.image_refs(db_session)}
    assert refs[out.id].case_kg == 12.5


def test_imported_item_needs_case_kg(db_session, admin, make_product):
    imported = _imported_category(db_session)
    with pytest.raises(ValidationFailedError, match="1 case"):
        product_service.create(db_session, admin, _payload(db_session, make_product, category_id=imported.id))


def test_case_kg_must_be_positive():
    with pytest.raises(ValidationError):
        ProductCreate(product_code="X1", description="Apple", category_id=1, unit_id=1, case_kg=0)


def test_moving_out_of_imported_drops_case_kg(db_session, admin, make_product):
    imported = _imported_category(db_session)
    payload = _payload(db_session, make_product, category_id=imported.id, case_kg=18)
    out = product_service.create(db_session, admin, payload)

    ref = make_product()
    edited = product_service.update(
        db_session,
        admin,
        out.id,
        _payload(db_session, make_product, category_id=ref.category_id, unit_id=ref.unit_id, case_kg=18),
    )
    assert edited.unit_code == "KG"
    assert edited.case_kg is None


def test_case_kg_is_ignored_for_other_categories(db_session, admin, make_product):
    out = product_service.create(db_session, admin, _payload(db_session, make_product, case_kg=10))
    assert out.case_kg is None
    assert out.unit_code == "KG"
