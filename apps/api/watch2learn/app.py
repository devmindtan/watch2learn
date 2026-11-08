"""FastAPI entry point for local video-to-vocabulary lessons."""

import asyncio
import hashlib
import logging
import mimetypes
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (
    explain,
    jobs,
    learning,
    pronunciation,
    security,
    storage,
    translation,
    tts,
    youtube,
)
from .asr import model_ready, transcribe_clip, transcribe_mandarin
from .dictionary import load_cedict, load_vietnamese
from .lesson import (
    ANALYSIS_VERSION,
    add_vietnamese_definitions,
    build_lesson,
    simplified_cues,
)
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
MEDIA_SUFFIXES = storage.MEDIA_SUFFIXES
JOBS_ROOT = PROJECT_ROOT / "data" / "jobs"
YOUTUBE_SOURCE_PREFIX = "youtube:"
YOUTUBE_ASR_SOURCE_PREFIX = "youtube-asr:"
RUNNING_TASKS: set[asyncio.Task] = set()
DOWNLOADS: dict[str, dict] = {}
DOWNLOADS_LOCK = Lock()
TRANSLATION_UPGRADE_LOCK = Lock()
logger = logging.getLogger(__name__)
Report = Callable[[str, int], None]


def no_report(_stage: str, _progress: int) -> None:
    return None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    resume_pending_jobs()
    cleanup_abandoned_job_files()
    task = asyncio.create_task(asyncio.to_thread(upgrade_saved_lessons))
    RUNNING_TASKS.add(task)
    task.add_done_callback(RUNNING_TASKS.discard)
    yield


app = FastAPI(title="Watch2Learn", version="0.4.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="assets")


@app.middleware("http")
async def require_access_token(request: Request, call_next):
    if not security.request_allowed(
        request.method, request.url.path, request.headers, request.query_params
    ):
        return JSONResponse(
            {"detail": "Cần mã truy cập hợp lệ để dùng máy chủ này."}, status_code=401
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=security.allowed_origins(),
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_private_network=True,  # a public HTTPS page may call this machine
    max_age=600,
)


def cleanup_abandoned_job_files() -> None:
    if not JOBS_ROOT.is_dir():
        return
    active = {Path(item["work_dir"]).resolve() for item in jobs.pending()}
    for work_dir in [*JOBS_ROOT.glob("lesson-*"), *JOBS_ROOT.glob("download-*")]:
        if work_dir.is_dir() and work_dir.resolve() not in active:
            shutil.rmtree(work_dir, ignore_errors=True)


class LessonRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_SUBTITLE_CHARACTERS)
    filename: str = Field(default="subtitles.srt", max_length=255)
    language: str = Field(default="zh", pattern=r"^zh(?:-(?:Hans|Hant))?$")


class YoutubeLessonRequest(BaseModel):
    url: str = Field(min_length=11, max_length=500)
    confirm_rights: bool = False
    transcript: Literal["subtitles", "asr"] = "subtitles"


def translate_cues(cues: list[Cue]) -> tuple[list[dict] | None, dict]:
    """Translate whole sentences when the optional local model exists; never fail a lesson."""
    details = translation.provenance() | {"unit": translation.TRANSLATION_UNIT}
    if not details["available"]:
        return None, details
    try:
        return translation.translate_cues_in_context(cues), details
    except Exception as error:  # model runtime/output is untrusted and optional
        logger.warning("Vietnamese translation failed: %s", error)
        return None, details | {"available": False, "error": type(error).__name__}


def analyze_cues(cues: list[Cue], report: Report = no_report) -> dict:
    report("translating", 88)
    translations, translation_details = translate_cues(simplified_cues(cues))
    report("analyzing-vocabulary", 94)
    return build_lesson(cues, load_cedict(), load_vietnamese(), translations, translation_details)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
