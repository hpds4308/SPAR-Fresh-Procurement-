"""
DB-backed tests for notification emails — notification_service.py. Emails
built by request handlers are captured by the autouse `sent_emails`
fixture (conftest.py); scheduled reminders are sent through a stubbed
email_core.send_email.
"""
from datetime import date, datetime, time, timedelta

import pytest

from app.core import email as email_core
from app.models.email_log import EmailLog
from app.models.pricing import SupplierPrice
from app.services import message_service, notification_service as ns, price_approval_service as pas, pricing_service
from app.services.price_approval_service import BUSINESS_TZ


@pytest.fixture()
def ctx(db_session, make_supplier, make_branch, make_user, make_product):
    supplier = make_supplier(email="orders@bloomax.test")
    branch = make_branch(branch_name="Galle")
    admin = make_user(role="ADMIN", email="admin@spar.test")
    supplier_user = make_user(role="SUPPLIER", supplier=supplier)
    branch_user = make_user(role="BRANCH", branch=branch)
    delivery = datetime.now(BUSINESS_TZ).date() + timedelta(days=5)
    product = make_product(description="BANANA AMBUL")
    row = SupplierPrice(
        supplier_id=supplier.id, product_id=product.id, delivery_date=delivery, price=180, unit_code="KG",
        submitted_by=supplier_user.id,
    )
    db_session.add(row)
    db_session.commit()
    return dict(
        supplier=supplier, branch=branch, admin=admin, supplier_user=supplier_user, branch_user=branch_user,
        delivery=delivery, row=row,
    )


def _send_sheet(db_session, ctx):
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["row"].id, 165)
    return pas.send_for_approval(db_session, ctx["admin"], ctx["supplier"].id, ctx["delivery"])


def test_supplier_is_emailed_when_spar_adjusts_their_price(db_session, ctx, sent_emails):
    _send_sheet(db_session, ctx)
    [email] = sent_emails
    assert email.to == ["orders@bloomax.test"]
    assert email.subject == "SPAR adjusted your price for Banana Ambul"
    assert email.table == [("Banana Ambul", "Rs. 180.00", "Rs. 165.00")]
    assert any("2:00 PM" in line for line in email.lines)


def test_supplier_without_email_gets_nothing(db_session, ctx, sent_emails):
    ctx["supplier"].email = None
    db_session.commit()
    _send_sheet(db_session, ctx)
    assert sent_emails == []


def test_admin_is_emailed_when_supplier_answers(db_session, ctx, sent_emails):
    rev = _send_sheet(db_session, ctx)
    sent_emails.clear()
    pas.respond(
        db_session, ctx["supplier_user"], rev.id, snapshot_hash=rev.snapshot_hash,
        decisions=[{"supplier_price_id": ctx["row"].id, "decision": "REJECTED", "counter_price": 172}],
        note=None, signature_image=None, agreed=False, ip_address=None, user_agent=None,
    )
    [email] = sent_emails
    assert email.to == ["admin@spar.test"]
    assert email.subject == f"{ctx['supplier'].supplier_name} rejected your adjusted price"
    assert email.table == [("Banana Ambul", "Rs. 165.00", "Rejected — their price Rs. 172.00")]


def test_branch_message_emails_supplier_and_admin_once_per_unread_batch(db_session, ctx, sent_emails):
    message_service.send_to_peer(db_session, ctx["branch_user"], ctx["supplier"].id, "Need 20kg more")
    subjects = sorted(e.subject for e in sent_emails)
    assert subjects == sorted([
        "Galle branch sent you a message",
        f"Galle branch sent a message to {ctx['supplier'].supplier_name}",
    ])
    to_supplier = next(e for e in sent_emails if e.kind == "MESSAGE_TO_SUPPLIER")
    assert "Need 20kg more" in to_supplier.lines

    # Still unread: a second message doesn't email again.
    sent_emails.clear()
    message_service.send_to_peer(db_session, ctx["branch_user"], ctx["supplier"].id, "Please confirm")
    assert sent_emails == []

    # Once the supplier has read it, the next one does.
    message_service.list_with_peer(db_session, ctx["supplier_user"], ctx["branch"].id)
    message_service.send_to_peer(db_session, ctx["branch_user"], ctx["supplier"].id, "Thanks")
    assert [e.kind for e in sent_emails] == ["MESSAGE_TO_SUPPLIER"]


def test_admin_message_emails_supplier(db_session, ctx, sent_emails):
    message_service.send_as_admin(db_session, ctx["admin"], ctx["supplier"].id, "Hi")
    [email] = sent_emails
    assert (email.to, email.subject) == (["orders@bloomax.test"], "SPAR Admin sent you a message")


