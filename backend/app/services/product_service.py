"""
Admin Product List — the whole fruit & veg catalogue, including items
that were removed. Removing a product never deletes the row: past orders,
prices and purchase orders still point at it. It is marked INACTIVE
instead, which already hides it from branch ordering, supplier price
sheets, the Master Data Sheet and everything else that lists ACTIVE
products. Restoring flips it back.
"""
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.user import User
from app.schemas.product import ProductAdminOut, ProductCreate, ProductOption, ProductOptionsOut

ACTIVE = "ACTIVE"
INACTIVE = "INACTIVE"


def _out(p: Product, categories: dict[int, str], units: dict[int, str]) -> ProductAdminOut:
    return ProductAdminOut(
        id=p.id,
        product_code=p.product_code,
        pos_code=p.pos_code,
        description=p.description,
        category_id=p.category_id,
        category_name=categories.get(p.category_id, "—"),
        subcategory=p.subcategory,
        unit_id=p.unit_id,
        unit_code=units.get(p.unit_id, "—"),
        status=p.status,
        created_at=p.created_at,
    )


def _lookups(db: Session) -> tuple[dict[int, str], dict[int, str]]:
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    return categories, units


def list_all(db: Session) -> list[ProductAdminOut]:
    """Every product, active and removed, in the usual category/name order."""
    categories, units = _lookups(db)
    rows = db.query(Product).order_by(Product.category_id, Product.description).all()
    return [_out(p, categories, units) for p in rows]


def options(db: Session) -> ProductOptionsOut:
    return ProductOptionsOut(
        categories=[ProductOption(id=c.id, name=c.name) for c in db.query(ProductCategory).order_by(ProductCategory.id)],
        units=[ProductOption(id=u.id, name=u.code) for u in db.query(ProductUnit).order_by(ProductUnit.code)],
    )


def create(db: Session, admin: User, payload: ProductCreate) -> ProductAdminOut:
    if db.get(ProductCategory, payload.category_id) is None:
        raise ValidationFailedError("Choose a category.")
    if db.get(ProductUnit, payload.unit_id) is None:
        raise ValidationFailedError("Choose a unit.")

    clash = db.query(Product).filter(func.lower(Product.product_code) == payload.product_code.lower()).first()
    if clash:
        if clash.status != ACTIVE:
            raise ConflictError(
                f'Product code {payload.product_code} belongs to "{clash.description}", which was removed. '
                "Restore it from the list instead of adding it again."
            )
        raise ConflictError(f'Product code {payload.product_code} is already used by "{clash.description}".')

    row = Product(
        product_code=payload.product_code,
        pos_code=payload.pos_code,
        # Matches how the seed import flags items that came without a POS code.
        pos_code_flag=None if payload.pos_code else "MISSING",
        description=payload.description,
        category_id=payload.category_id,
        subcategory=payload.subcategory,
        unit_id=payload.unit_id,
        status=ACTIVE,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(f"Product code {payload.product_code} is already used by another product.")
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PRODUCT_CREATED",
        entity_type="product",
        entity_id=row.id,
        description=f'Product "{row.description}" ({row.product_code}) added.',
    )
    return _out(row, *_lookups(db))


def _set_status(db: Session, admin: User, product_id: int, status: str) -> ProductAdminOut:
    row = db.get(Product, product_id)
    if row is None:
        raise NotFoundError("That product no longer exists.")
    if row.status != status:
        row.status = status
        db.commit()
        db.refresh(row)
        removed = status == INACTIVE
        write_audit_log(
            db,
            user_id=admin.id,
            role="ADMIN",
            action="PRODUCT_REMOVED" if removed else "PRODUCT_RESTORED",
            entity_type="product",
            entity_id=row.id,
            description=f'Product "{row.description}" ({row.product_code}) {"removed" if removed else "restored"}.',
        )
    return _out(row, *_lookups(db))


def remove(db: Session, admin: User, product_id: int) -> ProductAdminOut:
    return _set_status(db, admin, product_id, INACTIVE)


def restore(db: Session, admin: User, product_id: int) -> ProductAdminOut:
    return _set_status(db, admin, product_id, ACTIVE)
