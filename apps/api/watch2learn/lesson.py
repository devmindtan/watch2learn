"""Build context-rich Mandarin vocabulary lessons from subtitle cues."""

import re
from collections import defaultdict
from hashlib import sha256

import jieba
from pypinyin import Style, lazy_pinyin
from pypinyin.contrib.tone_convert import to_tone

from .dictionary import Cedict
from .subtitles import Cue

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def vocabulary_id(word: str) -> str:
    return f"word-{sha256(word.encode()).hexdigest()[:12]}"


def generated_pinyin(word: str, style: Style) -> str:
    return " ".join(lazy_pinyin(word, style=style, neutral_tone_with_five=True))


def dictionary_pinyin(numbered: str) -> str:
    return " ".join(to_tone(syllable.lower().replace("u:", "v")) for syllable in numbered.split())


def cue_tokens(cue: Cue) -> list[dict]:
    tokens = []
    cursor = 0
    for word, start, end in jieba.tokenize(cue.text):
        if start > cursor:
            tokens.append({"text": cue.text[cursor:start]})
        token = {"text": word}
        if CJK_RE.search(word):
            token |= {
                "vocabulary_id": vocabulary_id(word),
                "start_offset": start,
                "end_offset": end,
            }
        tokens.append(token)
        cursor = end
    if cursor < len(cue.text):
        tokens.append({"text": cue.text[cursor:]})
    return tokens


def build_lesson(cues: list[Cue], dictionary: Cedict) -> dict:
    occurrences: dict[str, list[dict]] = defaultdict(list)
    surface_forms: dict[str, set[str]] = defaultdict(set)
    cue_rows = []

    for index, cue in enumerate(cues):
        before_text = cues[index - 1].text if index else None
        after_text = cues[index + 1].text if index + 1 < len(cues) else None
        segments = cue_tokens(cue)
        cue_rows.append(
            {
                "id": cue.id,
                "start_ms": cue.start_ms,
                "end_ms": cue.end_ms,
                "text": cue.text,
                "segments": segments,
            }
        )
        for segment in segments:
            word_id = segment.get("vocabulary_id")
            if not word_id:
                continue
            surface = segment["text"]
            entries = dictionary.lookup(surface)
            canonical = entries[0].simplified if entries else surface
            canonical_id = vocabulary_id(canonical)
            segment["vocabulary_id"] = canonical_id
            surface_forms[canonical_id].add(surface)
            occurrences[canonical_id].append(
                {
                    "cue_id": cue.id,
                    "start_ms": cue.start_ms,
                    "end_ms": cue.end_ms,
                    "surface": surface,
                    "start_offset": segment["start_offset"],
                    "end_offset": segment["end_offset"],
                    "before_text": before_text,
                    "cue_text": cue.text,
                    "after_text": after_text,
                }
            )

    vocabulary = []
    for word_id, word_occurrences in occurrences.items():
        surface = word_occurrences[0]["surface"]
        entries = dictionary.lookup(surface)
        primary = entries[0] if entries else None
        word = primary.simplified if primary else surface
        vocabulary.append(
            {
                "id": word_id,
                "word": word,
                "traditional": primary.traditional if primary else None,
                "surface_forms": sorted(surface_forms[word_id]),
                "pinyin": (
                    dictionary_pinyin(primary.pinyin)
                    if primary
                    else generated_pinyin(word, Style.TONE)
                ),
                "pinyin_numbered": (
                    primary.pinyin if primary else generated_pinyin(word, Style.TONE3)
                ),
                "definitions": list(primary.definitions[:5]) if primary else [],
                "dictionary_alternatives": max(0, len(entries) - 1),
                "occurrence_count": len(word_occurrences),
                "occurrences": word_occurrences,
            }
        )

    vocabulary.sort(
        key=lambda item: (
            -item["occurrence_count"],
            item["occurrences"][0]["start_ms"],
            item["word"],
        )
    )
    return {
        "cues": cue_rows,
        "vocabulary": vocabulary,
        "dictionary": {
            "loaded": dictionary.source is not None,
            "source": str(dictionary.source) if dictionary.source else None,
            "license": "CC BY-SA 4.0",
        },
    }
