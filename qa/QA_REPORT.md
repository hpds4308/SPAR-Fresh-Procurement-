# QA Report — SPAR Fresh Procurement Platform

| | |
|---|---|
| **Audited** | `C:\spar-project` @ `master` (commit `cef4b72`), 2026-09-21 |
| **Auditor scope** | Full 7-phase pass, local environment only (production/Railway was **not** touched) |
| **Source code modified** | **Audit phase: none** (everything is under `/qa`). **Fix phase: see §8** — the 6 findings you approved are fixed in the working tree (uncommitted, not deployed) |
| **Reproduce** | See [`qa/README.md`](README.md) |

> **Scope note.** The audit brief describes an AI "vibe-coding" site (prompt → generated code → preview → deploy, credits, billing).
> This repository is a different product: an internal **fresh-produce procurement platform** (FastAPI + Postgres + React/Vite, hosted on Railway).
> On your confirmation I audited it as-is and mapped the brief onto its real flows. **N/A for this product:** prompt injection / system-prompt
> extraction, generated-code sandbox isolation (iframe/CSP/executor), code editor, live preview, export-as-project, deploy, credits/billing.
> Their closest real equivalents were tested instead: order/price integrity, Excel upload/export, chat text handling, the POS and Harti integrations,
> and "AI provider down" ↔ "POS integration down".

---

## 1. Executive summary

**Overall quality: 6 / 10.** The core procurement loop works end to end and the authorization model is genuinely solid; the weaknesses are
availability/hardening, a few business-logic gaps, and mobile/accessibility polish.

**Release recommendation: NO-GO for wider or unattended rollout until items 1–5 of §7 are fixed. The current supervised pilot can continue** if
(a) the seeded default passwords are confirmed changed, and (b) the POS "Stock in Hand" integration is switched off or time-boxed until BUG-07/SEC-03 are fixed.

> **Update after the fix pass (§8):** items 1–4 of §7 — passwords/`SECRET_KEY`, Excel upload cap, POS resilience, revocable sessions — are implemented and verified locally (**uncommitted, not deployed**; read §8b before deploying). Once deployed, the No-Go is lifted for the supervised pilot; wider rollout still needs item 5 (rate limiting behind the proxy, to be verified on Railway) and items 6–8 (order-status integrity, zero-price validation, login/lockout fixes).

**What is good (verified, not assumed)**
* All 5 critical flows pass in a real browser: login/roles, branch order (draft → reload → submit → lock), admin matrix + Excel export, supplier price, assignment → `ASSIGNED`, delivery confirmation.
* Authorization: a generated matrix over **all 89 routes** shows no route is accidentally public, every `require_roles` restriction returns 403 to other roles, and the "any logged-in role" set equals an explicit whitelist. Cross-branch IDOR test passes. JWTs signed with other/default secrets and `alg=none` are rejected.
* No raw SQL, file writes, shell execution or `dangerouslySetInnerHTML` anywhere → SQL-injection, path-traversal and stored-XSS surfaces are effectively closed. Hostile strings (`' OR 1=1--`, `<script>`, `${jndi:…}`, Sinhala/Tamil/emoji) round-trip as inert text.
* Docs/OpenAPI disabled in production mode; CORS rejects foreign origins; argon2 hashing; consistent error envelope; migrations apply cleanly from empty (17/17).
* Type-check clean (`tsc --noEmit` exit 0); lint clean on correctness rules; the app's own suite: **186 passed / 0 failed**.

**Top risks**

| # | Risk | Evidence |
|---|---|---|
| 1 | **One authenticated request can freeze the whole API.** A 63 KB `.xlsx` passes the 5 MB check, then `preview-excel` runs **57 s** and a concurrent `/health` took **55.6 s**; 248 KB → 207 s then HTTP 500. | SEC-02 |
| 2 | **A slow/dead POS stalls everything.** 15 concurrent `stock-in-hand` calls exhaust the DB pool (`QueuePool limit of size 5 overflow 10`); `/health` blocked 29 s, others got HTTP 500 — contradicting the code's "never an error" contract. | SEC-03, BUG-07 |
| 3 | **Seeded accounts share the password `ChangeMe123!`** with no forced change; deploy notes say production was seeded this way. *Unverified on prod (not tested by rule).* | SEC-01 |
| 4 | **Stolen sessions cannot be revoked.** Logout / password change / admin reset leave the 7-day refresh token valid; tokens live in `localStorage`. | BUG-03 |
| 5 | **Rate limiting probably shared across all users in production** (keyed on socket IP behind a proxy that is not trusted). Locally a spoofed `X-Forwarded-For` bypassed it 13/13. *Needs prod verification.* | SEC-05 |
| 6 | **Business data integrity:** admin edits leave orders stuck in `ASSIGNED`; prices/quantities that round to `0.00` are accepted. | BUG-12, BUG-08 |

✅ **Risks 1–4 (SEC-02, SEC-03/BUG-07, SEC-01, BUG-03) are fixed in the working tree — see §8.** Risks 5–6 are still open.

**Headline numbers:** **at audit time** app suite 186 ✅ · QA suite 203 passed + 29 xfailed · Playwright 41 (31 pass, 10 pin defects); **after the fix pass** app suite **195 ✅** · QA suite **248 passed + 20 xfailed (the still-open findings), 0 failed** · Playwright ****49 tests in 8.5 min: 39 pass as written (31 original + 8 new for the fixes), 10 pin still-open defects (all behaving as expected), 0 unexpected, 0 skipped**** · 26 confirmed bugs (+1 informational) · 10 security findings · 9 open risks · line coverage of the app's own tests **61 %** (auth service 24 %, users API 20 %, messages 17 %, reports 13 %, POS 0 %, Harti import 0 %).

---

## 2. Bugs

Severity: Blocker / Critical / Major / Minor / Trivial. Priority: P0 (now) … P3 (backlog). "Test" = the pinned regression test in `/qa` (an `xfail` that flips red when fixed).

### 2a. Confirmed bugs (reproduced by an automated test or a live run)

