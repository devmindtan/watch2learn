#!/usr/bin/env bash
# Install or update the Watch2Learn speech worker on the GPU machine (docs/gpu-host.md).
# Runs on the laptop; everything on the GPU machine lives in ~/watch2learn-gpu (WSL).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
HOST=${WATCH2LEARN_GPU_HOST:-$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['host'])" "$ROOT/.gpu/host.json")}
[[ "$HOST" =~ ^[A-Za-z0-9._@-]+$ ]] || { echo "Invalid GPU host: $HOST" >&2; exit 1; }
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" wsl -e bash -lc)
remote() { "${SSH[@]}" "\"$1\""; }
BASE='$HOME/watch2learn-gpu'
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

echo "1/6 Requirements (pyproject direct deps + PyTorch 2.8 CUDA 12.8, as other GPU services)"
# Direct dependencies only (the worker adds transformers, whose pins differ from the
# laptop lock); yt-dlp is not needed on the worker.
python3 - "$ROOT/pyproject.toml" > "$TMP/requirements-gpu.txt" <<'PY'
import sys, tomllib
data = tomllib.load(open(sys.argv[1], "rb"))
for spec in data["project"]["dependencies"] + data["dependency-groups"]["asr"]:
    if not spec.startswith("yt-dlp"):
        print(spec)
PY
printf 'torch==2.8.0\ntorchaudio==2.8.0\ntransformers==4.57.6\n' >> "$TMP/requirements-gpu.txt"

echo "2/6 Code"
remote "mkdir -p $BASE/app $BASE/bin $BASE/tmp $BASE/data/models/voices && rm -rf $BASE/app/apps $BASE/app/scripts"
tar -C "$ROOT" -czf - pyproject.toml apps/api/watch2learn scripts/gpu -C "$TMP" requirements-gpu.txt \
  | "${SSH[@]}" "\"tar -xzf - -C $BASE/app\""

echo "3/6 Tools (uv, ffmpeg)"
remote "test -x $BASE/bin/uv" || cat "$(command -v uv)" | "${SSH[@]}" "\"cat > $BASE/bin/uv && chmod +x $BASE/bin/uv\""
if ! remote "test -x $BASE/app/.tools/bin/ffmpeg || command -v ffmpeg >/dev/null"; then
  remote "mkdir -p $BASE/app/.tools/bin"
  cat "$ROOT/.tools/bin/ffmpeg" | "${SSH[@]}" "\"cat > $BASE/app/.tools/bin/ffmpeg && chmod +x $BASE/app/.tools/bin/ffmpeg\""
fi

echo "4/6 Python environment (CUDA)"
remote "cd $BASE && bin/uv venv --allow-existing --python 3.12 .venv >/dev/null && bin/uv pip install --python .venv/bin/python -r app/requirements-gpu.txt --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match"

echo "5/6 Models (pinned copies from this laptop; VieNeu PyTorch + codec downloaded there)"
for dir in faster-whisper-small voices/kokoro; do
  if ! remote "test -d $BASE/data/models/$dir"; then
    tar -C "$ROOT/data/models" -cf - "$dir" | "${SSH[@]}" "\"tar -xf - -C $BASE/data/models\""
  fi
done
remote "cd $BASE && .venv/bin/python app/scripts/gpu/fetch_models.py $BASE/data/models/voices"

echo "6/6 Service scripts"
remote "cp $BASE/app/scripts/gpu/run.sh $BASE/app/scripts/gpu/stop.sh $BASE/ && chmod +x $BASE/run.sh $BASE/stop.sh"
echo "Done. The backend will use it automatically when the GPU machine is on."
