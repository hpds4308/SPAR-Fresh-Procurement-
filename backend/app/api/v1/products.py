from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.user import User
from app.schemas.product import (
    ProductAdminOut,
    ProductCreate,
    ProductImageRef,
    ProductOptionsOut,
    ProductOut,
    ProductUpdate,
)
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


@router.get("/images", response_model=list[ProductImageRef])
def product_images(db: Session = Depends(get_db)):
    """Which products have a photo (any signed-in user - thumbnails show on every page)."""
    return product_service.image_refs(db)


@router.get("/{product_id}/image")
def product_image(product_id: int, size: str = "full", db: Session = Depends(get_db)):
    """The product's photo; size=thumb for the small list version."""
    data, content_type = product_service.get_image(db, product_id, thumb=size == "thumb")
    return Response(
        content=data,
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"},
    )


@router.post("", response_model=ProductAdminOut, status_code=201)
def create_product(
    payload: ProductCreate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return product_service.create(db, admin, payload)


@router.patch("/{product_id}", response_model=ProductAdminOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Edits code, POS code, description, category, subcategory and unit."""
    return product_service.update(db, admin, product_id, payload)


@router.put("/{product_id}/image", response_model=ProductAdminOut)
def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    thumb: UploadFile = File(...),
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Sets (or replaces) the product's 1080x1080 photo and its list thumbnail."""
    data = file.file.read(product_service.MAX_IMAGE_BYTES + 1)
    thumb_data = thumb.file.read(product_service.MAX_THUMB_BYTES + 1)
    return product_service.set_image(db, admin, product_id, data, thumb_data)


@router.delete("/{product_id}/image", response_model=ProductAdminOut)
def remove_product_image(
    product_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return product_service.remove_image(db, admin, product_id)


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
