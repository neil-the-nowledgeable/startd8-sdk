# Wireframe — Usage

**Date:** 2026-06-05
**Spec:** [`WIREFRAME_REQUIREMENTS.md`](WIREFRAME_REQUIREMENTS.md) (v0.4) /
[`WIREFRAME_PLAN.md`](WIREFRAME_PLAN.md) (v1.2)

`startd8 wireframe` is the $0, read-only, advisory pre-generation summary of the deterministic
cascade: it shows what `generate scaffold` / `generate backend` / `generate views` WILL build
from the assembly input manifests — and, per section, what has **not been defined yet**.

## Quick start

```bash
# Convention defaults (prisma/schema.prisma, app.yaml, prisma/*.yaml exact filenames):
startd8 wireframe --project .

# From one or more machine-readable inventories (last wins per key):
startd8 wireframe --inputs docs/ASSEMBLY_INPUTS.yaml

# Machine output for CI / pipelines (stdout is JSON only):
startd8 wireframe --json --no-write

# Kickoff review mode — show only the gaps:
startd8 wireframe --only-issues
```

Direct flags mirror the generators' exact spellings: `--schema --pages --ai-passes
--human-inputs --completeness --pages-authoring --views`, and `--manifest` for `app.yaml`
(scaffold's spelling; `--app` aliases it). Flags override `--inputs` values.

Persisted artifact: `.startd8/wireframe/wireframe-plan.json` (atomic write; `--no-write` skips).
Pipeline runs write to `pipeline-output/<run>/wireframe/` instead (never both).

## Statuses

`planned` (manifest authored) · `defaults` (absent but generator produces defaulted output —
`app.yaml`, `human_inputs.yaml`, `completeness.yaml`) · `placeholder` (stub/sentinel) ·
`not defined` (absent, nothing generated) · `invalid` (present but fails its parser or, for the
lenient-parsed `schema.prisma`, its recoverability check).

Footer: status counts, shape summary (entities/routes/pages/views/passes), and **cascade
readiness** — `scaffold|backend|views: ready | blocked(<reason>)`.

## cap-dev-pipe (opt-in)

```bash
STARTD8_WIREFRAME=1 ./run-prime-contractor.sh ...
# optional: STARTD8_WIREFRAME_INPUTS=/path/to/assembly-inputs.yaml
```

Runs early (pre-workflow), never blocks (always exit 0; crashes leave `wireframe-error.json`).
The pipeline never *runs* the cascade — this is visibility only (Group F boundary).

## Running against a consumer project

The wireframe is an SDK capability serving **any** project on the contract-first cascade
(requirements §1.0) — point it at the consumer's root:

```bash
startd8 wireframe --project /path/to/consumer-project
```

First real use (OQ-8 pilot, 2026-06-05) was the reference consumer — strtd8, the first of the
expected many — where it surfaced 3 invalid manifests pre-cascade (see that repo's
`docs/SDK_WIREFRAME_CAPABILITY_2026-06-05.md`).

## When to use wireframe vs sapper vs kickoff FR-X1 (R2-S5)

| | **wireframe** | **sapper** | **kickoff FR-X1 pre-flight** |
|---|---|---|---|
| Question | What will the $0 cascade build, and what isn't defined yet? | What SDK-mechanism friction will this run hit (routing, invention, conventions)? | Are the five input classes provisioned (`authored`/`placeholder`/`absent`)? |
| Inputs | Assembly manifests (Group F: contract + 6 YAML) | ForwardManifest / Prime-EMIT artifacts | All five classes (data-model, content, conventions, build prefs, observability) |
| Output | App-shape tree + JSON plan (`schema_version`, fingerprint, readiness) | Ranked friction findings (verdict/severity/file:line) | Per-input provisioning report |
| Gating | Never (advisory; CI gates from the JSON itself) | Advisory survey | VALIDATE gate (kickoff machinery) |
| Cost | $0, read-only, deterministic | $0 survey | $0 |
| When | Front bookend (DATA MODEL design), before any generation; kickoff review artifact | Before/around Prime contractor runs | Kickoff POLISH stage |

The wireframe subsumes neither: no mechanism/friction analysis, and only Group F of the
five-class pre-flight.
