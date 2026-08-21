from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.email import send_email_with_attachment
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.master_data import MasterDataSheetOut, MasterDataRowOut, MasterDataFieldUpdateRequest
from app.services import master_data_service

router = APIRouter(prefix="/master-data", dependencies=[Depends(get_current_user)])

MASTER_DATA_EMAIL_RECIPIENT = "pathiragedimujaya4308@gmail.com"


@router.get("", response_model=MasterDataSheetOut)
def get_master_data(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """One row per active product: Admin's margin reference fields plus every
    active supplier's most recent Adjusted Price, read-only, side by side."""
    return master_data_service.get_master_data_sheet(db)


@router.patch("/{product_id}", response_model=MasterDataRowOut)
def update_master_data(
    product_id: int,
    payload: MasterDataFieldUpdateRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Update exactly one of pos_code / target_gp_percent / selling_price. Null clears it. cost_price isn't editable — see schema."""
    return master_data_service.update_master_data_field(db, product_id, payload.field, payload.value)


@router.get("/export")
def export_master_data(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Same data as GET /master-data, downloaded as .xlsx — mirrors the on-screen table exactly."""
    import io

    excel_bytes = master_data_service.build_master_data_excel(db)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="master-data-sheet.xlsx"'},
    )


@router.post("/send-email")
def send_master_data_email(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Emails the current Master Data Sheet as an .xlsx attachment to the fixed recipient
    below. Requires SMTP_* to be configured in .env — see .env.example."""
    excel_bytes = master_data_service.build_master_data_excel(db)
    today = date.today().isoformat()
    send_email_with_attachment(
        to=MASTER_DATA_EMAIL_RECIPIENT,
        subject=f"SPAR Master Data Sheet — {today}",
        body=(
            f"Attached is the current Master Data Sheet, exported {today}.\n\n"
            "This is an automated export from the SPAR procurement platform."
        ),
        attachment_bytes=excel_bytes,
        attachment_filename=f"master-data-sheet-{today}.xlsx",
    )
    return {"sent_to": MASTER_DATA_EMAIL_RECIPIENT}
