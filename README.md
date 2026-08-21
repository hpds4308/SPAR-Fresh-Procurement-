# SPAR Sri Lanka — Fresh Produce Procurement Platform

Phase 3 build. On top of the Phase 2 foundation (database, backend, health
check), this adds: real login, role-based access (Admin / Branch /
Supplier), password security, account lockout, and one working dashboard
per role. Actual ordering, pricing, and procurement screens arrive in the
next phases.

## What you need installed

- **Docker Desktop** (includes Docker Compose) — https://www.docker.com/products/docker-desktop/
  That's the only thing you need installed on your machine. Everything
  else (Python, Node, PostgreSQL) runs inside containers.

## How to run it (step by step)

1. **Open a terminal** in this project folder (the folder containing this
   README and `docker-compose.yml`).

2. **Create your environment file** — copy the example and (optionally)
   edit the secret key:
   ```
   cp .env.example .env
   ```

3. **Start everything**:
   ```
   docker compose up --build
   ```
   The first run takes a few minutes (downloading images, installing
   dependencies). Leave this terminal window open — it shows live logs.

4. **Create the database tables** — open a **second terminal**, in the
   same folder, and run:
   ```
   docker compose exec backend alembic upgrade head
   ```

5. **Load the starter data** (13 branches, 16 suppliers, the 188-item
   product list) — in the same terminal:
   ```
   docker compose exec backend python -m scripts.seed_master_data
   ```
   This will print out the 4 products whose POS codes are missing/invalid
   in the source file — those are flagged for review, not guessed at.

6. **Create login accounts** — one Admin account, plus one account per
   branch and per supplier:
   ```
   docker compose exec backend python -m scripts.seed_users
   ```
   This prints every username it created and the shared starting
   password. **Write these down** — this is the only time they're shown.

7. **Open the app in your browser**: http://localhost:5173
   You'll land on a login page. Sign in with any of the printed usernames
   (e.g. `admin`, `br01` for Kurunegala branch, `sup01` for Bloomax) and
   the starting password. You'll be taken straight to the right dashboard
   for that account (Admin, Branch, or Supplier).

   - Backend API docs: http://localhost:8000/api/v1/docs
   - Health check directly: http://localhost:8000/api/v1/health

8. **To stop everything**: go back to the first terminal and press
   `Ctrl + C`, or run `docker compose down` from either terminal.

9. **To start it again later** (data is kept):
   ```
   docker compose up
   ```
   (no `--build` needed unless you changed dependencies — you do NOT
   need to run the seed scripts again, your accounts and data are saved)

