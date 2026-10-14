"""
DB-backed tests for chat — message_service.py, focused on the direct
supplier <-> branch conversations and how they stay apart from the
Admin threads.
"""
import pytest

from app.core.errors import NotFoundError
from app.services import message_service as svc


@pytest.fixture()
def ctx(make_supplier, make_branch, make_user):
    supplier = make_supplier()
    other_supplier = make_supplier()
    branch = make_branch()
    other_branch = make_branch()
    return dict(
        supplier=supplier,
        branch=branch,
        other_branch=other_branch,
        other_supplier=other_supplier,
        supplier_user=make_user(role="SUPPLIER", supplier=supplier),
        branch_user=make_user(role="BRANCH", branch=branch),
        other_branch_user=make_user(role="BRANCH", branch=other_branch),
        admin=make_user(role="ADMIN"),
    )


def test_supplier_and_branch_chat_both_ways(db_session, ctx):
    svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "Tomatoes arrive at 7am")
    svc.send_to_peer(db_session, ctx["branch_user"], ctx["supplier"].id, "Thanks, noted")

    for user, other in ((ctx["supplier_user"], ctx["branch"].id), (ctx["branch_user"], ctx["supplier"].id)):
        bodies = [m.body for m in svc.list_with_peer(db_session, user, other)]
        assert bodies == ["Tomatoes arrive at 7am", "Thanks, noted"]


def test_other_branch_cannot_see_the_chat(db_session, ctx):
    svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "Only for you")
    assert svc.list_with_peer(db_session, ctx["other_branch_user"], ctx["supplier"].id) == []


def test_unread_counts_and_marking_read(db_session, ctx):
    svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "Hello branch")
    assert svc.branch_unread_count(db_session, ctx["branch_user"]) == 1
    contacts = {c.id: c for c in svc.list_contacts(db_session, ctx["branch_user"])}
    assert contacts[ctx["supplier"].id].unread_count == 1
    assert contacts[ctx["supplier"].id].last_message_body == "Hello branch"

    svc.list_with_peer(db_session, ctx["branch_user"], ctx["supplier"].id)
    assert svc.branch_unread_count(db_session, ctx["branch_user"]) == 0
    # The sender never has their own message as unread.
    assert svc.supplier_unread_count(db_session, ctx["supplier_user"]) == 0


def test_contacts_list_every_active_counterparty(db_session, ctx):
    supplier_contacts = {c.id for c in svc.list_contacts(db_session, ctx["supplier_user"])}
    assert {ctx["branch"].id, ctx["other_branch"].id} <= supplier_contacts
    branch_contacts = {c.id for c in svc.list_contacts(db_session, ctx["branch_user"])}
    assert {ctx["supplier"].id, ctx["other_supplier"].id} <= branch_contacts


def test_unknown_or_inactive_counterparty_is_refused(db_session, ctx, make_branch):
    closed = make_branch(status="INACTIVE")
    with pytest.raises(NotFoundError):
        svc.send_to_peer(db_session, ctx["supplier_user"], closed.id, "hi")
    with pytest.raises(NotFoundError):
        svc.send_to_peer(db_session, ctx["supplier_user"], 999999, "hi")


def test_pair_chats_stay_out_of_admin_threads(db_session, ctx):
    svc.send_as_supplier(db_session, ctx["supplier_user"], "To admin")
    svc.send_as_branch(db_session, ctx["branch_user"], "Branch to admin")
    svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "To branch")

    assert [m.body for m in svc.list_for_supplier(db_session, ctx["supplier_user"], mark_read=False)] == ["To admin"]
    assert [m.body for m in svc.list_for_branch(db_session, ctx["branch_user"], mark_read=False)] == ["Branch to admin"]
    assert [m.body for m in svc.list_for_admin(db_session, ctx["supplier"].id, mark_read=False)] == ["To admin"]
    assert [m.body for m in svc.list_for_admin_branch(db_session, ctx["branch"].id, mark_read=False)] == ["Branch to admin"]
    # Admin's badge covers all three, split per Messages tab.
    unread = svc.admin_unread_count(db_session)
    assert (unread.count, unread.suppliers, unread.branches, unread.supplier_branch) == (3, 1, 1, 1)


def test_admin_is_notified_of_pair_chats(db_session, ctx):
    svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "Delivery delayed")

    unread = svc.admin_unread_count(db_session)
    assert (unread.count, unread.supplier_branch) == (1, 1)
    assert unread.latest_supplier_branch == f"{ctx['supplier'].supplier_name} → {ctx['branch'].branch_name}"
    assert unread.latest_supplier_branch_id is not None

    [conv] = svc.list_pair_conversations(db_session)
    assert (conv.supplier_id, conv.branch_id) == (ctx["supplier"].id, ctx["branch"].id)
    assert (conv.message_count, conv.unread_count) == (1, 1)
    assert conv.last_sender_role == "SUPPLIER"

    # Opening it clears Admin's badge — but not the branch's.
    bodies = [m.body for m in svc.list_pair_for_admin(db_session, ctx["supplier"].id, ctx["branch"].id)]
    assert bodies == ["Delivery delayed"]
    assert svc.admin_unread_count(db_session).count == 0
    assert svc.list_pair_conversations(db_session)[0].unread_count == 0
    assert svc.branch_unread_count(db_session, ctx["branch_user"]) == 1


