# Contract Leverage Consolidation + ContextCore Contracts Adoption — Implementation Plan

**Version:** 0.1 (initial plan)
**Date:** 2026-06-12
**Status:** Draft — ready to build
**Worktree:** `startd8-sdk-contracts` (branch `feat/contracts-leverage-finish`)
**Covers:**
- `CONTRACT_LEVERAGE_CONSOLIDATION_REQUIREMENTS.md` v0.2 (Semantic Validation — the keystone + 3 gated eliminations)
- `CONTEXTCORE_CONTRACTS_ADOPTION_REQUIREMENTS.md` v0.2 (the remaining unshipped contracts-adoption items)

> **One-line framing.** Generation already builds to a typed contract; the *detached* Semantic
> Compliance Reviewer can't reach it (the forward manifest is never persisted) so it re-derives intent
> from prose. **Persist the one contract artifact (keystone), then delete the three duplications it was
> forcing.** Separately, finish the two cheap ContextCore contract layers (postexec wiring + regression
> CLI surface) that the adoption pass left at "function exists, not wired."

---

## 0. What's already done (baseline in this branch)

Committed on `feat/contracts-leverage-finish` (wip commit `b8beb904`):
- `workflows/_contracts_integration.py` — `run_preflight()` (FR-PRE-1/2/3) + `compare_contracts()` (FR-REG-1).
- `workflows/registry.py` — preflight wired into both sync `run_workflow` and async `arun_workflow`.
- `tests/unit/workflows/test_contracts_integration.py` — preflight + compare graceful-degradation tests.

