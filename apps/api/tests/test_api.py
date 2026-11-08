import asyncio
import io
import wave

import httpx
from watch2learn import app as app_module
from watch2learn.app import app
from watch2learn.subtitles import Cue


async def request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_health_and_lesson_endpoint():
    assert asyncio.run(request("GET", "/api/health")).status_code == 200
    response = asyncio.run(
        request(
            "POST",
            "/api/lessons/mandarin",
            json={
                "filename": "lesson.srt",
                "language": "zh",
                "content": "1\n00:00:00,000 --> 00:00:02,000\n你好，欢迎学习中文。\n",
            },
        )
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["cues"][0]["text"] == "你好，欢迎学习中文。"
    assert payload["vocabulary"]
    assert payload["vocabulary"][0]["occurrences"][0]["cue_text"]


def test_invalid_subtitle_returns_useful_error():
    response = asyncio.run(
        request(
            "POST",
            "/api/lessons/mandarin",
            json={"content": "not a subtitle", "filename": "bad.srt", "language": "zh"},
        )
    )
    assert response.status_code == 422
    assert "No valid" in response.json()["detail"]


def test_video_without_subtitle_uses_local_asr(monkeypatch):
    audio = io.BytesIO()
    with wave.open(audio, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * 16_000)

    def fake_transcribe(path):
        assert path.name == "speech.wav"
        return [Cue("cue-1", 0, 1200, "你好，欢迎学习中文。")], {"method": "test-asr"}

    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(app_module, "transcribe_mandarin", fake_transcribe)
    monkeypatch.setattr(app_module.asyncio, "to_thread", run_inline)
    response = asyncio.run(
        request(
            "POST",
            "/api/lessons/mandarin-video",
            files={"video": ("lesson.wav", audio.getvalue(), "audio/wav")},
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"]["method"] == "test-asr"
    assert payload["cues"][0]["text"] == "你好，欢迎学习中文。"
