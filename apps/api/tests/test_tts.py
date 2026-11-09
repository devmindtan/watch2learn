import asyncio

import httpx
import pytest
from watch2learn import app as app_module
from watch2learn import tts
from watch2learn.app import app

FAKE_VOICES = {
    "vi": [{"id": "Ngọc Huyền", "label": "Ngọc Huyền"}, {"id": "Hải Đăng", "label": "Hải Đăng"}],
    "zh": [{"id": "zf_001", "label": "Nữ 1"}, {"id": "zm_010", "label": "Nam 2"}],
}


async def call(method, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_missing_voices_and_invalid_requests(monkeypatch):
    monkeypatch.setattr(tts, "voices_ready", lambda: False)
    hello = {"parts": [{"text": "你好", "lang": "zh"}]}
    response = asyncio.run(call("POST", "/api/tts", json=hello))
    assert response.status_code == 503 and "setup:voices" in response.json()["detail"]
    monkeypatch.setattr(tts, "voices_ready", lambda: True)
    bad_lang = {"parts": [{"text": "hi", "lang": "en"}]}
    assert asyncio.run(call("POST", "/api/tts", json=bad_lang)).status_code == 422
    assert asyncio.run(call("POST", "/api/tts", json={"parts": []})).status_code == 422


def test_voice_choice_is_validated_saved_and_used(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.jobs, "DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr(tts, "voices_ready", lambda: True)
    monkeypatch.setattr(tts, "available_voices", lambda: FAKE_VOICES)
    used = []

    def fake_synthesize(parts, voices):
        used.append(voices)
        path = tmp_path / "speech.m4a"
        path.write_bytes(b"audio")
        return path

    monkeypatch.setattr(tts, "synthesize", fake_synthesize)
    listed = asyncio.run(call("GET", "/api/voices")).json()
    assert listed["selected"] == tts.DEFAULT_VOICES
    assert asyncio.run(call("PUT", "/api/voices", json={"vi": "Nobody"})).status_code == 422
    saved = asyncio.run(call("PUT", "/api/voices", json={"vi": "Hải Đăng", "zh": "zm_010"}))
    assert saved.json()["selected"] == {"vi": "Hải Đăng", "zh": "zm_010"}

    parts = {"parts": [{"text": "你好", "lang": "zh"}]}
    assert asyncio.run(call("POST", "/api/tts", json=parts)).status_code == 200
    preview = parts | {"voices": {"zh": "zf_001"}}
    assert asyncio.run(call("POST", "/api/tts", json=preview)).status_code == 200
    assert used == [{"vi": "Hải Đăng", "zh": "zm_010"}, {"vi": "Hải Đăng", "zh": "zf_001"}]


@pytest.mark.skipif(not tts.voices_ready(), reason="run pnpm setup:voices")
def test_local_voices_read_mixed_chinese_and_vietnamese(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    parts = [
        {"text": "Từ này đọc là", "lang": "vi", "rate": 1.0},
        {"text": "手机", "lang": "zh", "rate": 0.8},
        {"text": "nghĩa là điện thoại di động.", "lang": "vi", "rate": 1.0},
    ]
    first = tts.synthesize(parts)
    assert first.stat().st_size > 5000
    assert tts.synthesize(parts) == first  # cached
    voices = tts.available_voices()
    assert any(item["id"] == tts.DEFAULT_VOICES["vi"] for item in voices["vi"])
