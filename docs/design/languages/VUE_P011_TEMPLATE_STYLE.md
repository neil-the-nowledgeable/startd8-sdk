# Vue SFC: `<template>` and `<style>` (REQ-VUE-P-011, Phase C.5)

**Status:** Implemented — support level **documented**; **script-only** MicroPrime
splice; **LLM** for template/style when the task says so; **guardrail** snapshot
in `vue_sfc` + splice warning on mismatch.

## Support levels

| Area | Basic tier (this SDK) | Future / follow-on |
|------|------------------------|--------------------|
| **`<script>`** (primary) | Structured extraction, splice, Node parser parity, repair projection | — |
| **`<template>`** | LLM / whole-file edit when required by task; not a MicroPrime splicer block | Optional sub-block contract + tools |
| **`<style>`** (incl. `scoped`) | Same as template; **no** SCSS/Less unless project already does | Preprocessor awareness per REQ main doc |

## Guardrails

- `non_script_region_snapshot` / `non_script_blocks_unchanged` in
  `startd8.languages.vue_sfc` compare template + **inline** style bodies
  (external `<style src>` skipped).
- After Vue script splice, the splicer logs a **warning** if the snapshot
  changes — should not happen for a correct `reinject_vue_script` round-trip.

## References

- [REQ_JS_HOST_FRAMEWORKS_AND_VUE.md](REQ_JS_HOST_FRAMEWORKS_AND_VUE.md) — REQ-VUE-P-011
- [PLAN_PHASE_C_VUE_PARITY.md](PLAN_PHASE_C_VUE_PARITY.md) — stream C.5
