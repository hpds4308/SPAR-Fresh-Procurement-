from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.user import User
from app.schemas.product import ProductAdminOut, ProductCreate, ProductOptionsOut, ProductOut
from app.services import product_service

router = APIRouter(prefix="/products", dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    # Category IDs already match the client's requested display grouping
    # (1=Fruit, 2=Vege Low, 3=Vege Pola, 4=Vege Up); within each category,
    # items are alphabetical.
    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .order_by(Product.category_id, Product.description)
        .all()
    )
    return [
        ProductOut(
            id=p.id,
            product_code=p.product_code,
            description=p.description,
            category_name=categories.get(p.category_id, "—"),
            subcategory=p.subcategory,
            unit_code=units.get(p.unit_id, "—"),
            status=p.status,
        )
        for p in products
    ]


# --------------------------------------------------------------------------
# Admin Product List � view every item, add new ones, remove / restore
# --------------------------------------------------------------------------


@router.get("/all", response_model=list[ProductAdminOut])
def list_all_products(
    _admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every product, including removed ones."""
    return product_service.list_all(db)


@router.get("/options", response_model=ProductOptionsOut)
def product_options(
    _admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Categories and units to choose from when adding a product."""
    return product_service.options(db)


@router.post("", response_model=ProductAdminOut, status_code=201)
def create_product(
    payload: ProductCreate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return product_service.create(db, admin, payload)


@router.delete("/{product_id}", response_model=ProductAdminOut)
def remove_product(
    product_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Takes the product off the list (marks it INACTIVE); its history is kept."""
    return product_service.remove(db, admin, product_id)


@router.post("/{product_id}/restore", response_model=ProductAdminOut)
def restore_product(
    product_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return product_service.restore(db, admin, product_id)
