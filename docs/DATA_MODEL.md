# Data Model & Business Rules

This document exists because the same word — "delivery date" — means three
different things in three different parts of this system, and that
mismatch has already caused two real bugs (a duplicate-order crash, and
Cost Price silently showing nothing). Read this before touching date logic
anywhere in the codebase.

## The three delivery-date conventions

| Feature | Table | Delivery date = | Why |
|---|---|---|---|
| Branch Orders | `orders` | **order date + 2 days** | Same lead time as supplier pricing (below) — a branch's order and the prices used to fulfill it are submitted the same day, for the same future delivery date. |
| Supplier Orders (Admin → Supplier) | `supplier_order_items` | whatever delivery date Admin targets | Mirrors branch orders — Admin builds a supplier order for whichever delivery date the Order Matrix shows real demand for (now typically order date + 2, since that's what branch orders target). |
| Submit Prices | `supplier_prices` | **order date + 2 days** | Suppliers need lead time to plan and price ahead. |
| Keells / Market Reference Prices | `market_reference_prices` | whatever date Admin picks | Independent of the order/pricing cycle — just a dated reference snapshot. |

**The consequence:** since branch orders and supplier pricing both target
order date + 2, an order built by Admin will usually *have* an exact-date
match in `supplier_prices` now — this used to be the rare case (branch
orders were same-day while pricing was +2) and is now the common one. An
exact match can still be missing when a supplier hasn't submitted for
that specific date yet (missed cutoff, new product). See "Cost Price
resolution" below for how we handle it either way.

## Cost Price resolution (`supplier_order_service._resolve_prices`)

When Admin builds a Supplier Order, "Cost Price" for each line is resolved
in this priority order:

1. **Explicit per-line override** — Admin typed a specific price on that
   order line (`SupplierOrderItem.agreed_price`).
2. **Sent Adjusted Price** — Admin negotiated a price on the Supplier
   Prices page *and clicked Send* for the exact order date.
   A draft adjustment that was never sent does NOT count.
3. **Submitted price** for the exact order date.
4. **Fallback: most recent submitted/adjusted price for that product, any
   date** — flagged `price_is_estimated: true` in the API response and
   shown in amber in the UI, for whenever a supplier hasn't submitted a
   price for that exact delivery date yet.

If none of the four apply, Cost Price is `null` and shows as "—".

**Golden rule:** every place that computes "what does this cost" must use
this same four-tier resolution, not read `agreed_price` or
`SupplierPrice.price` directly. See `_resolve_prices` and `_to_item_out`
in `supplier_order_service.py` for the canonical implementation — Master
Data Sheet's Cost Price uses a *different*, simpler rule (see below) and
that's intentional, not an oversight.

## Master Data Sheet's Cost Price is NOT the same calculation

Master Data Sheet's "Cost Price" column is deliberately different from
Supplier Orders' Cost Price: it's the **highest of suppliers' most recent
SUBMITTED prices** — explicitly never their Adjusted Price, even though
Adjusted Price is what shows in the per-supplier columns right next to
it. Computed live in `master_data_service._latest_prices`
(`submitted_only`, not `adjusted_or_submitted`). This is a margin-analysis
figure (a conservative ceiling for GP% math based on what suppliers are
actually asking), not a "what will we pay" figure. Don't try to unify
this with Supplier Orders' Cost Price — they answer different questions,
and don't accidentally swap `submitted_only` for `adjusted_or_submitted`
when touching this function — that's the one thing this rule depends on.

## Adjusted Price: draft vs. sent

`SupplierPrice.adjusted_price` and `SupplierPrice.sent_to_supplier_at` are
two separate fields on purpose:

- Admin can set `adjusted_price` at any time — it's a draft, visible only
  to Admin (e.g. on Master Data Sheet, which shows drafts too since it's
  Admin-only).
- The supplier only ever sees it once `sent_to_supplier_at` is set (via
  the explicit "Send" / "Send All" action on Supplier Prices).
- Editing `adjusted_price` after it was sent automatically clears
  `sent_to_supplier_at` — the supplier never sees a stale number; Admin
  must re-send.

Anywhere you resolve "the adjusted price," ask: does this audience get to
see drafts (Admin-only screens) or only sent values (supplier-facing
screens, and the 4-tier Cost Price resolution above)?

## One thread per supplier (Messages)

There is exactly one chat thread per supplier (`messages.supplier_id`),
shared by every Admin user and every user of that supplier — not one
thread per order, per product, or per user pair. `sender_role` +
`sender_user_id` identify who actually typed each message within the
shared thread.

## Order uniqueness: `order_date`, not `delivery_date`

`orders` is constrained one-per-branch-per-`order_date`
(`uq_orders_branch_order_date`, migration `0009`), not per `delivery_date`.
This was originally per-`delivery_date` and caused a real production bug:
before `order_date == delivery_date` was enforced, a branch's last
"old-rule" order (order_date = yesterday, delivery_date = today) collided
with a legitimately new order placed today, because both targeted the
same `delivery_date`. If you ever reintroduce an order_date/delivery_date
offset, re-audit this constraint first.

**Update:** the order_date/delivery_date offset was reintroduced (branch
orders now target order_date + 2, matching supplier pricing) — re-audited
per the note above. The constraint is keyed on `order_date` alone, so two
different `order_date`s never collide even though they may (now, usually
do) share the same `delivery_date`; still safe.

## Quick reference: which fields are user-editable vs. computed

| Field | Editable by | Notes |
|---|---|---|
| `SupplierPrice.price` | Supplier | Their own submission |
| `SupplierPrice.adjusted_price` | Admin | Draft until sent |
| `SupplierOrderItem.agreed_price` | Admin | Per-line override, highest priority in Cost Price resolution |
| `Product.target_gp_percent` | Admin | Defaults to 0.30 if never set |
| `Product.selling_price` | Admin | Manual, no computation |
| `Product.reference_cost_price` | — | Column still exists in the DB but is **unused** — Master Data Sheet computes Cost Price live instead. Safe to ignore; not worth a migration to drop it. |
| `MarketReferencePrice.price` | Admin | Via the Keells Prices page only — the same column on Supplier Prices is read-only |
