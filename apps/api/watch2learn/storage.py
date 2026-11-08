"""Persistent per-lesson media folder: data/media/<lesson-id>/video.<ext>."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from .media import media_binary
from .security import signed_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MEDIA_ROOT = PROJECT_ROOT / "data" / "media"
LESSON_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MEDIA_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mp3", ".m4a", ".wav"}


def lesson_dir(lesson_id: str) -> Path:
    if not LESSON_ID_RE.fullmatch(lesson_id):
        raise ValueError("Invalid lesson ID")
    return MEDIA_ROOT / lesson_id


def stored_media(lesson_id: str) -> Path | None:
    try:
        directory = lesson_dir(lesson_id)
    except ValueError:
        return None
    if not directory.is_dir():
        return None
    files = [
        path
        for path in directory.glob("video.*")
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
    ]
    return files[0] if files else None


def store_media(lesson_id: str, source: Path) -> Path:
    """Move a finished media file into the lesson folder, replacing any older copy."""
    suffix = source.suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        raise ValueError("Unsupported media format")
    directory = lesson_dir(lesson_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"video{suffix}"
    staging = directory / f".incoming{suffix}"
    shutil.move(str(source), staging)
    for old in [*directory.glob("video.*"), directory / "thumb.jpg"]:
        old.unlink(missing_ok=True)
    os.replace(staging, target)
    return target


def thumbnail(lesson_id: str) -> Path | None:
    """A small JPEG frame next to the saved video, created on first request."""
    media = stored_media(lesson_id)
    if not media:
        return None
    target = media.parent / "thumb.jpg"
    if target.is_file():
        return target
    for offset in ("3", "0"):
        try:
            subprocess.run(
                [
                    str(media_binary("ffmpeg")),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-ss",
                    offset,
                    "-i",
                    str(media),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=480:-2",
                    "-q:v",
                    "5",
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            continue
        if target.is_file() and target.stat().st_size:
            return target
    target.unlink(missing_ok=True)
    return None


def delete_media(lesson_id: str) -> None:
    try:
        shutil.rmtree(lesson_dir(lesson_id), ignore_errors=True)
    except ValueError:
        return


def media_info(lesson_id: str) -> dict:
    path = stored_media(lesson_id)
    if not path:
        return {"available": False}
    return {
        "available": True,
        "url": signed_url(f"/api/lessons/{lesson_id}/media"),
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
    }
