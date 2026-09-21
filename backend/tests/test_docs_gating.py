"""
M-1: interactive API docs (Swagger UI) and the raw OpenAPI schema must be
reachable in development/testing but disabled in production. Verifies
the actual FastAPI app construction, not just the boolean that feeds it
— re-imports app.main with APP_ENV forced to each value in turn, since
docs_url/openapi_url are set once at module import time.
"""
import importlib
import os
import sys


def _import_app_with_env(app_env):
    """
    Forces a fresh import of app.main (and app.core.config, whose
    module-level `settings` singleton is what app.main reads APP_ENV
    from) under the given APP_ENV, restoring both the environment and
    the module cache afterward so this doesn't leak into other tests.
    """
    original_env = os.environ.get("APP_ENV")
    original_secret = os.environ.get("SECRET_KEY")
    modules_to_clear = ["app.main", "app.core.config"]
    saved_modules = {name: sys.modules.get(name) for name in modules_to_clear}
    try:
        os.environ["APP_ENV"] = app_env
        # A production start-up now refuses the placeholder SECRET_KEY (SEC-10), so give this
        # simulated production boot a real-looking key. Restored below like APP_ENV.
        os.environ["SECRET_KEY"] = "test-only-secret-that-is-not-a-placeholder-0123456789abcdef"
        for name in modules_to_clear:
            sys.modules.pop(name, None)
        main = importlib.import_module("app.main")
        return main.app
    finally:
        if original_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = original_env
        if original_secret is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = original_secret
        for name, mod in saved_modules.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


def test_docs_disabled_in_production():
    app = _import_app_with_env("production")
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_docs_enabled_in_development():
    app = _import_app_with_env("development")
    assert app.docs_url == "/api/v1/docs"
    assert app.openapi_url == "/api/v1/openapi.json"


def test_docs_enabled_when_app_env_unset_or_unrecognized():
    # Anything that isn't literally "production" keeps docs on — a typo
    # in APP_ENV should fail open to "docs visible", never silently
    # closed in a way that could be mistaken for a working prod gate.
    app = _import_app_with_env("staging")
    assert app.docs_url == "/api/v1/docs"
