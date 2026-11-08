import asyncio
import time

import httpx
from watch2learn import security, storage
from watch2learn.app import app


async def call(method, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_without_token_the_local_backend_is_open(monkeypatch, tmp_path):
    monkeypatch.delenv("WATCH2LEARN_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(security, "TOKEN_FILE", tmp_path / "missing")
    assert asyncio.run(call("GET", "/api/lessons")).status_code == 200
    assert security.signed_url("/api/lessons/x/media") == "/api/lessons/x/media"


def test_token_protects_every_api_route(monkeypatch):
    monkeypatch.setenv("WATCH2LEARN_ACCESS_TOKEN", "secret-token")
    assert asyncio.run(call("GET", "/api/lessons")).status_code == 401
    assert asyncio.run(call("DELETE", "/api/lessons/abc")).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert asyncio.run(call("GET", "/api/lessons", headers=wrong)).status_code == 401
    good = {"Authorization": "Bearer secret-token"}
    assert asyncio.run(call("GET", "/api/lessons", headers=good)).status_code == 200

    health = asyncio.run(call("GET", "/api/health")).json()
    assert health == {"status": "ok", "auth_required": True, "authorized": False}
    assert asyncio.run(call("GET", "/api/health", headers=good)).json()["authorized"] is True
    assert asyncio.run(call("GET", "/")).status_code == 200  # the UI itself is public


def test_media_urls_are_signed_and_expire(monkeypatch, tmp_path):
    monkeypatch.setenv("WATCH2LEARN_ACCESS_TOKEN", "secret-token")
    path = "/api/lessons/0123456789abcdef0123456789abcdef/media"
    url = security.signed_url(path)
    query = dict(item.split("=") for item in url.split("?")[1].split("&"))
    assert security.valid_signature("secret-token", path, query["expires"], query["signature"])
    expires, signature = query["expires"], query["signature"]
    assert not security.valid_signature("secret-token", path + "x", expires, signature)
    old = security.signed_url(path, now=time.time() - 10 * security.SIGNED_URL_SECONDS)
    old_query = dict(item.split("=") for item in old.split("?")[1].split("&"))
    assert not security.valid_signature(
        "secret-token", path, old_query["expires"], old_query["signature"]
    )
    # signature only grants read access, never writes
    allowed = security.request_allowed("DELETE", path, {}, query)
    assert allowed is False
    monkeypatch.setattr(storage, "MEDIA_ROOT", tmp_path)
    (tmp_path / "0123456789abcdef0123456789abcdef").mkdir()
    (tmp_path / "0123456789abcdef0123456789abcdef" / "video.mp4").write_bytes(b"v")
    monkeypatch.setattr(storage, "PROJECT_ROOT", tmp_path)
    assert "signature=" in storage.media_info("0123456789abcdef0123456789abcdef")["url"]


def test_public_page_preflight_allows_private_network(monkeypatch):
    monkeypatch.setenv("WATCH2LEARN_ACCESS_TOKEN", "secret-token")
    response = asyncio.run(
        call(
            "OPTIONS",
            "/api/lessons",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
                "Access-Control-Request-Private-Network": "true",
            },
        )
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-private-network"] == "true"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
