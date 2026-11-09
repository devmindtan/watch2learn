"""Speech worker that runs on the GPU machine (WATCH2LEARN_DEVICE=cuda).

Started by ~/watch2learn-gpu/run.sh inside the laptop's SSH tunnel and bound to
127.0.0.1 only. It serves the heavy models: Whisper ASR and VieNeu/Kokoro TTS.
Bodies are raw bytes (WAV audio or JSON); there is no authentication because the
port is reachable only through that tunnel.
"""

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import tts
from .asr import transcribe_clip, transcribe_mandarin

VERSION = "1"
MAX_AUDIO_BYTES = 600 * 1024 * 1024
WORK_DIR = Path(os.environ.get("WATCH2LEARN_WORKER_TMP", tempfile.gettempdir()))
app = FastAPI(title="Watch2Learn speech worker", version=VERSION)


def device_name() -> str:
    if os.environ.get("WATCH2LEARN_DEVICE") != "cuda":
        return "cpu"
    try:
        import torch

        return torch.cuda.get_device_name(0)
    except Exception:  # torch missing or no CUDA device
        return "cuda"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": VERSION, "device": device_name(), "tts": tts.voices_ready()}


class Part(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    lang: str = Field(pattern="^(zh|vi)$")
    rate: float = Field(default=1.0, ge=0.5, le=1.5)


class SpeechRequest(BaseModel):
    parts: list[Part] = Field(min_length=1, max_length=tts.MAX_PARTS)
    voices: dict[str, str] = Field(default_factory=dict)


@app.post("/tts")
async def speak(request: SpeechRequest) -> FileResponse:
    parts = [part.model_dump() for part in request.parts]
    path = await asyncio.to_thread(tts.synthesize, parts, request.voices)
    return FileResponse(path, media_type="audio/mp4")


@app.get("/voices")
async def voices() -> dict:
    return await asyncio.to_thread(tts.available_voices)


async def saved_body(request: Request) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(suffix=".wav", dir=WORK_DIR)
    size = 0
    with os.fdopen(handle, "wb") as output:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                output.close()
                Path(name).unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Audio is too large")
            output.write(chunk)
    return Path(name)


@app.post("/transcribe")
async def transcribe(request: Request) -> dict:
    path = await saved_body(request)
    try:
        cues, transcript = await asyncio.to_thread(transcribe_mandarin, path)
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        path.unlink(missing_ok=True)
    return {
        "cues": [
            {"id": cue.id, "start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text}
            for cue in cues
        ],
        "transcript": transcript | {"device": device_name()},
    }


@app.post("/transcribe-clip")
async def transcribe_short(request: Request) -> dict:
    path = await saved_body(request)
    try:
        return {"text": await asyncio.to_thread(transcribe_clip, path)}
    finally:
        path.unlink(missing_ok=True)
