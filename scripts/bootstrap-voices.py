# ruff: noqa: E501 -- pinned URLs and SHA-256 table
"""Install the pinned local voices: VieNeu-TTS (Vietnamese) and Kokoro (Chinese).

int8 graphs are used when the CPU has VNNI (they distort without it); otherwise the
fp32 graphs are downloaded. Every file is pinned to a revision and SHA-256.
"""

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "data" / "models" / "voices"

VIENEU = (
    "https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo/resolve/"
    "61b85e3d937fbbacb387714180e8182823512523"
)
VIENEU_GRAPHS = {
    "int8": {
        "onnx_int8/config.json": "a9f8d9c4b4736448ab355d1a98cfe48f5e39aecf2916c37b0806c228612e9a2d",
        "onnx_int8/tokenizer.json": "6cc6bcbe380b8c37bd9f2514e37c5dfa3e00e122c6e3125dae5c4afe48e39158",
        "onnx_int8/vieneu_acoustic_cached.onnx": (
            "f631e3387c788c3d8b9a5ac5df94952af5bc4c4d1049ff8a751e76a246fff2d4"
        ),
        "onnx_int8/vieneu_backbone_shared.data": (
            "bb683925f7c8d826fadca4f8a0252ae4d5fc5b7837c14f6857e18f4c6666588d"
        ),
        "onnx_int8/vieneu_decode_step.onnx": (
            "2c5b30bd8ccb751c58d651f44c074df10c4113efd08719adaa8e3dec6a6ce2ca"
        ),
        "onnx_int8/vieneu_prefill.onnx": (
            "c6a80dabf67c820de798f8deb7d4e0f37d81b5d76e33fbe20ab5a67f2d371f4e"
        ),
        "onnx_int8/vieneu_v3_heads.npz": (
            "fb22484baa424bbb775133a6e5f0d00d6299b2b256fbe3312a864b85b9aed01e"
        ),
    },
    "fp32": {
        "onnx_update/config.json": "17d89d414ee302a82db7b330bf57b4cdf8541569392119c81f552178cafcb79b",
        "onnx_update/tokenizer.json": "6cc6bcbe380b8c37bd9f2514e37c5dfa3e00e122c6e3125dae5c4afe48e39158",
        "onnx_update/vieneu_acoustic_cached.onnx": (
            "f631e3387c788c3d8b9a5ac5df94952af5bc4c4d1049ff8a751e76a246fff2d4"
        ),
        "onnx_update/vieneu_backbone_shared.data": (
            "c7c072193db33d0542457e2612c7272c44c4279d1cafaf0aa4c379964911db2f"
        ),
        "onnx_update/vieneu_decode_step.onnx": (
            "bedc379cea61ea5d616312750d95ad3924e055856662d19187a889a5edc24ceb"
        ),
        "onnx_update/vieneu_prefill.onnx": (
            "27f8b064f6b57b5448e95d095f1959588c005d614678045c2b97ecccf3b7a0f7"
        ),
        "onnx_update/vieneu_v3_heads.npz": (
            "fb22484baa424bbb775133a6e5f0d00d6299b2b256fbe3312a864b85b9aed01e"
        ),
    },
}
MOSS = (
    "https://huggingface.co/OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX/resolve/"
    "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae"
)
MOSS_FILES = {
    "codec_browser_onnx_meta.json": "3e291c883bb7d11ff2fe8e964e3e495519760358859f35c951254c7741592731",
    "moss_audio_tokenizer_decode_full.onnx": (
        "0fbbafe3fd4afa2a019af5c5ced204af6e2d1db044fa40f021525d2aee95b4ac"
    ),
    "moss_audio_tokenizer_decode_shared.data": (
        "e69d52e0f4e84ca27850557ee54face46632d3a5a16c89bd246c7c408466dcad"
    ),
    "moss_audio_tokenizer_decode_step.onnx": (
        "9527c86a29e1837edec1f74db57d5eeaadb3a715af3382703566460afed25855"
    ),
}
KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
KOKORO_CONFIG = (
    "https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/resolve/"
    "01e7505bd6a7a2ac4975463114c3a7650a9f7218/config.json"
)
KOKORO_MODELS = {
    "int8": (
        "kokoro-v1.1-zh.int8.onnx",
        "11751c087b4bbeed031e2b687b11dda698bd27ba0509472f960b57f835a999f7",
    ),
    "fp32": (
        "kokoro-v1.1-zh.onnx",
        "859f9ded9f53be16c24857cdab3254a45da53c3afd5ba6ef134c7de3f822e326",
    ),
}
KOKORO_FILES = {
    "voices-v1.1-zh.bin": "14cb6186c99e4f6016871405f62046c5df863ae27465cbdc4ee08be7dd703acd",
}
KOKORO_CONFIG_SHA = "bc333efa5ce4ceff433c8c8e5d027a1eca0166001e4e4a62bea2d26ff7a46890"


def cpu_has_vnni() -> bool:
    try:
        flags = Path("/proc/cpuinfo").read_text(encoding="utf-8")
    except OSError:
        return False
    return "avx512_vnni" in flags or "avx_vnni" in flags


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, target: Path, expected: str) -> None:
    if target.is_file() and sha256(target) == expected:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    print(f"  downloading {target.relative_to(TARGET)}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Watch2Learn/0.5"})
        with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256(partial)
        if actual != expected:
            raise RuntimeError(
                f"{target.name} checksum mismatch: expected {expected}, got {actual}"
            )
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    precision = "int8" if cpu_has_vnni() else "fp32"
    print(f"Installing local voices ({precision}; VieNeu-TTS v3 Turbo + Kokoro v1.1-zh)...")
    for remote, expected in VIENEU_GRAPHS[precision].items():
        fetch(f"{VIENEU}/{remote}", TARGET / "vieneu" / remote, expected)
    for name, expected in MOSS_FILES.items():
        fetch(f"{MOSS}/{name}", TARGET / "moss" / name, expected)
    model_name, model_sha = KOKORO_MODELS[precision]
    fetch(f"{KOKORO_RELEASE}/{model_name}", TARGET / "kokoro" / "model.onnx", model_sha)
    for name, expected in KOKORO_FILES.items():
        fetch(f"{KOKORO_RELEASE}/{name}", TARGET / "kokoro" / name, expected)
    fetch(KOKORO_CONFIG, TARGET / "kokoro" / "config.json", KOKORO_CONFIG_SHA)
    (TARGET / "SOURCE.json").write_text(
        json.dumps(
            {
                "precision": precision,
                "vieneu": {
                    "source": VIENEU,
                    "license": "Apache-2.0",
                    "graphs": f"onnx_{precision}",
                },
                "moss_codec": {"source": MOSS, "license": "Apache-2.0"},
                "kokoro": {
                    "model": f"{KOKORO_RELEASE}/{model_name}",
                    "config": KOKORO_CONFIG,
                    "license": "Apache-2.0 (hexgrad/Kokoro-82M-v1.1-zh); ONNX export by kokoro-onnx (MIT)",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Voices are ready at {TARGET}")


if __name__ == "__main__":
    main()
