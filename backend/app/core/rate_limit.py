"""
Per-IP request rate limiting (slowapi/limits), separate from the
per-account failed-login lockout in auth_service.py. The lockout stops
someone guessing one account's password; this stops one source hammering
the API generally — including spreading login attempts across many
different usernames, which the lockout alone wouldn't catch quickly.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
