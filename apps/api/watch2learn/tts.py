"""Local text-to-speech: VieNeu-TTS v3 Turbo (Vietnamese) and Kokoro v1.1-zh (Chinese).

Audio is produced on the backend because Chrome on Linux exposes no Web Speech
voices. Both models run on CPU through ONNX Runtime; outputs are resampled to
24 kHz, loudness-matched so the two voices sound alike in level, and cached as AAC.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

from .media import media_binary

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VOICE_DIR = PROJECT_ROOT / "data" / "models" / "voices"
CACHE_DIR = PROJECT_ROOT / "data" / "tts-cache"
SAMPLE_RATE = 24_000
VIENEU_RATE = 48_000
PAUSE_SECONDS = 0.3
TARGET_RMS = 0.08
MAX_PARTS = 60
MAX_CHARACTERS = 3000
DEFAULT_VOICES = {"vi": "Ngọc Huyền", "zh": "zf_001"}
CHINESE_VOICES = [
    ("zf_001", "Nữ 1"),
    ("zf_002", "Nữ 2"),
    ("zf_003", "Nữ 3"),
    ("zf_004", "Nữ 4"),
    ("zf_005", "Nữ 5"),
    ("zm_009", "Nam 1"),
    ("zm_010", "Nam 2"),
    ("zm_011", "Nam 3"),
    ("zm_012", "Nam 4"),
    ("zm_013", "Nam 5"),
]
_VIENEU_LOCK = threading.Lock()
_KOKORO_LOCK = threading.Lock()


def voice_dir() -> Path:
    return Path(os.environ.get("WATCH2LEARN_VOICE_DIR", VOICE_DIR))


def vieneu_graphs() -> Path | None:
    for name in ("onnx_int8", "onnx_update"):
        path = voice_dir() / "vieneu" / name
        if (path / "config.json").is_file():
            return path
    return None


def on_cuda() -> bool:
    return os.environ.get("WATCH2LEARN_DEVICE") == "cuda"  # set on the GPU worker


def vieneu_torch_ready() -> bool:
    root = voice_dir()
    return (root / "vieneu-torch" / "update" / "model.safetensors").is_file() and (
        root / "moss-torch" / "config.json"
    ).is_file()


def voices_ready() -> bool:
    root = voice_dir()
    vietnamese = (
        vieneu_torch_ready()
        if on_cuda()
        else vieneu_graphs() is not None
        and (root / "moss" / "moss_audio_tokenizer_decode_full.onnx").is_file()
    )
    return vietnamese and all(
        (root / "kokoro" / name).is_file()
        for name in ("model.onnx", "voices-v1.1-zh.bin", "config.json")
    )


@lru_cache(maxsize=1)
def vieneu():
    from vieneu import Vieneu
    from vieneu._v3_turbo_engine import onnx_runtime_lite

    if on_cuda():  # the author's GPU path: PyTorch model + MOSS codec from pinned local copies
        return Vieneu(
            backbone_repo=str(voice_dir() / "vieneu-torch"),
            moss_tokenizer=str(voice_dir() / "moss-torch"),
            device="cuda",
        )

    # The SDK does not forward `codec_dir`; point it at our pinned local copy so the
    # codec is not looked up in the Hugging Face cache (whose symlinked external
    # data newer ONNX Runtime versions refuse to load).
    codec_dir = str(voice_dir() / "moss")
    original = onnx_runtime_lite.OnnxV3LiteEngine.__init__

    def init(self, *args, **kwargs):
        kwargs.setdefault("codec_dir", codec_dir)
        original(self, *args, **kwargs)

    onnx_runtime_lite.OnnxV3LiteEngine.__init__ = init
    graphs = vieneu_graphs()
    return Vieneu(
        backbone_repo=str(voice_dir() / "vieneu"),
        onnx_dir=str(graphs),
        precision="int8" if graphs.name == "onnx_int8" else "fp32",
    )


@lru_cache(maxsize=1)
def kokoro():
    import onnxruntime
    from misaki import zh

    root = voice_dir() / "kokoro"
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = max(1, min(7, (os.cpu_count() or 2) - 1))
    session = onnxruntime.InferenceSession(
        str(root / "model.onnx"), options, providers=["CPUExecutionProvider"]
    )
    vocab = json.loads((root / "config.json").read_text(encoding="utf-8"))["vocab"]
    styles = dict(np.load(root / "voices-v1.1-zh.bin"))
    return session, vocab, styles, zh.ZHG2P(version="1.1")


def available_voices() -> dict:
    with _VIENEU_LOCK:
        vietnamese = [{"id": name, "label": label} for label, name in vieneu().list_preset_voices()]
    chinese = [{"id": name, "label": label} for name, label in CHINESE_VOICES]
    return {"vi": vietnamese, "zh": chinese}


def loudness_matched(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
    if rms < 1e-6:
        return audio
    return np.clip(audio * (TARGET_RMS / rms), -0.98, 0.98)


def speak_vietnamese(text: str, voice: str) -> np.ndarray:
    import soxr

    with _VIENEU_LOCK:
        audio = vieneu().infer(text, voice=voice)
    return soxr.resample(np.asarray(audio, dtype=np.float32), VIENEU_RATE, SAMPLE_RATE)


def speak_chinese(text: str, voice: str, rate: float) -> np.ndarray:
    session, vocab, styles, g2p = kokoro()
    with _KOKORO_LOCK:
        phonemes, _tokens = g2p(text)
    ids = [vocab[symbol] for symbol in phonemes if symbol in vocab][:500]
    if not ids:
        return np.zeros(0, dtype=np.float32)
    style = styles[voice][min(len(ids), len(styles[voice]) - 1)]
    audio = session.run(
        None,
        {
            "input_ids": np.array([[0, *ids, 0]], dtype=np.int64),
            "style": np.asarray(style, dtype=np.float32).reshape(1, -1),
            "speed": np.array([max(0.5, min(1.5, rate))], dtype=np.float32),
        },
    )[0]
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def part_audio(part: dict, voices: dict) -> np.ndarray:
    """One part's loudness-matched audio, cached on disk: fixed phrases (section
    titles, tone descriptions, a word read slowly) recur across lessons."""
    lang = part["lang"]
    voice = voices[lang]
    rate = round(float(part.get("rate", 1.0)), 2)
    payload = json.dumps(["part-1", lang, voice, rate, part["text"]], ensure_ascii=False)
    path = CACHE_DIR / "parts" / f"{hashlib.sha256(payload.encode()).hexdigest()}.npy"
    if path.is_file():
        return np.load(path)
    if lang == "zh":
        audio = speak_chinese(part["text"], voice, rate)
    else:
        audio = speak_vietnamese(part["text"], voice)
    audio = loudness_matched(audio)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.stem + ".part.npy")
    np.save(partial, audio)
    os.replace(partial, path)
    return audio


COMMON_PHRASES = [
    "Từ này đọc thế nào.",
    "Câu này đọc thế nào.",
    "Từ này đọc là",
    "Câu này đọc là",
    "Đọc chậm lại:",
    "Chữ",
    "Nghĩa là gì.",
    "Lưu ý khi phát âm.",
    "Thường gặp ở đâu trong giao tiếp.",
    "Sử dụng thực tế như thế nào.",
    "Cấu trúc câu.",
    "Thường nói khi nào, ở đâu.",
    "Câu trong video là:",
    "Ví dụ:",
    "Từng từ trong câu:",
    "thanh 1, giọng cao và đều.",
    "thanh 2, giọng đi lên, gần giống dấu sắc.",
    "thanh 3, giọng hạ thấp rồi lên, gần giống dấu hỏi.",
    "thanh 4, giọng rơi mạnh từ cao xuống.",
    "thanh nhẹ, đọc ngắn và nhẹ.",
]


def warm_up(voices: dict) -> None:
    """Load both models and pre-read the fixed lesson phrases (run in background)."""
    voices = DEFAULT_VOICES | voices
    for phrase in COMMON_PHRASES:
        part_audio({"text": phrase, "lang": "vi", "rate": 1.0}, voices)
    part_audio({"text": "你好", "lang": "zh", "rate": 0.8}, voices)


def cache_key(parts: list[dict], voices: dict) -> str:
    payload = json.dumps(["vieneu-kokoro-1", voices, parts], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def synthesize(parts: list[dict], voices: dict | None = None) -> Path:
    """Speak parts [{text, lang: zh|vi, rate}] in order with the chosen voices → .m4a."""
    voices = DEFAULT_VOICES | (voices or {})
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / f"{cache_key(parts, voices)}.m4a"
    if target.is_file():
        return target
    pause = np.zeros(int(SAMPLE_RATE * PAUSE_SECONDS), dtype=np.float32)
    pieces = []
    for part in parts:
        audio = part_audio(part, voices)
        if audio.size:
            pieces.extend([audio, pause])
    if not pieces:
        raise ValueError("Nothing to read aloud")
    samples = (np.concatenate(pieces) * 32767).astype(np.int16)
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as work:
        wav_path = Path(work) / "speech.wav"
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(samples.tobytes())
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
