# Vue SFC and MicroPrime (REQ-VUE-B-008)

MicroPrime treats each ``.vue`` file as a **Vue 3 SFC**. The manifest repair
pipeline is skipped for ``language_id=vue`` (REQ-VUE-B-006) because buffers may
contain ``<template>`` / ``<script>`` markup, not Python. Contractor
``run_file_whole_contractor_repair`` also skips raw ``.vue`` buffers for the
same reason.

## Splicing (REQ-VUE-B-003)

``splice_body_into_skeleton(..., file_path=…)`` extracts the primary non-``src``
``<script setup>`` or first ``<script>`` block, runs the Node.js text splicer on
that inner script, then reinjects the result into the SFC. Pass the real file
path (e.g. ``src/App.vue``) so ``.vue`` dispatch runs.

## Full-file LLM (REQ-VUE-P-016)

File-level Ollama-whole for Vue SFC is **disabled by default**. Set
``STARTD8_VUE_FILE_OLLAMA_WHOLE=1`` to allow it. When disabled, MicroPrime logs
once per engine instance and uses element-by-element generation.

## Syntax checks (REQ-VUE-B-005 / REQ-VUE-P-005)

By default ``VueLanguageProfile.syntax_check_command`` runs
``npx vue-tsc --noEmit --pretty false {file}`` (from project root in Prime
checkpoints). Set ``STARTD8_VUE_SYNTAX_CHECK=0`` to disable subprocess checks
and rely on ``validate_syntax`` (extracted script + Node check) only.

## Scope and Part C

**Basic tier (this doc):** script-block–centric workflow; do not expect
MicroPrime to rewrite ``<template>`` or ``<style>`` unless the task explicitly
covers them. **Parity / template tooling:** see
[PLAN_PHASE_C_VUE_PARITY.md](PLAN_PHASE_C_VUE_PARITY.md). **Host vs dialect:**
[PLAN_PHASE_A_JS_HOST_ABSTRACTION.md](PLAN_PHASE_A_JS_HOST_ABSTRACTION.md).

Fixture: ``tests/fixtures/lang-vue-basic/App.vue``.

**Phase C:** broader parity (parsers, TS rigor, repair matrix, template policy) is tracked in [PLAN_PHASE_C_VUE_PARITY.md](PLAN_PHASE_C_VUE_PARITY.md).
