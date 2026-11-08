---
name: watch2learn-architecture
description: Design or change Watch2Learn service boundaries, data models, processing jobs, storage, source ingestion, deployment, or language-adapter contracts. Use for architecture decisions and cross-module feature design; do not use for a small isolated implementation that preserves existing contracts.
---

# Watch2Learn Architecture

Keep the core product runnable locally without a paid service. Begin with the
modular-monolith baseline in [references/architecture-principles.md](references/architecture-principles.md)
and deviate only for a measured requirement.

## Workflow

1. Define the learner outcome and the smallest vertical slice.
2. Identify affected contracts: source, transcript, language adapter, lesson,
   learner vocabulary, or review.
3. Preserve timestamps, provenance, resumability, and correction paths.
4. Treat media inputs and processor output as untrusted at each boundary.
5. Prefer SQLite, local files, and an in-process/durable job runner until their
   limits are demonstrated.
6. Record a concise decision in `docs/` when a public contract, data lifecycle,
   trust boundary, or long-lived technology choice changes.

Consult `docs/architecture.md` for the current baseline. If proposing a package,
model, dataset, API, or hosting service, also load `free-only-dependencies`.
