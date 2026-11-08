# Architecture principles

- Model a transcript as ordered immutable cues with millisecond time ranges and
  provenance. Derived tokens and corrections refer back to stable cue IDs.
- Model vocabulary as lexemes plus occurrences. An occurrence keeps cue ID, time
  range, surface form, and surrounding context.
- Give raw media, derived audio, transcripts, lessons, and learner data distinct
  retention policies.
- Jobs have stable input fingerprints, versioned processor settings, observable
  stages, and idempotent writes.
- Source adapters acquire media metadata/captions; language adapters interpret
  text. Neither should depend on the other's concrete implementation.
- Make CPU-only execution work. Acceleration is optional and capability-detected.
- Keep model and dictionary downloads explicit, checksummed, replaceable, and out
  of version control.
- Do not add distributed infrastructure to solve a hypothetical scale problem.