async def health(request: Request) -> dict:
    token = security.access_token()
    authorized = not token or security.bearer_matches(token, request.headers.get("authorization"))
    if not authorized:
        return {"status": "ok", "auth_required": True, "authorized": False}
    dictionary = load_cedict()
    return {
        "status": "ok",
        "auth_required": bool(token),
        "authorized": True,
        "dictionary_loaded": dictionary.source is not None,
        "vietnamese_dictionary_loaded": load_vietnamese().source is not None,
        "asr_model_ready": model_ready(),
        "translation_model_ready": translation.model_ready(),
        "translation_unit": translation.TRANSLATION_UNIT,
        "explain_model_ready": await asyncio.to_thread(explain.model_ready),
        "explain_model": explain.model_name(),
        "tts_ready": tts.voices_ready(),
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


def transcribe_media(source: Path, work_dir: Path, report: Report) -> dict:
    report("extracting-audio", 30)
    speech = work_dir / "speech.wav"
    speech.unlink(missing_ok=True)  # a resumed job may have left a partial file
    audio_path = extract_asr_audio(source, speech)
    report("transcribing-mandarin", 40)
    cues, transcript = transcribe_mandarin(
        audio_path,
        on_progress=lambda fraction: report("transcribing-mandarin", 40 + round(fraction * 45)),
    )
    return {"transcript": transcript, **analyze_cues(cues, report)}


def process_video(
    source: Path,
    work_dir: Path,
    uploaded_subtitle: Path | None = None,
    report: Report | None = None,
) -> dict:
    report = report or no_report
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
            embedded = work_dir / "embedded.vtt"
            embedded.unlink(missing_ok=True)
            subtitle_path = extract_embedded_subtitles(source, subtitle_index, embedded)
            cues = parse_subtitles(subtitle_path.read_text(encoding="utf-8-sig"))
            transcript = {"method": "embedded-subtitle", "stream_index": subtitle_index}
        except (OSError, UnicodeDecodeError, ValueError, subprocess.SubprocessError):
            cues = []
        if cues:
            return {"transcript": transcript, **analyze_cues(cues, report)}

    if not any(stream.get("codec_type") == "audio" for stream in probe.get("streams", [])):
        raise RuntimeError("Video has no readable audio or subtitle stream")
    return transcribe_media(source, work_dir, report)


def process_youtube(
    video_id: str, work_dir: Path, report: Report | None = None, use_subtitles: bool = True
) -> dict:
    """Prefer uploader-provided Chinese subtitles unless asked to transcribe locally."""
    report = report or no_report
    report("fetching-youtube", 8)
    metadata = youtube.fetch_metadata(video_id)
    source = {
        "kind": "youtube",
        "video_id": video_id,
        "url": youtube.canonical_url(video_id),
        "title": metadata["title"],
        "channel": metadata["channel"],
    }
    common = {"filename": metadata["title"], "source": source}
    language = youtube.choose_subtitle(metadata["subtitles"]) if use_subtitles else None
    if language:
        report("reading-youtube-subtitle", 20)
        try:
            subtitle = youtube.download_subtitle(video_id, language, work_dir)
            cues = parse_subtitles(subtitle.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, ValueError, RuntimeError) as error:
            logger.warning("YouTube subtitle %s unusable: %s", language, error)
            cues = []
        if cues:
            transcript = {"method": "youtube-subtitle", "language": language}
            return {**common, "transcript": transcript, **analyze_cues(cues, report)}

    report("downloading-audio", 15)
    audio = youtube.download(
        video_id,
        work_dir / "youtube-audio",
        audio_only=True,
        on_progress=lambda fraction: report("downloading-audio", 15 + round(fraction * 13)),
    )
    return {**common, **transcribe_media(audio, work_dir, report)}


def run_video_job(
    job_id: str,
    filename: str,
    source: Path | str,
    work_dir: Path,
    subtitle_path: Path | None,
) -> None:
    def report(stage: str, progress: int) -> None:
        jobs.update(job_id, stage, progress)

    try:
        source_text = str(source)
        if source_text.startswith(YOUTUBE_ASR_SOURCE_PREFIX):
            video_id = source_text.removeprefix(YOUTUBE_ASR_SOURCE_PREFIX)
            lesson = process_youtube(video_id, work_dir, report, use_subtitles=False)
        elif source_text.startswith(YOUTUBE_SOURCE_PREFIX):
            video_id = source_text.removeprefix(YOUTUBE_SOURCE_PREFIX)
            lesson = process_youtube(video_id, work_dir, report)
        else:
            lesson = process_video(Path(source), work_dir, subtitle_path, report)
            lesson["source"] = {"kind": "file", "filename": filename}
            report("saving-video", 98)
            storage.store_media(job_id, Path(source))
        jobs.complete(job_id, {"filename": filename, **lesson, "id": job_id, "language": "zh"})
    except Exception as error:
        jobs.fail(job_id, f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def start_job(
    job_id: str, filename: str, source: Path | str, work_dir: Path, subtitle: Path | None
) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(run_video_job, job_id, filename, source, work_dir, subtitle)
    )
    RUNNING_TASKS.add(task)
    task.add_done_callback(RUNNING_TASKS.discard)


def resume_pending_jobs() -> None:
    for item in jobs.pending():
        source_text = item["source_path"] or ""
        work_dir = Path(item["work_dir"])
        subtitle = Path(item["subtitle_path"]) if item["subtitle_path"] else None
        inside_jobs = work_dir.parent.resolve() == JOBS_ROOT.resolve()
        is_youtube = source_text.startswith((YOUTUBE_SOURCE_PREFIX, YOUTUBE_ASR_SOURCE_PREFIX))
        if is_youtube and inside_jobs:
            work_dir.mkdir(parents=True, exist_ok=True)
            start_job(item["id"], item["filename"], source_text, work_dir, None)
        elif Path(source_text).is_file() and inside_jobs:
            start_job(item["id"], item["filename"], Path(source_text), work_dir, subtitle)
        else:
            jobs.fail(
                item["id"],
                "Temporary source media is missing; please select the video again.",
            )


def fingerprint_for(*parts: str) -> str:
    return hashlib.sha256(":".join([*parts, ANALYSIS_VERSION]).encode()).hexdigest()


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

        fingerprint = fingerprint_for(video_digest, subtitle_digest)
        existing = jobs.find_completed(fingerprint)
        if existing:
            if not storage.stored_media(existing["id"]):
                storage.store_media(existing["id"], source)  # older lessons kept no video
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


@app.post("/api/lessons/youtube", status_code=202)
async def create_youtube_lesson(request: YoutubeLessonRequest) -> dict:
    if not request.confirm_rights:
        raise HTTPException(
            status_code=422,
            detail="Hãy xác nhận bạn có quyền sử dụng video này trước khi phân tích.",
        )
    try:
        video_id = youtube.parse_video_id(request.url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    prefix = YOUTUBE_ASR_SOURCE_PREFIX if request.transcript == "asr" else YOUTUBE_SOURCE_PREFIX
    source = prefix + video_id
    fingerprint = fingerprint_for(source)
    existing = jobs.find_completed(fingerprint)
    if existing:
        return existing
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="lesson-", dir=JOBS_ROOT))
    filename = f"YouTube {video_id}"
    job = jobs.create(fingerprint, filename, work_dir, source, None)
    start_job(job["id"], filename, source, work_dir, None)
    return job


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job was not found")
    return job


