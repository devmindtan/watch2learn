"""FastAPI entry point for local video-to-vocabulary lessons."""

import asyncio
import hashlib
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import jobs, translation
from .asr import model_ready, transcribe_mandarin
from .dictionary import load_cedict, load_vietnamese
from .lesson import ANALYSIS_VERSION, add_vietnamese_definitions, build_lesson
from .media import (
    extract_asr_audio,
    extract_embedded_subtitles,
    preferred_subtitle_stream,
    probe_media,
)
from .subtitles import Cue, parse_subtitles

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = PROJECT_ROOT / "apps" / "web"
MAX_SUBTITLE_CHARACTERS = 2_000_000
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
MEDIA_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mp3", ".m4a", ".wav"}
JOBS_ROOT = PROJECT_ROOT / "data" / "jobs"
RUNNING_TASKS: set[asyncio.Task] = set()
MAX_TRANSLATION_LINES = 100
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    resume_pending_jobs()
    cleanup_abandoned_job_files()
    yield


app = FastAPI(title="Watch2Learn", version="0.2.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")


def cleanup_abandoned_job_files() -> None:
    if not JOBS_ROOT.is_dir():
        return
    active = {Path(item["work_dir"]).resolve() for item in jobs.pending()}
    for work_dir in JOBS_ROOT.glob("lesson-*"):
        if work_dir.is_dir() and work_dir.resolve() not in active:
            shutil.rmtree(work_dir, ignore_errors=True)


class LessonRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_SUBTITLE_CHARACTERS)
    filename: str = Field(default="subtitles.srt", max_length=255)
    language: str = Field(default="zh", pattern=r"^zh(?:-(?:Hans|Hant))?$")


class TranslationRequest(BaseModel):
    texts: list[Annotated[str, Field(max_length=translation.MAX_TEXT_CHARACTERS)]] = Field(
        min_length=1, max_length=MAX_TRANSLATION_LINES
    )


def translate_cues(cues: list[Cue]) -> tuple[list[str] | None, dict]:
    """Translate cue text when the optional local model exists; never fail the lesson."""
    details = translation.provenance()
    if not details["available"]:
        return None, details
    try:
        return translation.translate_to_vietnamese([cue.text for cue in cues]), details
    except Exception as error:  # model output/runtime is untrusted and optional
        logger.warning("Vietnamese translation failed: %s", error)
        return None, details | {"available": False, "error": type(error).__name__}


def analyze_cues(
    cues: list[Cue], report: Callable[[str, int], None] = lambda _stage, _progress: None
) -> dict:
    report("translating", 88)
    translations, translation_details = translate_cues(cues)
    report("analyzing-vocabulary", 94)
    return build_lesson(cues, load_cedict(), load_vietnamese(), translations, translation_details)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
async def health() -> dict:
    dictionary = load_cedict()
    return {
        "status": "ok",
        "dictionary_loaded": dictionary.source is not None,
        "vietnamese_dictionary_loaded": load_vietnamese().source is not None,
        "asr_model_ready": model_ready(),
        "translation_model_ready": translation.model_ready(),
    }


