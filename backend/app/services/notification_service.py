"""
Notification emails.

Who gets what:
  Suppliers (to the email on their Account page)
    - SPAR adjusted your price(s)       — a price sheet was sent for approval
    - <Galle branch / SPAR Admin> sent you a message
    - SPAR issued purchase order PO-…
    - 8 AM on a price submission day: please submit your prices before 12:00
    - 1 PM: please approve or reject SPAR's prices before 2:00 PM
  Admin (to every active admin's Account email)
    - <Bloomax / Galle branch> sent you a message
    - Bloomax ↔ Kandy: a supplier and a branch messaged each other
    - Bloomax answered your adjusted prices (approved / rejected)
Branches get no email — they have no email address in the app.

Chat emails go out once per batch of unread messages: only for a message
when the recipient has no earlier unread message from the same chat, so a
burst of ten messages is one email, not ten.

Request handlers call the on_* hooks, which build the email from the
request's data and hand it to a background thread (dispatch) so sending
never slows the request down. Scheduled reminders run in their own thread
(start_scheduler) and send directly (deliver). Every email is recorded in
email_log — SKIPPED while email isn't configured — and reminders carry a
dedupe_key so each goes out once, however often the scheduler wakes up.
"""
import html
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import email as email_core
from app.core.config import settings
from app.models.branch import Branch
from app.models.email_log import EmailLog
from app.models.message import Message
from app.models.price_revision import SupplierPriceRevision
from app.models.pricing import SupplierPrice
from app.models.supplier import Supplier
from app.models.user import Role, User, UserRole
from app.services import settings_service

logger = logging.getLogger("spar.notifications")
BUSINESS_TZ = ZoneInfo("Asia/Colombo")


@dataclass
class Email:
    kind: str
    to: list[str]
    subject: str
    # Short paragraphs of plain text; the HTML version is built from them.
    lines: list[str]
    button: tuple[str, str] | None = None  # (label, app path like "/supplier?tab=approvals")
    # Simple rows shown as a table, e.g. [("Banana", "Rs. 180.00", "Rs. 165.00")].
    table: list[tuple[str, ...]] = field(default_factory=list)
    table_header: tuple[str, ...] = ()
    dedupe_key: str | None = None


# ---- Building and sending ----


def _link(path: str) -> str | None:
    base = settings.APP_URL.rstrip("/")
    return f"{base}{path}" if base else None


def _render(email: Email) -> tuple[str, str]:
    """(plain text, HTML) bodies."""
    url = _link(email.button[1]) if email.button else None
    text_parts = list(email.lines)
    if email.table:
        if email.table_header:
            text_parts.append(" | ".join(email.table_header))
        text_parts += [" | ".join(row) for row in email.table]
    if url:
        text_parts.append(f"{email.button[0]}: {url}")
    text_parts.append("— SPAR Fresh Procurement")
    text = "\n\n".join(text_parts)

    esc = html.escape
    body = "".join(f'<p style="margin:0 0 14px">{esc(line)}</p>' for line in email.lines)
    if email.table:
        head = "".join(
            f'<th style="text-align:left;padding:6px 10px;border-bottom:1px solid #d9e3dc;color:#5b6b61;'
            f'font-size:12px">{esc(h)}</th>'
            for h in email.table_header
        )
        rows = "".join(
            "<tr>" + "".join(f'<td style="padding:6px 10px;border-bottom:1px solid #eef3ef">{esc(c)}</td>' for c in row) + "</tr>"
            for row in email.table
        )
        body += (
            '<table style="border-collapse:collapse;margin:0 0 16px;font-size:14px">'
            + (f"<thead><tr>{head}</tr></thead>" if head else "")
            + f"<tbody>{rows}</tbody></table>"
        )
    if url:
        body += (
            f'<p style="margin:18px 0"><a href="{esc(url)}" style="background:#1f6b45;color:#fff;'
            f'text-decoration:none;padding:10px 18px;border-radius:999px;font-weight:600">{esc(email.button[0])}</a></p>'
        )
    page = (
        '<div style="font-family:Arial,Helvetica,sans-serif;background:#f4f7f5;padding:24px">'
        '<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;'
        'border:1px solid #e3ebe5">'
        '<div style="background:#e30613;color:#fff;padding:14px 22px;font-weight:700;font-size:18px">'
        "SPAR <span style=\"font-weight:400\">Fresh Procurement</span></div>"
        f'<div style="padding:22px;color:#17251d;font-size:15px;line-height:1.5">{body}</div>'
        '<div style="padding:12px 22px;background:#f4f7f5;color:#7a887f;font-size:12px">'
        "You're getting this because of your account on SPAR Fresh Procurement.</div>"
        "</div></div>"
    )
    return text, page