def thumbnail_url(item: dict, has_media: bool) -> str | None:
    if has_media:
        return security.signed_url(f"/api/lessons/{item['id']}/thumbnail")
    if item.get("youtube_id"):
        return f"https://i.ytimg.com/vi/{item['youtube_id']}/mqdefault.jpg"
    return None


@app.get("/api/lessons")
async def list_lessons() -> list[dict]:
    learned = {
        word_id
        for word_id, entry in learning.learner_state()["words"].items()
        if entry["status"] == "learned"
    }
    lessons = []
    for item in jobs.recent_lessons():
        word_ids = set(item.pop("vocabulary_ids"))
        has_media = storage.stored_media(item["id"]) is not None
        lessons.append(
            item
            | {
                "has_media": has_media,
                "thumbnail_url": thumbnail_url(item, has_media),
                "learned_count": len(word_ids & learned),
            }
        )
    return lessons


@app.get("/api/lessons/{lesson_id}/thumbnail")
async def lesson_thumbnail(lesson_id: str) -> FileResponse:
    path = await asyncio.to_thread(storage.thumbnail, lesson_id)
    if not path:
        raise HTTPException(status_code=404, detail="No thumbnail for this lesson")
    headers = {"Cache-Control": "private, max-age=86400"}
    return FileResponse(path, media_type="image/jpeg", headers=headers)


