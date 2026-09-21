# QA suite (added by the QA audit)

Findings live in [`QA_REPORT.md`](QA_REPORT.md); the fixes made afterwards are in its §8. During the audit nothing under `backend/` or
`frontend/` was modified; the fix pass then touched only the files listed in §8. Everything here runs against a **local** stack only.

```
qa/
  QA_REPORT.md            the report
  pytest.ini              pytest config for qa/backend
  reset_qa_db.py          clears orders/prices/assignments/messages, restores the seeded password + lifts must_change_password,
                          in the LOCAL `spar_qa` DB only (refuses anything else)
  backend/                pytest: reuses the app's own DB fixtures (imports backend/tests/conftest.py, edits nothing)
    test_qa_auth.py                    login, lockout, refresh tokens, recovery token, rate limit
    test_qa_authz_matrix.py            generated from the route table: all 89 routes x anonymous / wrong role
    test_qa_orders_and_validation.py   Excel upload, rounding, hostile text, order/assignment rules, timezone
    test_qa_pos_stock.py               POS integration failure modes using a real local TCP server
    test_qa_session_and_password.py    BUG-03 / SEC-01 fixes: token versioning, per-session logout, forced password change, migration
    test_qa_excel_and_pos_limits.py    SEC-02 / SEC-03 fixes: upload caps, POS circuit breaker, concurrency cap, DB session released
  e2e/                    Playwright (Chromium) + axe-core
    tests/01-auth.spec.ts              flow 1: login, roles, guards, refresh, logout
    tests/02-procurement-cycle.spec.ts flows 2-5: order -> matrix/export -> supplier price -> assignment -> delivery confirm
    tests/03-responsive-a11y.spec.ts   320/375/768/1024/1440 px layout + WCAG 2.1 A/AA scan
    tests/04-session-and-password.spec.ts  forced password change, deep-link bypass, logout revocation, shared-login second device
    tests/99-rate-limit.spec.ts        login rate-limit UX (runs last; waits for the window to clear)
    scripts/page_metrics.mjs           load metrics for the production build, unthrottled / Slow 4G / Fast 3G
  perf/concurrency_check.py           13 simultaneous order submissions, first-submit race, dead-POS starvation
```

## Convention: `xfail` = a confirmed defect, pinned

* A test that **passes** documents behaviour that is correct today.
* `@pytest.mark.xfail(strict=True, reason="BUG-xx ...")` (pytest) / `test.fail(true, "BUG-xx ...")` (Playwright) pins a
  **confirmed defect** from the report. The suite is green today; the moment a bug is fixed the test turns red
  ("unexpectedly passed") — delete the marker and keep the test as a regression guard.
* `xfail(strict=False, reason="RISK-xx ...")` pins a suspected risk / product decision.
* Findings that have been **fixed** (BUG-03, BUG-07, SEC-01, SEC-02, SEC-03, SEC-10) no longer carry a marker: their tests now assert the fixed behaviour.

## Run it

Prerequisites (all local): Python 3.12 with `backend/requirements.txt` + `pytest-cov`, a Postgres reachable through
`DATABASE_URL`, Node 20+.

```bash
# 1) backend tests (the app's own 195 + the QA suite). A "<db>_test" database is created + migrated automatically.
export DATABASE_URL=postgresql+psycopg2://USER:PASS@127.0.0.1:5432/spar_procurement
cd backend && python -m pytest --cov=app            # existing suite, ~40 s
cd .. && python -m pytest -c qa/pytest.ini qa/backend   # QA suite, ~50 s

# 2) e2e: needs migrated + seeded data (python -m scripts.seed_master_data && python -m scripts.seed_users), a backend on :8000
#    and the Vite dev server on :5173 (VITE_API_BASE_URL=http://localhost:8000).
cd qa/e2e && npm install && npx playwright install chromium
QA_DATABASE_URL=postgresql://USER:PASS@127.0.0.1:5432/spar_qa python ../reset_qa_db.py   # only the local DB named `spar_qa`
#    (seed it with `python -m scripts.seed_users --no-force-change` or just run the reset script, which lifts the flag)
npx playwright test               # ~10 min: logins are paced to stay under the 10/min login rate limit
```

Notes
* The supplier-price / assignment steps only run on **Mon/Wed/Fri (Asia/Colombo)** — that is the app's own rule
  (`pricing_service.SUBMISSION_WEEKDAYS`); on other days they are reported as skipped.
* Set `QA_PASSWORD` if the seeded accounts do not use the default password.
* For capacity numbers the backend was started with the slowapi limiter disabled through a scratch launcher
  (not part of the repo); the shipped limiter is exercised by `test_login_rate_limit_*` and `99-rate-limit.spec.ts`.
