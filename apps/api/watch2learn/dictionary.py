"""Minimal CC-CEDICT-format parser (CC-CEDICT, CVDICT) with explicit local data provenance."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CEDICT_RE = re.compile(
    r"^(?P<traditional>\S+)\s+(?P<simplified>\S+)\s+"
    r"\[(?P<pinyin>[^]]+)]\s+/(?P<definitions>.*)/$"
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = PROJECT_ROOT / "data" / "dictionaries" / "cedict_ts.u8"
VIETNAMESE_PATH = PROJECT_ROOT / "data" / "dictionaries" / "cvdict.u8"


@dataclass(frozen=True)
class DictionaryEntry:
    traditional: str
    simplified: str
    pinyin: str
    definitions: tuple[str, ...]


class Cedict:
    def __init__(self, entries: dict[str, list[DictionaryEntry]], source: Path | None = None):
        self.entries = entries
        self.source = source

    @classmethod
    def empty(cls) -> "Cedict":
        return cls({})

    @classmethod
    def from_text(cls, content: str, source: Path | None = None) -> "Cedict":
        entries: dict[str, list[DictionaryEntry]] = {}
        for line in content.splitlines():
            if not line or line.startswith("#"):
                continue
            match = CEDICT_RE.match(line)
            if not match:
                continue
            entry = DictionaryEntry(
                match.group("traditional"),
                match.group("simplified"),
                match.group("pinyin"),
                tuple(part for part in match.group("definitions").split("/") if part),
            )
            for headword in {entry.simplified, entry.traditional}:
                entries.setdefault(headword, []).append(entry)
        return cls(entries, source)

    def lookup(self, word: str) -> list[DictionaryEntry]:
        return self.entries.get(word, [])


@lru_cache(maxsize=4)
def load_cedict(path: str | Path = DEFAULT_PATH) -> Cedict:
    source = Path(path)
    if not source.is_file():
        return Cedict.empty()
    return Cedict.from_text(source.read_text(encoding="utf-8-sig"), source)


def load_vietnamese() -> Cedict:
    """Chinese-Vietnamese meanings from CVDICT, which shares the CC-CEDICT format."""
    return load_cedict(VIETNAMESE_PATH)
