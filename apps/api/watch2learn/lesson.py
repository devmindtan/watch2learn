"""Build context-rich Mandarin vocabulary lessons from subtitle cues."""

import re
from collections import Counter, defaultdict
from hashlib import sha256

import jieba
from opencc import OpenCC
from pypinyin import Style, lazy_pinyin, pinyin
from pypinyin.contrib.tone_convert import to_tone

from .dictionary import Cedict, DictionaryEntry
from .mandarin_text import LATIN_WORD_RE, chinese_spans
from .subtitles import Cue

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
TONE_RE = re.compile(r"[1-5]")
MAX_ALTERNATIVE_READINGS = 4
ANALYSIS_VERSION = "zh-v4"
_TO_SIMPLIFIED = OpenCC("t2s")


def to_simplified(text: str) -> str:
    """Learner-facing Chinese is simplified; the original stays in `text_original`."""
    return _TO_SIMPLIFIED.convert(text)


def simplified_cues(cues: list[Cue]) -> list[Cue]:
    return [Cue(cue.id, cue.start_ms, cue.end_ms, to_simplified(cue.text)) for cue in cues]


def vocabulary_id(word: str) -> str:
    return f"word-{sha256(word.encode()).hexdigest()[:12]}"


def generated_pinyin(word: str, style: Style) -> str:
    return " ".join(lazy_pinyin(word, style=style, neutral_tone_with_five=True))


def dictionary_pinyin(numbered: str) -> str:
    return " ".join(to_tone(syllable.lower().replace("u:", "v")) for syllable in numbered.split())


def normalized_reading(numbered: str) -> str:
    return " ".join(numbered.lower().replace("u:", "v").replace("ü", "v").split())


def contextual_readings(text: str) -> list[str]:
    """One numbered-tone syllable per character, disambiguated by the whole cue."""
    readings = pinyin(
        text,
        style=Style.TONE3,
        neutral_tone_with_five=True,
        errors=lambda chunk: [""] * len(chunk),
    )
    flat = [item[0] or "" for item in readings]
    return flat if len(flat) == len(text) else [""] * len(text)


def choose_entry(entries: list[DictionaryEntry], reading: str) -> DictionaryEntry | None:
    """Prefer the dictionary sense whose reading matches the sentence-level reading."""
    if not entries:
        return None
    reading = normalized_reading(reading)
    toneless = TONE_RE.sub("", reading)

    def score(entry: DictionaryEntry) -> int:
        candidate = normalized_reading(entry.pinyin)
        if reading and candidate == reading:
            return 2
        return 1 if toneless and TONE_RE.sub("", candidate) == toneless else 0

    return max(entries, key=score)  # max keeps dictionary order among equal scores


def vietnamese_definitions(
    vietnamese: Cedict | None, word: str, primary: DictionaryEntry | None
) -> list[str]:
    """Prefer the CVDICT sense with the same headword and reading as the CC-CEDICT entry."""
    if vietnamese is None:
        return []
    entries = vietnamese.lookup(word)
    if primary:
        reading = normalized_reading(primary.pinyin)
        entries = sorted(entries, key=lambda entry: normalized_reading(entry.pinyin) != reading)
    return list(entries[0].definitions[:6]) if entries else []


def alternative_readings(
    entries: list[DictionaryEntry], primary: DictionaryEntry, vietnamese: Cedict | None
) -> list[dict]:
    """Other readings/senses so the learner can correct an ambiguous analysis."""
    alternatives = []
    seen = {normalized_reading(primary.pinyin)}
    for entry in entries:
        reading = normalized_reading(entry.pinyin)
        if reading in seen:
            continue
        seen.add(reading)
        alternatives.append(
            {
                "pinyin": dictionary_pinyin(entry.pinyin),
                "pinyin_numbered": entry.pinyin,
                "definitions": list(entry.definitions[:3]),
                "definitions_vi": vietnamese_definitions(vietnamese, entry.simplified, entry)[:3],
            }
        )
        if len(alternatives) == MAX_ALTERNATIVE_READINGS:
            break
    return alternatives


def add_vietnamese_definitions(lesson: dict, english: Cedict, vietnamese: Cedict) -> dict:
    """Backfill Vietnamese meanings for lessons saved before CVDICT was available."""
    if vietnamese.source is None:
        return lesson
    for item in lesson.get("vocabulary", []):
        if item.get("definitions_vi"):
            continue
        primary = choose_entry(english.lookup(item["word"]), item.get("pinyin_numbered", ""))
        item["definitions_vi"] = vietnamese_definitions(vietnamese, item["word"], primary)
    lesson["vietnamese_dictionary"] = dictionary_provenance(vietnamese, "CVDICT")
    return lesson


