import asyncio

import httpx
import pytest
from watch2learn import app as app_module
from watch2learn import storage, youtube
from watch2learn.app import app
from watch2learn.subtitles import Cue


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&t=10s",
        "youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw?si=abc",
        "https://m.youtube.com/shorts/jNQXAC9IVRw",
        "https://www.youtube.com/embed/jNQXAC9IVRw",
        "jNQXAC9IVRw",
    ],
)
def test_parse_video_id_accepts_common_youtube_links(url):
    assert youtube.parse_video_id(url) == "jNQXAC9IVRw"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com.evil.example/watch?v=jNQXAC9IVRw",
        "file:///etc/passwd",
        "https://www.youtube.com/watch?v=bad",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw;rm",
        "--exec=calc https://youtu.be/jNQXAC9IVRw",
    ],
)
def test_parse_video_id_rejects_other_hosts_and_injection(url):
    with pytest.raises(ValueError):
        youtube.parse_video_id(url)


def test_subtitle_choice_prefers_simplified_chinese_and_ignores_other_languages():
    assert youtube.choose_subtitle(["en", "zh-Hant", "zh-Hans"]) == "zh-Hans"
    assert youtube.choose_subtitle(["zh-Hant-TW"]) == "zh-Hant-TW"
    assert youtube.choose_subtitle(["en", "vi"]) is None


async def call(method, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.jobs, "DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr(app_module, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(storage, "MEDIA_ROOT", tmp_path / "data" / "media")
    monkeypatch.setattr(storage, "PROJECT_ROOT", tmp_path)

    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(app_module.asyncio, "to_thread", run_inline)


def test_youtube_lesson_requires_rights_confirmation():
    response = asyncio.run(
        call("POST", "/api/lessons/youtube", json={"url": "https://youtu.be/jNQXAC9IVRw"})
    )
    assert response.status_code == 422


def test_youtube_lesson_uses_uploader_subtitles_and_downloads_on_request(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(
        youtube,
        "fetch_metadata",
        lambda video_id: {
            "video_id": video_id,
            "title": "中文课",
            "channel": "Teacher",
            "duration": 60,
            "subtitles": ["en", "zh-Hans"],
        },
    )

    def fake_subtitle(video_id, language, work_dir):
        assert language == "zh-Hans"
        path = work_dir / "youtube-subtitle.zh-Hans.vtt"
        path.write_text("WEBVTT\n\n00:00.000 --> 00:02.000\n今天学习中文。\n", encoding="utf-8")
        return path

    def fake_download(video_id, output_stem, audio_only, on_progress=None):
        assert audio_only is False
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        path = output_stem.with_suffix(".mp4")
        path.write_bytes(b"\0" * 2048)
        return path

    monkeypatch.setattr(youtube, "download_subtitle", fake_subtitle)
    monkeypatch.setattr(youtube, "download", fake_download)
    monkeypatch.setattr(app_module, "transcribe_mandarin", lambda *a, **k: pytest.fail("no ASR"))

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            body = {"url": "https://youtu.be/jNQXAC9IVRw", "confirm_rights": True}
            job = (await client.post("/api/lessons/youtube", json=body)).json()
            for _ in range(100):
                job = (await client.get(f"/api/jobs/{job['id']}")).json()
                if job["status"] not in {"queued", "processing"}:
                    break
                await asyncio.sleep(0.02)
            assert job["status"] == "complete", job
            lesson = (await client.get(f"/api/lessons/{job['id']}")).json()
            assert lesson["filename"] == "中文课"
            assert lesson["source"]["video_id"] == "jNQXAC9IVRw"
            assert lesson["transcript"]["method"] == "youtube-subtitle"
            assert lesson["media"] == {"available": False}

            started = await client.post(f"/api/lessons/{job['id']}/download")
            assert started.status_code == 202
            for _ in range(100):
                status = (await client.get(f"/api/lessons/{job['id']}/download")).json()
                if status["status"] != "running":
                    break
                await asyncio.sleep(0.02)
            assert status["status"] == "complete", status
            media = await client.get(
                f"/api/lessons/{job['id']}/media", headers={"Range": "bytes=0-99"}
            )
            assert media.status_code == 206
            assert len(media.content) == 100

            listed = (await client.get("/api/lessons")).json()
            assert listed[0]["has_media"] is True
            assert listed[0]["source_kind"] == "youtube"

            assert (await client.delete(f"/api/lessons/{job['id']}")).status_code == 204
            assert (await client.get(f"/api/lessons/{job['id']}")).status_code == 404
            assert not (tmp_path / "data" / "media" / job["id"]).exists()

    asyncio.run(scenario())


def test_uploaded_video_is_kept_in_lesson_media_folder(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(
        app_module,
        "transcribe_mandarin",
        lambda path, on_progress=None: ([Cue("cue-1", 0, 900, "你好。")], {"method": "test"}),
    )
    audio_only = {"streams": [{"codec_type": "audio"}]}
    monkeypatch.setattr(app_module, "probe_media", lambda path: audio_only)
    monkeypatch.setattr(
        app_module, "extract_asr_audio", lambda source, output: output.write_bytes(b"") or output
    )

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"video": ("clip.mp4", b"fake-video-bytes", "video/mp4")}
            job = (await client.post("/api/lessons/mandarin-video", files=files)).json()
            for _ in range(100):
                job = (await client.get(f"/api/jobs/{job['id']}")).json()
                if job["status"] not in {"queued", "processing"}:
                    break
                await asyncio.sleep(0.02)
            assert job["status"] == "complete", job
            lesson = (await client.get(f"/api/lessons/{job['id']}")).json()
            assert lesson["media"]["available"] is True
            assert lesson["media"]["path"] == f"data/media/{job['id']}/video.mp4"
            media = await client.get(lesson["media"]["url"])
            assert media.content == b"fake-video-bytes"
            assert media.headers["content-type"] == "video/mp4"

    asyncio.run(scenario())
    assert (tmp_path / "data" / "media").is_dir()