def completed_lesson(lesson_id: str) -> dict:
    job = jobs.get(lesson_id)
    if not job or job["status"] != "complete":
        raise HTTPException(status_code=404, detail="Completed lesson was not found")
    return job["result"]


@app.get("/api/lessons/{lesson_id}")
async def saved_lesson(lesson_id: str) -> dict:
    completed_lesson(lesson_id)
    current = await asyncio.to_thread(ensure_current_analysis, lesson_id)
    lesson = add_vietnamese_definitions(current, load_cedict(), load_vietnamese())
    lesson.setdefault("source", {"kind": "file", "filename": lesson.get("filename")})
    return lesson | {"id": lesson_id, "media": storage.media_info(lesson_id)}


@app.delete("/api/lessons/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: str) -> None:
    if lesson_id in DOWNLOADS and DOWNLOADS[lesson_id]["status"] == "running":
        raise HTTPException(status_code=409, detail="Video is still downloading")
    if not jobs.delete(lesson_id):
        raise HTTPException(status_code=404, detail="Lesson was not found")
    storage.delete_media(lesson_id)


@app.get("/api/lessons/{lesson_id}/media")
async def lesson_media(lesson_id: str) -> FileResponse:
    path = storage.stored_media(lesson_id)
    if not path:
        raise HTTPException(status_code=404, detail="No saved video for this lesson")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"},
    )


@app.put("/api/lessons/{lesson_id}/media")
async def replace_lesson_media(lesson_id: str, video: Annotated[UploadFile, File()]) -> dict:
    """Attach the original video to a lesson saved before videos were kept."""
    completed_lesson(lesson_id)
    suffix = Path(video.filename or "").suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported video or audio format")
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="download-", dir=JOBS_ROOT))
    try:
        upload = work_dir / f"upload{suffix}"
        size, _ = await save_upload(video, upload, MAX_VIDEO_BYTES)
        if not size:
            raise HTTPException(status_code=422, detail="Video is empty")
        storage.store_media(lesson_id, upload)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return storage.media_info(lesson_id)


def run_youtube_download(lesson_id: str, video_id: str) -> None:
    work_dir = JOBS_ROOT / f"download-{lesson_id}"
    state = DOWNLOADS[lesson_id]
    try:

        def progress(fraction: float) -> None:
            state["progress"] = round(fraction * 100)

        path = youtube.download(
            video_id, work_dir / "video", audio_only=False, on_progress=progress
        )
        storage.store_media(lesson_id, path)
        state.update(status="complete", progress=100)
    except Exception as error:
        state.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def download_status(lesson_id: str) -> dict:
    if storage.stored_media(lesson_id):
        return {"status": "complete", "progress": 100, "media": storage.media_info(lesson_id)}
    return DOWNLOADS.get(lesson_id, {"status": "idle", "progress": 0})


@app.post("/api/lessons/{lesson_id}/download", status_code=202)
async def download_lesson_video(lesson_id: str) -> dict:
    """Save a YouTube lesson's video (≤720p MP4) into the lesson's media folder."""
    source = completed_lesson(lesson_id).get("source", {})
    if source.get("kind") != "youtube":
        raise HTTPException(status_code=422, detail="Only YouTube lessons can be downloaded")
    with DOWNLOADS_LOCK:
        current = download_status(lesson_id)
        if current["status"] in {"running", "complete"}:
            return current
        DOWNLOADS[lesson_id] = {"status": "running", "progress": 0}
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(
        asyncio.to_thread(run_youtube_download, lesson_id, source["video_id"])
    )
    RUNNING_TASKS.add(task)
    task.add_done_callback(RUNNING_TASKS.discard)
    return DOWNLOADS[lesson_id]


@app.get("/api/lessons/{lesson_id}/download")
async def lesson_download_status(lesson_id: str) -> dict:
    completed_lesson(lesson_id)
    return download_status(lesson_id)


def translation_is_current(lesson: dict) -> bool:
    current = lesson.get("translation") or {}
    complete = all(cue.get("translation_vi") is not None for cue in lesson.get("cues", []))
    return current.get("unit") == translation.TRANSLATION_UNIT and complete


