# Development memory

This is a compact evidence log, not a diary. Add an entry after a user correction,
a defect that escaped a completed check, or a manual task repeated at least twice.

## 2026-11-08 — Subtitle upload was incorrectly made the primary input

- Evidence: the completed first UI required an SRT/VTT file; the user corrected
  that ordinary learners only have a video and expect the product to process it.
- Root cause: the easiest testable transcript path was mistaken for the product's
  main user journey.
- Reusable rule: local video is the required input; supplied or embedded Mandarin
  subtitles are optimizations, and local ASR is the automatic fallback.
- Verification: the form requires only video and the video endpoint produces timed
  cues without an uploaded subtitle.

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

## 2026-11-08 — synchronous TestClient requests stalled in the sandbox

- Evidence: the API suite timed out twice at its first `fastapi.testclient`
  request, while parser and lesson tests completed normally.
- Root cause: TestClient's synchronous portal/thread path did not complete in the
  restricted runner; the application did not require that thread boundary.
- Reusable rule: test ASGI endpoints with `httpx.AsyncClient` and `ASGITransport`
  when a real synchronous client thread is not part of the behavior under test.
- Verification: the API request/validation tests finish inside the sandbox and the
  same app is exercised over real HTTP during Playwright QA.

## 2026-11-08 — generated patches repeatedly left blank lines at EOF

- Evidence: `git diff --check` rejected both attempted commits because several new
  text files ended with an extra blank line.
- Root cause: patch-created files were not normalized before the first quality run.
- Reusable rule: make whitespace validation part of `pnpm quality`, not only the
  final commit command; keep the cached-diff check immediately before commit too.
- Verification: `pnpm whitespace` and `git diff --cached --check` both pass.
