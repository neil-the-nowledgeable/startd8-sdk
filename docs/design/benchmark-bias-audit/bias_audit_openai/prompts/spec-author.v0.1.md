# Spec-Author Prompt Template v0.1

## Run Metadata

{{RUN_METADATA}}

## Role

You are authoring one benchmark implementation specification from a neutral source brief. Your task is
to choose a clear, implementable spec while preserving every OPEN choice as your own authored decision.

## Neutral Brief

{{NEUTRAL_BRIEF}}

## Experiment Instructions

{{EXPERIMENT_INSTRUCTIONS}}

Default experiment instruction for this template:

- Author only the prose implementation specification.
- Do not write a test suite.
- Do not write a reference implementation.
- You may propose a proto shape only in a clearly marked "secondary contract sketch" section.
- Do not copy existing pricing seed names listed as forbidden inputs.
- For every OPEN item you resolve, include a short "Open Item Decisions" entry explaining the decision.
- For every FIXED item, preserve the constraint without changing its meaning.

## Output Contract

Write exactly these files:

- `spec.md`
- `authoring_manifest.json`

`spec.md` must contain:

- Title
- Scope
- Service behavior
- Input/output shape
- Validation behavior
- Open Item Decisions
- Assumptions
- Non-goals

`authoring_manifest.json` must conform to `self-manifest.schema.json`.

## Allowed Dependencies

{{ALLOWED_DEPENDENCIES}}

## Forbidden Inputs

{{FORBIDDEN_INPUTS}}