def ensure_current_translation(lesson_id: str) -> dict | None:
    """Translate a saved lesson once under the current rules and persist it."""
    with TRANSLATION_UPGRADE_LOCK:  # one upgrade at a time; re-read after waiting
        job = jobs.get(lesson_id)
        if not job or job["status"] != "complete":
            return None
        lesson = job["result"]
        if translation_is_current(lesson):
            return lesson
        cues = [
            Cue(cue["id"], cue["start_ms"], cue["end_ms"], cue["text"]) for cue in lesson["cues"]
        ]
        rows, details = translate_cues(cues)
        if rows is None:
            raise RuntimeError("Không thể dịch bài học này")
        for cue, row in zip(lesson["cues"], rows, strict=True):
            cue.update(row)
        lesson["translation"] = details
        jobs.save_result(lesson_id, lesson)
        return lesson


TRANSLATION_FIELDS = ("translation_vi", "translation_skipped", "translation_group")
TRANSLATION_FIELDS += ("translation_group_end",)


def ensure_current_analysis(lesson_id: str) -> dict | None:
    """Re-run segmentation/readings/meanings on a lesson saved by an older analyser.

    Original cue text, timing and stored translations are kept; vocabulary IDs are
    content hashes, so learner known-word state still matches.
    """
    with TRANSLATION_UPGRADE_LOCK:
        job = jobs.get(lesson_id)
        if not job or job["status"] != "complete":
            return None
        lesson = job["result"]
        if lesson.get("analysis", {}).get("version") == ANALYSIS_VERSION:
            return lesson
        stored = lesson["cues"]
        cues = [
            Cue(cue["id"], cue["start_ms"], cue["end_ms"], cue.get("text_original") or cue["text"])
            for cue in stored
        ]
        rows = [{key: cue.get(key) for key in TRANSLATION_FIELDS} for cue in stored]
        rebuilt = build_lesson(
            cues, load_cedict(), load_vietnamese(), rows, lesson.get("translation")
        )
        lesson.update(rebuilt)
        jobs.save_result(lesson_id, lesson)
        return lesson


def upgrade_saved_lessons() -> None:
    """At startup, bring every saved lesson to the current analysis and translation
    rules in the background so opening a lesson never waits for it."""
    for lesson_id in jobs.completed_ids():
        try:
            ensure_current_analysis(lesson_id)
            if translation.model_ready():
                ensure_current_translation(lesson_id)
        except Exception as error:  # keep upgrading the remaining lessons
            logger.warning("Could not upgrade translation of %s: %s", lesson_id, error)


