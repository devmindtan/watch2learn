"""Offline Chinese-to-Vietnamese sentence translation with a local OPUS-MT model."""

import os
import re
from functools import lru_cache
from pathlib import Path
from threading import Lock

from .mandarin_text import chinese_text

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "opus-mt-zh-vi"
MODEL_FILES = ("model.bin", "config.json", "shared_vocabulary.json", "source.spm", "target.spm")
MAX_TEXT_CHARACTERS = 500
BATCH_SIZE = 16
SPECIAL_TOKENS = {"</s>", "<s>", "<pad>", "<unk>"}
_LOCK = Lock()
WRAPPED_RE = re.compile(r"^\s*[（(【\[]\s*(.+?)\s*[）)】\]]\s*$")
MARKUP_RE = re.compile(r"\{\\[^}]*\}|<[^>]{1,40}>")
TRANSLATION_UNIT = "zh-clause-v4"


def chinese_source(text: str) -> str:
    """The part of a cue that may be translated: only Chinese is ever translated
    (clause by clause, see mandarin_text)."""
    return chinese_text(text)


def clean_output(text: str) -> str:
    """Model output is untrusted: drop subtitle/HTML markup the model sometimes emits."""
    return " ".join(MARKUP_RE.sub(" ", text).split())


def model_path() -> Path:
    return Path(os.environ.get("WATCH2LEARN_TRANSLATION_MODEL", DEFAULT_MODEL_PATH))


def model_ready() -> bool:
    path = model_path()
    return all((path / name).is_file() for name in MODEL_FILES)


def provenance() -> dict:
    return {
        "target_language": "vi",
        "available": model_ready(),
        "model": model_path().name,
        "method": "machine-translation",
    }


@lru_cache(maxsize=1)
def load_model():
    if not model_ready():
        raise RuntimeError(
            "Translation model is missing; run pnpm setup:translation once to enable it"
        )
    import ctranslate2
    import sentencepiece

    path = model_path()
    translator = ctranslate2.Translator(
        str(path),
        device="cpu",
        compute_type="int8",
        inter_threads=1,
        intra_threads=max(1, min(4, os.cpu_count() or 1)),
    )
    source = sentencepiece.SentencePieceProcessor(model_file=str(path / "source.spm"))
    target = sentencepiece.SentencePieceProcessor(model_file=str(path / "target.spm"))
    return translator, source, target


def translate_to_vietnamese(texts: list[str]) -> list[str]:
    """Translate Chinese lines in order; blank input yields blank output."""
    translator, source, target = load_model()
    results = [""] * len(texts)
    pending = []
    wrapped = set()
    for index, text in enumerate(texts):
        text = (text or "").strip()[:MAX_TEXT_CHARACTERS]
        if not text:
            continue
        match = WRAPPED_RE.match(text)
        if match:  # stage directions like （轻轻地哼着歌）: translate the inside only
            wrapped.add(index)
            text = match.group(1)
        pending.append((index, text))
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        tokens = [source.encode(text, out_type=str) + ["</s>"] for _, text in batch]
        with _LOCK:
            outputs = translator.translate_batch(
                tokens, beam_size=4, max_decoding_length=256, max_batch_size=BATCH_SIZE
            )
        for (index, _), output in zip(batch, outputs, strict=True):
            pieces = [piece for piece in output.hypotheses[0] if piece not in SPECIAL_TOKENS]
            result = clean_output(target.decode(pieces))
            results[index] = f"({result.rstrip('.')})" if index in wrapped and result else result
    return results


# Subtitle cues are usually whole sentences (and Chinese subtitles often omit
# punctuation), so only an explicit trailing comma/colon/dash marks a split sentence.
CONTINUATION_END = tuple("，,、：:—")
MAX_GROUP_GAP_MS = 700
MAX_GROUP_CHARACTERS = 60
MAX_GROUP_CUES = 3


def sentence_groups(cues: list) -> list[list[int]]:
    """Join cues that split one sentence so it is translated as a whole.

    A cue continues into the next when both are Chinese, it ends with a comma-like
    mark, the pause is short, and the joined text stays sentence-sized.
    """
    chinese = [bool(chinese_source(cue.text)) for cue in cues]
    groups: list[list[int]] = []
    current: list[int] = []
    length = 0
    for index, cue in enumerate(cues):
        current.append(index)
        length += len(cue.text)
        following = cues[index + 1] if index + 1 < len(cues) else None
        continues = (
            following is not None
            and chinese[index]
            and chinese[index + 1]
            and cue.text.rstrip().endswith(CONTINUATION_END)
            and following.start_ms - cue.end_ms <= MAX_GROUP_GAP_MS
            and length + len(following.text) <= MAX_GROUP_CHARACTERS
            and len(current) < MAX_GROUP_CUES
        )
        if not continues:
            groups.append(current)
            current, length = [], 0
    return groups


def join_cue_text(texts: list[str]) -> str:
    joined = ""
    for text in texts:
        text = text.strip()
        if joined and not joined.endswith(("，", ",", "、", "：", ":")):
            joined += "，"
        joined += text
    return joined


def translate_cues_in_context(cues: list) -> list[dict]:
    """Per cue: the Vietnamese translation of the sentence it belongs to."""
    groups = sentence_groups(cues)
    sentences = translate_to_vietnamese(
        [join_cue_text([chinese_source(cues[index].text) for index in group]) for group in groups]
    )
    rows: list[dict] = [{} for _ in cues]
    for group, sentence in zip(groups, sentences, strict=True):
        for index in group:
            rows[index] = {
                "translation_vi": sentence if chinese_source(cues[index].text) else "",
                "translation_skipped": None if chinese_source(cues[index].text) else "not-chinese",
                "translation_group": cues[group[0]].id,
                "translation_group_end": cues[group[-1]].id,
            }
    return rows