| ID | Title | Sev | Pri | Area | Steps to reproduce | Expected | Actual | Evidence | Suggested fix |
|---|---|---|---|---|---|---|---|---|---|
| BUG-01 | Lockout counter never resets, so one typo re-locks | Major | P1 | Auth | 5 wrong logins → wait 15 min (or set `locked_until` in the past) → 1 wrong login | Counter restarts; 1 typo = 1 failure | Immediately locked another 15 min | [auth_service.py:35-42](../backend/app/services/auth_service.py:35); test `test_bug01_*` | Reset `failed_login_attempts` when `locked_until` has passed (or on expiry check) |
| BUG-02 | Login is case- and whitespace-sensitive; no `autocapitalize="none"` | Major | P1 | Auth / mobile | Type `Br02` or `br02 ` (phone keyboards capitalise the first letter) | Logs in | "Incorrect username or password" + counts toward lockout (BUG-01) | [auth_service.py:33](../backend/app/services/auth_service.py:33), [LoginPage.tsx:76-82](../frontend/src/features/auth/LoginPage.tsx:76) (no `autocapitalize/autocomplete/autocorrect`); tests `test_bug02_*`, `AUTH-08/09` | `.strip().lower()` server-side (usernames are created lowercase); add `autoCapitalize="none" autoComplete="username"` |
| BUG-03 | ✅ **FIXED (§8)** — Refresh tokens cannot be revoked | Major (High security) | P1 | Auth | Login → logout / change password / admin reset → `POST /auth/refresh` with the old refresh token | 401 | 200 + new access token, valid up to 7 days | [auth.py:39-59](../backend/app/api/v1/auth.py:39), [auth_service.py:75-87](../backend/app/services/auth_service.py:75), [users.py:165-204](../backend/app/api/v1/users.py:165); tests `test_bug03a/b/c` | `token_version` column on `users` (or a `jti` deny-list) checked in `decode_token`; bump on logout/reset/change; rotate refresh tokens |
| BUG-04 | Admin can deactivate their own account; recovery cannot undo it | Major | P2 | Users | Admin → `POST /users/{own id}/deactivate` → try recovery-token flow | Rejected / recoverable | 200; `redeem-recovery-token` sets a password but login still says "deactivated" | [users.py:279-287](../backend/app/api/v1/users.py:279), [auth_service.py:122-151](../backend/app/services/auth_service.py:122); tests `test_bug04*` | Refuse self-deactivation and deactivating the last active admin; have `redeem_recovery_token` set `is_active=True` |
| BUG-05 | Username enumeration (message + timing) | Minor | P3 | Auth | Compare locked vs unknown user; time valid vs unknown username | Indistinguishable | "Account temporarily locked…" only for real users; valid ≈ 125–155 ms vs unknown ≈ 11–13 ms (**~10×**, measured) | [auth_service.py:33-44](../backend/app/services/auth_service.py:33); test `test_bug05_*` | Same message for locked; verify a dummy argon2 hash for unknown users |
| BUG-06 | Excel upload: a `nan` quantity → HTTP 500 | Minor | P3 | Orders | Upload `.xlsx` with text cell `nan`/`NaN` in Quantity | Row error "not a valid quantity" | 500 (NaN passes both range checks, then cannot be JSON-encoded) | [order_service.py:214-225](../backend/app/services/order_service.py:214); tests `[nan]`,`[NaN]` (`inf`, `1e999` are handled correctly) | `math.isfinite(value)` check |
| BUG-07 | ✅ **FIXED (§8)** — POS lookup: connection resets/hang-ups → HTTP 500 | Major | P1 | POS | Local server that closes the socket / truncates the body; call `GET /orders/stock-in-hand` | `{}` ("never an error", module docstring) | Unhandled `ConnectionAbortedError`/`RemoteDisconnected`/`IncompleteRead` → 500 | [pos_stock_service.py:77,113](../backend/app/services/pos_stock_service.py:113) catch only `URLError/TimeoutError/ValueError`; `test_qa_pos_stock.py` | Catch `OSError` + `http.client.HTTPException` in both places |
| BUG-08 | Values that round to `0.00` pass `Field(gt=0)` | Major | P1 | Pricing / orders | `PriceEntry(price=0.004)`; order qty `0.004`; assignment `agreed_price=0.004` | 422 | Accepted and stored as `0.00` (validator rounds *after* the `gt` check). A supplier can submit a "free" price that becomes the lowest quote | [schemas/pricing.py:7-15](../backend/app/schemas/pricing.py:7), [order.py:7-16](../backend/app/schemas/order.py:7), [assignment.py:48-57](../backend/app/schemas/assignment.py:48); tests `test_bug08_*` | Round in a `mode="before"` validator, or `ge=0.01`; re-check after rounding |
| BUG-09 | NUL byte in text → HTTP 500 (and 500 has no CORS headers) | Minor | P3 | Input | `POST /messages/mine {"body":"a\u0000b"}`; login with `"a\u0000b"` | 4xx | 500 (psycopg2 rejects NUL) | [schemas/message.py:17](../backend/app/schemas/message.py:17); live run; tests `test_bug09_*` | Strip/reject `\x00` in a shared validator |
| BUG-10 | Free-text fields unbounded; no request-size limit | Minor | P3 | Input | `POST /orders/draft` with a 3 MB `notes` | 422 | 200, stored | [schemas/order.py:10,20,117](../backend/app/schemas/order.py:10); test `test_bug10_*` | `max_length` on notes; body-size limit at proxy/middleware |
| BUG-11 | Server-local `date.today()` vs Asia/Colombo business date | Minor | P3 | Reports / import | On a UTC host between 00:00–05:30 Colombo, default report window / email subject / Harti "today" are one day behind | Business date | Off by one day for 5.5 h nightly | [reports.py:38,58](../backend/app/api/v1/reports.py:38), [master_data.py:80](../backend/app/api/v1/master_data.py:80), [harti_import_service.py:193,303](../backend/app/services/harti_import_service.py:193); test `test_bug11_*` | `datetime.now(BUSINESS_TZ).date()` everywhere |
| BUG-12 | Admin add/remove order line never recomputes order status | Major | P1 | Orders | Order fully assigned (10/10 → `ASSIGNED`) → admin raises the line to 25 | Reverts to `SUBMITTED` ("status always reflects current assignment coverage") | Stays `ASSIGNED` while 15 are uncovered | [order_service.py:521-616](../backend/app/services/order_service.py:521); only caller of the recompute is [assignment_service.py:195](../backend/app/services/assignment_service.py:195); test `test_bug12_*` | Call the recompute after add/remove |
| BUG-13 | Exported files always download with a generic name | Minor | P3 | Export | Admin → Download Excel | `order-matrix-2026-09-23.xlsx` | `order-matrix.xlsx`: API and SPA are cross-origin and CORS does not expose `Content-Disposition` | [main.py:37-43](../backend/app/main.py:37) (no `expose_headers`); [orders.ts:186](../frontend/src/api/orders.ts:186), [reports.ts:80](../frontend/src/api/reports.ts:80), [masterData.ts:55](../frontend/src/api/masterData.ts:55), [supplierOrders.ts:66](../frontend/src/api/supplierOrders.ts:66); e2e `ORDER/ADMIN-01`, `EXPORT-02` | `expose_headers=["Content-Disposition"]` |
| BUG-14 | Login button unreachable on a phone in landscape | Minor | P2 | UI | Viewport 667×375 → `/login` | Scroll to *Sign in* | Card is ~417 px tall inside `h-screen overflow-hidden`; button clipped, no scroll | [LoginPage.tsx:39](../frontend/src/features/auth/LoginPage.tsx:39); e2e `RESP-LOGIN-LANDSCAPE` (portrait 320–1440 px all pass) | `min-h-screen overflow-y-auto` |
| BUG-15 | Rate-limited login shows "Request failed with status 429." | Minor | P3 | UX | 11 wrong logins in a minute, then any login | "Too many attempts, try again in a minute" | slowapi's body is `{"error":…}`; client reads only `detail` | [client.ts:77-78](../frontend/src/api/client.ts:77); e2e `RATE-01` | Custom `RateLimitExceeded` handler returning `detail`; map 429 in client |
| BUG-16 | WCAG 2.1 AA failures on every screen | Major | P2 | Accessibility | axe-core on login / branch / admin / supplier | 0 critical/serious | Login: contrast ×3 · Branch: contrast ×6 · Admin: contrast ×25, scrollable-region-focusable ×1, **select-name (critical) ×1** · Supplier: contrast ×33, **select-name (critical) ×1**. Also: the 188 quantity inputs have accessible name "0" (placeholder only), and *Show password* has `tabIndex={-1}` | `qa/e2e/results/axe-*.json`; [LoginPage.tsx:105](../frontend/src/features/auth/LoginPage.tsx:105); e2e `A11Y-*` | Darken low-contrast text tokens; label the selects and quantity inputs (`aria-label={product}`); remove `tabIndex={-1}` |
| BUG-17 | Two simultaneous first submissions → one gets HTTP 500 | Minor | P3 | Orders | Same branch sends 2 concurrent `POST /orders` before any order exists | `[200, 422]` | `[200, 500]` (exactly one order persisted — data is safe, message is wrong). `db.flush()` is unguarded; only `commit()` handles `IntegrityError` | [order_service.py:491](../backend/app/services/order_service.py:491) (and `:426` for drafts), guard exists at `:497`; `qa/perf/concurrency_check.py orders` | Wrap the flush like `admin_add_order_line` does (`:566`) |
| BUG-18 | Backup script records a failed `pg_dump` as a good backup | Major | P1 | Ops (VPS path) | `set -eu` + `pg_dump … \| gzip > file` in `sh` (no `pipefail`) | Failure detected | `if` sees gzip's status → success; retention then deletes the old good dumps | [backup_db.sh:20](../docker/backup_db.sh:20); logic demonstrated in `sh` (real `pg_dump` not run) | `set -o pipefail` (bash image) or dump to file, check exit, then gzip; alert on tiny files |
| BUG-19 | Any unhandled 500 reaches the browser as a "network error" | Minor | P3 | API/UX | Trigger any 500 (e.g. BUG-09) with an `Origin` header | JSON error visible to the SPA | Response has **no** `Access-Control-Allow-Origin` (ServerErrorMiddleware sits outside CORS) → SPA says "Network error reaching the server" | live run; [errors.py:54-61](../backend/app/core/errors.py:54) | Add CORS headers in the 500 handler or register a catch-all inside the middleware stack |
| BUG-20 | New Order / Submit Prices pages download ~13 MB and 207 requests on first load | Major | P2 | Performance | Open `/branch` (production build) | Lazy, small assets | Every product image is pre-fetched with `new Image()` just to learn which exist (63 PNGs, ≤ 526 KB each = 12.3 MB; 125 probes are 404s) for a **hover-only** preview that touch devices cannot use | [OrderForm.tsx:113-117](../frontend/src/features/branch/OrderForm.tsx:113), [PriceForm.tsx:101-105](../frontend/src/features/supplier/PriceForm.tsx:101); `page_metrics.mjs`: 207 req / 12,893 KB | Return `has_image` from the API, serve ~20 KB WebP thumbs, load on hover only |
| BUG-21 | Login screen autoplays a 12 MB video | Minor | P3 | Performance | Open `/login` on mobile data | Light page | `login-produce-1080p.mp4` (12 MB) streams behind the form; post-login welcome videos add 8.2 MB + 0.9 MB | [LoginPage.tsx:40-49](../frontend/src/features/auth/LoginPage.tsx:40) | ≤ 1 MB 480p loop, `preload="metadata"`, skip on `saveData` / small screens |
| BUG-22 | Download helpers bypass `apiFetch` | Minor | P3 | Frontend | Idle > 15 min (access-token TTL) then *Download Excel* | Silent refresh, retry | Raw `fetch` with the stale token → generic "Could not download…" (server message discarded) | [orders.ts:177-183](../frontend/src/api/orders.ts:177), [reports.ts:71-77](../frontend/src/api/reports.ts:71), [masterData.ts:45-51](../frontend/src/api/masterData.ts:45), [supplierOrders.ts:55-63](../frontend/src/api/supplierOrders.ts:55) | Route through `apiFetch` (support blob responses) |
| BUG-23 | README/doc drift and dead code | Minor | P3 | Docs | Compare README with the UI | Docs match | README promises a supplier **"Confirmed Orders"** tab (Phase 5d) — it does not exist; `fetchMyAssignments()` is never called; README says supplier prices are "daily", code allows **Mon/Wed/Fri only**; login placeholder says `e.g. branch.kandy` but real usernames are `br01…` | [assignments.ts:70](../frontend/src/api/assignments.ts:70); [README.md:206](../README.md); [LoginPage.tsx:79](../frontend/src/features/auth/LoginPage.tsx:79); e2e `SUPPLIER-01` | Update docs/placeholder or (re)build the screen — see RISK-05 |
| BUG-24 | Unbounded N+1 queries on list endpoints | Minor | P3 | Performance | `GET /users` (30 users) / `GET /orders` | Constant query count | `/users` = ~90 queries, **16 req/s, p50 621 ms**; `/orders` adds 2 queries per row and is unpaginated (a branch's full history) | [users.py:35-59](../backend/app/api/v1/users.py:35), [orders.py:294-332](../backend/app/api/v1/orders.py:294); autocannon | Joins / `IN` batching; paginate |
| BUG-25 | Inconsistent date/time presentation | Trivial | P4 | UI | Branch → My Orders after confirming | One format, business TZ | `2026-09-23`, "Wednesday, September 23" and browser-locale `9/21/2026, 1:19:56 PM` mixed | e2e run output | One formatter pinned to Asia/Colombo |
| BUG-26 | Non-reproducible frontend image build | Minor | P3 | Ops | `frontend/Dockerfile.railway` | Locked versions | Copies only `package.json` then `npm install` (lockfile ignored) | [Dockerfile.railway:11-12](../frontend/Dockerfile.railway:11) | `COPY package*.json` + `npm ci` |
| BUG-27 | Dev-only duplicate requests on load | Trivial | P4 | Frontend | Open any page in `vite` dev | — | `React.StrictMode` double-invokes effects (2× every request) — **dev only**, not in the production build | [main.tsx:10](../frontend/src/main.tsx:10) | None needed; noted so it isn't mistaken for a bug |

### 2b. Suspected risks (not proven — need a decision or production evidence)

| ID | Risk | Why it matters | How to verify / decide |
|---|---|---|---|
| RISK-01 | Weak password policy: `min_length=8` only; the seeded/temporary passwords are guessable | [schemas/auth.py:23](../backend/app/schemas/auth.py:23); `test_risk01_*` accepts `aaaaaaaa` | Product decision: length ≥ 10 + deny-list |
| RISK-02 | Rate limiter keys on socket IP; production is behind a proxy (Railway/Caddy) not listed in uvicorn's trusted hosts | If untrusted, **all ~30 users share one 10/min login bucket and one 300/min global bucket** (4 s message polling makes 300/min plausible). If trusted, spoofed XFF bypasses it (proved locally 13/13). Audit-log `ip_address` is wrong either way | Prod: `SELECT DISTINCT ip_address FROM audit_logs WHERE action='LOGIN'` — one internal IP confirms it. Fix: `--proxy-headers --forwarded-allow-ips=<proxy>` + key on the client IP |
| RISK-03 | ✅ **FIXED (§8)** — POS integration: no negative cache; each call may block 2 × 15 s holding a DB connection | Basis of SEC-03 | Add short timeout + circuit breaker |
| RISK-04 | Admin can add lines to a **CONFIRMED** order (branch already signed off) | `test_risk04_*`; silently changes a closed record | Business decision (block, or require reason + audit) |
| RISK-05 | Assignments made in the Order Matrix (`PUT /orders/admin/product/{id}/assignments`) are never shown to the supplier: `GET /assignments/mine` works but no UI calls it; the supplier only sees Admin-built "Orders by Branch" | Branch sees `ASSIGNED`, supplier sees nothing unless Admin also builds a Supplier Order | Confirm the intended hand-off process |
| RISK-06 | Production may still use the seeded password | See SEC-01 | Owner check |
| RISK-07 | Account-lockout as denial of service: 5 requests lock any *known* account (`admin`, `br01…br13`, `sup01…`) for 15 min; the per-IP limit does not stop it | Predictable usernames | Lock per (user, IP) or add captcha/backoff |
| RISK-08 | `admin_add_order_line` promotes a branch's private **DRAFT** to SUBMITTED | Documented, but a branch mid-edit gets locked out | Confirm intended |
| RISK-09 | On refresh failure `apiFetch` clears tokens but `AuthContext.user` is not reset; concurrent 401s each trigger a refresh | UI can sit on a dead session showing errors | Manual test with an expired refresh token |

---

## 3. Security findings (ranked)

| Rank | ID | Sev | Status | Finding | Evidence | Fix |
|---|---|---|---|---|---|---|
| 1 | SEC-01 | **High** | Suspected (prod not tested) — **✅ fix implemented (§8), not yet deployed** | All 30 seeded accounts share `ChangeMe123!`; no forced first-login change; temp passwords from *reset* also persist. Deploy notes say production was seeded this way | [seed_users.py:21](../backend/scripts/seed_users.py:21); live: `br03`/`ChangeMe123!` logs in locally | Force change on first login (`must_change_password`), rotate now, longer policy |
| 2 | SEC-02 | **High** | **Confirmed — ✅ fixed (§8)** | Excel upload has no decompressed-size / row cap → any branch account can stall the API and force a 1M-line response | 63 KB file: **56.8 s**, `/health` **55.6 s**; 248 KB: **207 s → 500**; `test_sec02_*`; [orders.py:253-272](../backend/app/api/v1/orders.py:253), [order_service.py:250-280](../backend/app/services/order_service.py:250) | Reject `> N` rows / uncompressed bytes before parsing; cap returned lines; run in a worker with timeout |
| 3 | SEC-03 | **High** | **Confirmed — ✅ fixed (§8)** | POS outage exhausts the DB pool (15 connections) and starves the API; DB session is held during the outbound call | 45 concurrent `stock-in-hand` with a hanging POS: p50 30.5 s, `/health` 29 s, `QueuePool limit … timeout 30.00` 500s; `qa/perf/concurrency_check.py posdown` | Timeout ≤ 3 s, circuit breaker/negative cache, release the session before the call, cap concurrency |
| 4 | SEC-04 | Medium | **Confirmed — partly mitigated (§8: revocable; still in `localStorage`)** | Non-revocable 7-day refresh tokens stored in `localStorage` (XSS ⇒ 7-day takeover; logout does nothing server-side) | BUG-03 tests; [client.ts:19-22](../frontend/src/api/client.ts:19) | Token versioning; shorter refresh TTL; consider httpOnly cookie |
| 5 | SEC-05 | Medium | Suspected (prod unverified) | Client-IP handling: shared bucket behind proxy **or** spoofable XFF; audit-log IPs unreliable | 13/13 spoofed logins allowed locally; [Dockerfile:16](../backend/Dockerfile:16) (no `--forwarded-allow-ips`) | RISK-02 |
| 6 | SEC-06 | Medium | **Confirmed** (config) | Railway frontend (nginx) sends **no** CSP / X-Frame-Options / HSTS / Referrer-Policy — they exist only in the VPS `Caddyfile` | [nginx.conf](../frontend/nginx.conf) (only `Cache-Control`); [Caddyfile:20-27](../Caddyfile) | Add the same headers to nginx (or Railway edge) |
| 7 | SEC-07 | Medium | **Confirmed** | Known-vulnerable dependencies | `pip-audit`: **40 advisories** — starlette 0.50.0 (5), python-multipart 0.0.18 (6, *the upload parser*), pyasn1 (4), pdfminer-six (2, parses external PDFs in the Harti import), ecdsa, python-dotenv, pytest (dev). `npm audit`: 5 — react-router-dom 6.30.4 (open-redirect ⇒ XSS, runtime), vite/esbuild/nanoid (dev-server only) | Bump `python-multipart` (≥ 0.0.31), `fastapi` (to a release that pulls a fixed `starlette`), `python-dotenv`, `react-router-dom` (6.30.6); re-audit |
| 8 | SEC-08 | Medium | Suspected (config) | POS credentials (Basic + JSON body) are sent to whatever URL is configured; your deployment notes say the production POS URL is plain `http://` on a public IP. `urllib` also follows redirects and re-sends `Authorization` | [pos_stock_service.py:52-86](../backend/app/services/pos_stock_service.py:52) | HTTPS/VPN/IP-allow-list; refuse `http://` outside dev; disable redirects |
| 9 | SEC-09 | Low | **Confirmed** | Username enumeration (message + ~10× timing) and lockout DoS (RISK-07) | BUG-05 | Uniform message + dummy hash |
| 10 | SEC-10 | Low | **Confirmed — ✅ fixed (§8)** | `SECRET_KEY` falls back to a public default with no production guard (a forged token needs only a user id). Local tests rejected forged tokens **only because the instance used a different key** | [config.py:21](../backend/app/core/config.py:21) | Fail startup when `APP_ENV=production` and the key is the default/short |

Checked and **not** vulnerable: SQL injection (no raw SQL; 5 injection-style usernames → clean 401), path traversal/file write (none), stored/reflected XSS (React text rendering; no HTML sinks), IDOR (test + route matrix), JWT `alg=none` / wrong-secret forgery, CORS misconfiguration (foreign origin rejected), docs exposure in production, email header injection (`\s` excluded by the address regex), mass assignment on user/branch/supplier creation.
Not applicable: prompt injection / system-prompt leakage, sandbox/iframe/CSP for generated code, credit or payment tampering.

---

## 4. Test-case results

### 4a. Totals

| Suite | Result |
|---|---|
| App's own suite (`backend/tests`, 15 files) | **186 passed, 0 failed** — line coverage **61 %** (3,428 statements, 1,335 missed) |
| QA backend suite (`qa/backend`, 5 files) | **203 passed, 29 xfailed (pinned defects/risks), 0 failed** |
| Playwright E2E (Chromium) | **41 tests: 31 pass, 10 pin confirmed defects (all behaving as expected), 0 unexpected, 0 skipped** (run on a Monday, so the supplier steps executed) |
| Live probes (scripted, local) | 15 probes, listed in 4c |

*(After the fix pass the app's own suite is 195 tests; the QA suite adds 268 collected cases — 248 pass, 20 pin open findings.)*

Coverage gaps in the app's own tests: `auth_service` 24 %, `users.py` 20 %, `message_service` 17 %, `report_service` 13 %, `reports.py` 28 %, `supplier_orders.py` 32 %, `pos_stock_service` 0 %, `harti_import_service` 0 % — **the areas where most bugs above were found**.

### 4b. Test-case table (functional)

`Pass` = behaves correctly · `Fail` = defect confirmed (linked) · `Skip` = day-dependent · counts are in 4a; parametrised cases are grouped.

| ID | Scenario | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|
| **AUTH-01** | Login page renders, show/hide password | Open `/login`; click *Show* | Labelled fields; type toggles | As expected | Pass |
| AUTH-02 | Wrong password | `br02` + bad password | Friendly error, stay on `/login` | "Incorrect username or password." | Pass |
| AUTH-03 ×3 | Role landing | Log in as admin / br02 / sup01 | `/admin` `/branch` `/supplier` (+ welcome splash for branch/supplier) | As expected | Pass |
| AUTH-04 | Route guard / deep link | Anonymous `/admin`; branch → `/admin`, `/supplier` | → `/login`; → `/branch` | As expected | Pass |
| AUTH-05 | Expired access token | Corrupt access token, reload | Silent refresh | New token, page works | Pass |
| AUTH-06 | Logout + back button | Logout → back | Tokens cleared; dashboard hidden | As expected | Pass |
| AUTH-07 | Second tab | Open `/` in a new tab | Same session | `/branch` | Pass |
| AUTH-08 | `Br02` (phone capitalisation) | Login with capital B | Logs in | 401 | **Fail** (BUG-02) |
| AUTH-09 | Mobile keyboard hints | Inspect `#username` | `autocapitalize=none` | attribute missing | **Fail** (BUG-02) |
| API-AUTH ×8 | Tokens, lockout, rate limit | Type-swap tokens; 5 bad logins; 12 rapid logins; deactivated refresh | 401 / locked / 429 | As expected | Pass |
| API-AUTH ×4 | Recovery token | Redeem, reuse, expire, supersede | Single-use, uniform error | As expected | Pass |
| API-AUTH | Lockout expiry | Lock → expire → 1 typo | Not re-locked | Re-locked | **Fail** (BUG-01) |
| API-AUTH ×3 | Refresh after logout / pw change / admin reset | see BUG-03 | 401 | 200 | **Fail** (BUG-03) |
| API-AUTH | Self-deactivate; recover deactivated admin | see BUG-04 | Rejected / recoverable | Allowed / not recoverable | **Fail** (BUG-04) |
| **ORDER-01** | Branch order lifecycle | Enter 12.5 → *Save* → reload → *Submit* | Draft restored; submit locks form | As expected | Pass |
| ORDER-02 | Order history | My Orders | `SUBMITTED`, delivery = today + 2 | As expected | Pass |
| ORDER-03 | Second submit same day | `POST /orders` again | 422 "already submitted" | As expected | Pass |
| API-ORD | 13 branches submit 60-line orders simultaneously | barrier-synchronised threads | 13 × 200 | 13/13, p50 528–629 ms, max 643 ms | Pass |
| API-ORD | Same branch, 2 simultaneous first submits | see BUG-17 | `[200,422]` | `[200,500]`, 1 order stored | **Fail** (BUG-17) |
| **ADMIN-01** | Order matrix + Excel export | Branch Orders → *Download Excel* | Kandy 12.5; valid `.xlsx` (zip magic, > 2 KB) | As expected; generic filename | Pass (+BUG-13) |
| **PRICE-01** | Supplier price → admin view | Submit 450 for AVOCADO | Stored; admin sees it | As expected (Mon/Wed/Fri only) | Pass |
| **ASSIGN-01** | Assign supplier | `PUT …/assignments` 12.5 @ 450 | `fully_assigned`; branch sees `ASSIGNED` | As expected | Pass |
| SUPPLIER-01 | Supplier sees the assignment | Supplier tabs / `GET /assignments/mine` | Screen exists | API has data, UI has no screen | **Risk** (RISK-05) |
| **CONFIRM-01** | Branch confirms with shortage | Received 10 of 12.5 | `CONFIRMED`, shortage shown | `CONFIRMED`, shortage shown (12.5 ordered / 10 received) | Pass |
| API-ORD | Over-assignment; confirm unassigned order | 10.5 vs demand 10; confirm `SUBMITTED` | 422 | 422 | Pass |
| API-ORD | Rounding to zero (price, qty, agreed price) | 0.004 | 422 | Accepted as 0.00 | **Fail** ×3 (BUG-08) |
| API-ORD | Raise demand on `ASSIGNED` order | 10 → 25 | back to `SUBMITTED` | stays `ASSIGNED` | **Fail** (BUG-12) |
| API-ORD | Edit a `CONFIRMED` order as admin | add line | Rejected? | Allowed | Risk (RISK-04) |
| API-XLS | Wrong file type / > 5 MB / formula & `<script>` text in cells | upload | 422 / not echoed | As expected | Pass ×3 |
| API-XLS | `inf`, `-inf`, `1e999`, `5,5`, full-width digit | upload | clean row error | As expected | Pass ×5 |
| API-XLS | `nan` / `NaN` | upload | row error | HTTP 500 | **Fail** ×2 (BUG-06) |
| API-XLS | 63 KB file expanding to 1M rows | upload | rejected fast | 57 s stall | **Fail** (SEC-02) |
| API-TXT | Empty / 2001-char message | `POST /messages/mine` | 422 | 422 | Pass |
| API-TXT ×9 | SQLi, `<script>`, JNDI, `{{7*7}}`, Sinhala+Tamil, emoji, newline/tab, 2000 chars | chat | stored verbatim, harmless | As expected | Pass |
| API-TXT ×5 | Injection-style login names | login | 401 | 401 | Pass |
| API-TXT | NUL byte in message / login | see BUG-09 | 4xx / 401 | 500 | **Fail** ×2 (BUG-09) |
| API-TXT | 3 MB order note | draft | 422 | 200 | **Fail** (BUG-10) |
| **AUTHZ** ×83 | Anonymous call to every non-public route (89 routes − 6 public) | generated from the route table | 401 | 401 | Pass ×83 |
| AUTHZ | Wrong-role call to every role-restricted route | generated | 403 | 403 | Pass ×75 |
| AUTHZ ×4 | Whitelist of login-only routes; supplier lists `/orders`; public `/settings` fields; cross-branch IDOR | – | as designed | As expected | Pass |
| POS ×3 | Not configured / happy path / URLError, timeout, bad JSON | mock + local TCP server | `{}` / parsed | As expected | Pass |
| POS ×3 | Socket closed / truncated body / login hang-up | local TCP server | `{}` | Exception → 500 | **Fail** (BUG-07) |
| POS | Dead POS retried on every request | 5 calls | 1 attempt | 5 attempts | Risk (RISK-03) |
| POS | Hung POS, 45 concurrent branch page loads | `concurrency_check.py posdown` | API stays up | `/health` 29 s, pool exhausted | **Fail** (SEC-03) |
| MIG | Alembic from empty DB | `upgrade head` | 17 revisions | OK | Pass |
| **RESP-LOGIN** ×5 | 320/375/768/1024/1440 px | open `/login` | no h-scroll, button reachable | As expected | Pass ×5 |
| RESP-LOGIN | 375×667 with "Forgot password?" open | click | reachable | As expected | Pass |
| RESP-LOGIN | 667×375 landscape | open | reachable | clipped | **Fail** (BUG-14) |
| RESP-BRANCH ×5 / ADMIN ×3 | No page-level horizontal scroll | 320–1440 px | 0 px | 0 px | Pass ×8 |
| A11Y ×4 | axe-core WCAG 2.1 A/AA | login, branch, admin, supplier | 0 critical/serious | see §5 | **Fail** ×4 (BUG-16) |
| A11Y-kbd | Tab to *Show password* | Tab | focus | skipped (`tabIndex=-1`) | **Fail** (BUG-16) |
| RATE-01 | UX of a 429 | 11 bad logins, then login | friendly text | "Request failed with status 429." | **Fail** (BUG-15) |

**"AI edge cases" mapping:** empty / very long / special-character / emoji / non-English / code-in-prompt → covered by the text and Excel rows above; vague or contradictory prompt, mid-way generation failure, retry → N/A; **provider down / 429 / 500 → tested as POS down (SEC-03/BUG-07)**; refresh mid-flow → ORDER-01 (draft survives reload); multi-tab / back / deep links → AUTH-04/06/07.

### 4c. Live probes (local, scripted)

| # | Probe | Result |
|---|---|---|
| L-1 | `GET /health` | 200 |
| L-2 | `/api/v1/docs`, `/openapi.json`, `/redoc` with `APP_ENV=production` | 404 (good) |
| L-3 | CORS preflight, allowed vs foreign origin | allowed origin echoed with credentials; `https://evil.example` → 400, no ACAO (good) |
| L-4 | JWT forged with the repo/`.env.example` default secrets, wrong secret, `alg=none` | all 401 (the local instance used a different key — see SEC-10) |
| L-5 | Malformed JSON / wrong types | clean 422 |
| L-6 | 13 wrong logins in a minute | first 9–10 → 401, then 429 (limit works) |
| L-7 | 13 logins with rotating `X-Forwarded-For` (trusted-proxy source) | 13/13 allowed → limiter bypassed |
| L-8 | Login latency: valid vs unknown user | 125–155 ms vs 11–13 ms |
| L-9 | 13 simultaneous 60-line order submissions | 13/13 OK, p50 528–629 ms |
| L-10 | First-submit race | `[200, 500]` |
| L-11 | Dead POS × 45 concurrent | p50 30.5 s, `/health` 29 s, 500 `QueuePool` |
| L-12 | Excel row-flood | 63 KB → 57 s; 248 KB → 207 s → 500 |
| L-13 | NUL byte login → 500 without CORS headers | confirmed |
| L-14 | Backup pipeline logic (`sh`, no `pipefail`) | failed `pg_dump` reported as success |
| L-15 | Alembic upgrade from empty | 17/17 |

---

## 5. Performance and accessibility

**Environment:** Windows laptop also running Docker Desktop, two browsers and the test runner; single uvicorn worker; embedded Postgres; seeded data (13 branches, 16 suppliers, 188 products, 30 users). Numbers are **indicative**, not a capacity plan.

**API throughput (autocannon, 8 s, limiter disabled via a scratch launcher)**

| Endpoint | Conn. | req/s | p50 | p97.5 | Note |
|---|---|---|---|---|---|
| `GET /health` | 20 | 237 | 71 ms | 213 ms | |
| `GET /orders/window` | 20 | 136 | 142 ms | 257 ms | 2 DB round trips + auth (2 more) |
| `GET /products` (188 rows) | 20 | 58 | 313 ms | 490 ms | polled on every New Order load |
| `GET /orders/admin/matrix` (188 × 13) | 10 | 40 | 228 ms | 400 ms | |
| `GET /users` (30 users) | 10 | 16 | 621 ms | 714 ms | N+1 (BUG-24) |
| `POST /auth/login` | 1 | ≈7/s per core (estimated, not load-tested) | 125–155 ms | – | argon2, CPU-bound; 13 branches logging in together ≈ 2 s of CPU |

Zero errors/timeouts in all runs. Message polling (4 s per open chat, 15 s unread badge) costs ~3 queries per request and continues in background tabs.

**Page load, production build (Chromium, cache disabled, 375×667)**

| Profile | Page | Content visible | FCP | LCP | Requests | Transferred |
|---|---|---|---|---|---|---|
| none | `/login` | 0.44 s | 0.40 s | 0.49 s | 10 | 2.1 MB (video streaming) |
| none | `/branch` | 0.46 s | 0.29 s | 0.45 s | **207** | **12.9 MB** (BUG-20) |
| Slow 4G | `/login` | 1.06 s | 1.01 s | 1.20 s | 10 | 184 KB at measurement |
| Slow 4G | `/branch` | 2.08 s | 1.19 s | 1.85 s | 25 at measurement | image pre-fetch still in flight |
| Fast 3G | `/login` | 2.22 s | 1.94 s | 2.31 s | 9 | 136 KB at measurement |
| Fast 3G | `/branch` | 3.76 s | 2.18 s | 3.41 s | 25 at measurement | |

Bundle: one JS chunk **387 kB (101 kB gzip)** + CSS 34 kB (6.8 kB gzip) — no route-level splitting, so suppliers download admin code. Static assets: product PNGs 12.3 MB, videos 12 + 8.2 + 0.9 MB.
**Lighthouse was not run** (see §6); the table above is a like-for-like substitute for load metrics.

**Reliability:** provider-down behaviour is the main gap (SEC-03/BUG-07). Concurrent order submission is safe (unique constraint holds; BUG-17 is cosmetic). Cutoff logic uses Asia/Colombo consistently for orders/prices, but not for reports (BUG-11).

**Accessibility (axe-core 4.x, WCAG 2.1 A/AA, Chromium, 1024×768)**

| Screen | Rules passed | Violations |
|---|---|---|
| Login | 14 | color-contrast ×3 (serious) |
| Branch → New Order | 16 | color-contrast ×6 (serious) |
| Admin dashboard | 20 | color-contrast ×25, scrollable-region-focusable ×1 (serious); **select-name ×1 (critical)** |
| Supplier dashboard | 19 | color-contrast ×33 (serious); **select-name ×1 (critical)** |

Also observed: 190/190 inputs on New Order have no `<label>`/`aria-label` (accessible name is the placeholder "0"); *Show password* is skipped by Tab; the branch welcome splash auto-plays video and only auto-continues after 20 s. Full JSON: `qa/e2e/results/axe-*.json`. **Responsive:** no horizontal overflow at 320/375/768/1024/1440 px on login and branch, and 320/375/768 px on admin; failure only in landscape phone (BUG-14). Supplier screens were not viewport-tested.
**Cross-browser:** Chromium only (see §6).

---

## 6. What I could NOT test, and why

| Not tested | Why |
|---|---|
| **Production / Railway** (real rate-limit bucket, whether default passwords are still set, real POS, prod headers) | Your rule: local only. Verification queries are given in RISK-02 / SEC-01 |
| Firefox, WebKit/Safari, Edge | Chromium-only install approved; the app has no obviously engine-specific code, but that is untested |
| **Lighthouse** scores | Not installed (not in the approved list); page-load metrics via Playwright/CDP substitute. Say the word and I'll run it |
| Real POS server, SMTP "Send to Master Data", Harti/CBSL/Dambulla price scrapers | Vendor credentials / external network / formats that change; only failure modes were simulated (POS) |
| Admin screens beyond the dashboard landing tab: Supplier Order Builder, Master Data sheet, Accounts, Settings, Reports, Keells/Market prices UIs | Their APIs are covered by route-matrix and unit tests, but no scripted UI walk-through |
| Excel **upload through the UI** | Covered at API level (15 app tests + 12 QA cases) |
| Docker images / `docker-compose.prod.yml` / Caddy / nginx at runtime | The Docker engine did not start on this machine; an embedded Postgres was used instead. Config was reviewed statically; the backup script logic was demonstrated but **not** run against a real `pg_dump`/restore |
| Offline mode, service-worker behaviour, screen-reader (NVDA/VoiceOver) and real-device testing | Out of tooling scope |
| Load beyond 20 connections / long soak / multi-instance behaviour (in-memory rate limiter and POS token cache are per process) | Time; single laptop |
| Data volume (thousands of orders) | Only seed data; N+1 findings are extrapolated from per-request query counts |

---

## 7. Recommended fix order (top 10)

1. ✅ **Passwords & secrets (SEC-01, SEC-10, RISK-01):** confirm/rotate the seeded `ChangeMe123!` accounts now, add forced first-login change, fail startup on the default `SECRET_KEY`.
2. ✅ (BUG-06 still open) **Cap the Excel upload (SEC-02, BUG-06):** max rows / uncompressed size, cap the returned lines, `isfinite` check.
3. ✅ **Make the POS integration harmless (SEC-03, BUG-07, RISK-03):** 2–3 s timeout, catch `OSError`/`HTTPException`, circuit breaker or negative cache, release the DB session before the outbound call. *Interim: unset `POS_API_BASE_URL`.*
4. ✅ **Revocable sessions (BUG-03, SEC-04):** `token_version` bumped on logout / password change / reset; rotate refresh tokens.
5. **Fix client-IP/rate-limit handling (SEC-05, RISK-02, BUG-15):** trusted-proxy config, verify with `audit_logs.ip_address`; friendly 429 message.
6. **Business-logic integrity (BUG-12, BUG-08, RISK-04):** recompute status after admin line edits; reject values that round to 0.00; decide on editing `CONFIRMED` orders.
7. **Login usability & lockout (BUG-02, BUG-01, BUG-05, RISK-07):** lowercase/trim usernames, `autocapitalize="none"`, reset the counter on expiry, uniform messages/timing.
8. **Admin safety (BUG-04):** block self-/last-admin deactivation; recovery token re-activates.
9. **Backups and deploy hygiene (BUG-18, BUG-26, SEC-06, SEC-07):** `pipefail` + size check + alert; `npm ci`; security headers on nginx; upgrade `python-multipart`, `starlette/fastapi`, `react-router-dom`.
10. **Mobile, performance, accessibility (BUG-20, BUG-21, BUG-14, BUG-16, BUG-13, BUG-19):** stop pre-fetching 188 images, slim the login video, fix landscape login, contrast/labels, expose `Content-Disposition`, CORS on 500s.

---

---

## 8. Fixes applied (group "Security and availability", approved 2026-09-21)

**Status:** implemented and verified locally; **uncommitted and not deployed.** Nothing was pushed, and production/Railway was not touched.
Scope was exactly the six findings you approved: SEC-02, SEC-03 + BUG-07 (+ RISK-03), BUG-03, SEC-10, SEC-01. Every other finding is unchanged.

### 8a. What changed and how it was verified

| Finding | Change | Before → after (measured locally) |
|---|---|---|
| **SEC-02** Excel upload can freeze the API | [orders.py](../backend/app/api/v1/orders.py): reads at most 5 MB + 1 byte and parses in the **threadpool** (the `async` handler used to parse on the event loop — that is why *everything* stalled). [order_service.py](../backend/app/services/order_service.py): reject a workbook whose declared unpacked size is > **8 MB**, more than **20,000** physical rows, or more than **2,000** product rows | 63 KB / 1M rows: **57 s stall** → **422 in 0.01 s**. 248 KB / 4M rows: **207 s → HTTP 500** → **422 in 0.01 s**. `/health` during the upload: **55.6 s → 4 ms**. A realistic 190-product template (+300 blank rows) still parses (test) |
| **SEC-03 / BUG-07 / RISK-03** Dead POS starves the API | [pos_stock_service.py](../backend/app/services/pos_stock_service.py): catches `OSError`, `http.client.HTTPException`, `ValueError` (was only `URLError/TimeoutError/ValueError`); timeout **15 s → 5 s**; **circuit breaker** (60 s cool-down after a failure); at most **4** simultaneous POS calls; cached token dropped on failure. [order_service.py](../backend/app/services/order_service.py): the DB session is **released before** the outbound call | 45 concurrent page loads with a hung POS — `/health`: **29 s → 0.00 s**; login: stalled → **0.09 s**; statuses: `[200, 500…]` → **all 200**; `stock-in-hand` p50 **30.5 s → 0.7 s** (max 5.3 s = the ≤ 4 calls allowed to probe before the breaker opens). Socket-closed / truncated-body / login-hang-up cases now return `{}` |
| **BUG-03** Sessions could not be revoked | New `users.token_version` stamped into every JWT (`tv`) and checked on each request + refresh; bumped on **password change, admin reset, admin-set password, recovery redemption, deactivation** (so re-activation cannot resurrect old sessions). New `revoked_tokens` table: **logout revokes that one refresh token** by `jti` — a shared branch/supplier login stays signed in on other devices. SPA now sends its refresh token on logout. Files: [security.py](../backend/app/core/security.py), [auth_service.py](../backend/app/services/auth_service.py), [auth.py](../backend/app/api/v1/auth.py), [users.py](../backend/app/api/v1/users.py), [AuthContext.tsx](../frontend/src/features/auth/AuthContext.tsx), migration `0018` | Live: after a password change the old access token → **401**, old refresh tokens (both devices) → **401**, fresh tokens → 200. After logout on device 1: its refresh → **401**, device 2's → **200**. Tokens issued before this release (no `tv`) still work until something bumps the version, so deploying does **not** sign anyone out (test) |
| **SEC-01** Everyone shares `ChangeMe123!`, no way to change it | New `users.must_change_password`. While set, `get_current_user` answers **403 "You must change your password"** for every route except `/auth/me`, `/auth/change-password`, `/auth/logout`, `/auth/refresh` and the public ones. **Migration 0018 verifies each existing hash and flags only accounts still on the seeded password.** Also flagged: new seeds (`--no-force-change` opts out for dev/CI), admin-created accounts, admin resets, admin-set passwords for *other* people. New screen [ForcedPasswordChange.tsx](../frontend/src/features/auth/ForcedPasswordChange.tsx) shown instead of the dashboard (deep links cannot bypass it). `change-password` now rejects "same as current", the seeded default and "equals the username", and **returns fresh tokens** so the user stays signed in | Migration on the seeded QA DB (30 accounts, 2 simulated as already changed): **28 flagged, the 2 changed accounts untouched**, 3.5 s. Browser: sign-in as `br02` with `ChangeMe123!` → "Choose your own password" → same-password / mismatch rejected → new password → straight into the dashboard. Note: there was **no UI anywhere to change a password before**, so it is very likely nobody has |
| **SEC-10** Placeholder `SECRET_KEY` | [config.py](../backend/app/core/config.py): the app **refuses to start** with `APP_ENV=production` and a `SECRET_KEY` that still starts with `changeme…` (the repo's placeholders). Short-but-custom keys are *not* refused, so a working deployment keeps booting | 9 new tests; the QA backend booted in production mode with a real key |

**Tests:** app suite **186 → 195 passed** (9 new config-guard tests; `test_docs_gating.py` updated to supply a real key when it simulates production). QA suite **248 passed + 20 xfailed** (the 20 are the still-open findings). New/converted regression tests: `qa/backend/test_qa_session_and_password.py` (26), `qa/backend/test_qa_excel_and_pos_limits.py` (10), plus the former pins for BUG-03/BUG-07/SEC-02/RISK-03 now assert the *fixed* behaviour. Full browser run after the fixes: **49/49 as expected**. New browser spec `qa/e2e/tests/04-session-and-password.spec.ts` (8 tests: forced change, deep-link bypass, API block, validation, sign-in after change, logout revocation, second device stays signed in). `tsc --noEmit` clean; production build OK (JS 387 → 391 kB).

### 8b. ⚠️ Read before deploying

1. **`SECRET_KEY` on the Railway backend must not be the placeholder** (it starts with `changeme`), otherwise the backend will now refuse to start. Your deploy notes say a real value was set — please confirm.
2. **Deploy backend and frontend together.** A cached old frontend against the new backend gets HTTP 403 on every call for flagged accounts (no screen to explain it) until the page is reloaded onto the new bundle.
3. **Every account still on `ChangeMe123!` will be asked for a new password at its next sign-in** — that is the point. The logins are *shared per branch/supplier*: whoever changes it first chooses the password for everybody, so tell staff who will do it and how to pass it on. Admins can hand out a fresh temporary password from *Accounts → Reset password* (that forces a change again).
4. Changing a password signs that account out everywhere else (the token version moves). Expected.
5. `alembic upgrade head` runs automatically when the backend container starts (`backend/Dockerfile`); 0018 takes a few seconds (one argon2 check per account). Its `downgrade` drops the columns, which also discards the flags.
6. Known limits of this fix: an access token lives up to 15 min after logout (only refresh tokens are revocable); refresh tokens are not rotated (rotation would sign users out when two tabs refresh together); tokens are still in `localStorage` (SEC-04 partly mitigated, not closed); the password policy is still "8+ characters" plus the new not-same/not-default/not-username rules (RISK-01 open — in the browser test `br02br02` was accepted).

### 8c. Still open (unchanged by this pass)

Top of the remaining list, in the order suggested in §7: **SEC-05 / RISK-02** (verify the rate-limit key behind the proxy on Railway), **BUG-12** (order status after admin edits), **BUG-08** (values rounding to 0.00), **BUG-01/02/05** (login lockout and case sensitivity), **BUG-04** (admin self-deactivation), **BUG-18** (backup script), SEC-06/07/08 (nginx headers, dependency upgrades, POS over plain HTTP), **BUG-06** (`nan` quantity — one line, same function as SEC-02 but outside the approved group), BUG-17 (first-submit race — it happened to return `[200, 422]` on the last run, but the code path is unchanged), and the performance/accessibility items.

### Appendix A — Product map (Phase 1)

* **Flows:** sign-in (JWT access 15 min + refresh 7 d, argon2, 5-strike lockout, per-IP rate limit, break-glass recovery token) → **Branch** (order by 14:00 for delivery +2 days, draft/submit/lock, Excel template upload, stock-in-hand from POS, delivery confirmation, chat) → **Supplier** (prices Mon/Wed/Fri before 12:00, orders by branch, chat) → **Admin** (order matrix + Excel export, per-product assignment, supplier order builder, supplier/Keells/local-market prices, master-data sheet + email, users, audit log, reports, settings).
* **Data model:** `docs/DATA_MODEL.md` — three different "delivery date" conventions are called out by the authors as a past bug source.
* **Assumptions:** roles are single-valued per user (`roles[0]`); usernames are lowercase by construction; one API process per deployment (in-memory rate limiter / POS token cache).

### Appendix B — Things done to the working tree
During the audit `git status` showed only `qa/` as new; the fix phase (§8) then modified 18 tracked files (14 source files, 1 test, README and a script docstring) and added 4 new ones (a migration, a model, a test file, one React screen) — all uncommitted; see `git status`. Also created outside the repo: a scratch venv, an embedded Postgres, launcher scripts, and (gitignored) four extra entries in `.claude/launch.json` (removed again at the end of the session). Every load/failure test ran against local instances; the load-test launcher disables the rate limiter **only in its own process**.

### Appendix C — Static-analysis output (Phase 2)

| Tool | Result |
|---|---|
| `tsc --noEmit` (frontend, strict) | exit 0, no errors |
| `vite build` | OK — 387 kB JS / 34 kB CSS |
| `ruff` (isolated, `E4,E7,E9,F,B,BLE,ASYNC`) on `app/` + `scripts/` | No undefined names/unused imports. Style-level only: `B008` ×many (FastAPI `Depends()` idiom — false positive), `B904` ×8 (`raise … from`), `BLE001` ×4 (broad `except`, all deliberate), `E741` ×1 (`scripts/smoke_test.py:289`); `F841` ×1 in `tests/test_assignment_status_recompute.py:216` |
| `bandit -ll` on `app/` | 3 × B310 (`urllib.urlopen` scheme audit) in `pos_stock_service.py:48,75` and `harti_import_service.py` — URLs come from config/constants, but see SEC-08 |
| `pip-audit` (full installed tree) | 40 advisories (see SEC-07) |
| `npm audit` | 5 (2 high dev-only: vite, nanoid; 3 moderate: react-router-dom ×2 runtime, esbuild dev-server) |
| Dead code | `fetchMyAssignments` (never called); `products.reference_cost_price` column documented as unused |
| Console (dev) | only React Router v7 future-flag warnings |
