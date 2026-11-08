# Watch2Learn agent rules

## Product boundaries

Build a local-first web application that extracts timestamped learning vocabulary
from permitted videos. Mandarin Chinese is the first language. Preserve a clean
language-adapter boundary instead of spreading Mandarin rules through generic
media, lesson, or review code.

Never introduce a paid API, metered SaaS, trial-only dependency, payment-card
requirement, or a service whose useful path depends on a paid tier. Prefer local
models, offline dictionaries, open formats, and self-hostable components. Do not
bypass DRM or access controls. Ingestion must require user-owned, licensed, public
domain, or otherwise permitted content.

## Skill routing

Load only the skills that match the task:

- `graphify`: before a broad cross-file change, unfamiliar architecture work,
  dependency-impact analysis, or finding reusable code in a mature codebase.
  Skip it for a new/small tree, a single known file, or documentation-only edits.
- `ponytail`: whenever implementing or reviewing code. Prefer reuse, platform
  features, and the smallest correct change; never cut validation, security,
  accessibility, data integrity, or required tests.
- `watch2learn-architecture`: for service boundaries, data models, pipeline stages,
  storage, queues, deployment, or adding a language/source adapter.
- `mandarin-video-vocabulary`: for subtitles, Mandarin ASR, segmentation, pinyin,
  simplified/traditional forms, dictionary lookup, word ranking, and timestamps.
- `watch2learn-ui`: for video-learning screens, transcript interaction, vocabulary
  cards, visual hierarchy, responsive behavior, and accessibility.
- `free-only-dependencies`: before adding or replacing any package, model, dataset,
  API, hosted service, analytics product, font, icon set, or deployment target.
- `playwright`: when browser behavior or an end-to-end user flow must be verified.
- `screenshot`: when visual output must be inspected or compared.
- `security-best-practices`: when code handles uploads, URLs, parsers, auth,
  secrets, user data, subprocesses, filesystem paths, or public deployment.
- `security-threat-model`: for a new trust boundary or architecture-level security
  review, not for every ordinary code edit.

Project skills live in `skills/` and are linked into `.agents/skills/`. If a link
is missing, run `bash scripts/link-project-skills.sh`.

## Change workflow

1. Read the smallest relevant scope and identify the end-to-end user outcome.
2. Use Graphify only when its routing condition above is met. If used, refresh a
   stale graph before relying on it.
3. Search for existing code before creating an abstraction or dependency.
4. Check the free-only and license policy before introducing external material.
5. Implement one vertical slice with explicit input/output contracts.
6. Add focused unit tests; use Playwright for a changed critical browser flow.
7. Run the narrow checks first, then the repository quality command.
8. Update docs when a public contract, architecture decision, data source, or
   license changes. Refresh Graphify after material structural changes.

## Commit workflow

After each completed, tested change, create one focused commit on the current
branch and do not push. Stage only the paths changed for that unit of work; never
use `git add .` or `git add -A`, and preserve unrelated worktree changes. Before
committing, inspect `git diff --check`, the staged diff, and run affected tests.
Do not commit a known-broken change, secrets, generated media, downloaded models,
dictionary dumps, caches, or Graphify output. Use an imperative commit subject
that describes the outcome, not the implementation session.

## Development memory

Context is product data: every vocabulary occurrence must keep the original cue,
neighboring cues when available, timestamp, surface form, source, and analysis
provenance. Do not present an isolated definition as if it captured the meaning in
the sentence.

When the user corrects an implementation, a defect reaches a completed check, or
the same manual task occurs at least twice, append a concise entry to
`docs/development-memory.md`. Record evidence, root cause, the reusable rule, and
how to verify it. Do not log speculation, routine one-off work, secrets, or noisy
session history. Promote stable repeated rules into `AGENTS.md` or a relevant skill
and keep the memory entry as provenance.

## Engineering invariants

- Subtitle cues and vocabulary occurrences retain source timestamps.
- Vocabulary occurrences retain enough neighboring context to disambiguate use.
- Raw media, derived audio, transcripts, and learner data have separate lifecycles.
- Jobs are resumable and idempotent; retries must not duplicate vocabulary.
- External URLs, uploaded filenames, subtitle markup, and model output are untrusted.
- Preserve the original Mandarin text; normalized forms are additional fields.
- Every generated definition or segmentation can be corrected by the learner.
- CPU-only local execution is a supported baseline; GPU is an optional accelerator.
- No language-specific conditional chain in generic pipeline code; use adapters.

## Current commands

```bash
pnpm setup
pnpm dev
pnpm quality
pnpm run doctor
python3 /home/devmindtan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/<skill>
```

Do not claim a check passed unless it was run. Do not commit generated media,
downloaded model weights, dictionary dumps, secrets, or `graphify-out/`.
