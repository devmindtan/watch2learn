"""Explicitly install the local Mandarin ASR model outside version control."""

import json
from pathlib import Path

from faster_whisper.utils import download_model

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "data" / "models" / "faster-whisper-small"


def main() -> None:
    if (TARGET / "model.bin").is_file():
        print(f"ASR model is already ready at {TARGET}")
        return

    TARGET.mkdir(parents=True, exist_ok=True)
    print("Downloading Systran/faster-whisper-small (MIT, about 484 MB)...")
    download_model("small", output_dir=str(TARGET))
    (TARGET / "SOURCE.json").write_text(
        json.dumps(
            {
                "repository": "Systran/faster-whisper-small",
                "source": "https://huggingface.co/Systran/faster-whisper-small",
                "license": "MIT",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"ASR model is ready at {TARGET}")


if __name__ == "__main__":
    main()