So **preflight (Quick Win #2) is functionally landed**; **regression (Quick Win #1) has its helper but
no CLI/CI surface yet**. Everything in the Contract-Leverage doc (Semantic Validation) is **not started**.

---

## 1. Open-question resolutions (from the planning investigation)

These are load-bearing; the plan below depends on them.

| OQ | Resolution | Consequence for the plan |
|----|-----------|--------------------------|
| **CL OQ-3** (Pydantic round-trip) | **YES, clean.** `ForwardManifest`/`InterfaceContract`/`ForwardElementSpec` are frozen Pydantic v2 models; only `_element_index`/`_name_index`/`_index_built` are `PrivateAttr` (auto-excluded, rebuilt lazily). `binding_text` is a **stored** `str` field (`forward_manifest.py:90`). | **FR-CL-1 is trivial**: `model_dump_json()` → `model_validate_json()`. No pre-work. |
| **CL OQ-4** (detached SCR reachability) | The SCR globs the **run output dir** for `prime-context-seed*.json` (`requirement_loader._select_seed_file`, `orchestrator.py:100`). The post-mortem uses `.startd8/` (`_manifest_path().parent`). These can differ. | **Write `forward-manifest.json` to the seed dir (run output dir)** so the detached SCR reaches it; post-mortem reads the same path (falls back from its in-memory param). See Risk R-1. |
| **CL OQ-5** (api_sig provenance tag) | **No `source`/`origin` field on `ForwardElementSpec`.** api_sig-derived class/function/method specs set `source_contract_id` (`extractor.py:781,890`); **variable/constant specs do NOT** (`extractor.py:794-799`). | E1 parity set must be derived by **walking `InterfaceContract`s whose `source_reference=="deterministic"`** and collecting their element names via the contract→element index — **not** by filtering specs on a tag. Variables need explicit handling (see WI-3). |
| **CL E3 location** | The `api_signatures` prose is fused into `task_description` **upstream in the design/seed stage** (`consumption_map.py:72-76`), **not** in `spec_builder.py`. | E3's gate/edit relocates to the seed/consumption layer, not `spec_builder`. May be reclassified to "deferred — different owner" (see WI-5). |
| **Adoption OQ-5** (L4 records) | SDK persists **no L4 runtime boundary records** (exit-only). | FR-POST-1 ships **chain-integrity + exit-requirements only**; L4 cross-ref stays deferred. |

---

## 2. Scope & sequencing

```
PHASE 1 — Semantic Validation keystone + eliminations (the headline)
  WI-1  FR-CL-1   Persist forward-manifest.json            [enabler — unblocks WI-2..4]
  WI-2  FR-CL-1   Post-mortem + detached SCR read it       [enabler completion]
  WI-3  FR-CL-3   E1: delete _NAME_RE (parity-gated)
  WI-4  FR-CL-2   E2: reviewer reads InterfaceContract     (behavior-gated)
  WI-5  FR-CL-3b  E3: drop api_signatures prose round-trip (golden-gated; scope TBD per §1)
  WI-6  FR-CL-3c  Anti-regression guard (grep+test)
  WI-7  FR-CL-5   Dedup parser_tier severity helper        [tiny]

PHASE 2 — Finish ContextCore contracts adoption (the "few other places")
  WI-8  FR-REG-2  Wire compare_contracts into a CLI/validate surface
  WI-9  FR-POST   postexec: run_postexec() helper + wire run-end (chain + exit only)
  WI-10 FR-CC-4   Verify OTel emission (not just get_logger) for preflight/postexec/regression

OUT OF SCOPE (explicitly deferred by both reqs docs)
  - FR-CL-4 binding_text → computed property (serialization change)
  - FR-CL-6 single generation-context assembler (the big architectural slice)
  - FR-ORD ordering / CausalClock, FR-LIN lineage / LineageContract (need new emission)
```

**Critical path:** WI-1 → (WI-2, WI-3, WI-4) → WI-5/WI-6. WI-7 is independent. Phase 2 is independent of Phase 1.

---

## 3. Work items (detailed)

### WI-1 — FR-CL-1 (keystone): persist `forward-manifest.json`
- **File:** `src/startd8/contractors/prime_contractor.py`, in `PrimeContractor.run()` (~after the
  `self._write_generation_manifest(result_dict)` call, ~line 5730).
- **Change:** when `self._forward_manifest is not None`, write
  `self._forward_manifest.model_dump_json(indent=2)` to **the run output dir** (the dir the detached
  SCR globs — see R-1 for exact resolution), guarded by `try/except OSError → logger.warning`.
- **No-op safety:** if no seed contained a forward manifest, `self._forward_manifest` is `None` → write nothing.
- **Tests:** unit — run a PrimeContractor with a manifest-bearing seed (or stub `self._forward_manifest`),
  assert the file exists and `ForwardManifest.model_validate_json(path.read_text())` round-trips equal.
- **Gate:** round-trip equality test green.

### WI-2 — FR-CL-1 (read side): post-mortem + detached SCR consume the persisted artifact
- **Files:** `src/startd8/contractors/prime_postmortem.py` (param at `~1605`, consumed in
  `_evaluate_disk_quality` `~2499-2613`); `src/startd8/semantic_compliance/requirement_loader.py`
  + `orchestrator.py`.
- **Change (post-mortem):** keep the in-memory `forward_manifest` param as fast path; when it is `None`,
  load `forward-manifest.json` from the output dir. Guarded; `None` on miss → today's behavior.
- **Change (SCR):** add a manifest loader alongside `_select_seed_file` that resolves
  `forward-manifest.json` in the same dir; expose the loaded `ForwardManifest` to the reviewer
  (used by WI-3/WI-4). Absent file → reviewer keeps today's prose-only path (FR-CC-1 ethos).
- **Tests:** post-mortem reads disk when param `None`; SCR locates manifest next to seed; both degrade
  gracefully when the file is missing.
- **Gate:** graceful-degradation tests green; reachability proven (file found from seed dir).

### WI-3 — FR-CL-3 (E1): delete `_NAME_RE`, use the manifest
- **File:** `src/startd8/semantic_compliance/signature_check.py` (regex at `26-30`, used `37/40`).
- **Replacement source of names:** the parity set is `{element.name for c in manifest.contracts
  if c.source_reference == "deterministic" for element in elements_of(c)}` via the contract→element
  index (`source_contract_id`). **Variables:** because variable specs carry no `source_contract_id`,
  add a targeted path — either (a) also collect names from `InterfaceContract`s of the variable kind
  if present, or (b) document that `_NAME_RE`'s variable arm (`(?P<var>\w+)\s*[:=(]`) had no manifest
  equivalent and assert the parity test covers only the kinds the extractor produces. Decide during
  build against the corpus.
- **Gate (hard):** **parity test** — over a corpus of seeds,
  `required_symbol_names(api_signatures) == manifest_api_sig_names(...)`. **Ship the deletion only if
  parity holds.** If it fails on variables, narrow E1 to functions/classes/methods and leave the
  variable backstop, or add a minimal `source` tag (last resort — touches serialization, weigh vs AG-1).
- **Tests:** parity test + existing signature_check behavior tests unchanged.

### WI-4 — FR-CL-2 (E2): reviewer rubric reads the contract
- **Files:** `src/startd8/semantic_compliance/reviewer.py` (`~101-110`, passes
  `api_signatures=loaded.api_signatures` to `render_rubric`); `prompts.py` (`~62`, `API SIGNATURES:`).
- **Change:** when the persisted manifest is available, render
  `[c.binding_text for c in manifest.contracts]` (+ `ForwardElementSpec`s) as the structural authority;
  keep `requirement_text` as **supporting** context (OQ-1: contract for *structure*, prose for *behavior*).
- **Gate (hard):** **behavior test** — verdicts on a known corpus must not regress, specifically the
  **Run-029 missing-symbol case** (must still FAIL).
- **Tests:** corpus behavior test; manifest-absent path falls back to prose (FR-CC-1).

### WI-5 — FR-CL-3b (E3): drop the `api_signatures` prose round-trip
- **Reality check (§1):** the prose embedding is upstream in `consumption_map.py:72-76` (design/seed
  stage), not `spec_builder`. Two options:
  - **(a) In-scope, relocated:** remove/skip the `api_signatures`→`task_description` prose fusion in
    `consumption_map.py` once the structured `InterfaceContract` P0 binding is confirmed to carry the
    same content. **Gate:** golden-prompt diff shows only the prose block removed; the P0 structured
    binding (`spec_builder.py:1165-1176`) is unchanged.
  - **(b) Defer:** if the consumption-map fusion has other consumers, reclassify E3 as a separate slice
    (it is generation-side, not the SCR asymmetry — lower value than E1/E2).
- **Decision rule:** prefer (a) if the only consumer of the fused prose is the generation prompt and the
  golden diff is clean; else (b). Record the decision in v0.3 of the reqs (step 2).

### WI-6 — FR-CL-3c: anti-regression guard
- **Add:** a test that greps `src/` for `api_signatures` regex parsing and asserts the only matches are
  in `forward_manifest_extractor._extract_api_signatures`. (Allowlist that one site.)
- **Gate:** runs in CI; fails if a new consumer re-parses `api_signatures`.

### WI-7 — FR-CL-5: dedup `parser_tier` severity calibration
- **Files:** `forward_manifest.py:608`, `forward_manifest_validator.py:89-96`.
- **Change:** extract `_severity_for_parser_tier(tier) -> str` (`"warning" if tier == "advisory" else
  "error"`) into one location; import at both sites. Note the two sites do slightly different things
  (one *skips* on `None`, one *maps* severity) — factor only the shared **severity-mapping** logic.
- **Tests:** unit on the helper; existing validator tests unchanged.

### WI-8 — FR-REG-2: surface `compare_contracts` at validate/CLI time
- **File:** the `manifest validate` CLI path (locate the existing `manifest` command group in `cli.py`).
- **Change:** add an optional `--against <old-contract>` (or auto-detect prior version) that calls
  `compare_contracts(old, new)` and prints the `DriftReport`; off-run, advisory by default.
- **Tests:** CLI invocation prints drift; absent ContextCore → graceful no-op (FR-CC-1).

### WI-9 — FR-POST: postexec helper + run-end wiring
- **File:** `workflows/_contracts_integration.py` (new `run_postexec(workflow, result, *, fail_closed)`)
  + `workflows/registry.py` (call after `workflow.run`/`arun` success, beside existing exit validation).
- **Change:** when `contract_path` present, call `PostExecutionValidator(...).validate(...)` for
  chain-integrity + final exit requirements (**no L4 cross-ref** — OQ-5). Advisory by default; attach
  findings to the run's post-mortem artifacts (FR-POST-2). Route through the single helper (FR-CC-5).
- **Tests:** mirror the preflight tests (noop without contract_path; never raises; fail_closed accepted).

### WI-10 — FR-CC-4: verify OTel emission
- **Check:** confirm preflight/postexec/regression findings emit via OTel (not just `get_logger` text).
  If the project's convention is span events/metrics, add them; else document that `get_logger` (with the
  OTel log bridge) satisfies FR-CC-4 and add a test asserting a log record is produced.

