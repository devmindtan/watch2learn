"""YouTube source adapter built on yt-dlp, for videos the learner may use.

Only a validated 11-character video ID crosses this boundary; user-supplied URLs are
never handed to yt-dlp. Commands are argument arrays with yt-dlp config files ignored.
"""

import contextlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .media import media_binary

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
PATH_PREFIXES = ("shorts", "embed", "live", "v")
MAX_DURATION_SECONDS = 3 * 60 * 60
CHINESE_SUBTITLE_PREFERENCE = ("zh-Hans", "zh-CN", "zh", "zh-SG", "zh-Hant", "zh-TW", "zh-HK")
PROGRESS_RE = re.compile(r"^W2L\s+([\d.]+)%")
METADATA_TIMEOUT = 120
DOWNLOAD_TIMEOUT = 4 * 60 * 60


def parse_video_id(url: str) -> str:
    """Return the video ID from a YouTube watch/short/embed URL or raise ValueError."""
    candidate = url.strip()
    if VIDEO_ID_RE.fullmatch(candidate):
        return candidate
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.hostname or "").lower()
    video_id = ""
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Chỉ hỗ trợ link YouTube dạng http(s)")
    if host in SHORT_HOSTS:
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        parts = [part for part in parsed.path.split("/") if part]
        if parts[:1] == ["watch"]:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) >= 2 and parts[0] in PATH_PREFIXES:
            video_id = parts[1]
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("Link YouTube không hợp lệ")
    return video_id


def canonical_url(video_id: str) -> str:
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("Invalid YouTube video ID")
    return f"https://www.youtube.com/watch?v={video_id}"


def base_command() -> list[str]:
    command = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--no-color"]
    for runtime in ("deno", "node"):
        if shutil.which(runtime):
            command += ["--js-runtimes", runtime]
            break
    with contextlib.suppress(RuntimeError):
        command += ["--ffmpeg-location", str(media_binary("ffmpeg").parent)]
    return command


def run(arguments: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            base_command() + arguments, check=True, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.CalledProcessError as error:
        message = (error.stderr or "").strip().splitlines()
        raise RuntimeError(message[-1] if message else "yt-dlp failed") from error


def fetch_metadata(video_id: str) -> dict:
    result = run(["-J", "--skip-download", canonical_url(video_id)], METADATA_TIMEOUT)
    data = json.loads(result.stdout)
    if data.get("is_live") or data.get("live_status") in {"is_live", "is_upcoming"}:
        raise RuntimeError("Không hỗ trợ video đang phát trực tiếp")
    duration = data.get("duration") or 0
    if duration > MAX_DURATION_SECONDS:
        raise RuntimeError("Video dài hơn 3 giờ; hãy chọn video ngắn hơn")
    return {
        "video_id": video_id,
        "title": str(data.get("title") or f"YouTube {video_id}")[:200],
        "channel": str(data.get("channel") or data.get("uploader") or "")[:200],
        "duration": duration,
        "subtitles": sorted(data.get("subtitles") or {}),
    }


def choose_subtitle(languages: list[str]) -> str | None:
    """Prefer uploader-provided Chinese subtitles; auto-captions are ignored on purpose."""
    for preferred in CHINESE_SUBTITLE_PREFERENCE:
        if preferred in languages:
            return preferred
    return next((language for language in languages if language.startswith("zh")), None)


def download_subtitle(video_id: str, language: str, work_dir: Path) -> Path:
    run(
        [
            "--skip-download",
            "--write-subs",
            "--sub-langs",
            language,
            "--sub-format",
            "vtt/srt/best",
            "--convert-subs",
            "vtt",
            "-o",
            str(work_dir / "youtube-subtitle.%(ext)s"),
            canonical_url(video_id),
        ],
        METADATA_TIMEOUT,
    )
    found = sorted(work_dir.glob("youtube-subtitle*.vtt"))
    if not found:
        raise RuntimeError("Không tải được phụ đề tiếng Trung")
    return found[0]


def download(
    video_id: str,
    output_stem: Path,
    audio_only: bool,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Download audio (for ASR) or a ≤720p MP4 (for offline viewing)."""
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    selector = (
        "bestaudio/best"
        if audio_only
        else (
            "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[height<=720][vcodec^=avc1]"
            "/bv*[height<=720][ext=mp4]+ba[ext=m4a]/bv*[height<=720]+ba/b"
        )
    )
    arguments = [
        "-f",
        selector,
        "--newline",
        "--progress-template",
        "download:W2L %(progress._percent_str)s",
        "--continue",
        "-o",
        f"{output_stem}.%(ext)s",
        canonical_url(video_id),
    ]
    if not audio_only:
        arguments[2:2] = ["--merge-output-format", "mp4"]
    process = subprocess.Popen(
        base_command() + arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for line in process.stdout or []:
            match = PROGRESS_RE.match(line.strip())
            if match and on_progress:
                on_progress(min(1.0, float(match.group(1)) / 100))
        stderr = process.stderr.read() if process.stderr else ""
        process.wait(timeout=DOWNLOAD_TIMEOUT)
    except BaseException:
        process.kill()
        raise
    if process.returncode:
        lines = stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "yt-dlp download failed")
    files = [
        path
        for path in output_stem.parent.glob(f"{output_stem.name}.*")
        if not path.name.endswith((".part", ".ytdl")) and ".f" not in path.suffixes[0]
    ]
    if not files:
        raise RuntimeError("yt-dlp did not produce a media file")
    return max(files, key=lambda path: path.stat().st_size)