def deliver(db: Session, email: Email) -> str:
    """Sends now and records it in email_log. Returns SENT / FAILED / SKIPPED / DUPLICATE."""
    if not email.to:
        return "SKIPPED"
    if email.dedupe_key and db.query(EmailLog.id).filter(EmailLog.dedupe_key == email.dedupe_key).first():
        return "DUPLICATE"
    text, page = _render(email)
    status, error = "SENT", None
    try:
        email_core.send_email(to=email.to, subject=email.subject, text=text, html=page)
    except email_core.EmailNotConfigured as e:
        status, error = "SKIPPED", str(e)
    except email_core.EmailError as e:
        status, error = "FAILED", str(e)
        logger.warning("Email %r to %s failed: %s", email.subject, email.to, e)
    db.add(
        EmailLog(
            kind=email.kind,
            dedupe_key=email.dedupe_key,
            recipient=", ".join(email.to)[:500],
            subject=email.subject[:300],
            status=status,
            error=error,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Another run logged the same reminder first.
        db.rollback()
        return "DUPLICATE"
    return status


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email")


def _deliver_in_own_session(email: Email) -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        deliver(db, email)
    except Exception:
        logger.exception("Sending email %r failed.", email.subject)
        db.rollback()
    finally:
        db.close()


def dispatch(email: Email) -> None:
    """Sends in the background — request handlers never wait on the email service."""
    if email.to:
        _executor.submit(_deliver_in_own_session, email)


def _safe(hook):
    """A notification must never break the action that triggered it."""

    def wrapper(*args, **kwargs):
        try:
            hook(*args, **kwargs)
        except Exception:
            logger.exception("Building notification %s failed.", hook.__name__)

    wrapper.__name__ = hook.__name__
    return wrapper


# ---- Recipients ----


def admin_emails(db: Session) -> list[str]:
    rows = (
        db.query(User.email)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.code == "ADMIN", User.is_active.is_(True), User.email.isnot(None), User.email != "")
        .distinct()
        .all()
    )
    return sorted({e for (e,) in rows})


def supplier_emails(supplier: Supplier | None) -> list[str]:
    return [supplier.email.strip()] if supplier and supplier.email and supplier.email.strip() else []


def _rs(n: float) -> str:
    return f"Rs. {n:,.2f}"


def _names(items: list[str], limit: int = 2) -> str:
    """["Banana", "Avocado", "Leeks"] -> "Banana, Avocado and 1 more"."""
    if len(items) <= limit + 1:
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    return ", ".join(items[:limit]) + f" and {len(items) - limit} more"


def _preview(body: str, attachments: int = 0) -> str:
    text = " ".join(body.split())
    if len(text) > 300:
        text = text[:297] + "…"
    if attachments:
        text = (text + " " if text else "") + f"[{attachments} attachment{'s' if attachments != 1 else ''}]"
    return text


def _fmt_day(d: date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def _cutoff_label(value: str) -> str:
    hh, mm = (int(x) for x in value.split(":"))
    return f"{(hh % 12) or 12}:{mm:02d} {'AM' if hh < 12 else 'PM'}"


# ---- Hooks: price sheets ----


@_safe
def on_price_sheet_sent(db: Session, rev: SupplierPriceRevision) -> None:
    from app.services import price_approval_service

    supplier = db.get(Supplier, rev.supplier_id)
    to = supplier_emails(supplier)
    if not to:
        return
    names = [i["product_description"].title() for i in rev.items]
    subject = (
        f"SPAR adjusted your price for {names[0]}"
        if len(names) == 1
        else f"SPAR adjusted your prices for {_names(names)}"
    )
    cutoff = price_approval_service.approval_cutoff(db)
    closes = price_approval_service.expires_at(rev.delivery_date, cutoff)
    lines = [
        f"Hello {supplier.supplier_name},",
        f"SPAR has adjusted {len(names)} of your price{'s' if len(names) != 1 else ''} for delivery on "
        f"{_fmt_day(rev.delivery_date)}. Please approve or reject each one — you can give your own final price "
        "for any you reject.",
        f"Please answer by {price_approval_service.format_cutoff(cutoff)} on {_fmt_day(closes.date())}. "
        "If you don't, your own submitted prices apply.",
    ]
    if any(i.get("final_offer") for i in rev.items):
        lines.append("Items you rejected before are SPAR's final price — approve or reject only.")
    dispatch(
        Email(
            kind="PRICE_SHEET_SENT",
            to=to,
            subject=subject,
            lines=lines,
            table_header=("Item", "Your price", "SPAR price"),
            table=[
                (i["product_description"].title(), _rs(i["supplier_price"]), _rs(i["adjusted_price"]))
                for i in rev.items
            ],
            button=("Review and answer", "/supplier?tab=approvals"),
        )
    )


@_safe
def on_price_sheet_answered(db: Session, rev: SupplierPriceRevision) -> None:
    from app.services import price_approval_service as pas

    to = admin_emails(db)
    if not to:
        return
    supplier = db.get(Supplier, rev.supplier_id)
    name = supplier.supplier_name if supplier else "A supplier"
    responses = pas.item_responses(rev)
    approved = [i for i in rev.items if responses.get(i["supplier_price_id"], {}).get("decision") == pas.APPROVED]
    rejected = [i for i in rev.items if responses.get(i["supplier_price_id"], {}).get("decision") == pas.REJECTED]
    if rejected and approved:
        subject = f"{name} approved {len(approved)} and rejected {len(rejected)} of your adjusted prices"
    elif rejected:
        subject = f"{name} rejected your adjusted price{'s' if len(rejected) != 1 else ''}"
    else:
        subject = f"{name} approved your adjusted price{'s' if len(approved) != 1 else ''}"

    def answer(i: dict) -> str:
        r = responses.get(i["supplier_price_id"], {})
        if r.get("decision") == pas.APPROVED:
            return "Approved"
        counter = r.get("counter_price")
        return f"Rejected — their price {_rs(counter)}" if counter is not None else "Rejected"

    lines = [f"{name} answered your price sheet for delivery on {_fmt_day(rev.delivery_date)}."]
    if rev.rejection_reason:
        lines.append(f'Their note: "{rev.rejection_reason}"')
    dispatch(
        Email(
            kind="PRICE_SHEET_ANSWERED",
            to=to,
            subject=subject,
            lines=lines,
            table_header=("Item", "SPAR price", "Answer"),
            table=[(i["product_description"].title(), _rs(i["adjusted_price"]), answer(i)) for i in rev.items],
            button=("Open Price Approvals", "/admin?tab=priceApprovals"),
        )
    )


# ---- Hooks: purchase orders ----


@_safe
def on_purchase_order_issued(db: Session, po) -> None:
    supplier = db.get(Supplier, po.supplier_id)
    to = supplier_emails(supplier)
    if not to:
        return
    revised = po.revision > 1
    dispatch(
        Email(
            kind="PURCHASE_ORDER_ISSUED",
            to=to,
            subject=f"SPAR {'updated' if revised else 'issued'} purchase order {po.po_number}",
            lines=[
                f"Hello {supplier.supplier_name},",
                f"SPAR has {'updated' if revised else 'issued'} purchase order {po.po_number}"
                + (f" (revision {po.revision})" if revised else "")
                + f" for delivery on {_fmt_day(po.delivery_date)}: {len(po.items)} line(s), total {_rs(float(po.total_amount))}.",
            ],
            button=("View purchase order", "/supplier?tab=purchaseOrders"),
        )
    )


# ---- Hooks: messages ----


def _first_unread(db: Session, msg: Message, read_column) -> bool:
    """True when `msg` is the recipient's only unread message from its sender's side in this chat."""
    query = db.query(Message.id).filter(
        Message.id < msg.id,
        Message.sender_role == msg.sender_role,
        read_column.is_(None),
    )
    query = query.filter(
        Message.supplier_id == msg.supplier_id if msg.supplier_id else Message.supplier_id.is_(None),
        Message.branch_id == msg.branch_id if msg.branch_id else Message.branch_id.is_(None),
    )
    return query.first() is None


@_safe
def on_message(db: Session, msg: Message, attachment_count: int = 0) -> None:
    supplier = db.get(Supplier, msg.supplier_id) if msg.supplier_id else None
    branch = db.get(Branch, msg.branch_id) if msg.branch_id else None
    preview = _preview(msg.body, attachment_count)
    is_pair = supplier is not None and branch is not None

    # To the supplier: from SPAR Admin, or from a branch in their direct chat.
    if supplier and msg.sender_role in ("ADMIN", "BRANCH") and _first_unread(db, msg, Message.read_by_supplier_at):
        sender = "SPAR Admin" if msg.sender_role == "ADMIN" else f"{branch.branch_name} branch"
        dispatch(
            Email(
                kind="MESSAGE_TO_SUPPLIER",
                to=supplier_emails(supplier),
                subject=f"{sender} sent you a message",
                lines=[f"Hello {supplier.supplier_name},", f"{sender} sent you a message:", preview],
                button=("Open Messages", "/supplier?tab=messages"),
            )
        )

    # To Admin: anything a supplier or branch sends — to Admin, or to each other.
    if msg.sender_role in ("SUPPLIER", "BRANCH") and _first_unread(db, msg, Message.read_by_admin_at):
        sender = supplier.supplier_name if msg.sender_role == "SUPPLIER" else f"{branch.branch_name} branch"
        if is_pair:
            other = f"{branch.branch_name} branch" if msg.sender_role == "SUPPLIER" else supplier.supplier_name
            subject = f"{sender} sent a message to {other}"
            intro = f"{sender} sent a message to {other} (supplier ↔ branch chat):"
        else:
            subject = f"{sender} sent you a message"
            intro = f"{sender} sent you a message:"
        dispatch(
            Email(
                kind="PAIR_MESSAGE_TO_ADMIN" if is_pair else "MESSAGE_TO_ADMIN",
                to=admin_emails(db),
                subject=subject,
                lines=[intro, preview],
                button=("Open Messages", "/admin?tab=messages"),
            )
        )


# ---- Scheduled reminders ----


def _parse_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def send_price_submission_reminders(db: Session, now: datetime) -> int:
    """
    8 AM on a price submission day: every active supplier with an email who
    hasn't submitted yet is reminded to submit before the price cutoff.
    """
    if now.weekday() not in settings_service.parse_weekdays(
        settings_service.get_setting(db, settings_service.SUPPLIER_PRICE_DAYS)
    ):
        return 0
    deadline = settings_service.get_setting(db, settings_service.SUPPLIER_PRICE_DEADLINE)
    if not (_parse_time(settings.PRICE_REMINDER_TIME) <= now.time() < _parse_time(deadline)):
        return 0
    delivery = now.date() + timedelta(days=2)
    submitted = {
        sid for (sid,) in db.query(SupplierPrice.supplier_id).filter(SupplierPrice.delivery_date == delivery).distinct()
    }
    sent = 0
    for supplier in db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.id):
        to = supplier_emails(supplier)
        if not to or supplier.id in submitted:
            continue
        result = deliver(
            db,
            Email(
                kind="PRICE_SUBMISSION_REMINDER",
                to=to,
                subject=f"Please submit your prices before {_cutoff_label(deadline)} today",
                lines=[
                    f"Good morning {supplier.supplier_name},",
                    f"Today is a price submission day. Please submit your prices for delivery on "
                    f"{_fmt_day(delivery)} before {_cutoff_label(deadline)} today.",
                ],
                button=("Submit prices", "/supplier?tab=submit"),
                dedupe_key=f"price-reminder:{delivery.isoformat()}:{supplier.id}",
            ),
        )
        sent += result == "SENT"
    return sent


def send_approval_reminders(db: Session, now: datetime) -> int:
    """
    An hour before the approval cutoff (1 PM for a 2 PM cutoff): suppliers
    with a price sheet still unanswered are reminded to answer in time.
    """
    from app.services import price_approval_service as pas

    cutoff = pas.approval_cutoff(db)
    cutoff_today = datetime.combine(now.date(), cutoff, tzinfo=BUSINESS_TZ)
    remind_from = cutoff_today - timedelta(minutes=settings.APPROVAL_REMINDER_MINUTES_BEFORE)
    if not (remind_from <= now < cutoff_today):
        return 0
    delivery = now.date() + timedelta(days=pas.SUBMISSION_DAYS_BEFORE_DELIVERY)
    sheets = (
        db.query(SupplierPriceRevision)
        .filter(SupplierPriceRevision.status == pas.PENDING, SupplierPriceRevision.delivery_date == delivery)
        .all()
    )
    sent = 0
    for rev in sheets:
        supplier = db.get(Supplier, rev.supplier_id)
        to = supplier_emails(supplier)
        if not to:
            continue
        result = deliver(
            db,
            Email(
                kind="APPROVAL_REMINDER",
                to=to,
                subject=f"Reminder: please answer SPAR's adjusted prices before {pas.format_cutoff(cutoff)}",
                lines=[
                    f"Hello {supplier.supplier_name},",
                    f"You haven't approved or rejected SPAR's adjusted prices for delivery on "
                    f"{_fmt_day(rev.delivery_date)} yet. Please submit your answer before "
                    f"{pas.format_cutoff(cutoff)} today — after that it can't be changed and your own "
                    "submitted prices apply.",
                ],
                table_header=("Item", "Your price", "SPAR price"),
                table=[
                    (i["product_description"].title(), _rs(i["supplier_price"]), _rs(i["adjusted_price"]))
                    for i in rev.items
                ],
                button=("Answer now", "/supplier?tab=approvals"),
                dedupe_key=f"approval-reminder:{rev.id}",
            ),
        )
        sent += result == "SENT"
    return sent


def run_due_reminders(db: Session, now: datetime | None = None) -> None:
    now = (now or datetime.now(BUSINESS_TZ)).astimezone(BUSINESS_TZ)
    send_price_submission_reminders(db, now)
    send_approval_reminders(db, now)


_stop = threading.Event()
_thread: threading.Thread | None = None


def _run_forever() -> None:
    from app.core.database import SessionLocal

    while not _stop.is_set():
        db = SessionLocal()
        try:
            run_due_reminders(db)
        except Exception:
            logger.exception("Sending reminder emails failed; will retry.")
            db.rollback()
        finally:
            db.close()
        _stop.wait(60)


def start_scheduler() -> None:
    global _thread
    if not settings.EMAIL_REMINDERS or (_thread and _thread.is_alive()):
        return
    _stop.clear()
    _thread = threading.Thread(target=_run_forever, name="email-reminders", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()


# ---- Admin > Settings ----


def recent_log(db: Session, limit: int = 25) -> list[EmailLog]:
    return db.query(EmailLog).order_by(EmailLog.id.desc()).limit(limit).all()


def send_test_email(db: Session, admin: User) -> str:
    if not admin.email:
        from app.core.errors import ValidationFailedError

        raise ValidationFailedError("Add your email on your Account page first — the test goes to that address.")
    return deliver(
        db,
        Email(
            kind="TEST",
            to=[admin.email],
            subject="SPAR Fresh Procurement — test email",
            lines=["This is a test email from SPAR Fresh Procurement. If you can read this, email is working."],
            button=("Open the app", "/admin"),
        ),
    )

