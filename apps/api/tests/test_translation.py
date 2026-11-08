import asyncio

import httpx
import pytest
from watch2learn import translation
from watch2learn.app import app


async def post_translate(payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/translate", json=payload)


def test_translate_endpoint_reports_missing_model(monkeypatch):
    monkeypatch.setattr(translation, "model_ready", lambda: False)
    response = asyncio.run(post_translate({"texts": ["你好"]}))
    assert response.status_code == 503
    assert "setup:translation" in response.json()["detail"]


def test_translate_endpoint_preserves_order_and_limits_input(monkeypatch):
    monkeypatch.setattr(translation, "model_ready", lambda: True)
    monkeypatch.setattr(
        translation, "translate_to_vietnamese", lambda texts: [f"vi:{text}" for text in texts]
    )
    response = asyncio.run(post_translate({"texts": ["你好", "再见"]}))
    assert response.status_code == 200
    assert response.json()["translations"] == ["vi:你好", "vi:再见"]

    assert asyncio.run(post_translate({"texts": []})).status_code == 422
    assert asyncio.run(post_translate({"texts": ["长" * 501]})).status_code == 422
    assert asyncio.run(post_translate({"texts": ["好"] * 101})).status_code == 422


@pytest.mark.skipif(not translation.model_ready(), reason="run pnpm setup:translation")
def test_local_model_translates_mandarin_to_vietnamese():
    result = translation.translate_to_vietnamese(["我们今天去看电影吧。", "", "你好"])
    assert "phim" in result[0].lower()
    assert result[1] == ""
    assert result[2]
