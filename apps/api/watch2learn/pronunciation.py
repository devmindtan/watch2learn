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


# Pronunciation hints for Vietnamese speakers, phrased to be read aloud (no pinyin
# letters) and attached to the character they concern.
INITIAL_TIPS = {
    "b": "phụ âm đầu đọc gần “p” tiếng Việt, không bật hơi",
    "p": "phụ âm đầu bật hơi mạnh, như đẩy một luồng hơi ra khỏi môi",
    "d": "phụ âm đầu đọc gần “t” tiếng Việt, không bật hơi",
    "t": "phụ âm đầu bật hơi, gần “th” tiếng Việt",
    "g": "phụ âm đầu đọc gần “c” tiếng Việt, không bật hơi",
    "k": "phụ âm đầu bật hơi mạnh, gần “kh” nhưng có hơi",
    "h": "phụ âm đầu đọc gần “kh” tiếng Việt",
    "f": "phụ âm đầu đọc gần “ph” tiếng Việt",
    "j": "phụ âm đầu đọc gần “ch” tiếng Việt, mặt lưỡi áp lên vòm miệng, không bật hơi",
    "q": "phụ âm đầu giống “ch” nhưng bật hơi mạnh",
    "x": "phụ âm đầu đọc gần “x” tiếng Việt, môi dẹt như đang cười",
    "zh": "phụ âm đầu uốn đầu lưỡi lên vòm miệng, gần “tr” tiếng Việt, không bật hơi",
    "ch": "phụ âm đầu uốn lưỡi như “tr” nhưng bật hơi mạnh",
    "sh": "phụ âm đầu uốn đầu lưỡi lên, gần “s” tiếng Việt đọc nặng",
    "r": "phụ âm đầu uốn lưỡi, gần “r” nhẹ kéo dài, không rung lưỡi",
    "z": "phụ âm đầu để đầu lưỡi thẳng chạm sau răng trên, gần “ch” nhẹ, không bật hơi",
    "c": "phụ âm đầu để đầu lưỡi thẳng như “ts” và bật hơi mạnh",
    "s": "phụ âm đầu đọc gần “x” tiếng Việt, đầu lưỡi thẳng",
}
FINAL_TIPS = {
    "e": "vần đọc gần “ưa”, miệng hé",
    "ian": "vần đọc gần “iên”",
    "ong": "vần đọc gần “ung”",
    "eng": "vần đọc gần “âng”",
    "ui": "vần đọc gần “uây”",
    "iu": "vần đọc gần “iêu”",
    "un": "vần đọc gần “uân”",
    "ou": "vần đọc gần “âu”",
    "ei": "vần đọc gần “ây”",
    "en": "vần đọc gần “ân”",
    "uo": "vần đọc gần “ua”",
    "ie": "vần đọc gần “iê”",
    "er": "đọc là “ơ” có uốn lưỡi",
    "v": "vần tròn môi như “u” nhưng lưỡi đặt như “i”",
    "ve": "vần tròn môi như “u” rồi chuyển sang “ê”",
    "van": "vần tròn môi như “u” rồi chuyển sang “iên”",
    "vn": "vần tròn môi như “u” rồi chuyển sang “in”",
}
TONE_NAMES = {
    "1": "thanh 1, giọng cao và đều",
    "2": "thanh 2, giọng đi lên",
    "3": "thanh 3, giọng hạ thấp rồi lên",
    "4": "thanh 4, giọng rơi mạnh từ cao xuống",
    "5": "thanh nhẹ, đọc ngắn và nhẹ",
}
APICAL_I = {"z", "c", "s"}
RETROFLEX_I = {"zh", "ch", "sh", "r"}


def learner_tips(syllables: list[tuple[str, str]]) -> list[str]:
    """Spoken-style hints for (character, numbered syllable) pairs, tone changes first."""
    tips: list[str] = []
    tones = [split_syllable(syllable)[2] for _, syllable in syllables]
    for index in range(len(tones) - 1):
        if tones[index] == "3" and tones[index + 1] == "3":
            pair = syllables[index][0] + syllables[index + 1][0]
            tips.append(
                f"{pair} có hai thanh 3 liền nhau, nên chữ {syllables[index][0]} "
                "đọc thành thanh 2, giọng đi lên."
            )
    for index, (character, _syllable) in enumerate(syllables):
        following = tones[index + 1] if index + 1 < len(tones) else None
        if character == "不" and following == "4":
            tips.append("不 đứng trước thanh 4 nên đọc thành thanh 2.")
        if character == "一" and following:
            tips.append(
                "一 đổi thanh theo chữ đứng sau: trước thanh 4 đọc thanh 2, còn lại thanh 4."
            )
    seen = set()
    for character, syllable in syllables:
        initial, final, _tone = split_syllable(syllable)
        if initial in {"j", "q", "x", "y"} and final.startswith("u"):
            final = "v" + final[1:]
        parts = []
        if initial in INITIAL_TIPS:
            parts.append(INITIAL_TIPS[initial])
        if final == "i" and initial in APICAL_I:
            parts.append("vần đọc gần “ư”, không đọc “i”")
        elif final == "i" and initial in RETROFLEX_I:
            parts.append("vần đọc gần “ư” có uốn lưỡi, không đọc “i”")
        elif final in FINAL_TIPS:
            parts.append(FINAL_TIPS[final])
        tip = "; ".join(parts)
        if tip and (initial, final) not in seen:
            seen.add((initial, final))
            tips.append(f"Chữ {character}: {tip}.")
    return tips
