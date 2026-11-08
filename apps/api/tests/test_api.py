import asyncio

import httpx
from watch2learn.app import app


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