def test_branch_reply_names_branch_first(db_session, ctx):
    svc.send_to_peer(db_session, ctx["branch_user"], ctx["supplier"].id, "Need more onions")
    unread = svc.admin_unread_count(db_session)
    assert unread.latest_supplier_branch == f"{ctx['branch'].branch_name} → {ctx['supplier'].supplier_name}"


def test_pair_chat_endpoints(client, ctx, auth_headers):
    supplier_h = auth_headers(ctx["supplier_user"])
    branch_h = auth_headers(ctx["branch_user"])
    admin_h = auth_headers(ctx["admin"])

    resp = client.post(f"/api/v1/messages/mine/with/{ctx['branch'].id}", headers=supplier_h, json={"body": "Hi"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["supplier_id"] == ctx["supplier"].id and resp.json()["branch_id"] == ctx["branch"].id

    assert client.get("/api/v1/messages/mine/unread-count", headers=branch_h).json() == {"count": 1}
    resp = client.get(f"/api/v1/messages/mine/with/{ctx['supplier'].id}", headers=branch_h)
    assert [m["body"] for m in resp.json()] == ["Hi"]

    resp = client.get("/api/v1/messages/admin/unread-count", headers=admin_h)
    assert resp.json()["count"] == 1 and resp.json()["supplier_branch"] == 1

    resp = client.get("/api/v1/messages/admin/supplier-branch", headers=admin_h)
    assert resp.status_code == 200 and len(resp.json()) == 1
    resp = client.get(
        f"/api/v1/messages/admin/supplier-branch/{ctx['supplier'].id}/{ctx['branch'].id}", headers=admin_h
    )
    assert [m["body"] for m in resp.json()] == ["Hi"]

    # Only Admin can use the oversight view; Admin can't post into a pair chat.
    assert client.get("/api/v1/messages/admin/supplier-branch", headers=supplier_h).status_code == 403
    assert client.post(f"/api/v1/messages/mine/with/{ctx['branch'].id}", headers=admin_h, json={"body": "x"}).status_code == 403


# ---- Attachments ----

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"x" * 64


def _upload(db_session, user, name="photo.png", data=PNG):
    return svc.upload_attachment(db_session, user, name, data)


def test_message_with_attachment_only(db_session, ctx):
    a = _upload(db_session, ctx["supplier_user"])
    msg = svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "", attachment_ids=[a.id])
    assert msg.body == ""
    assert [(x.filename, x.content_type) for x in msg.attachments] == [("photo.png", "image/png")]

    [listed] = svc.list_with_peer(db_session, ctx["branch_user"], ctx["supplier"].id)
    assert [x.id for x in listed.attachments] == [a.id]
    contacts = {c.id: c for c in svc.list_contacts(db_session, ctx["branch_user"])}
    assert contacts[ctx["supplier"].id].last_message_body == "📎 Attachment"


def test_empty_message_without_attachment_is_refused(db_session, ctx):
    from app.core.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        svc.send_as_supplier(db_session, ctx["supplier_user"], "   ")


def test_attachment_type_and_content_are_checked(db_session, ctx):
    from app.core.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        _upload(db_session, ctx["supplier_user"], "page.html", b"<script>alert(1)</script>")
    with pytest.raises(ValidationFailedError):
        _upload(db_session, ctx["supplier_user"], "fake.png", b"not really a png")
    with pytest.raises(ValidationFailedError):
        _upload(db_session, ctx["supplier_user"], "big.pdf", b"%PDF" + b"x" * svc.MAX_ATTACHMENT_BYTES)
    assert _upload(db_session, ctx["supplier_user"], "invoice.pdf", PDF).content_type == "application/pdf"


def test_cannot_send_someone_elses_upload(db_session, ctx):
    from app.core.errors import ValidationFailedError

    a = _upload(db_session, ctx["branch_user"])
    with pytest.raises(ValidationFailedError):
        svc.send_as_supplier(db_session, ctx["supplier_user"], "hi", attachment_ids=[a.id])


def test_who_can_download(db_session, ctx):
    a = _upload(db_session, ctx["supplier_user"], "invoice.pdf", PDF)
    # Before it's sent, only the uploader can fetch it.
    with pytest.raises(NotFoundError):
        svc.get_attachment(db_session, ctx["branch_user"], a.id)
    svc.send_to_peer(db_session, ctx["supplier_user"], ctx["branch"].id, "Invoice", attachment_ids=[a.id])

    for user in (ctx["supplier_user"], ctx["branch_user"], ctx["admin"]):
        assert svc.get_attachment(db_session, user, a.id).data == PDF
    with pytest.raises(NotFoundError):
        svc.get_attachment(db_session, ctx["other_branch_user"], a.id)


def test_attachment_endpoints(client, ctx, auth_headers):
    supplier_h = auth_headers(ctx["supplier_user"])
    resp = client.post(
        "/api/v1/messages/attachments",
        headers=supplier_h,
        files={"file": ("Delivery note.pdf", PDF, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    att = resp.json()

    resp = client.post(
        f"/api/v1/messages/mine/with/{ctx['branch'].id}",
        headers=supplier_h,
        json={"body": "", "attachment_ids": [att["id"]]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["attachments"][0]["filename"] == "Delivery note.pdf"

    resp = client.get(f"/api/v1/messages/attachments/{att['id']}", headers=auth_headers(ctx["branch_user"]))
    assert resp.status_code == 200
    assert resp.content == PDF
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "Delivery%20note.pdf" in resp.headers["content-disposition"]

    resp = client.get(f"/api/v1/messages/attachments/{att['id']}", headers=auth_headers(ctx["other_branch_user"]))
    assert resp.status_code == 404
