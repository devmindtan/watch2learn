"""Access control for exposing the local backend to a publicly hosted UI.

Without an access token the backend is meant for this machine only (`pnpm dev`
binds 127.0.0.1). Once a token exists (env `WATCH2LEARN_ACCESS_TOKEN` or the file
`data/access-token`), every `/api/*` request must carry `Authorization: Bearer`.
Media elements cannot send headers, so media/thumbnail URLs are HMAC-signed and
expire.
"""

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOKEN_FILE = PROJECT_ROOT / "data" / "access-token"
SIGNED_URL_SECONDS = 6 * 60 * 60
PUBLIC_PATHS = {"/api/health"}


def access_token() -> str | None:
    configured = os.environ.get("WATCH2LEARN_ACCESS_TOKEN", "").strip()
    if configured:
        return configured
    try:
        stored = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return stored or None


def create_token_file() -> str:
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return token


def allowed_origins() -> list[str]:
    raw = os.environ.get("WATCH2LEARN_ALLOWED_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


def _signature(token: str, path: str, expires: int) -> str:
    message = f"{path}\n{expires}".encode()
    return hmac.new(token.encode(), message, hashlib.sha256).hexdigest()


def signed_url(path: str, now: float | None = None) -> str:
    """URL usable by <video>/<img> without headers; unchanged when no token is set."""
    token = access_token()
    if not token:
        return path
    expires = int((now or time.time()) + SIGNED_URL_SECONDS)
    query = urlencode({"expires": expires, "signature": _signature(token, path, expires)})
    return f"{path}?{query}"


def valid_signature(token: str, path: str, expires: str | None, signature: str | None) -> bool:
    if not expires or not signature or not expires.isdigit():
        return False
    if int(expires) < time.time():
        return False
    return hmac.compare_digest(_signature(token, path, int(expires)), signature)


def bearer_matches(token: str, header: str | None) -> bool:
    if not header or not header.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), token.encode())


def request_allowed(method: str, path: str, headers, query) -> bool:
    token = access_token()
    if not token or not path.startswith("/api/") or method == "OPTIONS":
        return True
    if path in PUBLIC_PATHS or bearer_matches(token, headers.get("authorization")):
        return True
    return method in {"GET", "HEAD"} and valid_signature(
        token, path, query.get("expires"), query.get("signature")
    )
