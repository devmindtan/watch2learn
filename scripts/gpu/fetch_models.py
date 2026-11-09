"""Run on the GPU machine: download VieNeu-TTS (PyTorch) and the MOSS codec, pinned."""

import sys
from pathlib import Path

from huggingface_hub import snapshot_download

VOICES = Path(sys.argv[1])
snapshot_download(
    "pnnbao-ump/VieNeu-TTS-v3-Turbo",
    revision="61b85e3d937fbbacb387714180e8182823512523",
    local_dir=VOICES / "vieneu-torch",
    allow_patterns=[
        "update/*",
        "config.json",
        "tokenizer*",
        "special_tokens_map.json",
        "denoiser.onnx",
        "speaker_encoder.onnx",
    ],
)
snapshot_download(
    "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano",
    revision="6aa02b01e445cc585582cf0ba480bc3ea6c8dd68",
    local_dir=VOICES / "moss-torch",
)
print("VieNeu (PyTorch) and MOSS codec are ready in", VOICES)
