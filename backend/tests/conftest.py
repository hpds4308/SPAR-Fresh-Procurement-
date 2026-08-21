"""
Shared test doubles. These tests are pure unit tests — no live server,
no real database — so they run in CI without any setup. That's a
deliberate complement to scripts/smoke_test.py (which does exercise a
real server + database end-to-end): this suite covers the exact class of
bug smoke_test.py's own docstring says "have actually broken before"
(cutoff/date logic), but fast enough to run on every change instead of
only when someone remembers to run the smoke test by hand.
"""


class FakeQuery:
    """Mimics db.query(Model).filter(...).first() always finding nothing,
    so settings_service.get_setting() falls back to its .env-configured
    default — exactly the state a fresh install is in before Admin ever
    opens the Settings page."""

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class FakeDB:
    def query(self, *args, **kwargs):
        return FakeQuery()
