"""Install pinned, checksummed offline dictionaries (CC-CEDICT and CVDICT)."""

import gzip
import hashlib
import json
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DICTIONARY_DIR = PROJECT_ROOT / "data" / "dictionaries"


@dataclass(frozen=True)
class DictionarySource:
    name: str
    target: str
    url: str
    sha256: str
    snapshot: str
    attribution: str
    gzipped: bool


SOURCES = (
    DictionarySource(
        name="CC-CEDICT",
        target="cedict_ts.u8",
        url=(
            "https://github.com/oxalis-ink/cc-cedict/releases/download/"
            "1.0%2B20261007032622/cedict_1_0_ts_utf-8_mdbg.txt.gz"
        ),
        sha256="00e6c188df0056c42c0448386d0b4f532aa805d9fdd87aef139f72b421ace2f4",
        snapshot="1.0+20261007032622",
        attribution="MDBG and the CC-CEDICT editors and contributors",
        gzipped=True,
    ),
    DictionarySource(
        name="CVDICT",
        target="cvdict.u8",
        url=(
            "https://raw.githubusercontent.com/ph0ngp/CVDICT/"
            "c379d909e308343a247e51619f7839a2060a271c/CVDICT.u8"
        ),
        sha256="4dde4b204193efa9c192d7f7daeab1bb579c8ccd7c41ed90d1b6caee22ba0948",
        snapshot="c379d909e308343a247e51619f7839a2060a271c",
        attribution="Phong Phan (CVDICT), based on CC-CEDICT",
        gzipped=False,
    ),
)


def install(source: DictionarySource) -> None:
    target = DICTIONARY_DIR / source.target
    if target.is_file():
        print(f"{source.name} is already ready at {target}")
        return

    download = DICTIONARY_DIR / f"{source.target}.download.part"
    extracted = DICTIONARY_DIR / f"{source.target}.part"
    try:
        request = urllib.request.Request(source.url, headers={"User-Agent": "Watch2Learn/0.3"})
        with urllib.request.urlopen(request, timeout=60) as response, download.open("wb") as output:
            shutil.copyfileobj(response, output)
        digest = hashlib.sha256(download.read_bytes()).hexdigest()
        if digest != source.sha256:
            raise RuntimeError(
                f"{source.name} checksum mismatch: expected {source.sha256}, got {digest}"
            )
        if source.gzipped:
            with gzip.open(download, "rb") as compressed, extracted.open("wb") as output:
                shutil.copyfileobj(compressed, output)
        else:
            os.replace(download, extracted)
        os.replace(extracted, target)
        print(f"{source.name} is ready at {target}")
    finally:
        download.unlink(missing_ok=True)
        extracted.unlink(missing_ok=True)


def main() -> None:
    DICTIONARY_DIR.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        install(source)
    (DICTIONARY_DIR / "SOURCE.json").write_text(
        json.dumps(
            {
                source.target: {
                    "name": source.name,
                    "source": source.url,
                    "snapshot": source.snapshot,
                    "sha256": source.sha256,
                    "license": "CC BY-SA 4.0",
                    "attribution": source.attribution,
                }
                for source in SOURCES
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