10. **Updating an already-running install to this version**: replace your
    project folder with this new zip as before, then from a terminal in
    that folder run:
    ```
    docker compose up -d --build backend
    docker compose exec backend alembic upgrade head
    ```
    (If this version's Alembic message says "no migrations to apply" or
    similar, that's fine — not every update changes the database schema.)
    No need to re-run `seed_master_data` or `seed_users` — your existing
    accounts and product data are untouched. The frontend container picks
    up new files automatically; if the browser still shows old content,
    hard-refresh with Ctrl+Shift+R.

## What's actually in this build (Phase 3 + Phase 4 + Phase 5a + Phase 5b + Phase 5c + Phase 5d + Phase 5e + Phase 5f + Phase 5g)

- PostgreSQL database, running in Docker with a persistent volume (your
  data survives restarts).
- FastAPI backend with:
  - a `/api/v1/health` endpoint proving the API can reach the database
  - Alembic migrations (versioned schema changes)
  - the master-data tables: branches, suppliers, product categories,
    units, products, system settings, audit logs
  - **real authentication**: hashed passwords (argon2), JWT access +
    refresh tokens, failed-login lockout, `/auth/login`, `/auth/me`,
    `/auth/change-password`, `/auth/logout`
  - **role-based access control**: Admin / Branch / Supplier roles,
    enforced on the backend — never trusted from the frontend
  - an Admin-only `/users` endpoint to list/activate/deactivate accounts
  - every login, logout, and password change is written to the audit log
  - **Phase 4 — branch ordering**: `orders` / `order_lines` tables,
    `/api/v1/products` (read-only product list) and `/api/v1/orders`
    (submit, list, view). A branch places one order per day, always for
    delivery the *next* day, and only before the daily cutoff (default
    2:00 PM, Asia/Colombo time — configurable via `BRANCH_ORDER_DEADLINE`
    in `.env`). Branches never choose a supplier; that assignment is an
    Admin step coming in a later phase. The cutoff and "one order per
    branch per delivery date" rule are both enforced on the backend (the
    latter with a database constraint too), not just in the UI.
  - **Phase 5a — Admin order overview**: `/api/v1/orders/admin/matrix`
    returns every active product as a row and every branch as a column,
    with quantities ordered for a chosen delivery date — the consolidated
    view you sketched out. `/api/v1/orders/admin/matrix/export` returns
    the same data as a downloadable `.xlsx` file. Supplier assignment
    (turning this into purchase orders per supplier) is a separate,
    upcoming step.
  - **Phase 5b — supplier price submission**: `supplier_prices` table,
    `/api/v1/pricing` (submit/update), `/api/v1/pricing/mine` (view own
    submissions), `/api/v1/pricing/window`. A supplier submits prices for
    whichever products they can supply, before the daily cutoff (default
    12:00, Asia/Colombo — configurable via `SUPPLIER_PRICE_DEADLINE` in
    `.env`), and those prices apply to the *next* delivery day — same
    convention as branch orders, so Admin can line up what was ordered
    against what was quoted for the same day. Resubmitting a price before
    the cutoff updates it rather than creating a duplicate. Admin's
    screen to compare these prices, negotiate, and assign supplier(s) per
    product (with support for splitting one product across multiple
    suppliers) is the next phase.
  - **Phase 5c — Admin supplier assignment**: `supplier_assignments`
    table, `GET /api/v1/orders/admin/product/{id}/comparison` (all
    suppliers' quoted prices for a product + delivery date, alongside
    total branch demand), `PUT /api/v1/orders/admin/product/{id}/assignments`
    (set which supplier(s) get how much, at what *agreed* price — which
    may differ from their original quote if Admin negotiated it; a
    product's demand can be split across several suppliers). Once every
    product line on a branch's order is fully covered by assignments,
    that order's status automatically moves from SUBMITTED to ASSIGNED —
    and reverts back if an assignment is later reduced or removed.
    Sending the finalized order + agreed price to each supplier (so they
    see their own confirmed order) is the next phase.
  - **Phase 5d — supplier sees their confirmed orders**:
    `GET /api/v1/assignments/mine` returns a supplier's own confirmed
    assignments — which products, how much, and at what *agreed* price
    (not their original quote) — for a chosen delivery date, with a line
    total and grand total. This is distinct from `/pricing/mine`, which
    only shows what a supplier quoted; not every quote gets assigned, so
    this is the actual order they're expected to fulfill.
  - **Phase 5e — Admin reporting**: `GET /api/v1/reports/admin/summary`
    (and `.../export` for the same data as a multi-sheet `.xlsx`)
    aggregates orders and assignments across a date range: total orders,
    fulfillment rate (% of orders fully assigned), total committed spend,
    spend by day/supplier/category, and top products by quantity ordered.
    "Spend" is always based on Admin's *agreed* prices from assignments,
    not raw branch demand — demand isn't money until it's priced and
    assigned. Fulfillment is measured by order count, not by summing
    quantities across products, since different products use different
    units (kg, pcs, ...) that can't be added together meaningfully.
  - **Phase 5f — branch delivery confirmation**:
    `PUT /api/v1/orders/{order_id}/confirm-delivery` lets a branch record
    what actually arrived for one of their ASSIGNED orders — quantity per
    product, which can differ from what was ordered (that's the point: it
    catches shortages, overages, or substitutions rather than assuming
    delivery always matches the order). Once confirmed, the order moves
    to a new CONFIRMED status and stays there — a later change to
    supplier assignments on that delivery date won't reopen it.
  - **Phase 5g — supplier orders by branch**: a new
    `supplier_order_items` table plus `/api/v1/supplier-orders`
    (`GET /mine` for suppliers, `GET`/`PUT /admin` for Admin), and
    `GET /api/v1/pricing/admin` for Admin. This adds three things:
    1) **Admin can hand an order directly to a supplier, broken down by
       branch** — e.g. Malabe: Avocado 200kg, Pineapple 100kg;
       Kalubovila: Avocado 300kg, Pineapple 200kg — using the new
       "Supplier Orders" tab, which can optionally pull real branch
       demand for the chosen delivery date as click-to-add suggestions.
    2) **Suppliers can see their own orders grouped branch by branch**
       (new "Orders by Branch" tab), instead of only a flat product
       list.
    3) **Admin can browse every supplier's submitted prices for a
       delivery date in one screen** (new "Supplier Prices" tab), with
       the lowest quote per product highlighted, and filter by supplier
       or search by product — separate from the one-product-at-a-time
       comparison used during supplier assignment.
    This is a separate mechanism from Phase 5c's supplier assignments
    (which splits a product's *total* demand across suppliers without
    branch detail) — Admin can use either or both, they don't conflict.
