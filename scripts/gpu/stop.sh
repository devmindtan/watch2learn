#!/usr/bin/env bash
# Stop the Watch2Learn worker (processes whose working directory is in this runtime), freeing the VRAM.
BASE=$(realpath "$HOME/watch2learn-gpu")
pids=""
for d in /proc/[0-9]*; do
  p=${d#/proc/}; [ "$p" = "$$" ] && continue
  cwd=$(readlink "$d/cwd" 2>/dev/null) || continue
  case "$cwd" in "$BASE"|"$BASE"/*) pids="$pids $p";; esac
done
[ -z "$pids" ] && { echo "Watch2Learn worker is not running."; exit 0; }
kill $pids 2>/dev/null
for i in $(seq 16); do sleep 0.5; alive=$(ps -o pid= -p $pids 2>/dev/null); [ -z "$alive" ] && break; done
[ -n "$alive" ] && kill -9 $alive 2>/dev/null
echo "Stopped $(echo $pids | wc -w) Watch2Learn worker process(es)."
