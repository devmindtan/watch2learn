# Open-source evaluation

Evaluated on 2026-11-08. Re-check activity, release integrity, model licenses, and
transitive licenses before pinning a production version.

## Adopt for the initial stack

| Project | Role | License note | Decision |
| --- | --- | --- | --- |
| FFmpeg | media probing/extraction | LGPL/GPL depends on build flags | Use system binary; document build license |
| yt-dlp (`yt-dlp[default]`, incl. `yt-dlp-ejs`) | permitted YouTube metadata, subtitles, audio, optional video download | Unlicense | Python/uv install (system 2024 builds can no longer read YouTube); needs a local JS runtime (Node or Deno); subtitle-first |
| YouTube IFrame Player API | in-app playback of YouTube lessons | YouTube API Services terms; free, no key | Loaded only when a YouTube lesson is opened; `youtube-nocookie.com` host; local files never use it |
| SYSTRAN/faster-whisper | local ASR | MIT | CPU int8 ASR adapter |
| Systran/faster-whisper-small | multilingual model weights | MIT; about 484 MB | Explicit local download; Mandarin baseline |
| PyAV 18.1.0 | bundled audio decoder used by faster-whisper | BSD-3-Clause; bundles FFmpeg libraries | Temporary compatibility pin; faster-whisper 1.2.1 breaks with PyAV 19 |
| fxsjy/jieba | Mandarin segmentation | MIT | Baseline segmenter with correction support |
| pypinyin | readings | MIT | Generate pinyin; retain dictionary readings |
| CC-CEDICT | offline Chinese-English meanings | CC BY-SA 4.0; attribution/share-alike apply | Pinned checksummed snapshot from an unmodified GitHub redistribution mirror; never script MDBG |
| CVDICT (`ph0ngp/CVDICT`) | offline Chinese-Vietnamese meanings | CC BY-SA 4.0; derived from CC-CEDICT; meanings were machine-translated then manually reviewed by its author | Pinned commit + SHA-256; labelled as CVDICT in the UI; English CC-CEDICT kept alongside |
| OpenCC (`opencc` 1.4.x, BYVoid) | traditional → simplified conversion | Apache-2.0; offline phrase tables | Learner-facing text is simplified; original cue text kept in `text_original` |
| CTranslate2 + SentencePiece | local sentence-translation runtime | MIT / Apache-2.0 | CPU int8 inference; CTranslate2 already ships with faster-whisper |
| Helsinki-NLP/opus-mt-zh-vi (CTranslate2 int8 conversion `manancode/opus-mt-zh-vi-ctranslate2-android`) | offline zh→vi sentence translation | Apache-2.0; about 83 MB | Explicit `pnpm setup:translation`; pinned revision + per-file SHA-256; optional — lessons still work without it |
| Ollama + Qwen3 8B (`qwen3:8b`) | optional usage explanations in Vietnamese | Ollama MIT; Qwen3 weights Apache-2.0; ~5 GB, CPU ≈30–40 s per new explanation | Local only, cached; AI-labelled; dictionary meaning stays the source of truth |
| Piper (`piper-tts` 1.8.0, OHF-Voice/piper1-gpl) | reading words, sentences and explanations aloud on the backend | GPL-3.0-or-later; used as an installed library, not vendored | Chrome on Linux has no Web Speech voices by default; Chinese is fed our own pinyin (skips the heavy `zh` extra/g2pW) |
| Piper voice `zh_CN-chaowen-medium` | Chinese voice | dataset CC0; ~63 MB | Pinned revision + SHA-256 (`pnpm setup:voices`); ASR round-trip of synthesized sentences scores 100 % |
| Piper voice `vi_VN-vais1000-medium` | Vietnamese voice | VAIS-1000 dataset CC BY 4.0 (credit VAIS); ~63 MB | Rejected alternatives: `huayan`/`25hours_single` (unknown license), `vivos` (non-commercial) |
| Playwright | browser verification | Apache-2.0 | Critical flows only |
| FastAPI | local HTTP API | MIT | Serve the local lesson API and static client |
| pypinyin | Mandarin readings | MIT | Context-aware phrase readings with generated fallback |
| Graphify (`graphifyy`) | codebase graph | Apache-2.0; local code graph needs no cloud/API | Use local code-only features for broad/structural work; never Graphify Cloud/trials |
| Ponytail | minimal-code discipline | MIT | Use during implementation/review |

## Reference implementations, not dependencies

| Project | What to learn | Why not vendor/fork now |
| --- | --- | --- |
| `cmyui/yt-mandarin-subs` | word-aware Chinese subtitles, known-word state, difficulty preview | Browser-extension architecture differs; reuse ideas only after license review |
| `hockyy/miteiru` | offline dictionaries, multi-language adapter UX, Anki loop | CC BY-NC-SA prevents an unrestricted commercial path |
| Verso/Vilingua | local-first transcription and timestamped review | Useful product reference; early Windows-focused implementation |
| `huthvincent/yt-bilingual-app` | synchronized transcript and vocabulary interaction | Core path requires Gemini API, conflicting with free-only policy |

Do not copy code, UI assets, dictionaries, or generated datasets from a reference
repository unless its exact license and attribution requirements are recorded.

## Deferred choices

- Translation: sentence translation is now in scope and uses local OPUS-MT zh→vi
  (see above). Output is labelled as machine translation. A direct conversion from
  the original Helsinki-NLP weights would remove the third-party conversion, but
  needs PyTorch/Transformers at setup time; revisit if provenance needs tightening.
- Sino-Vietnamese (Hán Việt) readings: Unihan `kVietnamese` was evaluated and
  rejected for now — it misses common characters (電, 說, 愛) and mixes Nôm readings
  (們 → "món"). Choose a reviewed, clearly licensed dataset before adding it.
- HSK lists and frequency corpora: sources and licenses vary. Choose and document
  one dataset before implementing difficulty scoring.
- Speech model: start with `Systran/faster-whisper-small` on CPU int8. Keep the
  model replaceable and never download weights from an ordinary learner action.
- Hosting: local Docker/manual execution first. Public hosting is not part of the
  initial promise because media processing has real compute/storage cost.

## Sources

- Graphify: <https://github.com/Graphify-Labs/graphify>
- Ponytail: <https://github.com/DietrichGebert/ponytail>
- faster-whisper: <https://github.com/SYSTRAN/faster-whisper>
- faster-whisper-small: <https://huggingface.co/Systran/faster-whisper-small>
- yt-dlp: <https://github.com/yt-dlp/yt-dlp>
- Jieba: <https://github.com/fxsjy/jieba>
- CC-CEDICT: <https://cc-cedict.org/>
- CVDICT: <https://github.com/ph0ngp/CVDICT>
- OPUS-MT zh-vi: <https://huggingface.co/Helsinki-NLP/opus-mt-zh-vi>
- FastAPI: <https://github.com/fastapi/fastapi>
- pypinyin: <https://github.com/mozillazg/python-pinyin>
- YT Mandarin Subs: <https://github.com/cmyui/yt-mandarin-subs>
- Miteiru: <https://github.com/hockyy/miteiru>
- Verso: <https://www.vilingua.com/>
- Lingua Nova: <https://github.com/huthvincent/yt-bilingual-app>
