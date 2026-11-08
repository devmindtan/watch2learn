"""Explicitly install the local Chinese-to-Vietnamese translation model."""

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "data" / "models" / "opus-mt-zh-vi"
REPOSITORY = "manancode/opus-mt-zh-vi-ctranslate2-android"
REVISION = "3b89c3c2531af56d2d82ed85e9eda58a55147cb1"
FILES = {
    "config.json": "8f6496adfc930cbfecbe8281112197705c488fab47d34b4829b06d7f478909af",
    "model.bin": "488da6baa02675083a7f3e01e788e58e18b77e94b4cf9d2bfb4bcd4406204542",
    "shared_vocabulary.json": "acd383a08ad1f6e9f21cb8d3e860f52de1df4ef882be1b043814d7b3c3457592",
    "source.spm": "d617117f90da08f471ef72c649401748a26e9ffb22289986379a9b44f7d8810e",
    "target.spm": "eb082ee05298800b89d0cfa7101ef9e468b2554459a8e7635cb56cc17d0f3f02",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str, expected: str) -> None:
    target = TARGET / name
    if target.is_file() and sha256(target) == expected:
        return
    partial = TARGET / f"{name}.part"
    url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Watch2Learn/0.3"})
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256(partial)
        if actual != expected:
            raise RuntimeError(f"{name} checksum mismatch: expected {expected}, got {actual}")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    print("Installing OPUS-MT zh->vi for CTranslate2 (Apache-2.0, about 83 MB)...")
    for name, expected in FILES.items():
        fetch(name, expected)
    (TARGET / "SOURCE.json").write_text(
        json.dumps(
            {
                "repository": REPOSITORY,
                "source": f"https://huggingface.co/{REPOSITORY}",
                "revision": REVISION,
                "original_model": "https://huggingface.co/Helsinki-NLP/opus-mt-zh-vi",
                "license": "Apache-2.0",
                "files": FILES,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Translation model is ready at {TARGET}")


if __name__ == "__main__":
    main()
