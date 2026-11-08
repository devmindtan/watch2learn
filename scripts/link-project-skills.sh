#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$project_root/.agents/skills"

for skill_dir in "$project_root"/skills/*; do
  [[ -d "$skill_dir" ]] || continue
  skill_name="$(basename "$skill_dir")"
  target="$project_root/.agents/skills/$skill_name"
  relative_source="../../skills/$skill_name"
  if [[ -L "$target" ]]; then
    if [[ "$(readlink "$target")" != "$relative_source" ]]; then
      ln -sfn "$relative_source" "$target"
      echo "relinked $skill_name"
    fi
    continue
  fi
  if [[ -e "$target" ]]; then
    continue
  fi
  ln -s "$relative_source" "$target"
  echo "linked   $skill_name"
done
