# Architecture baseline

## Decision

Start as a modular monolith with a web client and a local Python processing
service. Use a durable job table rather than a distributed queue. This keeps the
first version runnable on one machine without paid infrastructure while preserving
clear seams for later extraction.

```text
browser
  -> web/API boundary
      -> media ingestion -> subtitle acquisition -> local ASR fallback
      -> language adapter -> vocabulary candidates -> lesson persistence
      -> video/transcript reader -> learner vocabulary and review
  -> SQLite + local object directory
```

## Implementation stack

| Area | Default | Why |
| --- | --- | --- |
| Web | Browser-native HTML/CSS/JS initially | No frontend runtime dependency for the first vertical slice |
| API/jobs | FastAPI + Python | Strong media/NLP ecosystem and typed contracts |
| Metadata | SQLite | Zero-cost, transactional, easy local backup |
| Media | FFmpeg/ffprobe | Mature local extraction and probing |
| URL captions | yt-dlp | Subtitle-first acquisition for permitted sources |
| ASR fallback | faster-whisper | Local CPU/GPU transcription; word timestamps |
| Mandarin adapter | Jieba + pypinyin + CC-CEDICT + CVDICT | Offline segmentation, context readings, English/Vietnamese meanings |
| Sentence translation | OPUS-MT zh→vi on CTranslate2 | Optional local machine translation per cue |
| Pronunciation | Original cue audio + browser Web Speech voices | No server TTS; replay the real sentence first |
| Browser tests | Playwright | Critical playback/transcript flow validation |

The browser keeps an object URL for playback and sends the video to the local API
for processing. The API prefers a suitable embedded Mandarin subtitle stream and
otherwise extracts mono 16 kHz audio for local faster-whisper transcription. An
uploaded SRT/VTT remains an optional fast path. A framework becomes justified when
UI state or reuse exceeds what the small native client can keep clear.

Video jobs are fingerprinted and processed in a local worker thread so long ASR
does not hold the browser request open. SQLite stores observable job state and the
completed lesson. Re-uploading the same video/settings reuses the completed result.
Derived audio and intermediate files live only in the per-job temporary directory
and are deleted after success or failure. The analysed source video is moved to
`data/media/<lesson-id>/video.<ext>` (ignored by Git) so a saved lesson can replay
its exact moments; it is served by `GET /api/lessons/{id}/media` with HTTP range
support and deleted together with the lesson (`DELETE /api/lessons/{id}`). Lessons
saved before this rule can attach their video with `PUT /api/lessons/{id}/media`.
If the local server stops mid-job, startup reads the durable record and resumes
processing from the retained source; unrelated orphan job directories are removed.

YouTube lessons (`POST /api/lessons/youtube`) require the learner to confirm they
may use the video. Only a validated 11-character video ID reaches yt-dlp (argument
arrays, `--ignore-config`, no playlists, live streams and >3 h videos rejected).
The pipeline prefers uploader-provided Chinese subtitles, ignores auto-captions
(they include machine translations), and otherwise downloads audio only for local
ASR. The browser plays the lesson through the YouTube IFrame player
(`youtube-nocookie.com`). `POST /api/lessons/{id}/download` saves a ≤720p MP4
(H.264 preferred) into the lesson media folder; the player then offers the local
copy.

Do not add Redis, Kafka, Kubernetes, a vector database, microservices, or a cloud
object store until measured requirements make the local design insufficient.

## Module contracts

- `sources`: accepts local media/subtitles and supported permitted URLs; emits a
  canonical media descriptor. It never performs language analysis.
- `transcripts`: emits ordered cues with stable IDs, start/end milliseconds,
  original text, language tag, source type, and confidence when available.
- `languages`: maps transcript cues to normalized tokens and vocabulary candidates.
  Each language implements the same adapter contract.
- `lessons`: combines occurrences, definitions, learner-known state, and ranking.
- `review`: owns saved vocabulary and scheduling; it does not mutate transcripts.

Translation works on sentences, not subtitle lines: consecutive cues are joined
when a cue lacks closing punctuation, the pause is ≤700 ms and the sentence stays
≤60 characters (max 3 cues). Each cue carries the sentence's `translation_vi`
plus `translation_group`/`translation_group_end` (or `null` when the optional
model is missing); the lesson records `translation.unit = "sentence"`. Bracketed
stage directions are translated from their inner text and model markup is
stripped. `POST /api/lessons/{id}/translations` re-translates and persists older
lessons. The word card shows "Trong câu này" — the CVDICT sense whose wording
appears in that sentence's translation — instead of an isolated definition. Only
Vietnamese meanings are shown; CC-CEDICT is still used for readings and sense
selection. Pinyin is chosen per occurrence: the
whole cue is read by pypinyin, and the dictionary entry whose reading matches is
selected, so polyphonic words (更 gèng/gēng, 行 xíng/háng) get the sense used in
that sentence; other readings stay available as `alternatives`.

## Mandarin record shape

A vocabulary entry should be able to hold simplified and traditional forms,
numbered and marked-tone pinyin, dictionary senses, HSK/frequency metadata with a
declared source, and one-to-many timestamped occurrences. Original cue text is
immutable; normalization and corrections are separate fields.

## Processing order

1. Probe source and compute a stable content fingerprint.
2. Prefer supplied or embedded subtitles over network captions and ASR.
3. Normalize subtitle timing/markup without losing original text.
4. Use local ASR only when a suitable transcript is unavailable.
5. Run the selected language adapter per cue.
6. Consolidate word occurrences without discarding cue boundaries.
7. Rank candidates using learner-known words, frequency, repetition, and context.
8. Persist a versioned lesson so processing can resume safely.

## Early security boundaries

Treat uploads, URLs, subtitle markup, archive contents, FFmpeg/yt-dlp output, and
model output as untrusted. Use argument arrays rather than shell interpolation,
canonicalize paths under per-job directories, impose size/time limits, and never
serve uploaded files as executable content.

## Context is a first-class learning record

A vocabulary occurrence is not just a word and translation. It retains the exact
surface form, original cue, preceding/following cue when available, timestamp,
source, normalization/segmenter version, selected dictionary sense, alternatives,
and learner correction. Reprocessing creates a new analysis version without
silently discarding corrections. UI and exports must keep a route back to the
original moment in the video.
