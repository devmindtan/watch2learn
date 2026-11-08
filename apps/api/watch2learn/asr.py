"""Offline Mandarin transcription using an explicitly installed Whisper model."""

import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from .subtitles import Cue

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "faster-whisper-small"
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")


def model_path() -> Path:
    return Path(os.environ.get("WATCH2LEARN_WHISPER_MODEL", DEFAULT_MODEL_PATH))


def model_ready() -> bool:
    path = model_path()
    return (path / "model.bin").is_file() and (path / "config.json").is_file()


@lru_cache(maxsize=1)
def load_model():
    if not model_ready():
        raise RuntimeError("ASR model is missing; run pnpm setup:asr once before processing video")
    from faster_whisper import WhisperModel

    return WhisperModel(
        str(model_path()),
        device="cpu",
        compute_type="int8",
        cpu_threads=max(1, min(8, os.cpu_count() or 1)),
        local_files_only=True,
    )


def transcribe_mandarin(
    audio_path: str | Path, on_progress: Callable[[float], None] | None = None
) -> tuple[list[Cue], dict]:
    segments, info = load_model().transcribe(
        str(audio_path),
        language="zh",
        # Detect language per window: foreign speech stays in its own language instead
        # of being rendered as Chinese, so it is never translated as if it were Chinese.
        multilingual=True,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )
    cues = []
    duration = max(float(getattr(info, "duration", 0)), 1.0)
    for index, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        if text and segment.end > segment.start:
            cues.append(
                Cue(
                    id=f"cue-{index}",
                    start_ms=round(segment.start * 1000),
                    end_ms=round(segment.end * 1000),
                    text=text,
                )
            )
        if on_progress:
            on_progress(min(1.0, segment.end / duration))
    if not cues:
        raise RuntimeError("No Mandarin speech was detected in this video")
    return cues, {
        "method": "faster-whisper",
        "model": model_path().name,
        "detected_language": info.language,
        "language_probability": round(info.language_probability, 4),
    }
