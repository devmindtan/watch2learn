"""Local text-to-speech with Piper voices, so audio works in every browser.

Chrome on Linux exposes no speech voices by default, so the browser's Web Speech
API cannot be relied on. Chinese is voiced from our own context-aware pinyin (the
`chaowen` voice takes pinyin phonemes), which avoids Piper's heavy g2pW extra and
keeps the spoken reading identical to the reading shown to the learner.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

from .lesson import contextual_readings, to_simplified
from .media import media_binary
from .pronunciation import split_syllable

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VOICE_DIR = PROJECT_ROOT / "data" / "models" / "piper"
CACHE_DIR = PROJECT_ROOT / "data" / "tts-cache"
VOICES = {"zh": "zh_CN-chaowen-medium", "vi": "vi_VN-vais1000-medium"}
SAMPLE_RATE = 22050
PAUSE_SECONDS = 0.25
GROUP_END = set("12345。？！.?!—…、，：；,:; ")
MAX_PARTS = 60
MAX_CHARACTERS = 3000


def voice_dir() -> Path:
    return Path(os.environ.get("WATCH2LEARN_VOICE_DIR", VOICE_DIR))


def voices_ready() -> bool:
    return all(
        (voice_dir() / f"{name}{suffix}").is_file()
        for name in VOICES.values()
        for suffix in (".onnx", ".onnx.json")
    )


@lru_cache(maxsize=2)
def load_voice(lang: str):
    from piper import PiperVoice

    return PiperVoice.load(str(voice_dir() / f"{VOICES[lang]}.onnx"))


def chinese_phoneme_ids(voice, text: str) -> list[int]:
    id_map = voice.config.phoneme_id_map
    ids = list(id_map["^"])
    simplified = to_simplified(text)
    for character, reading in zip(simplified, contextual_readings(simplified), strict=True):
        if reading:
            initial, final, tone = split_syllable(reading)
            phonemes = (initial or "Ø", final, tone)
            if not all(phoneme in id_map for phoneme in phonemes):
                continue
            for phoneme in phonemes:
                ids.extend(id_map[phoneme])
                if phoneme in GROUP_END:
                    ids.extend(id_map["_"])
        elif character in id_map:
            ids.extend(id_map[character] + id_map["_"])
    return ids + list(id_map["$"])


def to_int16(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < 1e-8:
        return np.zeros(audio.shape, dtype=np.int16)
    return (audio / peak * 32767 * 0.9).astype(np.int16)


def synthesize_part(text: str, lang: str, rate: float) -> np.ndarray:
    from piper.config import SynthesisConfig

    voice = load_voice(lang)
    config = SynthesisConfig(length_scale=1.0 / max(0.5, min(1.5, rate)))
    if lang == "zh":
        ids = chinese_phoneme_ids(voice, text)
        if len(ids) <= 2:
            return np.zeros(0, dtype=np.int16)
        return to_int16(voice.phoneme_ids_to_audio(ids, config))
    chunks = [
        np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
        for chunk in voice.synthesize(text, config)
    ]
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)


def cache_key(parts: list[dict]) -> str:
    payload = json.dumps([VOICES, parts], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def synthesize(parts: list[dict]) -> Path:
    """Speak parts [{text, lang: zh|vi, rate}] in order → cached AAC (.m4a) file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / f"{cache_key(parts)}.m4a"
    if target.is_file():
        return target
    pause = np.zeros(int(SAMPLE_RATE * PAUSE_SECONDS), dtype=np.int16)
    pieces = []
    for part in parts:
        audio = synthesize_part(part["text"], part["lang"], part.get("rate", 1.0))
        if audio.size:
            pieces.extend([audio, pause])
    if not pieces:
        raise ValueError("Nothing to read aloud")
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as work:
        wav_path = Path(work) / "speech.wav"
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(np.concatenate(pieces).tobytes())
        partial = Path(work) / "speech.m4a"
        subprocess.run(
            [
                str(media_binary("ffmpeg")),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(wav_path),
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                str(partial),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        os.replace(partial, target)
    return target
