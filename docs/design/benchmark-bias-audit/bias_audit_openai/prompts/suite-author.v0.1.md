# Suite-Author Prompt Template v0.1

## Run Metadata

{{RUN_METADATA}}

## Role

You are authoring a behavioral test suite for a fixed benchmark spec. Your suite should detect
incorrect implementations without changing the spec's semantics.

## Neutral Brief

{{NEUTRAL_BRIEF}}

## Experiment Instructions

{{EXPERIMENT_INSTRUCTIONS}}

Default experiment instruction for this template:

- Author only the behavioral suite.
- Treat the provided fixed spec and canonical proto as authoritative for this experiment.
- Do not alter the spec, proto, harness, oracle, or runtime.
- Do not repair or reinterpret ambiguous behavior beyond the fixed spec.
- Localize each assertion to the behavior it is intended to detect.
- Include a manifest entry mapping each test to the FIXED/OPEN item it exercises.

## Output Contract

Write exactly these files:

- `suite.py`
- `suite_manifest.json`
- `authoring_manifest.json`

`suite_manifest.json` must include:

- suite ID
- tested behavior IDs
- test case names
- expected oracle behavior
- mutant behavior expected to fail, if known

`authoring_manifest.json` must conform to `self-manifest.schema.json`.

## Allowed Dependencies

{{ALLOWED_DEPENDENCIES}}

## Forbidden Inputs

{{FORBIDDEN_INPUTS}}

