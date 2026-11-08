"""Portable, read-only-by-default FFmpeg adapter for future local ASR."""

import json
import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def media_binary(name: str) -> Path:
    configured = os.environ.get(f"WATCH2LEARN_{name.upper()}")
    candidates = [Path(configured)] if configured else []
    candidates.append(PROJECT_ROOT / ".tools" / "bin" / name)
    system = shutil.which(name)
    if system:
        candidates.append(Path(system))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(f"{name} was not found; run bash scripts/bootstrap-media-tools.sh")


def probe_media(path: str | Path) -> dict:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    result = subprocess.run(
        [
            str(media_binary("ffprobe")),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def extract_asr_audio(source: str | Path, output: str | Path) -> Path:
    source_path = Path(source)
    output_path = Path(output)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(media_binary("ffmpeg")),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


def preferred_subtitle_stream(probe: dict) -> int | None:
    streams = [
        stream for stream in probe.get("streams", []) if stream.get("codec_type") == "subtitle"
    ]
    if not streams:
        return None
    for stream in streams:
        language = str(stream.get("tags", {}).get("language", "")).lower()
        if language.startswith(("zh", "chi", "zho")):
            return int(stream["index"])
    for stream in streams:
        language = str(stream.get("tags", {}).get("language", "")).lower()
        if language in {"", "und"}:
            return int(stream["index"])
    return None


def extract_embedded_subtitles(source: str | Path, stream_index: int, output: str | Path) -> Path:
    source_path = Path(source)
    output_path = Path(output)
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(media_binary("ffmpeg")),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-n",
            "-i",
            str(source_path),
            "-map",
            f"0:{stream_index}",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path