@app.post("/api/lessons/{lesson_id}/translations")
async def translate_saved_lesson(lesson_id: str) -> dict:
    """Re-translate an older lesson under the current rules and persist the result."""
    completed_lesson(lesson_id)
    if not translation.model_ready():
        raise HTTPException(
            status_code=503,
            detail="Mô hình dịch offline chưa được cài. Chạy pnpm setup:translation.",
        )
    try:
        lesson = await asyncio.to_thread(ensure_current_translation, lesson_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if lesson is None:
        raise HTTPException(status_code=404, detail="Completed lesson was not found")
    return {
        "translation": lesson["translation"],
        "cues": [
            {
                key: cue.get(key)
                for key in (
                    "id",
                    "translation_vi",
                    "translation_skipped",
                    "translation_group",
                    "translation_group_end",
                )
            }
            for cue in lesson["cues"]
        ],
    }


WORD_ID_PATTERN = r"^word-[0-9a-f]{12}$"
Status = Literal["saved", "learned"]


class WordUpdate(BaseModel):
    status: Status | None = None
    own_meaning: str | None = Field(default=None, max_length=500)
    lesson_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    cue_id: str | None = Field(default=None, max_length=64)


class SentenceUpdate(BaseModel):
    status: Status | None = None


class LibraryImport(BaseModel):
    learned: list[Annotated[str, Field(pattern=WORD_ID_PATTERN)]] = Field(
        default_factory=list, max_length=20000
    )
    meanings: dict[str, Annotated[str, Field(max_length=500)]] = Field(default_factory=dict)


def check_word_id(word_id: str) -> None:
    if not re.fullmatch(WORD_ID_PATTERN, word_id):
        raise HTTPException(status_code=422, detail="Invalid word ID")


def find_cue(lesson: dict, cue_id: str) -> dict:
    cue = next((item for item in lesson.get("cues", []) if item["id"] == cue_id), None)
    if not cue:
        raise HTTPException(status_code=404, detail="Sentence was not found in this lesson")
    return cue


def with_lesson_links(rows: list[dict]) -> list[dict]:
    existing = set(jobs.completed_ids())
    return [row | {"lesson_exists": row.get("lesson_id") in existing} for row in rows]


@app.get("/api/library/state")
async def library_state() -> dict:
    return learning.learner_state()


@app.get("/api/library/words")
async def library_words(status: Status | None = None) -> list[dict]:
    return with_lesson_links(learning.list_words(status))


@app.put("/api/library/words/{word_id}")
async def update_library_word(word_id: str, update: WordUpdate) -> dict:
    check_word_id(word_id)
    fields = None
    if update.lesson_id:
        fields = learning.word_fields(completed_lesson(update.lesson_id), word_id, update.cue_id)
        if not fields:
            raise HTTPException(status_code=404, detail="Word was not found in this lesson")
    saved = learning.save_word(word_id, update.status, update.own_meaning, update.lesson_id, fields)
    if not saved:
        raise HTTPException(status_code=422, detail="lesson_id is required to save a new word")
    return saved


@app.delete("/api/library/words/{word_id}", status_code=204)
async def delete_library_word(word_id: str) -> None:
    check_word_id(word_id)
    if not learning.delete_word(word_id):
        raise HTTPException(status_code=404, detail="Word is not in the library")


@app.get("/api/library/sentences")
async def library_sentences(status: Status | None = None) -> list[dict]:
    return with_lesson_links(learning.list_sentences(status))


@app.put("/api/library/sentences/{lesson_id}/{cue_id}")
async def update_library_sentence(lesson_id: str, cue_id: str, update: SentenceUpdate) -> dict:
    cue = find_cue(completed_lesson(lesson_id), cue_id)
    return learning.save_sentence(lesson_id, cue, update.status)


@app.delete("/api/library/sentences/{lesson_id}/{cue_id}", status_code=204)
async def delete_library_sentence(lesson_id: str, cue_id: str) -> None:
    if not learning.delete_sentence(learning.sentence_id(lesson_id, cue_id)):
        raise HTTPException(status_code=404, detail="Sentence is not in the library")


@app.post("/api/library/import")
async def import_library(payload: LibraryImport) -> dict:
    """One-time move of words marked in a browser's local storage to the backend."""
    meaning_ids = {key for key in payload.meanings if re.fullmatch(WORD_ID_PATTERN, key)}
    wanted = set(payload.learned) | meaning_ids
    imported = 0
    for lesson_id in jobs.completed_ids():
        if not wanted:
            break
        lesson = jobs.get(lesson_id)["result"]
        for word in lesson.get("vocabulary", []):
            if word["id"] not in wanted:
                continue
            fields = learning.word_fields(lesson, word["id"], None)
            status = "learned" if word["id"] in payload.learned else "saved"
            learning.save_word(
                word["id"], status, payload.meanings.get(word["id"]), lesson_id, fields
            )
            wanted.discard(word["id"])
            imported += 1
    return {"imported": imported, "not_found": len(wanted)}


MAX_RECORDING_BYTES = 4 * 1024 * 1024
RECORDING_SUFFIXES = {".webm", ".ogg", ".m4a", ".mp4", ".wav", ".mp3"}


def check_pronunciation(recording: Path, work_dir: Path, target: str) -> dict:
    speech = extract_asr_audio(recording, work_dir / "speech.wav")
    probe = probe_media(speech)
    duration = float(probe.get("format", {}).get("duration") or 0)
    if duration < 0.3:
        raise ValueError("Bản ghi quá ngắn — hãy giữ nút ghi âm lâu hơn một chút.")
    if duration > 30:
        raise ValueError("Bản ghi dài quá 30 giây.")
    return pronunciation.score_pronunciation(target, transcribe_clip(speech))


@app.post("/api/pronunciation")
async def score_recording(
    audio: Annotated[UploadFile, File()],
    target: Annotated[str, Form(min_length=1, max_length=200)],
    kind: Annotated[Literal["word", "sentence"] | None, Form()] = None,
    item_id: Annotated[str | None, Form(max_length=120)] = None,
) -> dict:
    """Record yourself saying a word/sentence; get an estimated % and per-syllable feedback."""
    if not pronunciation.han_syllables(target):
        raise HTTPException(status_code=422, detail="Câu mẫu không có chữ Hán")
    suffix = Path(audio.filename or "recording.webm").suffix.lower() or ".webm"
    if suffix not in RECORDING_SUFFIXES:
        suffix = ".webm"
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="speech-", dir=JOBS_ROOT))
    try:
        recording = work_dir / f"recording{suffix}"
        size, _ = await save_upload(audio, recording, MAX_RECORDING_BYTES)
        if not size:
            raise HTTPException(status_code=422, detail="Không nhận được âm thanh")
        try:
            result = await asyncio.to_thread(check_pronunciation, recording, work_dir, target)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            raise HTTPException(status_code=422, detail="Không đọc được bản ghi âm") from error
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    if kind and item_id:
        learning.record_score(kind, item_id, result["score"])
    return result


