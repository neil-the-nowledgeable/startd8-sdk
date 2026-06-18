# Proto-Collection Prompt Template v0.1

## Run Metadata

{{RUN_METADATA}}

## Role

You are proposing a gRPC contract shape from a neutral source brief. This output is collected only for
divergence analysis and optional contract-shape sensitivity. It is not used in the primary FR-6
score-impact run.

## Neutral Brief

{{NEUTRAL_BRIEF}}

## Experiment Instructions

{{EXPERIMENT_INSTRUCTIONS}}

Default experiment instruction for this template:

- Author only a `.proto` contract and a contract rationale.
- Keep all source-grounded FIXED items expressible.
- Make explicit decisions for every OPEN item your contract resolves.
- Do not copy existing pricing seed names listed as forbidden inputs.
- Do not include implementation code or tests.

## Output Contract

Write exactly these files:

- `pricing_candidate.proto`
- `contract_rationale.md`
- `authoring_manifest.json`

`contract_rationale.md` must include:

- field/message naming rationale
- mapping from FIXED items to proto elements
- OPEN item decisions
- known omissions

`authoring_manifest.json` must conform to `self-manifest.schema.json`.

## Allowed Dependencies

{{ALLOWED_DEPENDENCIES}}

## Forbidden Inputs

{{FORBIDDEN_INPUTS}}

