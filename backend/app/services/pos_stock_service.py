"""
Stock-in-hand lookup against SPAR's 24X7Retail / Dynamic Web POS system
(see the vendor's Web API Document — getToken, getStockInHand).

This is a display enhancement on the branch order form, not part of the
order-placement business logic, so every failure mode here — not
configured, POS unreachable, bad credentials, a branch with no location
code yet — resolves to "just don't show stock for these items," never
an error surfaced to the branch user and never anything that blocks
saving or submitting an order.

That contract is enforced on three levels (QA findings BUG-07 / SEC-03):
  * every network/protocol failure is caught, not just the URLError family - a reset connection, a
    truncated body or a hang-up used to escape as an HTTP 500;
  * short timeouts plus a circuit breaker: after one failure the POS is left alone for a minute, so a
    dead POS costs one slow request per minute instead of one per page load;
  * a small cap on simultaneous POS calls, so even a slow-but-alive POS can never tie up more than a
    handful of workers (and, with them, database connections).

Field ownership: the POS system's own product code is products.pos_code,
and its own location code is branches.pos_location_code — both distinct
from and never assumed to match our own product_code/branch_code (see
the models for why).
"""
import http.client
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from base64 import b64encode

from app.core.config import settings

logger = logging.getLogger("spar.pos_stock")

# Seconds allowed for each socket operation (connect / read). Was 15: with two calls per lookup a dead POS
# held a worker for 30 s. A healthy POS answers in well under a second.
REQUEST_TIMEOUT = 5
# After a failed call, skip the POS entirely for this long instead of retrying on every page load.
FAILURE_COOLDOWN_SECONDS = 60
# At most this many POS calls in flight at once; further requests just show no stock figures.
MAX_CONCURRENT_POS_CALLS = 4

# Everything that can go wrong talking to a remote HTTP server: URLError/HTTPError/TimeoutError/
# ConnectionResetError/ConnectionAbortedError are all OSError; truncated or malformed HTTP is
# http.client.HTTPException (IncompleteRead, RemoteDisconnected, BadStatusLine); bad JSON is ValueError.
_NETWORK_ERRORS = (OSError, http.client.HTTPException, ValueError)
# The vendor's doc states a token is valid for 20 minutes; re-authenticate
# a little early so a request never starts on a token that expires mid-flight.
_TOKEN_LIFETIME_SECONDS = 18 * 60

# Process-local cache — one backend instance, no need for anything shared
# like Redis for a single bearer token.
_cached_token: str | None = None
_cached_token_expires_at: float = 0.0

# Circuit breaker state (monotonic clock) and the in-flight cap.
_breaker_open_until: float = 0.0
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_POS_CALLS)


def _trip_breaker(reason: object) -> None:
    global _breaker_open_until, _cached_token, _cached_token_expires_at
    _breaker_open_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS
    _cached_token, _cached_token_expires_at = None, 0.0  # the failure may have been an expired token
    logger.warning("POS unavailable (%s); skipping stock lookups for %ss", reason, FAILURE_COOLDOWN_SECONDS)


def _is_configured() -> bool:
    return bool(settings.POS_API_BASE_URL and settings.POS_API_USERNAME and settings.POS_API_PASSWORD)


def _post_json(url: str, body: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read())


def _get_token() -> str | None:
    global _cached_token, _cached_token_expires_at

    if _cached_token and time.time() < _cached_token_expires_at:
        return _cached_token

    base = settings.POS_API_BASE_URL.rstrip("/")
    credentials = b64encode(f"{settings.POS_API_USERNAME}:{settings.POS_API_PASSWORD}".encode()).decode()
    # The vendor's own Web API document describes Basic Auth with no
    # request body, but the deployed server actually rejects that with
    # "the UserName field is required" — it wants a JSON body with
    # PascalCase UserName/Password too, confirmed directly against the
    # live server. Sending both satisfies whichever the server checks.
    login_body = json.dumps(
        {"UserName": settings.POS_API_USERNAME, "Password": settings.POS_API_PASSWORD}
    ).encode()
    req = urllib.request.Request(
        f"{base}/api/Login/authenticate",
        data=login_body,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read())
    except _NETWORK_ERRORS as e:
        logger.warning("could not authenticate with the POS system: %s", e)
        return None

    token = (body.get("Data") or {}).get("Token")
    if not token:
        logger.warning("POS authentication succeeded but no token was returned: %s", body.get("StatusMessage"))
        return None

    _cached_token = token
    _cached_token_expires_at = time.time() + _TOKEN_LIFETIME_SECONDS
    return token


def get_stock_in_hand(pos_product_codes: list[str], pos_location_code: str) -> dict[str, float]:
    """
    Returns {pos_product_code: current_stock_in_hand} for whatever the POS
    system has data for — silently fewer keys than requested is normal
    (a product the POS doesn't carry, for instance), not an error.
    Returns {} if POS integration isn't configured, the branch has no
    location code, or the call fails for any reason.
    """
    if not pos_product_codes or not pos_location_code or not _is_configured():
        return {}

    if time.monotonic() < _breaker_open_until:
        return {}  # POS recently failed - don't make this request wait for it too
    if not _slots.acquire(blocking=False):
        return {}  # POS is already busy serving other requests - degrade instead of queueing

    try:
        token = _get_token()
        if not token:
            _trip_breaker("authentication failed")
            return {}

        base = settings.POS_API_BASE_URL.rstrip("/")
        try:
            body = _post_json(
                f"{base}/api/SIH/getSIH",
                {"Products": pos_product_codes, "Locations": [pos_location_code]},
                token=token,
            )
        except _NETWORK_ERRORS as e:
            logger.warning("could not fetch stock-in-hand from the POS system: %s", e)
            _trip_breaker(type(e).__name__)
            return {}
    finally:
        _slots.release()

    result: dict[str, float] = {}
    for location in body.get("Data") or []:
        for product in location.get("Products") or []:
            code = product.get("ProductCode")
            quantity = product.get("CurrentStockInHand")
            if code is not None and quantity is not None:
                try:
                    result[str(code)] = float(quantity)
                except (TypeError, ValueError):
                    continue
    return result
