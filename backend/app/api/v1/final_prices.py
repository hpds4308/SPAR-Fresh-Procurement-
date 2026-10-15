"""
Final price lists — see final_price_service.py.
"""
from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.schemas.final_price import FinalDatesOut, FinalPriceListOut, SparSignatureIn, SparSignatureOut
from app.services import final_price_service as svc

router = APIRouter(prefix="/final-prices")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/signature", response_model=SparSignatureOut)
def get_spar_signature(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return svc.get_signature(db)


@router.put("/signature", response_model=SparSignatureOut)
def set_spar_signature(
    payload: SparSignatureIn,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """SPAR's signature, stamped automatically on every supplier's final price list."""
    return svc.set_signature(
        db, admin, name=payload.signatory_name, title=payload.signatory_title, signature_image=payload.signature_image
    )


@router.get("/mine/dates", response_model=FinalDatesOut)
def my_final_dates(current_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    return svc.final_dates(db, current_user)


@router.get("/mine", response_model=FinalPriceListOut)
def my_final_prices(
    delivery_date: date,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    return svc.build_list(db, current_user, delivery_date)


@router.get("/mine/excel")
def my_final_prices_excel(
    delivery_date: date,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    data = svc.build_list(db, current_user, delivery_date)
    content = svc.build_excel(data)
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{svc.filename(data, "xlsx")}"'},
    )


@router.get("/mine/pdf")
def my_final_prices_pdf(
    delivery_date: date,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    data = svc.build_list(db, current_user, delivery_date)
    content = svc.build_pdf(data)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{svc.filename(data, "pdf")}"'},
    )
