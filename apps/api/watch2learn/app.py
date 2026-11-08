"""FastAPI entry point for local video-to-vocabulary lessons."""

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .asr import model_ready, transcribe_mandarin
from .dictionary import load_cedict
from .lesson import build_lesson
from .media import (
    extract_asr_audio,
    extract_embedded_subtitles,
    preferred_subtitle_stream,
    probe_media,
)
from .subtitles import parse_subtitles

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = PROJECT_ROOT / "apps" / "web"
MAX_SUBTITLE_CHARACTERS = 2_000_000
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
MEDIA_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mp3", ".m4a", ".wav"}
JOBS_ROOT = PROJECT_ROOT / "data" / "jobs"

app = FastAPI(title="Watch2Learn", version="0.1.0")
app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")


class LessonRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_SUBTITLE_CHARACTERS)
    filename: str = Field(default="subtitles.srt", max_length=255)
    language: str = Field(default="zh", pattern=r"^zh(?:-(?:Hans|Hant))?$")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
async def health() -> dict:
    dictionary = load_cedict()
    return {
        "status": "ok",
        "dictionary_loaded": dictionary.source is not None,
        "asr_model_ready": model_ready(),
    }


@app.post("/api/lessons/mandarin")
async def create_mandarin_lesson(request: LessonRequest) -> dict:
    try:
        cues = parse_subtitles(request.content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    lesson = build_lesson(cues, load_cedict())
    return {
        "filename": request.filename,
        "language": request.language,
        "transcript": {"method": "uploaded-subtitle"},
        **lesson,
    }


async def save_upload(video: UploadFile, destination: Path) -> int:
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await video.read(8 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_VIDEO_BYTES:
                    raise HTTPException(
                        status_code=413, detail="Video exceeds the 4 GiB local limit"
                    )
                output.write(chunk)
    finally:
        await video.close()
    return size


def process_video(source: Path, work_dir: Path) -> dict:
    probe = probe_media(source)
    subtitle_index = preferred_subtitle_stream(probe)
    if subtitle_index is not None:
        try:
            subtitle_path = extract_embedded_subtitles(
                source, subtitle_index, work_dir / "embedded.vtt"
            )
            cues = parse_subtitles(subtitle_path.read_text(encoding="utf-8-sig"))
            transcript = {"method": "embedded-subtitle", "stream_index": subtitle_index}
        except (OSError, UnicodeDecodeError, ValueError, subprocess.SubprocessError):
            cues = []
        if cues:
            return {"transcript": transcript, **build_lesson(cues, load_cedict())}

    if not any(stream.get("codec_type") == "audio" for stream in probe.get("streams", [])):
        raise RuntimeError("Video has no readable audio or subtitle stream")
    audio_path = extract_asr_audio(source, work_dir / "speech.wav")
    cues, transcript = transcribe_mandarin(audio_path)
    return {"transcript": transcript, **build_lesson(cues, load_cedict())}


@app.post("/api/lessons/mandarin-video")
async def create_mandarin_video_lesson(video: Annotated[UploadFile, File()]) -> dict:
    filename = Path(video.filename or "video").name
    suffix = Path(filename).suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported video or audio format")
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="lesson-", dir=JOBS_ROOT))
    source = work_dir / f"source{suffix}"
    try:
        size = await save_upload(video, source)
        if not size:
            raise HTTPException(status_code=422, detail="Video is empty")
        lesson = await asyncio.to_thread(process_video, source, work_dir)
        return {
            "filename": filename,
            "language": "zh",
            **lesson,
        }
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        status = 503 if "ASR model is missing" in str(error) else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
