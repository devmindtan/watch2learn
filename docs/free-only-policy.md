# Free-only dependency policy

"Free" means the core product can be developed, run, tested, and self-hosted
without payment details, credits, quotas that require an upgrade, or a proprietary
API. A free trial or promotional credit does not qualify.

Before adding an external component, record:

- canonical source and maintainer;
- software or data license and relevant attribution/share-alike obligations;
- whether model weights have a separate license;
- whether all required features work locally/offline;
- expected CPU, RAM, disk, and download cost;
- a migration/removal path.

Permissive and recognized copyleft open-source licenses are acceptable when their
obligations fit distribution. Source-available, non-commercial, or no-derivatives
licenses require an explicit project decision and must not be copied into the
product by default.

The repository rejects required integrations with OpenAI, Gemini, DeepL, hosted
translation/ASR, paid analytics, commercial font/icon licenses, or "free tier"
hosting as part of the core path. Optional future connectors must remain disabled,
isolated, and unnecessary for all core outcomes; none are planned in phase one.

Video availability does not grant reuse rights. Only process content the learner
is authorized to access and use. Do not implement DRM or access-control bypasses.