def test_supplier_message_emails_admin(db_session, ctx, sent_emails):
    message_service.send_as_supplier(db_session, ctx["supplier_user"], "Delivery delayed")
    [email] = sent_emails
    assert (email.to, email.subject) == (["admin@spar.test"], f"{ctx['supplier'].supplier_name} sent you a message")


def test_supplier_message_to_branch_emails_admin(db_session, ctx, sent_emails):
    message_service.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "On the way")
    [email] = sent_emails
    assert email.kind == "PAIR_MESSAGE_TO_ADMIN"
    assert email.subject == f"{ctx['supplier'].supplier_name} sent a message to Galle branch"


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(email_core, "send_email", lambda **kw: sent.append(kw))
    return sent


def _next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7 or 7)


def test_morning_price_reminder(db_session, ctx, outbox, make_supplier):
    make_supplier(email=None)  # no email -> no reminder
    monday = _next_weekday(datetime.now(BUSINESS_TZ).date(), 0)

    def at(h, m):
        return datetime.combine(monday, time(h, m), tzinfo=BUSINESS_TZ)

    assert ns.send_price_submission_reminders(db_session, at(7, 59)) == 0
    assert ns.send_price_submission_reminders(db_session, at(8, 0)) == 1
    assert outbox[0]["to"] == ["orders@bloomax.test"]
    assert outbox[0]["subject"] == "Please submit your prices before 12:00 PM today"
    # Once a day, however often the scheduler wakes up.
    assert ns.send_price_submission_reminders(db_session, at(8, 1)) == 0
    assert db_session.query(EmailLog).filter(EmailLog.kind == "PRICE_SUBMISSION_REMINDER").count() == 1
    # Not on a non-submission day (Tuesday).
    assert ns.send_price_submission_reminders(db_session, at(8, 0) + timedelta(days=1)) == 0


def test_morning_reminder_skips_suppliers_who_already_submitted(db_session, ctx, outbox):
    monday = _next_weekday(datetime.now(BUSINESS_TZ).date(), 0)
    db_session.add(
        SupplierPrice(
            supplier_id=ctx["supplier"].id, product_id=ctx["row"].product_id, delivery_date=monday + timedelta(days=2),
            price=100, unit_code="KG", submitted_by=ctx["supplier_user"].id,
        )
    )
    db_session.commit()
    morning = datetime.combine(monday, time(8, 30), tzinfo=BUSINESS_TZ)
    assert ns.send_price_submission_reminders(db_session, morning) == 0


def test_one_pm_reminder_for_unanswered_sheet(db_session, ctx, outbox):
    rev = _send_sheet(db_session, ctx)
    submission_day = rev.delivery_date - timedelta(days=2)

    def at(h, m):
        return datetime.combine(submission_day, time(h, m), tzinfo=BUSINESS_TZ)

    assert ns.send_approval_reminders(db_session, at(12, 59)) == 0
    assert ns.send_approval_reminders(db_session, at(13, 0)) == 1
    assert outbox[0]["subject"] == "Reminder: please answer SPAR's adjusted prices before 2:00 PM"
    assert ns.send_approval_reminders(db_session, at(13, 30)) == 0  # once
    assert ns.send_approval_reminders(db_session, at(14, 0)) == 0  # closed


def test_reminder_logged_as_skipped_when_email_not_configured(db_session, ctx, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monday = _next_weekday(datetime.now(BUSINESS_TZ).date(), 0)
    ns.send_price_submission_reminders(db_session, datetime.combine(monday, time(9, 0), tzinfo=BUSINESS_TZ))
    log = db_session.query(EmailLog).filter(EmailLog.kind == "PRICE_SUBMISSION_REMINDER").one()
    assert log.status == "SKIPPED"


def test_html_escapes_message_content():
    email = ns.Email(kind="X", to=["a@b.c"], subject="s", lines=["<script>alert(1)</script>"])
    text, page = ns._render(email)
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<script>alert(1)</script>" in text


def test_admin_account_and_email_status(client, ctx, auth_headers):
    h = auth_headers(ctx["admin"])
    resp = client.put(
        "/api/v1/users/me/account", headers=h,
        json={"full_name": "  Dinu  P ", "email": "procurement@spar.test", "phone": "0771234567"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "Dinu P"
    assert client.get("/api/v1/users/me/account", headers=h).json()["email"] == "procurement@spar.test"

    bad = client.put("/api/v1/users/me/account", headers=h, json={"full_name": "x", "email": "nope"})
    assert bad.status_code == 422

    status = client.get("/api/v1/settings/email-status", headers=h).json()
    assert "procurement@spar.test" in status["admin_recipients"]
    assert client.get("/api/v1/settings/email-status", headers=auth_headers(ctx["supplier_user"])).status_code == 403
