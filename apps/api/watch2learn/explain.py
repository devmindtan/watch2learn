"""Vietnamese teaching explanations from a local Ollama model, streamed and cached.

A word lesson is short and about real use: where and how the word is used, how
native speakers say it (example sentences), and a note only when the word has
something special. It does not depend on the video sentence, so one lesson per
word and reading is cached and shared by every video (a global dictionary).
Readings, tones and pronunciation hints are computed by us and given to the model
as facts; the model only writes the teaching text. Lessons are written ahead of
time after an import (prepare.py); on demand they stream section by section.
Nothing leaves the machine.
"""

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass

from pypinyin.contrib.tone_convert import to_tone, to_tone3

from . import pronunciation, word_dictionary
from .gpu_host import GPU
from .jobs import connect, initialize, now
from .mandarin_text import chinese_text

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"
TIMEOUT_SECONDS = 300
PROMPT_VERSION = "vi-teacher-8"
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
TAG = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)


@dataclass(frozen=True)
class LessonRequest:
    """One lesson to write. Word lessons live in the global dictionary (`word`);
    sentence lessons in the explanation cache, keyed by their prompt."""

    prompt: str
    keys: tuple[str, ...]
    subject: str
    word: dict | None = None


# Reading, meaning and pronunciation notes are built from verified data; the model
# writes only the parts that need world knowledge.
WORD_SECTIONS = ("cach_dung", "luu_y")
SENTENCE_SECTIONS = ("cau_truc", "giao_tiep")
# Chinese grammar terms the model sometimes uses inside Vietnamese prose.
GRAMMAR_TERMS = {
    "主语": "chủ ngữ",
    "谓语": "vị ngữ",
    "宾语": "tân ngữ",
    "动词": "động từ",
    "名词": "danh từ",
    "形容词": "tính từ",
    "副词": "phó từ",
    "量词": "lượng từ",
    "补语": "bổ ngữ",
    "定语": "định ngữ",
    "状语": "trạng ngữ",
    "介词": "giới từ",
    "连词": "liên từ",
    "助词": "trợ từ",
    "代词": "đại từ",
    "数词": "số từ",
    "语气词": "từ ngữ khí",
    "句型": "mẫu câu",
    "结构": "cấu trúc",
}
SYSTEM_PROMPT = (
    "Bạn là giáo viên tiếng Trung giỏi, dạy người Việt mới học. Viết hoàn toàn bằng tiếng Việt "
    "tự nhiên, thân thiện, câu ngắn, để đọc thành tiếng như đang giảng bài. Không dùng markdown, "
    "không viết pinyin. Thuật ngữ ngữ pháp phải bằng tiếng Việt (chủ ngữ, động từ, tân ngữ...). "
    "Khi nhắc chữ Hán khác (từ hay đi kèm, ví dụ) luôn kèm nghĩa tiếng Việt ngay sau. "
    "Dữ kiện về cách đọc, thanh điệu và mẹo phát âm được cung cấp là chuẩn: dùng đúng, không tự "
    "sửa. Chỉ nói điều bạn chắc chắn. Trả lời đúng theo các thẻ được yêu cầu, không thêm gì khác."
)
SPOKEN_STYLE = (
    "Người học đã thấy cách đọc và nghĩa trên màn hình, đừng nhắc lại. Lời giảng sẽ được đọc "
    "thành tiếng liền một mạch: viết như đang nói chuyện với học viên, câu nối câu tự nhiên, "
    "không liệt kê, không tiêu đề, không chép lại lời yêu cầu này.\n"
)
WORD_TASK = (
    SPOKEN_STYLE
    + "Hãy giảng 3 ý theo thứ tự: (1) từ này dùng thế nào: hay đi với từ nào, đứng ở đâu "
    "trong câu; (2) dùng ở đâu: tình huống nào, trang trọng hay thân mật; (3) lưu ý, chỉ khi "
    "từ có điểm đặc biệt như dễ nhầm với từ khác, sắc thái, lượng từ riêng.\n"
    "Ý 1 và 2 viết liền trong thẻ cach_dung (2–3 câu). Ý 3 viết trong thẻ luu_y (1–2 câu), "
    "không có gì đặc biệt hoặc không chắc chắn thì để thẻ trống, đừng bịa. "
    "Thêm đúng 2 thẻ vi_du, mỗi thẻ là một câu ngắn "
    "người bản xứ hay nói, rồi dấu |, rồi nghĩa tiếng Việt; trong thẻ vi_du không có ngoặc.\n"
    "Bài mẫu cho từ 吃饭 (chỉ để xem cách trình bày, không chép nội dung):\n"
    "<cach_dung>Từ này là một động từ, thường đứng ngay sau chủ ngữ, và hay đi với 一起 "
    "(cùng nhau) hoặc 去 (đi) khi rủ ai đó. Bạn sẽ nghe nó hằng ngày trong gia đình, với bạn "
    "bè, cả ở chỗ làm, vì người Trung Quốc còn dùng nó như một lời hỏi thăm.</cach_dung>\n"
    "<vi_du>我们一起吃饭吧。 | Chúng mình cùng đi ăn nhé.</vi_du>\n"
    "<vi_du>你吃饭了吗？ | Bạn ăn cơm chưa?</vi_du>\n"
    "<luu_y>Bạn cần lưu ý là khi muốn nói ăn một món cụ thể thì bỏ 饭 đi, ví dụ 吃面 là ăn "
    "mì.</luu_y>"
)
SENTENCE_TASK = (
    SPOKEN_STYLE
    + "Hãy giảng 2 ý theo thứ tự: (1) câu này thường được nói khi nào, ở đâu, viết trong thẻ "
    "giao_tiep (1–2 câu); (2) mẫu câu và vai trò của các từ quan trọng, kèm nghĩa, viết nối "
    "tiếp trong thẻ cau_truc (2–3 câu). Thêm đúng 2 thẻ vi_du, mỗi thẻ là một câu tương tự, "
    "ngắn, rồi dấu |, rồi nghĩa tiếng Việt; trong thẻ vi_du không có ngoặc.\n"
    "Cách trình bày:\n"
    "<giao_tiep>…</giao_tiep>\n<cau_truc>…</cau_truc>\n"
    "<vi_du>câu chữ Hán giản thể | nghĩa tiếng Việt</vi_du>\n"
    "<vi_du>câu chữ Hán giản thể | nghĩa tiếng Việt</vi_du>"
)


