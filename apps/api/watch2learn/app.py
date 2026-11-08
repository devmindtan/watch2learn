"""FastAPI entry point for the first Watch2Learn vertical slice."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .dictionary import load_cedict
from .lesson import build_lesson
from .subtitles import parse_subtitles

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = PROJECT_ROOT / "apps" / "web"
MAX_SUBTITLE_CHARACTERS = 2_000_000

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
    return {"status": "ok", "dictionary_loaded": dictionary.source is not None}


@app.post("/api/lessons/mandarin")
async def create_mandarin_lesson(request: LessonRequest) -> dict:
    try:
        cues = parse_subtitles(request.content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    lesson = build_lesson(cues, load_cedict())
    return {"filename": request.filename, "language": request.language, **lesson}
