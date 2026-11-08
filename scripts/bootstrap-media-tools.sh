#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tools_dir="$project_root/.tools"
bin_dir="$tools_dir/bin"

if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "FFmpeg and ffprobe already exist on PATH."
  exit 0
fi

case "$(uname -m)" in
  x86_64) platform="linux64" ;;
  aarch64|arm64) platform="linuxarm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    echo "Install FFmpeg through the operating system package manager." >&2
    exit 1
    ;;
esac

archive="ffmpeg-master-latest-${platform}-lgpl.tar.xz"
release_base="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

echo "Downloading the current LGPL FFmpeg build and published checksum..."
curl --fail --location --retry 3 \
  --output "$temp_dir/checksums.sha256" "$release_base/checksums.sha256"
curl --fail --location --retry 3 \
  --output "$temp_dir/$archive" "$release_base/$archive"

expected_line="$(rg "  ${archive}$" "$temp_dir/checksums.sha256")"
if [[ -z "$expected_line" ]]; then
  echo "No checksum was published for $archive." >&2
  exit 1
fi

printf '%s\n' "$expected_line" > "$temp_dir/selected.sha256"
(
  cd "$temp_dir"
  sha256sum --check selected.sha256
)

mkdir -p "$temp_dir/unpacked" "$bin_dir" "$tools_dir/ffmpeg-license"
tar -xJf "$temp_dir/$archive" -C "$temp_dir/unpacked"

ffmpeg_path="$(find "$temp_dir/unpacked" -type f -path '*/bin/ffmpeg' -print -quit)"
ffprobe_path="$(find "$temp_dir/unpacked" -type f -path '*/bin/ffprobe' -print -quit)"
license_path="$(find "$temp_dir/unpacked" -type f -iname 'LICENSE*' -print -quit)"

if [[ -z "$ffmpeg_path" || -z "$ffprobe_path" ]]; then
  echo "Downloaded archive did not contain ffmpeg and ffprobe." >&2
  exit 1
fi

install -m 0755 "$ffmpeg_path" "$bin_dir/ffmpeg"
install -m 0755 "$ffprobe_path" "$bin_dir/ffprobe"
if [[ -n "$license_path" ]]; then
  install -m 0644 "$license_path" "$tools_dir/ffmpeg-license/$(basename "$license_path")"
fi

echo "Installed local FFmpeg tools in $bin_dir."
echo "They are ignored by Git; rerun this script on another machine."
