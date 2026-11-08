# Tool and skill workflows

## Routing principle

Tools are conditional, not ceremonial. A tool must reduce uncertainty, catch a
real risk, or verify an outcome. `AGENTS.md` is the source of truth for activation.

| Situation | Required route |
| --- | --- |
| One known file, small edit | Ponytail; focused test |
| Broad/unfamiliar cross-file change | Graphify, then Ponytail |
| New package/model/data/service | Free-only dependency review first |
| Media/subtitle/Mandarin pipeline | Mandarin skill + security skill if input boundary changes |
| Learning/player UI | UI skill; screenshot for visuals; Playwright for behavior |
| Upload, URL ingestion, subprocess, auth | Security best practices |
| New public trust boundary | Threat model before implementation |

## Graphify lifecycle

Graphify is installed as the `graphify` executable and its project skill lives in
`.agents/skills/graphify`. Do not commit generated graphs.
Use its local code graph only; Graphify Cloud and metered model backends are outside
the free-only policy.

```bash
graphify extract .
graphify query "where is transcript normalization implemented"
graphify update .
```

Create the first graph only after there is enough application code for cross-file
relationships to be useful. Refresh it after material structural changes.

## Quality gate

If the operating system does not provide FFmpeg, install the verified local LGPL
build with `bash scripts/bootstrap-media-tools.sh`. It is stored under the ignored
`.tools/` directory.

Run the narrow tests for changed modules, then:

```bash
bash scripts/check-free-policy.sh
bash scripts/doctor.sh --ci
```

Once application packages exist, add their lint, typecheck, unit, integration, and
E2E commands to the root `quality` script. Do not add placeholder checks that pass
without inspecting application code.

## Commit-only handoff

Every completed and verified change gets one focused local commit. Never push.
Stage explicit paths, review the staged diff, and leave unrelated changes alone.
The full rule is in `AGENTS.md` and applies to both agents and human-assisted work.

## Learning loop

Use `docs/development-memory.md` for demonstrated mistakes, user corrections, and
manual workflows repeated at least twice. Entries become actionable only when they
include a root cause, reusable rule, and verification. If a rule remains useful,
promote it into `AGENTS.md`, a skill, a test, or an automated script.