---

## 4. Risks & mitigations

- **R-1 (write/read location mismatch).** Post-mortem uses `.startd8/`; detached SCR globs the run output
  dir for seeds. **Mitigation:** make the **seed dir** (run output dir) the canonical write location for
  `forward-manifest.json`; have the post-mortem fall back to that same dir. Add a test that the SCR finds
  the file from the seed path. Verify the exact dir during WI-1 (don't assume `.startd8`).
- **R-2 (E1 variable parity, OQ-5).** Variable specs lack `source_contract_id`. **Mitigation:** corpus
  parity test is the gate; if variables break parity, narrow E1 (keep regex variable arm) rather than
  add a model field. Don't ship E1 on a red parity test.
- **R-3 (E3 has other consumers).** **Mitigation:** golden-prompt diff + grep for `consumption_map`
  output consumers before removing; fall back to defer (option b).
- **R-4 (regressing SCR verdicts).** **Mitigation:** WI-4 is gated on the Run-029 behavior test; manifest
  absent → unchanged prose path.
- **R-5 (scope creep into FR-CL-6/FR-CL-4).** **Mitigation:** explicitly out of scope; AG-1/AG-2 hold
  (no new contract type, no new enricher/validator).

---

## 5. Test/gate summary (ship criteria)

| WI | Gate (must be green to ship) |
|----|------------------------------|
| WI-1/2 | round-trip equality; graceful degradation (absent file); SCR reachability from seed dir |
| WI-3 (E1) | **parity test** over corpus (api_sig names == manifest names) |
| WI-4 (E2) | **behavior test** — Run-029 missing-symbol still FAILs; no corpus regression |
| WI-5 (E3) | **golden-prompt diff** — only prose block removed; structured binding unchanged |
| WI-6 | anti-regression grep/test green in CI |
| WI-7 | helper unit test; validator tests unchanged |
| WI-8 | CLI prints drift; graceful no-op without ContextCore |
| WI-9 | preflight-style helper tests; findings attached to post-mortem |
| WI-10 | OTel emission asserted (or documented as satisfied by log bridge) |

---

## 6. Reflective-requirements follow-up (step 2)

The planning pass surfaced four deltas that should be **folded back into the requirements** (v0.2 → v0.3)
before/while building, per the standing "requirements before implementation" rule:
1. **CL OQ-3 resolved** → mark FR-CL-1 "trivial, no pre-work" (clean Pydantic round-trip).
2. **CL OQ-5 resolved with a caveat** → record that there is **no provenance tag**; the api_sig set is
   derived via `source_contract_id` on deterministic contracts, and **variables are not tagged**
   (affects E1 parity scope).
3. **E3 relocation** → the prose embedding is in `consumption_map.py` (design/seed), **not**
   `spec_builder.py`; update FR-CL-3b's location/gate, possibly reclassify as a separate slice.
4. **CL OQ-4 resolved** → canonical write location is the **seed/run output dir**, not `.startd8`;
   record the reachability decision (R-1).

These are genuine spec-affecting discoveries (not just build details), so the reflective loop earns its
keep here — it's a focused fold-back, not a full re-spec.