class ExplainRequest(BaseModel):
    lesson_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    word_id: str | None = Field(default=None, pattern=WORD_ID_PATTERN)
    cue_id: str | None = Field(default=None, max_length=64)


def sentence_words(lesson: dict, cue: dict) -> list[dict]:
    """Dictionary meaning of each word in the cue, in sentence order."""
    words = {item["id"]: item for item in lesson.get("vocabulary", [])}
    glossary = []
    for segment in cue.get("segments", []):
        word = words.get(segment.get("vocabulary_id"))
        if not word:
            continue
        meanings = [item for item in word.get("definitions_vi", []) if ":" not in item[:3]]
        glossary.append(
            {
                "word": segment["text"],
                "pinyin": segment.get("pinyin"),
                "meaning": meanings[0] if meanings else None,
            }
        )
    return glossary


@app.post("/api/explain")
async def explain_word(request: ExplainRequest) -> dict:
    """AI (local Ollama) explanation of a word in context, or of a whole sentence."""
    lesson = completed_lesson(request.lesson_id)
    if not request.word_id:
        if not request.cue_id:
            raise HTTPException(status_code=422, detail="word_id or cue_id is required")
        cue = find_cue(lesson, request.cue_id)
        try:
            return await asyncio.to_thread(
                explain.explain_sentence,
                cue["text"],
                cue.get("translation_vi"),
                sentence_words(lesson, cue),
            ) | {"words": sentence_words(lesson, cue)}
        except (OSError, KeyError, ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=503,
                detail=f"Chưa dùng được AI local ({explain.model_name()} qua Ollama): {error}",
            ) from error
    word = next((item for item in lesson["vocabulary"] if item["id"] == request.word_id), None)
    if not word:
        raise HTTPException(status_code=404, detail="Word was not found in this lesson")
    fields = learning.word_fields(lesson, request.word_id, request.cue_id)
    try:
        return await asyncio.to_thread(
            explain.explain_word, word, fields["sentence"] or "", fields["sentence_translation"]
        )
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Chưa dùng được AI local ({explain.model_name()} qua Ollama): {error}",
        ) from error


class SpeechPart(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    lang: Literal["zh", "vi"]
    rate: float = Field(default=1.0, ge=0.5, le=1.5)


class SpeechRequest(BaseModel):
    parts: list[SpeechPart] = Field(min_length=1, max_length=tts.MAX_PARTS)


@app.post("/api/tts")
async def read_aloud(request: SpeechRequest) -> FileResponse:
    """Read Chinese/Vietnamese parts aloud with local Piper voices (cached AAC audio)."""
    if not tts.voices_ready():
        raise HTTPException(
            status_code=503, detail="Chưa cài giọng đọc trên máy chủ. Chạy pnpm setup:voices."
        )
    parts = [part.model_dump() for part in request.parts]
    if sum(len(part["text"]) for part in parts) > tts.MAX_CHARACTERS:
        raise HTTPException(status_code=413, detail="Đoạn cần đọc quá dài")
    try:
        path = await asyncio.to_thread(tts.synthesize, parts)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise HTTPException(status_code=503, detail="Không tạo được giọng đọc") from error
    headers = {"Cache-Control": "private, max-age=86400"}
    return FileResponse(path, media_type="audio/mp4", headers=headers)
