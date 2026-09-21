"""
SEC-10: a production start-up must refuse the placeholder SECRET_KEY that ships in the repo
(.env.example / config.py defaults) - anyone can read it, and a JWT only needs a user id to be forged.
"""
import pytest
from pydantic import ValidationError

from app.core.config import Settings

PLACEHOLDERS = ["changeme-generate-a-real-secret-in-.env", "changeme-generate-a-real-secret", "ChangeMe", "  CHANGEME-x  "]


@pytest.mark.parametrize("key", PLACEHOLDERS)
def test_production_refuses_placeholder_secret(key):
    with pytest.raises(ValidationError, match="SECRET_KEY is still the placeholder"):
        Settings(APP_ENV="production", SECRET_KEY=key, _env_file=None)


def test_production_accepts_a_real_secret():
    s = Settings(APP_ENV="production", SECRET_KEY="a" * 64, _env_file=None)
    assert s.APP_ENV == "production"


@pytest.mark.parametrize("env", ["development", "testing", "staging"])
def test_non_production_environments_keep_the_placeholder_working(env):
    # local dev / CI boot without ceremony
    assert Settings(APP_ENV=env, SECRET_KEY="changeme-anything", _env_file=None).SECRET_KEY.startswith("changeme")


def test_default_secret_key_is_a_placeholder_so_unconfigured_production_fails():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", _env_file=None)
