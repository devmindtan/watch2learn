"""Spoken-style usage explanations from a local Ollama model, cached per word context.

Dictionary meaning and pinyin stay the source of truth (the UI reads them from the
lesson); the model only adds "when/where is this used" in Vietnamese and is
labelled as AI-generated. Nothing leaves the machine.
"""

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

from .jobs import connect, initialize, now

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"
TIMEOUT_SECONDS = 300
SYSTEM_PROMPT = (
    "Bạn là giáo viên tiếng Trung cho người Việt. Trả lời hoàn toàn bằng tiếng Việt tự nhiên, "
    "ngắn gọn, để đọc thành tiếng. Không dùng markdown, không gạch đầu dòng, không viết pinyin. "
    "Chữ Trung Quốc chỉ dùng giản thể. Chỉ nói điều bạn chắc chắn; nếu không chắc thì nói rõ."
)


def ollama_url() -> str:
    return os.environ.get("WATCH2LEARN_OLLAMA_URL", DEFAULT_URL).rstrip("/")


def model_name() -> str:
    return os.environ.get("WATCH2LEARN_OLLAMA_MODEL", DEFAULT_MODEL)


def model_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{ollama_url()}/api/tags", timeout=1.5) as response:
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


def prompt_for(word: dict, sentence: str, translation: str | None) -> str:
    meanings = "; ".join(item for item in word.get("definitions_vi", []) if ":" not in item[:3])
    return (
        f"Từ: {word['word']}. Nghĩa trong từ điển: {meanings or 'chưa có'}.\n"
        f"Câu trong video: {sentence}\n"
        f"Bản dịch máy của câu: {translation or 'chưa có'}\n\n"
        "Giải thích trong ba ý ngắn, viết liền thành đoạn văn để đọc: "
        "thứ nhất, trong câu này từ đó mang nghĩa gì; "
        "thứ hai, người Trung Quốc thường dùng từ này khi nào và ở đâu trong đời sống "
        "(tình huống, trang trọng hay thân mật); "
        "thứ ba, một câu ví dụ ngắn, đơn giản bằng chữ Hán kèm nghĩa tiếng Việt. "
        "Tổng cộng dưới 110 từ."
    )


def clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"[*#`_>]+", "", text)
    text = re.sub(r"^\s*[-•\d]+[.)]?\s+", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


def ask_ollama(prompt: str) -> str:
    body = json.dumps(
        {
            "model": model_name(),
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.3, "num_predict": 400},
        }
    ).encode()
    request = urllib.request.Request(
        f"{ollama_url()}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)["message"]["content"]


def explain_word(word: dict, sentence: str, translation: str | None) -> dict:
    prompt = prompt_for(word, sentence, translation)
    key = hashlib.sha256(f"{model_name()}\n{prompt}".encode()).hexdigest()
    initialize_cache()
    with connect() as connection:
        row = connection.execute(
            "SELECT text, model FROM explanations WHERE cache_key = ?", (key,)
        ).fetchone()
    if row:
        return {"text": row["text"], "model": row["model"], "cached": True, "source": "ai-local"}
    text = clean(ask_ollama(prompt))
    if not text:
        raise RuntimeError("The local model returned an empty explanation")
    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO explanations VALUES (?, ?, ?, ?, ?)",
            (key, word["id"], model_name(), text, now()),
        )
    return {"text": text, "model": model_name(), "cached": False, "source": "ai-local"}