- A React frontend with:
  - a real login page
  - automatic redirect to the right dashboard based on role
  - route protection (a Branch user can't open the Admin dashboard URL,
    even by typing it directly)
  - **Branch dashboard**: a searchable/filterable product list to enter
    quantities against and submit as an order, plus an order history tab
    showing past submissions, their line items, and — once an order is
    ASSIGNED — a "Confirm Delivery" action to record what actually
    arrived per product, with mismatches from the ordered quantity
    highlighted
  - **Admin dashboard**: a "Branch Orders" tab with the consolidated
    order matrix (products x branches, delivery-date picker, Excel
    export), and now a "Reports" tab with date-range KPIs, spend
    breakdowns by day/supplier/category, and a top-products table, also
    exportable to Excel
  - **Supplier dashboard**: a "Submit Prices" tab, a "My Submitted
    Prices" tab, and a "Confirmed Orders" tab showing exactly what
    Admin has assigned to that supplier — product, quantity, agreed
    price, and a running total — with a delivery-date picker
- Your real product list (188 items) and supplier list (16 suppliers),
  converted into seed files under `/database/seed/`, ready to load.
- One login account per branch and per supplier, plus one Admin account
  (see step 6 above) — shared logins as agreed, not per staff member.

**Trying out Phase 4**: log in as any branch (e.g. `br02` / Kandy). You'll
land on the Branch dashboard with a "New Order" tab open — search or
filter products, enter quantities, and submit. Check the "My Orders" tab
afterward to see it recorded. If you're testing after 2:00 PM, the form
will show ordering is closed for the day instead — that's expected.

**Trying out Phase 5a**: log in as `admin`. The dashboard now shows the
order matrix for the most recent delivery date with submitted orders —
switch the date dropdown to see other days, or click "Download Excel" to
get the same table as a spreadsheet.

**Trying out Phase 5b**: log in as a supplier (e.g. `sup01` / Bloomax).
Search or filter products, enter Rs. prices for what that supplier can
provide, and submit. Revisit the form later (before the 12:00 cutoff) to
see your own prices pre-filled and adjust them. If you're testing after
12:00, the form will show submission is closed for the day instead —
that's expected.

**Trying out Phase 5c**: with at least one branch order and one supplier
price submitted for the same delivery date, log in as `admin` and click
any product row in the matrix. A panel opens showing all suppliers who
quoted a price for that product — click "Assign" next to one to add them,
enter the quantity and the agreed price (pre-filled from their quote, but
editable if you negotiated a different number), and add more suppliers to
split the quantity if needed. "Save Assignment" writes it, and once a
branch's whole order is covered it flips to ASSIGNED — check "My Orders"
on that branch's dashboard to see the status change.

**Trying out Phase 5d**: after Admin assigns a supplier to at least one
product (Phase 5c), log in as that supplier and open the "Confirmed
Orders" tab. You should see the product, quantity, and the *agreed* price
Admin set — which may be different from the price you originally
quoted if it was negotiated.

**Trying out Phase 5e**: log in as `admin` and click the new "Reports"
tab. It defaults to the last 7 days — use the quick-range buttons or the
date pickers to change that. With the test data from earlier phases,
you should see at least one day of spend, Kandy counted as a branch, and
Bloomax show up under "Spend by supplier" once you've made an assignment.
Click "Download Excel" for the same data as a 4-sheet workbook.

**Trying out Phase 5f**: after an order reaches ASSIGNED status (Phase
5c), log in as that branch, open "My Orders", expand the order, and
click "Confirm Delivery". Enter what actually arrived per product — try
entering a different number than what was ordered for at least one line
to see the mismatch highlighted in the order detail afterward. The order
status changes to CONFIRMED once submitted.

**Trying out Phase 5g**: log in as `admin` and click the new "Supplier
Orders" tab. Pick a supplier and a delivery date, then click "Show
branch demand for this date" to see what each branch actually ordered —
click any product chip to add it as a line, or use "+ Add line" to enter
one manually (branch, product, quantity, and an optional agreed price).
Save, then log in as that supplier and open the new "Orders by Branch"
tab — you'll see the same order, grouped by branch, exactly as it was
entered. Back as `admin`, the new "Supplier Prices" tab shows every
supplier's submitted prices for a chosen delivery date in one table,
with the lowest quote per product highlighted and a search/filter box.

## Project layout

```
/backend      FastAPI app, models, Alembic migrations, seed script
/frontend     React + TypeScript + Tailwind app
/database/seed  CSV seed data (branches, suppliers, products)
docker-compose.yml
.env.example
```
