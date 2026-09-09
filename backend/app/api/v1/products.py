from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.user import User
from app.schemas.product import ProductOut

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
