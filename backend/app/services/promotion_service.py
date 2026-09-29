from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.product import Product
from app.models.promotion import ProductPromotion, PromotionType
from app.models.user import User
from app.schemas.promotion import PromotionOut, PromotionSave, PromotionTypeIn, PromotionTypeOut
from app.services.order_service import BUSINESS_TZ


def _out(row: ProductPromotion) -> PromotionOut:
    return PromotionOut(
        product_id=row.product_id,
        promotion_type_id=row.promotion_type_id,
        promotion_name=row.promotion_type.name,
        color=row.promotion_type.color,
        start_date=row.start_date,
        end_date=row.end_date,
    )


# --------------------------------------------------------------------------
# Promotion types — the promotions Admin creates and deletes
# --------------------------------------------------------------------------


def list_types(db: Session) -> list[PromotionTypeOut]:
    """Every promotion Admin has created, oldest first, with how many products use it."""
    counts = dict(
        db.query(ProductPromotion.promotion_type_id, func.count(ProductPromotion.id))
        .group_by(ProductPromotion.promotion_type_id)
        .all()
    )
    return [
        PromotionTypeOut(id=t.id, name=t.name, color=t.color, product_count=counts.get(t.id, 0))
        for t in db.query(PromotionType).order_by(PromotionType.id).all()
    ]


def create_type(db: Session, admin: User, payload: PromotionTypeIn) -> PromotionTypeOut:
    clash = db.query(PromotionType.id).filter(func.lower(PromotionType.name) == payload.name.lower()).first()
    if clash:
        raise ConflictError(f'A promotion called "{payload.name}" already exists.')
    row = PromotionType(name=payload.name, color=payload.color, created_by=admin.id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(f'A promotion called "{payload.name}" already exists.')
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PROMOTION_CREATED",
        entity_type="promotion_type",
        entity_id=row.id,
        description=f'Promotion "{row.name}" created.',
    )
    return PromotionTypeOut(id=row.id, name=row.name, color=row.color, product_count=0)


def delete_type(db: Session, admin: User, type_id: int) -> None:
    """Deletes a promotion and removes it from every product it was set on."""
    row = db.get(PromotionType, type_id)
    if row is None:
        raise NotFoundError("That promotion no longer exists.")
    name = row.name
    removed = (
        db.query(ProductPromotion)
        .filter(ProductPromotion.promotion_type_id == type_id)
        .delete(synchronize_session=False)
    )
    db.delete(row)
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PROMOTION_DELETED",
        entity_type="promotion_type",
        entity_id=type_id,
        description=f'Promotion "{name}" deleted; removed from {removed} product(s).',
    )


# --------------------------------------------------------------------------
# Product promotions — which product runs which promotion, and when
# --------------------------------------------------------------------------


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
        type_ids = {ln.promotion_type_id for ln in payload.lines}
        known = {tid for (tid,) in db.query(PromotionType.id).filter(PromotionType.id.in_(type_ids)).all()}
        if type_ids - known:
            raise ValidationFailedError("One of the chosen promotions was deleted. Refresh the page and try again.")

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
                    promotion_type_id=ln.promotion_type_id,
                    start_date=ln.start_date,
                    end_date=ln.end_date,
                    updated_by=admin.id,
                )
            )
        elif (row.promotion_type_id, row.start_date, row.end_date) != (
            ln.promotion_type_id,
            ln.start_date,
            ln.end_date,
        ):
            row.promotion_type_id = ln.promotion_type_id
            row.start_date = ln.start_date
            row.end_date = ln.end_date
            row.updated_by = admin.id
    db.commit()
    # Changed rows still hold the relationship loaded for their old type.
    db.expire_all()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PROMOTIONS_SAVED",
        entity_type="product_promotion",
        description=f"Promotions saved: {len(wanted)} product(s) on promotion, {removed} removed.",
    )
    return list_all(db)
