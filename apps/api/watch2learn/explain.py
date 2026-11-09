"""Vietnamese teaching explanations from a local Ollama model, streamed and cached.

A word lesson answers, in Vietnamese: how is it read, what does it mean, what to
watch when pronouncing it, where it is met in conversation and how it is used in
practice (with examples). Readings, tones and pronunciation hints are computed by
us and given to the model as facts; the model only writes the teaching text.
Sections are streamed as soon as each one is complete, because a CPU-only 8B
model needs over a minute for the whole lesson. Nothing leaves the machine.
"""

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterator

from .gpu_host import GPU
from .jobs import connect, initialize, now

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"
TIMEOUT_SECONDS = 300
PROMPT_VERSION = "vi-teacher-4"
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
TAG = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)
# Reading, meaning and pronunciation notes are built from verified data; the model
# writes only the parts that need world knowledge.
WORD_SECTIONS = ("giao_tiep", "su_dung")
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
FORMAT_RULES = (
    "<vi_du>câu ví dụ chữ Hán giản thể | nghĩa tiếng Việt</vi_du>\n"
    "<vi_du>câu ví dụ thứ hai | nghĩa tiếng Việt</vi_du>\n"
    "Mỗi thẻ 1–3 câu tiếng Việt. Bắt buộc có đủ các thẻ và 2 câu ví dụ ngắn, đơn giản."
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
    syllables = ", ".join(
        f"{item['character']} = {item['pinyin']} (thanh {item['tone']})"
        for item in facts["syllables"]
    )
    tips = " ".join(facts["tips"]) or "không có lưu ý đặc biệt"
    return f"Cách đọc chuẩn từng chữ: {syllables}.\nMẹo phát âm chuẩn cho người Việt: {tips}\n"


def word_prompt(word: dict, facts: dict, sentence: str, translation: str | None) -> str:
    meanings = "; ".join(item for item in word.get("definitions_vi", []) if ":" not in item[:3])
    return (
        f"Từ đang học: {word['word']}\n"
        f"{facts_block(facts)}"
        f"Nghĩa trong từ điển: {meanings or 'chưa có'}\n"
        f"Câu trong video: {sentence}\n"
        f"Bản dịch máy của câu: {translation or 'chưa có'}\n\n"
        "Cách đọc, nghĩa và lưu ý phát âm đã được giảng riêng. Bạn chỉ viết theo đúng mẫu:\n"
        "<giao_tiep>Từ này thường gặp ở đâu, trong tình huống giao tiếp nào, trang trọng hay "
        "thân mật.</giao_tiep>\n"
        "<su_dung>Trong thực tế dùng thế nào: hay đi với từ nào (kèm nghĩa), đứng ở đâu trong "
        "câu.</su_dung>\n" + FORMAT_RULES
    )


def sentence_prompt(sentence: str, translation: str | None, words: list[dict], facts: dict) -> str:
    glossary = "; ".join(
        f"{item['word']} = {item['meaning']}" for item in words if item.get("meaning")
    )
    return (
        f"Câu đang học: {sentence}\n"
        f"{facts_block(facts)}"
        f"Bản dịch máy: {translation or 'chưa có'}\n"
        f"Nghĩa từng từ theo từ điển: {glossary or 'chưa có'}\n\n"
        "Cách đọc, nghĩa và lưu ý phát âm đã được giảng riêng. Bạn chỉ viết theo đúng mẫu:\n"
        "<cau_truc>Mẫu câu và vai trò của các từ quan trọng (kèm nghĩa).</cau_truc>\n"
        "<giao_tiep>Câu này thường được nói khi nào, ở đâu.</giao_tiep>\n" + FORMAT_RULES
    )


def clean(text: str) -> str:
    text = re.sub(r"[*#`_>]+", "", text)
    for term, vietnamese in GRAMMAR_TERMS.items():
        text = text.replace(term, vietnamese)
    return " ".join(text.split())


def stream_ollama(prompt: str) -> Iterator[str]:
    body = json.dumps(
        {
            "model": model_name(),
            "stream": True,
            "think": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.3, "num_predict": 600},
        }
    ).encode()
    request = urllib.request.Request(
        f"{ollama_url()}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        for line in response:
            if not line.strip():
                continue
            chunk = json.loads(line)
            yield chunk.get("message", {}).get("content", "")
            if chunk.get("done"):
                return


def parse_example(text: str) -> dict | None:
    chinese, _, vietnamese = text.partition("|")
    chinese, vietnamese = clean(chinese), clean(vietnamese)
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
            if tag in keys and clean(content):
                yield {"key": tag, "text": clean(content)}
            elif tag == "vi_du" and examples < 2 and (example := parse_example(content)):
                examples += 1
                yield {"example": example}


def cache_key(prompt: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}\n{model_name()}\n{prompt}".encode()).hexdigest()


def stream_lesson(prompt: str, keys: tuple[str, ...], subject: str) -> Iterator[dict]:
    """Yield sections as they are written (or all at once from the cache)."""
    key = cache_key(prompt)
    initialize_cache()
    with connect() as connection:
        row = connection.execute(
            "SELECT text FROM explanations WHERE cache_key = ?", (key,)
        ).fetchone()
    if row:
        for event in json.loads(row["text"]):
            yield event | {"cached": True}
        return
    events = []
    for event in tagged_sections(stream_ollama(prompt), keys):
        events.append(event)
        yield event
    if not any("key" in event for event in events):
        raise RuntimeError("The local model returned an empty explanation")
    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO explanations VALUES (?, ?, ?, ?, ?)",
            (key, subject, model_name(), json.dumps(events, ensure_ascii=False), now()),
        )


def word_lesson(word: dict, facts: dict, sentence: str, translation: str | None):
    prompt = word_prompt(word, facts, sentence, translation)
    return stream_lesson(prompt, WORD_SECTIONS, word["id"])


def sentence_lesson(sentence: str, translation: str | None, words: list[dict], facts: dict):
    prompt = sentence_prompt(sentence, translation, words, facts)
    return stream_lesson(prompt, SENTENCE_SECTIONS, f"sentence:{sentence}")