@app.post("/api/lessons/mandarin")
async def create_mandarin_lesson(request: LessonRequest) -> dict:
    try:
        cues = parse_subtitles(request.content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    lesson = await asyncio.to_thread(analyze_cues, cues)
    return {
        "filename": request.filename,
        "language": request.language,
        "transcript": {"method": "uploaded-subtitle"},
        **lesson,
    }


async def save_upload(upload: UploadFile, destination: Path, limit: int) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(8 * 1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="Uploaded file is too large")
                digest.update(chunk)
                output.write(chunk)
    finally:
        await upload.close()
    return size, digest.hexdigest()


def process_video(
    source: Path,
    work_dir: Path,
    uploaded_subtitle: Path | None = None,
    report: Callable[[str, int], None] | None = None,
) -> dict:
    report = report or (lambda _stage, _progress: None)
    if uploaded_subtitle:
        report("reading-subtitle", 15)
        try:
            cues = parse_subtitles(uploaded_subtitle.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, ValueError):
            cues = []
        if cues:
            return {"transcript": {"method": "uploaded-subtitle"}, **analyze_cues(cues, report)}

    report("probing-video", 15)
    probe = probe_media(source)
    subtitle_index = preferred_subtitle_stream(probe)
    if subtitle_index is not None:
        report("reading-embedded-subtitle", 25)
        try:
            subtitle_path = extract_embedded_subtitles(
                source, subtitle_index, work_dir / "embedded.vtt"
            )
            cues = parse_subtitles(subtitle_path.read_text(encoding="utf-8-sig"))
            transcript = {"method": "embedded-subtitle", "stream_index": subtitle_index}
        except (OSError, UnicodeDecodeError, ValueError, subprocess.SubprocessError):
            cues = []
        if cues:
            return {"transcript": transcript, **analyze_cues(cues, report)}

    if not any(stream.get("codec_type") == "audio" for stream in probe.get("streams", [])):
        raise RuntimeError("Video has no readable audio or subtitle stream")
    report("extracting-audio", 30)
    audio_path = extract_asr_audio(source, work_dir / "speech.wav")
    report("transcribing-mandarin", 40)
    cues, transcript = transcribe_mandarin(
        audio_path,
        on_progress=lambda fraction: report("transcribing-mandarin", 40 + round(fraction * 45)),
    )
    return {"transcript": transcript, **analyze_cues(cues, report)}


def run_video_job(
    job_id: str,
    filename: str,
    source: Path,
    work_dir: Path,
    subtitle_path: Path | None,
) -> None:
    try:
        lesson = process_video(
            source,
            work_dir,
            subtitle_path,
            report=lambda stage, progress: jobs.update(job_id, stage, progress),
        )
        jobs.complete(job_id, {"id": job_id, "filename": filename, "language": "zh", **lesson})
    except Exception as error:
        jobs.fail(job_id, f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def start_job(job_id: str, filename: str, source: Path, work_dir: Path, subtitle: Path | None):
    task = asyncio.create_task(
        asyncio.to_thread(run_video_job, job_id, filename, source, work_dir, subtitle)
    )
    RUNNING_TASKS.add(task)
    task.add_done_callback(RUNNING_TASKS.discard)


def resume_pending_jobs() -> None:
    for item in jobs.pending():
        source = Path(item["source_path"])
        work_dir = Path(item["work_dir"])
        subtitle = Path(item["subtitle_path"]) if item["subtitle_path"] else None
        if source.is_file() and work_dir.parent.resolve() == JOBS_ROOT.resolve():
            start_job(item["id"], item["filename"], source, work_dir, subtitle)
        else:
            jobs.fail(
                item["id"],
                "Temporary source media is missing; please select the video again.",
            )


@app.post("/api/lessons/mandarin-video", status_code=202)
async def create_mandarin_video_lesson(
    video: Annotated[UploadFile, File()],
    subtitle: Annotated[UploadFile | None, File()] = None,
) -> dict:
    filename = Path(video.filename or "video").name
    suffix = Path(filename).suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported video or audio format")
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="lesson-", dir=JOBS_ROOT))
    source = work_dir / f"source{suffix}"
    try:
        size, video_digest = await save_upload(video, source, MAX_VIDEO_BYTES)
        if not size:
            raise HTTPException(status_code=422, detail="Video is empty")
        subtitle_path = None
        subtitle_digest = ""
        if subtitle:
            if Path(subtitle.filename or "").suffix.lower() not in {".srt", ".vtt"}:
                raise HTTPException(status_code=415, detail="Subtitle must be SRT or WebVTT")
            subtitle_path = work_dir / "uploaded-subtitle.vtt"
            _, subtitle_digest = await save_upload(
                subtitle, subtitle_path, MAX_SUBTITLE_CHARACTERS * 4
            )

        fingerprint_source = f"{video_digest}:{subtitle_digest}:{ANALYSIS_VERSION}"
        fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
        existing = jobs.find_completed(fingerprint)
        if existing:
            shutil.rmtree(work_dir, ignore_errors=True)
            return existing

        job = jobs.create(fingerprint, filename, work_dir, source, subtitle_path)
        start_job(job["id"], filename, source, work_dir, subtitle_path)
        return job
    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job was not found")
    return job


@app.get("/api/lessons")
async def list_lessons() -> list[dict]:
    return jobs.recent_lessons()


@app.get("/api/lessons/{lesson_id}")
async def saved_lesson(lesson_id: str) -> dict:
    job = jobs.get(lesson_id)
    if not job or job["status"] != "complete":
        raise HTTPException(status_code=404, detail="Completed lesson was not found")
    return add_vietnamese_definitions(job["result"], load_cedict(), load_vietnamese())


@app.post("/api/translate")
async def translate(request: TranslationRequest) -> dict:
    """Translate transcript lines locally, e.g. for lessons saved before translation."""
    if not translation.model_ready():
        raise HTTPException(
            status_code=503,
            detail="Mô hình dịch offline chưa được cài. Chạy pnpm setup:translation.",
        )
    translations = await asyncio.to_thread(translation.translate_to_vietnamese, request.texts)
    return {"translations": translations, **translation.provenance()}
