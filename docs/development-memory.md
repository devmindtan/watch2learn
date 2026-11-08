# Development memory

This is a compact evidence log, not a diary. Add an entry after a user correction,
a defect that escaped a completed check, or a manual task repeated at least twice.

## 2026-11-08 — Project skill links used one too many parent traversals

- Evidence: links created as `../../../skills/<name>` from `.agents/skills/` were
  broken; the correct repo-relative target is `../../skills/<name>`.
- Root cause: the link depth was not resolved from the symlink's containing
  directory before creation.
- Reusable rule: every generated relative symlink must be dereferenced in the same
  check that creates it.
- Verification: `test -f .agents/skills/<name>/SKILL.md` for every project skill.

## 2026-11-08 — System FFmpeg installation was not portable

- Evidence: `sudo apt-get install ffmpeg` required an interactive password and
  could not complete in the managed environment.
- Root cause: setup assumed administrative access.
- Reusable rule: prefer an existing system FFmpeg; otherwise provide a checksummed,
  repo-local bootstrap that never requires root and stays outside Git.
- Verification: `bash scripts/doctor.sh` resolves both `ffmpeg` and `ffprobe`.

## 2026-11-08 — pnpm checks can stall inside the restricted sandbox

- Evidence: `pnpm --version` and `pnpm quality` timed out without output inside the
  restricted sandbox but completed normally with the approved `pnpm` command.
- Root cause: the installed pnpm/mise runtime needs capabilities unavailable in the
  restricted execution context.
- Reusable rule: after one sandbox timeout with no child process/output, stop the
  orphaned session and rerun the exact scoped pnpm command with approval.
- Verification: capture the real exit status and output of `pnpm quality`.
