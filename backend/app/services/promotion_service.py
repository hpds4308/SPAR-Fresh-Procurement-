from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError
from app.models.product import Product
from app.models.promotion import ProductPromotion
from app.models.user import User
from app.schemas.promotion import PromotionOut, PromotionSave
from app.services.order_service import BUSINESS_TZ


def _out(row: ProductPromotion) -> PromotionOut:
    return PromotionOut(
        product_id=row.product_id,
        promotion_type=row.promotion_type,
        start_date=row.start_date,
        end_date=row.end_date,
    )


def list_all(db: Session) -> list[PromotionOut]:
    """Every saved promotion — upcoming, running and already ended."""
    return [_out(r) for r in db.query(ProductPromotion).all()]


def list_active(db: Session, today: date | None = None) -> list[PromotionOut]:
    """Only promotions running today; each one drops off after its end_date."""
    today = today or datetime.now(BUSINESS_TZ).date()
    rows = (
        db.query(ProductPromotion)
        .filter(ProductPromotion.start_date <= today, ProductPromotion.end_date >= today)
        .all()
    )
    return [_out(r) for r in rows]


def save_all(db: Session, admin: User, payload: PromotionSave) -> list[PromotionOut]:
    """Replaces the whole promotion list with payload.lines."""
    wanted = {ln.product_id: ln for ln in payload.lines}
    if len(wanted) != len(payload.lines):
        raise ValidationFailedError("Each product can only have one promotion.")
    if wanted:
        found = {
            pid
            for (pid,) in db.query(Product.id).filter(Product.id.in_(wanted.keys()), Product.status == "ACTIVE").all()
        }
        missing = set(wanted) - found
        if missing:
            raise ValidationFailedError(f"Unknown or inactive product id(s): {sorted(missing)}")

    existing = {r.product_id: r for r in db.query(ProductPromotion).all()}
    removed = 0
    for pid, row in existing.items():
        if pid not in wanted:
            db.delete(row)
            removed += 1
    for pid, ln in wanted.items():
        row = existing.get(pid)
        if row is None:
            db.add(
                ProductPromotion(
                    product_id=pid,
                    promotion_type=ln.promotion_type,
                    start_date=ln.start_date,
                    end_date=ln.end_date,
                    updated_by=admin.id,
                )
            )
        elif (row.promotion_type, row.start_date, row.end_date) != (ln.promotion_type, ln.start_date, ln.end_date):
            row.promotion_type = ln.promotion_type
            row.start_date = ln.start_date
            row.end_date = ln.end_date
            row.updated_by = admin.id
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PROMOTIONS_SAVED",
        entity_type="product_promotion",
        description=f"Promotions saved: {len(wanted)} product(s) on promotion, {removed} removed.",
    )
    return list_all(db)
