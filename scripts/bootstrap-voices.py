"""Install the pinned Piper voices used to read Chinese and Vietnamese aloud."""

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "data" / "models" / "piper"
REPOSITORY = "rhasspy/piper-voices"
REVISION = "e7229f7d33a10e145e109b886d661984201ac3c4"
FILES = {
    "zh/zh_CN/chaowen/medium/zh_CN-chaowen-medium.onnx": (
        "820d64ac16048fbcf38dd0823d37fab5f5e0c2bd71b01ca5a50f553fac19e746"
    ),
    "zh/zh_CN/chaowen/medium/zh_CN-chaowen-medium.onnx.json": (
        "a6bb2caafa0645642f13cbf7e2f6fbbb16fded66e51109fc26d622f6472fa16f"
    ),
    "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx": (
        "ec7c89e2c85f4d1edc24b6120c18aaf1bda614f06b511567eb9c7c0de15e2dab"
    ),
    "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json": (
        "fafb9da1354ed4b77c31af228ed41fb41cd825c14cffa105454b25e6ae751ee0"
    ),
}
LICENSES = {
    "zh_CN-chaowen-medium": "Piper voice; dataset CC0 (OHF-Voice/voice-datasets)",
    "vi_VN-vais1000-medium": "Piper voice; VAIS-1000 dataset CC BY 4.0 (attribution required)",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(remote: str, expected: str) -> None:
    target = TARGET / Path(remote).name
    if target.is_file() and sha256(target) == expected:
        return
    partial = target.with_name(target.name + ".part")
    url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{remote}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Watch2Learn/0.4"})
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256(partial)
        if actual != expected:
            raise RuntimeError(f"{remote} checksum mismatch: expected {expected}, got {actual}")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    print("Installing Piper voices zh_CN-chaowen and vi_VN-vais1000 (about 126 MB)...")
    for remote, expected in FILES.items():
        fetch(remote, expected)
    (TARGET / "SOURCE.json").write_text(
        json.dumps(
            {
                "repository": REPOSITORY,
                "revision": REVISION,
                "files": FILES,
                "licenses": LICENSES,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Voices are ready at {TARGET}")


if __name__ == "__main__":
    main()
