# Watch2Learn

Watch2Learn is a local-first web project that turns permitted video content into
timestamped vocabulary lessons. The first supported language is Mandarin Chinese;
the architecture keeps language-specific processing behind adapters so other
languages can be added later.

## Initial product loop

1. Import a local video, subtitle file, or a permitted video URL.
2. Prefer existing subtitles; transcribe locally only when subtitles are missing.
3. Segment Mandarin text, add pinyin and offline dictionary meanings.
4. Rank useful unknown words and keep their sentence and video timestamps.
5. Let learners save, review, and export vocabulary without a paid service.

## Non-negotiable constraints

- No paid API, metered SaaS, trial credit, or payment-card requirement.
- Local and self-hosted processing is the default.
- Do not download content the user is not authorized to use or bypass DRM.
- Keep third-party code and data licenses visible and auditable.
- Prefer existing code and the smallest maintainable implementation.

## Repository status

The first vertical slice is working: a local web UI accepts Mandarin SRT/WebVTT,
extracts timestamped vocabulary with Jieba and pypinyin, preserves neighboring cue
context, and uses CC-CEDICT when a local dictionary file is present. Video playback
uses a browser object URL, so the media file never leaves the browser.

## Start here

```bash
bash scripts/bootstrap-media-tools.sh # only when ffmpeg is not already installed
uv sync
pnpm dev
```

Open <http://127.0.0.1:8000>, choose a local video and a Mandarin SRT/VTT file.
The video stays in the browser; only subtitle text is sent to the local API.

For offline English meanings, manually place CC-CEDICT at
`data/dictionaries/cedict_ts.u8`; see [the dictionary instructions](data/dictionaries/README.md).

Run checks with:

```bash
bash scripts/doctor.sh
pnpm policy:free
pnpm quality
```

Read [the architecture](docs/architecture.md), [the open-source evaluation](docs/open-source-evaluation.md),
and [the workflow rules](docs/workflows.md) before implementing the first slice.
