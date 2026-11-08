"""Parse timed subtitle text without losing the original cue context."""

import re
from dataclasses import dataclass
from html import unescape

TIMING_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})(?:\s+.*)?$"
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Cue:
    id: str
    start_ms: int
    end_ms: int
    text: str


def timestamp_ms(value: str) -> int:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    whole_seconds, milliseconds = seconds.split(".", 1)
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(whole_seconds) * 1000
        + int(milliseconds.ljust(3, "0")[:3])
    )


def clean_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub("", text))).strip()


def parse_subtitles(content: str, *, max_cues: int = 10_000) -> list[Cue]:
    if not content.strip():
        raise ValueError("Subtitle content is empty")

    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[Cue] = []
    index = 0
    while index < len(lines):
        match = TIMING_RE.match(lines[index].strip())
        if not match:
            index += 1
            continue

        start_ms = timestamp_ms(match.group("start"))
        end_ms = timestamp_ms(match.group("end"))
        if end_ms <= start_ms:
            raise ValueError(f"Cue ending at line {index + 1} must end after it starts")

        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            if TIMING_RE.match(lines[index].strip()):
                break
            text_lines.append(lines[index])
            index += 1

        text = clean_text(text_lines)
        if text:
            cues.append(Cue(f"cue-{len(cues) + 1}", start_ms, end_ms, text))
            if len(cues) > max_cues:
                raise ValueError(f"Subtitle contains more than {max_cues} cues")

    if not cues:
        raise ValueError("No valid SRT or WebVTT cues were found")
    return cues
