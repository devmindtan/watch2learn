#!/usr/bin/env bash
# Watch2Learn speech worker on the GPU machine (WSL). Started by the laptop inside an
# SSH session that also carries the tunnel (127.0.0.1:8912 there). Loopback only.
BASE=$HOME/watch2learn-gpu
if curl -fsS -m 2 http://127.0.0.1:8911/health >/dev/null 2>&1; then echo "already running"; exec sleep infinity; fi
cd "$BASE/app" || exit 1
SITE=$(echo "$BASE"/.venv/lib/python3*/site-packages)
export LD_LIBRARY_PATH="$SITE/nvidia/cublas/lib:$SITE/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
export WATCH2LEARN_DEVICE=cuda WATCH2LEARN_GPU=off PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 \
  WATCH2LEARN_WHISPER_MODEL=$BASE/data/models/faster-whisper-small \
  WATCH2LEARN_VOICE_DIR=$BASE/data/models/voices WATCH2LEARN_WORKER_TMP=$BASE/tmp
echo "== start $(date '+%F %T')" >> "$BASE/server.log"
exec "$BASE/.venv/bin/python" -m uvicorn watch2learn.worker:app --app-dir apps/api \
  --host 127.0.0.1 --port 8911 >> "$BASE/server.log" 2>&1
