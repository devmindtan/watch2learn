# Development memory

This is a compact evidence log, not a diary. Add an entry after a user correction,
a defect that escaped a completed check, or a manual task repeated at least twice.

## 2026-11-08 — Model load did not prove that real audio could be decoded

- Evidence: the model loaded and mocked ASR tests passed, but a real Mandarin WAV
  failed because faster-whisper 1.2.1 passed a removed argument to PyAV 19.
- Root cause: dependency compatibility was tested only at import/model-load level,
  not through the decoder used by an actual media file.
- Reusable rule: every local media/ML stack needs one real-format decode or
  inference smoke test; pin a compatible transitive version when upstream has not
  released its fix.
- Verification: the ASR dependency group pins PyAV 18.1.0 and the test suite
  decodes a generated WAV through `faster_whisper.audio.decode_audio`.

## 2026-11-08 — Unified setup downloaded repo-local FFmpeg again

- Evidence: `pnpm setup` downloaded the 133 MB FFmpeg archive even though verified
  executables already existed under `.tools/bin`.
- Root cause: the bootstrap checked only the shell `PATH`, not its own install
  destination.
- Reusable rule: every explicit bootstrap must be idempotent by validating its
  output path before any network request.
- Verification: rerunning `pnpm setup` reports all three local assets ready and
  performs no download.

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

## 2026-11-08 — polyphonic words showed the first dictionary reading

- Evidence: in "这样更容易理解" the UI showed 更 as *gēng* "to change" instead of
  *gèng* "more"; the learner-facing reading and meaning were both wrong.
- Root cause: the lesson always used `dictionary.lookup(word)[0]`, ignoring the
  sentence the word appeared in.
- Reusable rule: choose readings per occurrence from the whole cue (pypinyin), pick
  the dictionary entry whose reading matches, and keep the other entries as
  learner-visible alternatives.
- Verification: `test_polyphonic_word_uses_sentence_reading_and_keeps_alternatives`.

## 2026-11-08 — subtitle lines were translated without their sentence

- Evidence: the learner asked for contextual (not word-for-word) translation;
  "我昨天去了一家 / 很有名的餐厅" translated per line gave "…một gia đình" (wrong),
  joined gave "Hôm qua tôi đến một nhà hàng nổi tiếng."
- Root cause: OPUS-MT received each subtitle cue in isolation, so a sentence split
  across cues lost its object/meaning.
- Reusable rule: translate sentence groups (see `translation.sentence_groups`),
  treat closing brackets as sentence ends, strip model markup, and show the word
  sense that appears in the sentence translation.
- Verification: `test_cues_split_mid_sentence_are_translated_together`,
  `test_bracketed_stage_direction_translates_inner_text`.

## 2026-11-08 — analysed videos were deleted after processing

- Evidence: the learner expected the analysed video to stay in a folder; saved
  lessons could not play without re-selecting the file.
- Root cause: the job cleanup removed the whole work directory, source included.
- Reusable rule: move the analysed source to `data/media/<lesson-id>/` before job
  cleanup; delete it only with the lesson.
- Verification: `test_uploaded_video_is_kept_in_lesson_media_folder`.

## 2026-11-08 — non-Chinese lines were sent to the zh→vi translator

- Evidence: the learner required that only Chinese is translated. English lines
  ("OK, let us start the lesson.") were passed to OPUS-MT, and ASR forced to
  `language="zh"` can render foreign speech as Chinese text.
- Root cause: translation and ASR assumed every cue was Mandarin.
- Reusable rule: gate translation with `chinese_source` (Han present, no kana/
  Hangul; mostly-foreign lines keep only Han), mark skipped cues, and run ASR with
  per-window language detection.
- Verification: `test_only_chinese_is_sent_for_translation`; mixed English/Chinese
  audio keeps English verbatim and untranslated.

## 2026-11-08 — sentence grouping hid translations; outdated lessons kept stale data

- Evidence: the learner saw lines without translation and re-translation waits.
  Real data (uploader subtitles and Whisper output) has one sentence per cue
  without punctuation, so "no closing punctuation" grouped 3 sentences and left 2
  rows blank. Each rule change re-translated lessons lazily on open. A lesson made
  before context readings still showed 上 shǎng / 說 shuì.
