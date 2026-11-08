---
name: free-only-dependencies
description: Evaluate any package, model, dataset, API, hosted service, analytics tool, font, icon set, or deployment choice for Watch2Learn's strict no-paid-services policy and license compatibility. Use before introducing or replacing external material; not for edits with no dependency or data-source impact.
---

# Free-only Dependencies

Read [references/review-checklist.md](references/review-checklist.md) and
`docs/free-only-policy.md`. Verify current facts against the upstream repository,
official license, model card, or dataset owner before approval.

## Decision rule

Approve only when the core use case works without payment details, trial credits,
metered API quota, or an eventual mandatory hosted tier. Prefer local, offline,
self-hostable, replaceable components.

Record the canonical source, exact license, transitive/build-license caveats,
model/data license, attribution duties, resource requirements, and removal path.
Reject unknown or incompatible licensing until clarified. A GitHub repository being
public does not make its contents open source.

Keep reference implementations separate from dependencies. Do not copy their code
or assets merely because the product idea is relevant.
