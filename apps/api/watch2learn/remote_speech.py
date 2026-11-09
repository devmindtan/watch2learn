"""Client for the speech worker on the GPU machine (TTS and ASR).

Every call returns None when the GPU machine is not usable or the call fails, so
callers fall back to running the same model on this laptop.
"""

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from . import prepare
from .gpu_host import GPU
from .subtitles import Cue

TIMEOUT_SECONDS = 3600
logger = logging.getLogger(__name__)


def call(path: str, body: bytes, content_type: str, timeout: float = TIMEOUT_SECONDS):
    prepare.note_speech()  # lesson preparation yields the shared card meanwhile
    base = GPU.endpoint("speech")
    if not base:
        return None
    request = urllib.request.Request(
        base + path, data=body, headers={"Content-Type": content_type}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return payload, response.headers.get("Content-Type", "")
    except (OSError, urllib.error.URLError) as error:
        logger.warning("GPU speech worker call %s failed, using the laptop: %s", path, error)
        return None


def synthesize(parts: list[dict], voices: dict) -> bytes | None:
    body = json.dumps({"parts": parts, "voices": voices}, ensure_ascii=False).encode()
    result = call("/tts", body, "application/json", timeout=600)
    return result[0] if result else None


def transcribe(audio_path: Path) -> tuple[list[Cue], dict] | None:
    result = call("/transcribe", audio_path.read_bytes(), "audio/wav")
    if not result:
        return None
    data = json.loads(result[0])
    cues = [
        Cue(item["id"], item["start_ms"], item["end_ms"], item["text"]) for item in data["cues"]
    ]
    return cues, data["transcript"] | {"machine": "gpu"}


def voices() -> dict | None:
    base = GPU.endpoint("speech")
    if not base:
        return None
    try:
        with urllib.request.urlopen(base + "/voices", timeout=120) as response:
            return json.load(response)
    except (OSError, ValueError) as error:
        logger.warning("GPU speech worker voices failed: %s", error)
        return None


def transcribe_clip(audio_path: Path) -> str | None:
    result = call("/transcribe-clip", audio_path.read_bytes(), "audio/wav", timeout=120)
    return json.loads(result[0])["text"] if result else None
