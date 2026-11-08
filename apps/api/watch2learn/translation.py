"""Offline Chinese-to-Vietnamese sentence translation with a local OPUS-MT model."""

import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "opus-mt-zh-vi"
MODEL_FILES = ("model.bin", "config.json", "shared_vocabulary.json", "source.spm", "target.spm")
MAX_TEXT_CHARACTERS = 500
BATCH_SIZE = 16
SPECIAL_TOKENS = {"</s>", "<s>", "<pad>", "<unk>"}
_LOCK = Lock()


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
    pending = [
        (index, text.strip()[:MAX_TEXT_CHARACTERS])
        for index, text in enumerate(texts)
        if text and text.strip()
    ]
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        tokens = [source.encode(text, out_type=str) + ["</s>"] for _, text in batch]
        with _LOCK:
            outputs = translator.translate_batch(
                tokens, beam_size=4, max_decoding_length=256, max_batch_size=BATCH_SIZE
            )
        for (index, _), output in zip(batch, outputs, strict=True):
            pieces = [piece for piece in output.hypotheses[0] if piece not in SPECIAL_TOKENS]
            results[index] = target.decode(pieces).strip()
    return results
