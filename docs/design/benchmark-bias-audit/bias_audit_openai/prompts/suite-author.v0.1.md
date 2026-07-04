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
- Make the suite bridge-executable by exposing a deterministic adapter seam that a future
  runner can bind to an implementation under test without editing `suite.py`.
- Write the two manifest files before writing `suite.py` so a timeout still leaves the run's
  declared artifact intent and bridge contract available for diagnostics.

## Output Contract

Write exactly these files in the current working directory, in this order:

- `suite_manifest.json`
- `authoring_manifest.json`
- `suite.py`

`suite_manifest.json` must include:

- suite ID
- tested behavior IDs
- test case names
- expected oracle behavior
- mutant behavior expected to fail, if known
- bridge contract metadata, including the callable names and request/response shape used by
  the adapter seam

`authoring_manifest.json` must conform to `self-manifest.schema.json`.

## Bridge Executability Contract

`suite.py` must be importable without network access, generated stubs, a live server, or writes outside
the suite directory. It may define local fixtures and expected case data, but the behavior checks must
be able to run against an injected implementation target.

Expose at least one of these vendor-neutral seams:

- Preferred: `bind_invoker(fn)`, where `fn(request: dict) -> dict` is stored by the suite and used by
  all implementation-facing tests.
- Acceptable: `configure(adapter)`, where `adapter` is a callable or object that the suite can use to
  invoke each test case.
- Acceptable: `run_all(call=None)`, `run_case(case_name, call=None)`, `run_ok_cases(call=None)`, or
  `run_invalid_cases(call=None)`, where the optional `call` argument supplies the implementation
  target.

Use plain JSON-compatible request and response dictionaries at the seam. Invalid-input cases should
expect a deterministic invalid-argument signal, either as a raised suite-local exception such as
`RpcStatusError(code="INVALID_ARGUMENT")` or as a result dictionary with an explicit
`code: "INVALID_ARGUMENT"` field. Do not hard-code successful behavior by bypassing the injected
implementation target in bridge-facing tests.

`suite_manifest.json` must declare the seam under a top-level `bridge_contract` object with:

- callable names exported by `suite.py`
- request shape and response shape
- invalid-argument signaling convention
- any suite-local exception class names used by invalid cases

## Allowed Dependencies

{{ALLOWED_DEPENDENCIES}}

## Forbidden Inputs

{{FORBIDDEN_INPUTS}}
