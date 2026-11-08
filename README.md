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

The local MVP accepts a Mandarin video, shows durable processing progress, prefers
embedded or optional SRT/WebVTT subtitles, and otherwise transcribes audio locally.
It extracts timestamped vocabulary with Jieba and pypinyin, preserves neighboring
cue context, adds offline CC-CEDICT meanings, and saves completed lessons in SQLite.

## Start here

```bash
pnpm setup                          # one-time local tool/model/dictionary setup
pnpm dev
```

Open <http://127.0.0.1:8000> and choose a local Mandarin video. A subtitle file is
optional. Processing runs as a local background job, completed lessons are saved,
and temporary media/audio files are deleted after the lesson is built.

Run checks with:

```bash
pnpm run doctor
pnpm policy:free
pnpm quality
```

Read [the architecture](docs/architecture.md), [the open-source evaluation](docs/open-source-evaluation.md),
and [the workflow rules](docs/workflows.md) before implementing the first slice.
