# GPU machine over Tailscale

The laptop has no graphics card. Heavy models run on the user's GPU machine
`desktop-kndgm60` (Windows 10 + WSL2 Ubuntu 24.04, GTX 1660 SUPER 6 GB) when it is on,
following the same pattern as the sibling project `20-repo-generate-video`
(`docs/architecture/gpu-host.md` there). Rule: **use the GPU machine when it is on;
run on the laptop only when it is not usable.**

| Service | Used for | On the GPU machine (WSL) | Laptop port | Fallback |
|---|---|---|---|---|
| Ollama (`qwen3:8b`), shared with the sibling project | AI parts of word/sentence lessons | `~/ollama-gpu` → 127.0.0.1:11434 | 127.0.0.1:11435 | laptop Ollama 127.0.0.1:11434 |
| Watch2Learn speech worker | Whisper ASR (video + pronunciation), VieNeu/Kokoro TTS | `~/watch2learn-gpu` → 127.0.0.1:8911 | 127.0.0.1:8912 | same models on the laptop CPU |

## How it connects

- Configuration: `.gpu/host.json` (`{"host": "desktop-kndgm60"}`, Git-ignored) or
  `WATCH2LEARN_GPU_HOST`; `WATCH2LEARN_GPU=off` forces the laptop. SSH uses the
  existing `Host desktop-kndgm60` entry (`~/.ssh/config`, key `~/.ssh/id_ed25519_gpu`).
- `apps/api/watch2learn/gpu_host.py`: one SSH round trip (`ss -ltnH` + `test -x
  <dir>/run.sh`, cached 60 s) decides GPU or laptop and records the reason. The GPU
  is skipped when it is off, the service is not installed, or another project's
  heavy model (VoiceStudio 3900, ComfyUI 8188) holds the card.
- A service is started by one SSH process that runs `<dir>/run.sh` in the
  foreground and forwards it to a laptop loopback port (`ssh -L`); nothing listens
  on the tailnet. If the port already answers (tunnel from the sibling project), it
  is reused. Tunnels close after 10 idle minutes (`WATCH2LEARN_GPU_IDLE_SECONDS`) and
  on backend shutdown; services started by Watch2Learn are stopped with `stop.sh`
  so VRAM is freed.
- Callers fall back to the laptop on any GPU error: `remote_speech.py` (TTS, ASR,
  voices) and `explain.ollama_url()`. Health checks never open tunnels.
- `/api/health` returns `gpu` (configured host, active tunnels, last reason).

## Install / update the speech worker

```bash
pnpm gpu:install   # scripts/gpu/install-worker.sh
pnpm gpu:status    # which machine each service would use now, and why
```

The installer ships the backend package, `uv`, ffmpeg and the pinned laptop models
(faster-whisper-small, Kokoro) over SSH, creates `~/watch2learn-gpu/.venv` with
PyTorch 2.8.0 + CUDA 12.8 (the version VoiceStudio already runs on this driver),
downloads the pinned VieNeu PyTorch weights and MOSS codec there
(`scripts/gpu/fetch_models.py`; the codec loads with `trust_remote_code`, pinned to a
revision) and installs `run.sh`/`stop.sh`. The worker (`watch2learn.worker`) runs
with `WATCH2LEARN_DEVICE=cuda`: Whisper float16 on CUDA, VieNeu via PyTorch on CUDA,
Kokoro on the GPU machine's CPU. Remove: `~/watch2learn-gpu/stop.sh`, then delete
the directory.

## Card sharing

The 6 GB card holds `qwen3:8b` only partly (27/37 layers). Watch2Learn's own two
services may run together: Ollama sizes its GPU layers to the free VRAM when it
loads. Other projects' heavy services make Watch2Learn fall back to the laptop.
