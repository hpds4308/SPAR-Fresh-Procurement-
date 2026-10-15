"""
Shared numeric ceiling for every request field backed by a NUMERIC(10,2)
database column (money and quantity fields across orders, pricing,
assignments, supplier orders, and master data).

Centralized here — unlike this codebase's usual per-schema-file
validators — specifically because it has to stay in lockstep with the
actual database column precision. A value at or above this ceiling
overflows NUMERIC(10,2) and previously reached the database uncaught,
surfacing as an unhandled 500 instead of a clean validation error;
duplicating the literal across every schema file would only need to
drift out of sync once to reopen that exact bug.
"""

MAX_NUMERIC_10_2 = 99999999.99


def one_decimal_error(value: float, label: str) -> str | None:
    """
    Supplier prices and branch order quantities may only use one decimal
    place: the second decimal must be 0 (5.70 is fine, 5.71 isn't). Returns
    the message to show, or None when the value is fine.
    """
    if round(value * 100) % 10:
        return f"{label} {value:.2f} isn't allowed — the second decimal must be 0 (e.g. 5.70, not 5.71)."
    return None
