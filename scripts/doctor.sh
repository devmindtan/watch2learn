#!/usr/bin/env bash
set -uo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$project_root/.tools/bin:$PATH"

ci_mode=false
if [[ "${1:-}" == "--ci" ]]; then
  ci_mode=true
fi

required=(git node pnpm python3 uv ffmpeg ffprobe yt-dlp)
optional=(docker graphify)
missing=0

for tool_name in "${required[@]}"; do
  if command -v "$tool_name" >/dev/null 2>&1; then
    echo "ok       $tool_name"
  else
    echo "missing  $tool_name"
    missing=1
  fi
done

for tool_name in "${optional[@]}"; do
  if command -v "$tool_name" >/dev/null 2>&1; then
    echo "ok       $tool_name (optional)"
  else
    echo "optional $tool_name"
  fi
done

if [[ ! -f AGENTS.md || ! -f docs/free-only-policy.md ]]; then
  echo "missing  repository rules or free-only policy"
  missing=1
fi

if [[ "$ci_mode" == false && ! -d .git ]]; then
  echo "notice   Git repository has not been initialized"
fi

if [[ "$ci_mode" == false ]]; then
  required_assets=(
    "data/models/faster-whisper-small/model.bin"
    "data/models/faster-whisper-small/config.json"
    "data/dictionaries/cedict_ts.u8"
    "data/dictionaries/cvdict.u8"
    "data/models/opus-mt-zh-vi/model.bin"
  )
  for asset_path in "${required_assets[@]}"; do
    if [[ -f "$project_root/$asset_path" ]]; then
      echo "ok       $asset_path"
    else
      echo "missing  $asset_path (run pnpm setup)"
      missing=1
    fi
  done
fi

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

echo "Watch2Learn toolchain is ready."