- Root cause: grouping heuristic built from a hypothetical, not real cues; saved
  lessons were only upgraded on demand, and analysis upgrades did not exist.
- Reusable rule: group only on explicit comma-like continuation; version both
  analysis and translation, and upgrade saved lessons in the background at startup
  without touching original cue text/timing.
- Verification: `test_only_comma_continued_cues_are_translated_together`,
  `test_startup_upgrade_translates_saved_lessons_once`,
  `test_old_lessons_get_context_readings_without_losing_text_or_translation`.

## 2026-11-08 — uploader YouTube subtitles contained nonsense lines

- Evidence: lesson `_tvupSFn1JE` showed "查得998 后来从特色攻略杀到荣哈迪" and
  "vitamin Shadowing Gum Mr Chinese"; the lines are in the uploader's own `zh`
  track, where Vietnamese narration was rendered as junk. Local ASR (multilingual)
  produced the Vietnamese narration verbatim and clean Chinese.
- Reusable rule: never treat uploader subtitles as ground truth; let the learner
  choose local listening up front and re-run it from the lesson.
- Verification: `test_learner_can_choose_local_listening_instead_of_youtube_subtitles`.

## 2026-11-08 — `pnpm dev --reload` restarted a running job into FileExistsError

- Evidence: job `b5545ebb` failed with `FileExistsError: …/speech.wav`.
- Root cause: code edits reloaded the server mid-job; the resumed job found the
  partial audio from the first run.
- Reusable rule: resumable stages must clear their own partial outputs first.
- Verification: the ASR-choice test seeds a stale `speech.wav`.

## 2026-11-08 — spoken explanations were silent in Chrome on Linux

- Evidence: the learner reported the word explanation as missing. A headed Chrome
  on this machine returned 0 `speechSynthesis` voices (13 363 only with
  `--enable-speech-dispatcher`); headless test runs had hidden the problem and the
  UI only showed a soft "default voice" note.
- Root cause: relying on browser Web Speech voices, which Chrome on Linux does not
  expose by default.
- Reusable rule: produce learner-facing audio on the backend (Piper) and treat
  browser voices as fallback; verify audio features with a headed browser or by
  asserting that audio playback actually started.
- Verification: `test_local_voices_read_mixed_chinese_and_vietnamese`; Playwright
  asserts `/api/tts` returns `audio/mp4` and an audio element starts playing.

## 2026-11-09 — spoken explanation re-read the screen and the voice sounded odd

- Evidence: the learner asked for a Vietnamese lesson in a fixed order — how the word
  is read, its meaning, pronunciation pitfalls, where it is met in conversation, how
  it is used — instead of reading the visible facts aloud; the model also produced
  Chinese grammar terms and an invented pronunciation note ("手 như thou"). The
  Piper voices were judged unnatural.
- Root cause: the narration was built from the display lines, and pronunciation
  advice was left to the model.
- Reusable rule: narrate as a teacher in the learner's language; keep readings,
  meanings and pronunciation hints deterministic (`learner_tips`) and let the model
  write only usage/situation text, streamed per section. Choose voices by listening
  (voice picker), not by intelligibility scores alone.
- Verification: `test_word_lesson_streams_vietnamese_sections_and_is_cached`,
  `test_pronunciation_tips_cover_tone_changes_and_hard_sounds`, voice picker preview.

## 2026-11-09 — GPU worker: orphaned tunnel and lockfile pins

- Evidence: a smoke-test script crashed while its SSH tunnel (`ssh -L … run.sh`) kept
  running, so the GPU worker held VRAM with no owner. Installing the worker with the
  laptop's exported lock failed twice (tokenizers, huggingface-hub pinned above what
  transformers 4.57.6 — VieNeu's GPU path — accepts).
- Root cause: `Popen` children outlive the parent; the laptop lock is resolved for a
  different package set than the GPU worker needs.
- Reusable rule: register tunnel shutdown with `atexit` and close idle tunnels; build
  the worker environment from direct dependencies (+ PyTorch/transformers) and let the
  resolver pick compatible transitive versions there.
- Verification: after a script exits, `ss -ltnH` on the GPU machine shows no 8911/
  11434 listener and VRAM returns to ~220 MiB; `pnpm gpu:install` completes.
