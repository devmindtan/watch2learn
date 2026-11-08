"""Install a pinned, checksummed CC-CEDICT snapshot from a redistribution mirror."""

import gzip
import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICTIONARY_DIR = PROJECT_ROOT / "data" / "dictionaries"
TARGET = DICTIONARY_DIR / "cedict_ts.u8"
SOURCE_METADATA = DICTIONARY_DIR / "SOURCE.json"
URL = (
    "https://github.com/oxalis-ink/cc-cedict/releases/download/"
    "1.0%2B20261007032622/cedict_1_0_ts_utf-8_mdbg.txt.gz"
)
EXPECTED_SHA256 = "00e6c188df0056c42c0448386d0b4f532aa805d9fdd87aef139f72b421ace2f4"


def main() -> None:
    if TARGET.is_file():
        print(f"CC-CEDICT is already ready at {TARGET}")
        return

    DICTIONARY_DIR.mkdir(parents=True, exist_ok=True)
    archive = DICTIONARY_DIR / "cedict.txt.gz.part"
    extracted = DICTIONARY_DIR / "cedict_ts.u8.part"
    try:
        request = urllib.request.Request(URL, headers={"User-Agent": "Watch2Learn/0.2"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != EXPECTED_SHA256:
            raise RuntimeError(
                f"CC-CEDICT checksum mismatch: expected {EXPECTED_SHA256}, got {digest}"
            )
        with gzip.open(archive, "rb") as source, extracted.open("wb") as output:
            shutil.copyfileobj(source, output)
        os.replace(extracted, TARGET)
        SOURCE_METADATA.write_text(
            json.dumps(
                {
                    "source": URL,
                    "snapshot": "1.0+20261007032622",
                    "sha256": EXPECTED_SHA256,
                    "license": "CC BY-SA 4.0",
                    "attribution": "MDBG and the CC-CEDICT editors and contributors",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"CC-CEDICT is ready at {TARGET}")
    finally:
        archive.unlink(missing_ok=True)
        extracted.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