def ollama_url(start: bool = True) -> str:
    """An explicit URL, else Ollama on the GPU machine when usable, else this laptop."""
    configured = os.environ.get("WATCH2LEARN_OLLAMA_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return GPU.endpoint("ollama", start=start) or DEFAULT_URL


def model_name() -> str:
    return os.environ.get("WATCH2LEARN_OLLAMA_MODEL", DEFAULT_MODEL)


def model_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{ollama_url(start=False)}/api/tags", timeout=1.5) as response:
            models = json.load(response).get("models", [])
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return any(item.get("name") == model_name() for item in models)


def initialize_cache() -> None:
    initialize()
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS explanations (
                cache_key TEXT PRIMARY KEY,
                word_id TEXT NOT NULL,
                model TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def facts_block(facts: dict) -> str:
    """The verified reading only: pronunciation tips are shown on screen, not taught here."""
    syllables = ", ".join(
        f"{item['character']} = {item['pinyin']} (thanh {item['tone']})"
        for item in facts["syllables"]
    )
    return f"Cách đọc chuẩn từng chữ: {syllables}.\n"


def word_prompt(word: dict, facts: dict) -> str:
    """Context-free on purpose: the same word and reading give the same cached lesson."""
    meanings = "; ".join(item for item in word.get("definitions_vi", []) if ":" not in item[:3])
    return (
        f"Từ đang học: {word['word']}\n"
        f"{facts_block(facts)}"
        f"Nghĩa trong từ điển: {meanings or 'chưa có'}\n\n" + WORD_TASK
    )


def sentence_prompt(sentence: str, translation: str | None, words: list[dict], facts: dict) -> str:
    glossary = "; ".join(
        f"{item['word']} = {item['meaning']}" for item in words if item.get("meaning")
    )
    return (
        f"Câu đang học: {sentence}\n"
        f"{facts_block(facts)}"
        f"Bản dịch máy: {translation or 'chưa có'}\n"
        f"Nghĩa từng từ theo từ điển: {glossary or 'chưa có'}\n\n" + SENTENCE_TASK
    )


def clean(text: str) -> str:
    text = re.sub(r"[*#`_>]+", "", text)
    for term, vietnamese in GRAMMAR_TERMS.items():
        text = text.replace(term, vietnamese)
    return " ".join(text.split())


def stream_ollama(prompt: str, base_url: str | None = None) -> Iterator[str]:
    body = json.dumps(
        {
            "model": model_name(),
            "stream": True,
            "think": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.3, "num_predict": 450},
        }
    ).encode()
    url = f"{base_url or ollama_url()}/api/chat"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        for line in response:
            if not line.strip():
                continue
            chunk = json.loads(line)
            yield chunk.get("message", {}).get("content", "")
            if chunk.get("done"):
                return


def is_empty_note(text: str) -> bool:
    """An optional section the model filled with "nothing special" instead of leaving it empty."""
    lowered = text.lower().strip(" .")
    lowered = lowered.removeprefix("bạn cần lưu ý là").strip(" ,:")
    return not lowered or (len(lowered) < 60 and lowered.startswith("không có"))


def parse_example(text: str) -> dict | None:
    chinese, _, vietnamese = text.partition("|")
    chinese = clean(re.sub(r"[（(][^）)]*[）)]", "", chinese))  # no gloss inside the sentence
    vietnamese = re.sub(r"^\s*nghĩa( tiếng Việt)?\s*[:：]\s*", "", clean(vietnamese), flags=re.I)
    return {"zh": chinese, "vi": vietnamese} if HAN.search(chinese) else None


def tagged_sections(chunks: Iterator[str], keys: tuple[str, ...]) -> Iterator[dict]:
    """Emit each <tag>…</tag> as soon as it closes: {"key", "text"} or {"example"}."""
    buffer = ""
    examples = 0
    for chunk in chunks:
        buffer += re.sub(r"</?think>", "", chunk)
        while match := TAG.search(buffer):
            tag, content = match.group(1), match.group(2)
            buffer = buffer[match.end() :]
            if tag in keys and not is_empty_note(clean(content)):
                yield {"key": tag, "text": clean(content)}
            elif tag == "vi_du" and examples < 2 and (example := parse_example(content)):
                examples += 1
                yield {"example": example}


def cache_key(prompt: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{model_name()}\n{prompt}".encode()).hexdigest()


def lesson_version() -> str:
    return f"{PROMPT_VERSION}:{model_name()}"


def cached_events(request: LessonRequest) -> list[dict] | None:
    if request.word:
        stored = word_dictionary.stored_lesson(request.word, lesson_version())
        if stored is not None:
            return stored
    initialize_cache()  # sentence lessons, and word lessons written before the dictionary
    with connect() as connection:
        row = connection.execute(
            "SELECT text FROM explanations WHERE cache_key = ?", (cache_key(request.prompt),)
        ).fetchone()
    if not row:
        return None
    events = json.loads(row["text"])
    if request.word:  # move an older cached word lesson into the dictionary
        word_dictionary.save_lesson(request.word, events, lesson_version())
    return events


def store_events(request: LessonRequest, events: list[dict]) -> None:
    if request.word:
        word_dictionary.save_lesson(request.word, events, lesson_version())
        return
    initialize_cache()
    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO explanations VALUES (?, ?, ?, ?, ?)",
            (
                cache_key(request.prompt),
                request.subject,
                model_name(),
                json.dumps(events, ensure_ascii=False),
                now(),
            ),
        )


def forget(request: LessonRequest) -> None:
    """The learner asked for the lesson to be written again."""
    if request.word:
        word_dictionary.clear_lesson(request.word)
    initialize_cache()
    with connect() as connection:
        connection.execute(
            "DELETE FROM explanations WHERE cache_key = ?", (cache_key(request.prompt),)
        )


def stream_lesson(request: LessonRequest, base_url: str | None = None) -> Iterator[dict]:
    """Yield sections as they are written (or all at once when already stored)."""
    stored = cached_events(request)
    if stored is not None:
        for event in stored:
            yield event | {"cached": True}
        return
    events = []
    for event in tagged_sections(stream_ollama(request.prompt, base_url), request.keys):
        events.append(event)
        yield event
    if not any("key" in event for event in events):
        raise RuntimeError("The local model returned an empty explanation")
    store_events(request, events)


def pronunciation_facts(text: str, marked_pinyin: str | None = None) -> dict:
    """Readings (as shown to the learner when given), tones and hints for Vietnamese speakers."""
    pairs = pronunciation.han_syllables(text)
    marked = (marked_pinyin or "").split()
    if marked and len(marked) == len(pairs):
        pairs = [
            (character, to_tone3(syllable, neutral_tone_with_five=True))
            for (character, _), syllable in zip(pairs, marked, strict=True)
        ]
    syllables = [
        {
            "character": character,
            "pinyin": to_tone(syllable),
            "tone": int(syllable[-1]) if syllable[-1:].isdigit() else 5,
        }
        for character, syllable in pairs
    ]
    return {"syllables": syllables, "tips": pronunciation.learner_tips(pairs)}


def sentence_words(lesson: dict, cue: dict) -> list[dict]:
    """Dictionary meaning of each word in the cue, in sentence order."""
    words = {item["id"]: item for item in lesson.get("vocabulary", [])}
    glossary = []
    for segment in cue.get("segments", []):
        word = words.get(segment.get("vocabulary_id"))
        if not word:
            continue
        meanings = [item for item in word.get("definitions_vi", []) if ":" not in item[:3]]
        glossary.append(
            {
                "word": segment["text"],
                "pinyin": segment.get("pinyin"),
                "meaning": meanings[0] if meanings else None,
            }
        )
    return glossary


def sentence_facts(cue: dict) -> dict:
    pinyin = " ".join(item["pinyin"] for item in cue.get("segments", []) if item.get("pinyin"))
    facts = pronunciation_facts(chinese_text(cue["text"]) or cue["text"], pinyin)
    facts["tips"] = facts["tips"][:6]
    return facts


def word_request(word: dict) -> LessonRequest:
    """The shared lesson for this word and reading (no video context on purpose)."""
    facts = pronunciation_facts(word["word"], word.get("pinyin"))
    return LessonRequest(word_prompt(word, facts), WORD_SECTIONS, word["id"], word)


def sentence_request(lesson: dict, cue: dict) -> LessonRequest:
    text = chinese_text(cue["text"]) or cue["text"]  # never teach the other-language parts
    prompt = sentence_prompt(
        text, cue.get("translation_vi"), sentence_words(lesson, cue), sentence_facts(cue)
    )
    return LessonRequest(prompt, SENTENCE_SECTIONS, f"sentence:{text}")


def lesson_requests(lesson: dict) -> list[LessonRequest]:
    """Every lesson a video offers: words first (most frequent first), then sentences."""
    words = sorted(lesson.get("vocabulary", []), key=lambda item: -item.get("occurrence_count", 0))
    requests = [word_request(word) for word in words]
    seen = set()
    for cue in lesson.get("cues", []):
        text = chinese_text(cue["text"])
        if cue.get("translation_skipped") or not text or text in seen:
            continue
        seen.add(text)
        requests.append(sentence_request(lesson, cue))
    return requests


def is_ready(request: LessonRequest) -> bool:
    return cached_events(request) is not None


def write_lesson(request: LessonRequest, base_url: str) -> None:
    """Write one lesson (used by the background preparation)."""
    for _event in stream_lesson(request, base_url):
        pass


def unload_model(base_url: str) -> None:
    """Free the model's memory (VRAM) so speech models can use the card."""
    body = json.dumps({"model": model_name(), "keep_alive": 0}).encode()
    request = urllib.request.Request(
        f"{base_url}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except OSError:
        pass
