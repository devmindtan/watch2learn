---
name: mandarin-video-vocabulary
description: Build or evaluate Watch2Learn's Mandarin video pipeline, including Chinese subtitles or local ASR, cue timing, segmentation, simplified/traditional forms, pinyin, offline dictionary lookup, candidate ranking, and learner corrections. Do not use for generic UI-only or non-language media plumbing.
---

# Mandarin Video Vocabulary

Read [references/pipeline.md](references/pipeline.md) before changing Mandarin
analysis behavior or its data contract.

## Required behavior

- Prefer supplied, embedded, or permitted captions before local ASR.
- Preserve original Hanzi and cue timing; normalization produces extra fields.
- Segment with dictionary-aware longest candidates but retain alternatives when
  ambiguity matters. Never assume each Hanzi is one word.
- Resolve pinyin from dictionary entries where possible; use generated pinyin as a
  fallback and represent neutral tone and polyphonic uncertainty explicitly.
- Support simplified and traditional forms without overwriting either.
- Keep dictionary meaning, frequency/level, and model confidence source-labelled.
- Rank learning candidates, but allow the learner to hide, merge, split, redefine,
  and mark words as known.
- Test segmentation and readings with real ambiguous sentences and timestamp
  boundaries, not only isolated words.

Use offline sources in the first release. Do not invent definitions with an LLM or
silently translate through a hosted API.
