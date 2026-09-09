"""
Stock-in-hand lookup against SPAR's 24X7Retail / Dynamic Web POS system
(see the vendor's Web API Document — getToken, getStockInHand).

This is a display enhancement on the branch order form, not part of the
order-placement business logic, so every failure mode here — not
configured, POS unreachable, bad credentials, a branch with no location
code yet — resolves to "just don't show stock for these items," never
an error surfaced to the branch user and never anything that blocks
saving or submitting an order.

Field ownership: the POS system's own product code is products.pos_code,
and its own location code is branches.pos_location_code — both distinct
from and never assumed to match our own product_code/branch_code (see
the models for why).
"""
import json
import logging
import time
import urllib.error
import urllib.request
from base64 import b64encode

from app.core.config import settings

logger = logging.getLogger("spar.pos_stock")

REQUEST_TIMEOUT = 15
# The vendor's doc states a token is valid for 20 minutes; re-authenticate
# a little early so a request never starts on a token that expires mid-flight.
_TOKEN_LIFETIME_SECONDS = 18 * 60

# Process-local cache — one backend instance, no need for anything shared
# like Redis for a single bearer token.
_cached_token: str | None = None
_cached_token_expires_at: float = 0.0


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
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
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

    token = _get_token()
    if not token:
        return {}

    base = settings.POS_API_BASE_URL.rstrip("/")
    try:
        body = _post_json(
            f"{base}/api/SIH/getSIH",
            {"Products": pos_product_codes, "Locations": [pos_location_code]},
            token=token,
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        logger.warning("could not fetch stock-in-hand from the POS system: %s", e)
        return {}

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
