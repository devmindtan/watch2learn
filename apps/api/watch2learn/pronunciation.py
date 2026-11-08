"""Estimate Mandarin pronunciation by comparing what local ASR heard with the target.

The comparison is done on pinyin syllables (initial, final, tone), not characters,
so homophones still count as correct. It is an estimate: Whisper infers tones from
the words it recognises rather than measuring pitch directly.
"""

from pypinyin.contrib.tone_convert import to_tone

from .lesson import CJK_RE, contextual_readings, to_simplified

INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q")
INITIALS += ("x", "r", "z", "c", "s", "y", "w")
WEIGHTS = {"initial": 0.35, "final": 0.4, "tone": 0.25}
EXTRA_SYLLABLE_PENALTY = 0.1


def han_syllables(text: str) -> list[tuple[str, str]]:
    """(character, numbered syllable) for every Chinese character, read in context."""
    simplified = to_simplified(text)
    readings = contextual_readings(simplified)
    return [
        (character, reading)
        for character, reading in zip(simplified, readings, strict=True)
        if CJK_RE.match(character) and reading
    ]


def split_syllable(syllable: str) -> tuple[str, str, str]:
    syllable = syllable.lower().replace("ü", "v")
    tone = syllable[-1] if syllable[-1:].isdigit() else "5"
    base = syllable.rstrip("012345")
    initial = next((item for item in INITIALS if base.startswith(item)), "")
    return initial, base[len(initial) :], tone


def similarity(expected: str, heard: str) -> dict:
    expected_initial, expected_final, expected_tone = split_syllable(expected)
    heard_initial, heard_final, heard_tone = split_syllable(heard)
    parts = {
        "initial": expected_initial == heard_initial,
        "final": expected_final == heard_final,
        # a neutral (light) tone is accepted however it was read
        "tone": expected_tone == "5" or expected_tone == heard_tone,
    }
    parts["score"] = sum(WEIGHTS[key] for key, ok in parts.items() if ok)
    if not (parts["initial"] or parts["final"]):
        parts["score"] = 0.0  # a different syllable; the tone alone earns nothing
    return parts


def align(expected: list[str], heard: list[str]) -> list[int | None]:
    """For each expected syllable, the index of the heard syllable it matches (or None)."""
    rows, columns = len(expected), len(heard)
    best = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            pair = similarity(expected[row - 1], heard[column - 1])["score"]
            best[row][column] = max(
                best[row - 1][column], best[row][column - 1], best[row - 1][column - 1] + pair
            )
    matches: list[int | None] = [None] * rows
    row, column = rows, columns
    while row and column:
        pair = similarity(expected[row - 1], heard[column - 1])["score"]
        if pair and best[row][column] == best[row - 1][column - 1] + pair:
            matches[row - 1] = column - 1
            row, column = row - 1, column - 1
        elif best[row][column] == best[row - 1][column]:
            row -= 1
        else:
            column -= 1
    return matches


def score_pronunciation(target: str, heard_text: str) -> dict:
    expected = han_syllables(target)
    heard = han_syllables(heard_text)
    if not expected:
        raise ValueError("Target has no Chinese characters")
    matches = align([syllable for _, syllable in expected], [syllable for _, syllable in heard])
    details = []
    total = 0.0
    for (character, syllable), match in zip(expected, matches, strict=True):
        heard_syllable = heard[match][1] if match is not None else None
        parts = (
            similarity(syllable, heard_syllable)
            if heard_syllable
            else {"initial": False, "final": False, "tone": False, "score": 0.0}
        )
        total += parts["score"]
        details.append(
            {
                "character": character,
                "expected": to_tone(syllable),
                "heard": to_tone(heard_syllable) if heard_syllable else None,
                "heard_character": heard[match][0] if match is not None else None,
                **parts,
                "score": round(parts["score"] * 100),
            }
        )
    extras = len(heard) - sum(match is not None for match in matches)
    raw = total / len(expected) - EXTRA_SYLLABLE_PENALTY * extras / len(expected)
    return {
        "score": max(0, min(100, round(raw * 100))),
        "heard_text": heard_text,
        "heard_pinyin": " ".join(to_tone(syllable) for _, syllable in heard),
        "syllables": details,
        "extra_syllables": extras,
        "method": "whisper-pinyin-comparison",
    }
