from datetime import date
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.email import email_configured, send_email_with_attachment
from app.core.errors import ValidationFailedError
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.master_data import (
    AutoGenerateSummaryOut,
    MasterDataFieldUpdateRequest,
    MasterDataRowOut,
    MasterDataSendOut,
    MasterDataSheetOut,
    MasterDataSubmissionOut,
    PublishSummaryOut,
)
from app.services import master_data_service, settings_service

router = APIRouter(prefix="/master-data", dependencies=[Depends(get_current_user)])


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


@router.post("/auto-generate-selling-prices", response_model=AutoGenerateSummaryOut)
def auto_generate_selling_prices(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Fills Selling Price only where it is blank, using GP = (selling - cost) / selling
    solved for selling price, then drops decimals and rounds up to the next 10.
    Existing prices (manual or generated earlier) and published prices are kept."""
    return master_data_service.auto_generate_selling_prices(db)


@router.get("/export")
def export_master_data(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Same data as GET /master-data, downloaded as .xlsx — mirrors the on-screen table exactly."""
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
    """Emails the current Master Data Sheet as an .xlsx attachment to the address
    set in Admin → Settings ("Master Data recipient email"). Requires SMTP_* to be
    configured too — see .env.example."""
    recipient = settings_service.get_setting(db, settings_service.MASTER_DATA_EMAIL).strip()
    if not recipient:
        raise ValidationFailedError(
            "No Master Data recipient email is set yet — add one in Admin → Settings first."
        )
    excel_bytes = master_data_service.build_master_data_excel(db)
    today = date.today().isoformat()
    send_email_with_attachment(
        to=recipient,
        subject=f"SPAR Master Data Sheet — {today}",
        body=(
            f"Attached is the current Master Data Sheet, exported {today}.\n\n"
            "This is an automated export from the SPAR procurement platform."
        ),
        attachment_bytes=excel_bytes,
        attachment_filename=f"master-data-sheet-{today}.xlsx",
    )
    return {"sent_to": recipient}


@router.post("/send", response_model=MasterDataSendOut)
def send_to_master_data(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Makes the current sheet the latest version for the Master Data Team (in the app).
    If a Master Data recipient email is set and email works, the same sheet is
    also emailed as before; an email problem never undoes the send."""
    result, sheet = master_data_service.send_to_master_data(db, admin)
    recipient = settings_service.get_setting(db, settings_service.MASTER_DATA_EMAIL).strip()
    if result.created and recipient and email_configured():
        sent_on = result.sent_at.date().isoformat()
        try:
            send_email_with_attachment(
                to=recipient,
                subject=f"SPAR Master Data Sheet v{result.version} — {sent_on}",
                body=(
                    f"Version {result.version} of the Master Data Sheet is ready in the SPAR procurement "
                    f"platform and attached here, sent {sent_on}.\n\n"
                    "This is an automated message from the SPAR procurement platform."
                ),
                attachment_bytes=master_data_service.sheet_to_excel(sheet),
                attachment_filename=f"SPAR-Master-Data-Sheet-v{result.version}-{sent_on}.xlsx",
            )
            result.emailed_to = recipient
        except ValidationFailedError as e:
            result.email_error = str(e)
    return result


# --------------------------------------------------------------------------
# Master Data Team: the latest sheet Admin sent, read-only
# --------------------------------------------------------------------------


@router.get("/team", response_model=MasterDataSubmissionOut)
def get_team_sheet(
    user: User = Depends(require_roles("MASTER_DATA", "ADMIN")),
    db: Session = Depends(get_db),
):
    """The latest Master Data Sheet Admin sent, exactly as sent. 404 until the first send."""
    return master_data_service.get_latest_submission(db)


@router.get("/team/export")
def export_team_sheet(
    user: User = Depends(require_roles("MASTER_DATA", "ADMIN")),
    db: Session = Depends(get_db),
):
    excel_bytes, filename = master_data_service.latest_submission_excel(db)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/team/publish", response_model=PublishSummaryOut)
def publish_selling_prices(
    user: User = Depends(require_roles("MASTER_DATA")),
    db: Session = Depends(get_db),
):
    """Update Selling Prices: every branch sees the selling prices in the latest sheet."""
    return master_data_service.publish_selling_prices(db, user)
