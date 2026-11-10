"""Which parts of a cue are Chinese.

Videos for Vietnamese learners mix languages inside one line ("Tôi đến đây,我来了,
我先走。"), and multilingual ASR writes them that way. Only Chinese is learnt and
translated, so a cue is judged clause by clause (split after punctuation):

- a clause of Chinese characters, possibly with a few ASCII words (iPhone), is Chinese;
- a clause with Vietnamese (or pinyin) letters is foreign as a whole: Chinese
  characters inside it are usually misheard speech ("tận 一下");
- another clause (mostly English) keeps only its runs of Chinese characters.
"""

import re

HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
HAN_RUN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]+")
LATIN_WORD_RE = re.compile(r"[A-Za-zÀ-ɏḀ-ỿ]+")
KANA_HANGUL_RE = re.compile(r"[぀-ヿㇰ-ㇿ가-힯ᄀ-ᇿ]")
CLAUSE_SPLIT_RE = re.compile(r"(?<=[,，。.!！?？;；:：、…\n])")


def _clause_spans(clause: str, offset: int) -> list[tuple[int, int, bool]]:
    han = len(HAN_RE.findall(clause))
    if not han:
        return [(offset, offset + len(clause), False)]
    words = LATIN_WORD_RE.findall(clause)
    if any(not word.isascii() for word in words):  # Vietnamese, pinyin with tone marks
        return [(offset, offset + len(clause), False)]
    if han >= len(words) * 2:  # one foreign word ≈ two Chinese characters
        return [(offset, offset + len(clause), True)]
    spans, cursor = [], 0
    for match in HAN_RUN_RE.finditer(clause):
        if match.start() > cursor:
            spans.append((offset + cursor, offset + match.start(), False))
        spans.append((offset + match.start(), offset + match.end(), True))
        cursor = match.end()
    if cursor < len(clause):
        spans.append((offset + cursor, offset + len(clause), False))
    return spans


def chinese_spans(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_chinese) ranges covering the whole text, adjacent kinds merged."""
    if KANA_HANGUL_RE.search(text):  # kanji/hanja inside Japanese/Korean
        return [(0, len(text), False)] if text else []
    spans: list[tuple[int, int, bool]] = []
    offset = 0
    for clause in CLAUSE_SPLIT_RE.split(text):
        for start, end, chinese in _clause_spans(clause, offset):
            if spans and spans[-1][2] == chinese and spans[-1][1] == start:
                spans[-1] = (spans[-1][0], end, chinese)
            elif end > start:
                spans.append((start, end, chinese))
        offset += len(clause)
    return spans


def chinese_text(text: str) -> str:
    """Only the Chinese parts of a cue, for translation ("" when there are none)."""
    parts = [text[start:end].strip() for start, end, chinese in chinese_spans(text) if chinese]
    return " ".join(part for part in parts if part)
