# Open-source evaluation

Evaluated on 2026-11-08. Re-check activity, release integrity, model licenses, and
transitive licenses before pinning a production version.

## Adopt for the initial stack

| Project | Role | License note | Decision |
| --- | --- | --- | --- |
| FFmpeg | media probing/extraction | LGPL/GPL depends on build flags | Use system binary; document build license |
| yt-dlp | permitted URL metadata/captions | source distribution is Unlicense; bundled builds differ | Use Python/uv source install, subtitle-first |
| SYSTRAN/faster-whisper | local ASR | MIT | CPU int8 ASR adapter |
| Systran/faster-whisper-small | multilingual model weights | MIT; about 484 MB | Explicit local download; Mandarin baseline |
| PyAV 18.1.0 | bundled audio decoder used by faster-whisper | BSD-3-Clause; bundles FFmpeg libraries | Temporary compatibility pin; faster-whisper 1.2.1 breaks with PyAV 19 |
| fxsjy/jieba | Mandarin segmentation | MIT | Baseline segmenter with correction support |
| pypinyin | readings | MIT | Generate pinyin; retain dictionary readings |
| CC-CEDICT | offline Chinese-English meanings | CC BY-SA 4.0; attribution/share-alike apply | Pinned checksummed snapshot from an unmodified GitHub redistribution mirror; never script MDBG |
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

- Translation: CC-CEDICT is enough for the first Mandarin vocabulary slice. Do not
  add a generative translation service. Evaluate a fully local translation model
  only when sentence translation becomes a scoped requirement.
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
- FastAPI: <https://github.com/fastapi/fastapi>
- pypinyin: <https://github.com/mozillazg/python-pinyin>
- YT Mandarin Subs: <https://github.com/cmyui/yt-mandarin-subs>
- Miteiru: <https://github.com/hockyy/miteiru>
- Verso: <https://www.vilingua.com/>
- Lingua Nova: <https://github.com/huthvincent/yt-bilingual-app>
