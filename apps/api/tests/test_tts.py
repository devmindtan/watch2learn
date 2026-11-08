import asyncio

import httpx
import pytest
from watch2learn import tts
from watch2learn.app import app


async def post(payload):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/tts", json=payload)


class FakeConfig:
    phoneme_id_map = {
        "^": [1], "$": [2], "_": [0], "Ø": [3], "x": [17], "ue": [63], "2": [65],
        "i": [39], "。": [69],
    }  # fmt: skip


class FakeVoice:
    config = FakeConfig()


def test_chinese_is_voiced_from_the_context_reading():
    # 学习 → xue2 xi2: initial, final and tone groups, pause after each tone
    ids = tts.chinese_phoneme_ids(FakeVoice(), "學習。")
    assert ids == [1, 17, 63, 65, 0, 17, 39, 65, 0, 69, 0, 2]


def test_endpoint_reports_missing_voices_and_validates_input(monkeypatch):
    monkeypatch.setattr(tts, "voices_ready", lambda: False)
    response = asyncio.run(post({"parts": [{"text": "你好", "lang": "zh"}]}))
    assert response.status_code == 503 and "setup:voices" in response.json()["detail"]
    monkeypatch.setattr(tts, "voices_ready", lambda: True)
    assert asyncio.run(post({"parts": [{"text": "hi", "lang": "en"}]})).status_code == 422
    assert asyncio.run(post({"parts": []})).status_code == 422


@pytest.mark.skipif(not tts.voices_ready(), reason="run pnpm setup:voices")
def test_local_voices_read_mixed_chinese_and_vietnamese(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    parts = [
        {"text": "Từ", "lang": "vi", "rate": 1.0},
        {"text": "手机", "lang": "zh", "rate": 0.8},
        {"text": "nghĩa là điện thoại di động.", "lang": "vi", "rate": 1.0},
    ]
    response = asyncio.run(post({"parts": parts}))
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert len(response.content) > 5000
    assert len(list(tmp_path.glob("*.m4a"))) == 1
    assert asyncio.run(post({"parts": parts})).content == response.content  # cached
