"""
The production Caddyfile's Content-Security-Policy allows index.html's one
inline <script> (the boot-splash fallback) by its sha256 hash. Editing that
script changes the hash, and a stale hash makes browsers block it — the
splash then never clears. Repo-root files aren't in the backend Docker
image, so this only runs from a full checkout.
"""
import base64
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "Caddyfile"
INDEX_HTML = ROOT / "frontend" / "index.html"

pytestmark = pytest.mark.skipif(
    not (CADDYFILE.exists() and INDEX_HTML.exists()), reason="needs the full repo checkout"
)


def test_csp_allows_every_inline_script_in_index_html():
    html = INDEX_HTML.read_text(encoding="utf-8")
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    allowed = set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", CADDYFILE.read_text(encoding="utf-8")))
    for body in inline:
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        assert digest in allowed, f"Caddyfile CSP is missing 'sha256-{digest}' for an inline script in index.html"