def dictionary_provenance(dictionary: Cedict | None, name: str) -> dict:
    source = dictionary.source if dictionary else None
    return {
        "name": name,
        "loaded": source is not None,
        "source": str(source) if source else None,
        "license": "CC BY-SA 4.0",
    }


def cue_tokens(cue: Cue) -> list[dict]:
    """Words of the Chinese parts; other-language parts stay as plain foreign text."""
    readings = contextual_readings(cue.text)
    tokens = []
    for span_start, span_end, chinese in chinese_spans(cue.text):
        part = cue.text[span_start:span_end]
        if not chinese:
            token = {"text": part}
            if LATIN_WORD_RE.search(part):
                token["foreign"] = True  # never learnt, read or translated
            tokens.append(token)
            continue
        cursor = 0
        for word, start, end in jieba.tokenize(part):
            if start > cursor:
                tokens.append({"text": part[cursor:start]})
            token = {"text": word}
            if CJK_RE.search(word):
                begin, finish = span_start + start, span_start + end
                token |= {
                    "vocabulary_id": vocabulary_id(word),
                    "start_offset": begin,
                    "end_offset": finish,
                    "reading": " ".join(filter(None, readings[begin:finish])),
                }
            tokens.append(token)
            cursor = end
        if cursor < len(part):
            tokens.append({"text": part[cursor:]})
    return tokens


def build_lesson(
    cues: list[Cue],
    dictionary: Cedict,
    vietnamese: Cedict | None = None,
    translations: list[dict] | None = None,
    translation_provenance: dict | None = None,
) -> dict:
    occurrences: dict[str, list[dict]] = defaultdict(list)
    chosen_entries: dict[str, Counter] = defaultdict(Counter)
    surface_forms: dict[str, set[str]] = defaultdict(set)
    cue_rows = []

    originals = {cue.id: cue.text for cue in cues}
    cues = simplified_cues(cues)
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
                "text_original": originals[cue.id] if originals[cue.id] != cue.text else None,
                **(translations[index] if translations else {"translation_vi": None}),
                "segments": segments,
            }
        )
        for segment in segments:
            if not segment.get("vocabulary_id"):
                continue
            surface = segment["text"]
            reading = segment.pop("reading")
            entry = choose_entry(dictionary.lookup(surface), reading)
            canonical = entry.simplified if entry else surface
            canonical_id = vocabulary_id(canonical)
            segment["vocabulary_id"] = canonical_id
            segment["pinyin"] = (
                dictionary_pinyin(entry.pinyin)
                if entry
                else dictionary_pinyin(reading)
                if reading
                else generated_pinyin(surface, Style.TONE)
            )
            surface_forms[canonical_id].add(surface)
            if entry:
                chosen_entries[canonical_id][entry] += 1
            occurrences[canonical_id].append(
                {
                    "cue_id": cue.id,
                    "start_ms": cue.start_ms,
                    "end_ms": cue.end_ms,
                    "surface": surface,
                    "pinyin": segment["pinyin"],
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
        counts = chosen_entries[word_id]
        primary = max(counts, key=counts.get) if counts else None
        word = primary.simplified if primary else surface
        vocabulary.append(
            {
                "id": word_id,
                "word": word,
                "traditional": primary.traditional if primary else None,
                "surface_forms": sorted(surface_forms[word_id]),
                "pinyin": word_occurrences[0]["pinyin"]
                if not primary
                else dictionary_pinyin(primary.pinyin),
                "pinyin_numbered": (
                    primary.pinyin if primary else generated_pinyin(word, Style.TONE3)
                ),
                "definitions": list(primary.definitions[:5]) if primary else [],
                "definitions_vi": vietnamese_definitions(vietnamese, word, primary),
                "dictionary_alternatives": max(0, len(entries) - 1),
                "alternatives": alternative_readings(entries, primary, vietnamese)
                if primary
                else [],
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
        "dictionary": dictionary_provenance(dictionary, "CC-CEDICT"),
        "vietnamese_dictionary": dictionary_provenance(vietnamese, "CVDICT"),
        "translation": translation_provenance
        or {"target_language": "vi", "available": False, "method": None},
        "analysis": {"version": ANALYSIS_VERSION, "pinyin": "pypinyin-context+cc-cedict"},
    }
