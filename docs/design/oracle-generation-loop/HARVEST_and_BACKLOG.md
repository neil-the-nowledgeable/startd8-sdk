# Oracle-Generation-Loop — HTH Harvest + Enhancement Backlog

**Harvested:** 2026-08-17 · **Surface:** the shipped loop (`804e9dd3`, 2,138 LOC) · **Scope:** `src/startd8/oracle_loop/`, `cli_oracle.py`, `deploy_harness/{ladder,deploy}.py` edits.

## Phase 1 — code-review (§1.5 value-path, security-weighted)

### Applied (Fix report)
- **[High/security-hardening] H1** — `runner._resolve_oneshot_cmd` left an **unresolved bare console-script verb** (`rm`/`curl`/`sh`) to run on the sandbox PATH. Contained by the sandbox (no host harm / no network), so not an RCE — but **wider than FR-2's "closed convention" claim** (claim>gate). Fixed: an unresolved console-script (not `pytest`/`python`, no `app/bin/` entry) → fail-loud `error`, never executed. One-shot allow-list is now genuinely `{pytest, python, resolved-app-console-script}` (defense-in-depth: sandbox + closed verb gate). +1 regression test (asserts `run_sandboxed` is never called).

### Verified clean (do not re-flag)
- **Service probe** is data-only: `_make_probe_client` renders a fixed loopback `httpx` call from `ProbeSpec` (method/path/body/status) — no clause-derived code (R1-F3 holds). The host-side `client(port)` carries only parsed data.
- **Sandbox routing:** one-shot→`run_sandboxed`, service-boot→`run_service_sandboxed`, live-probe→data-only httpx. All exec contained.
- **FR-11 gate:** `_run_oracle_rung` returns before any exec if `spec_path is None or not enabled`; the loop short-circuits to `disabled`. No generation/exec path while off.
- **Termination:** `for iteration in range(1, max_iterations+1)` is a hard ceiling + monotone-reduction stall + cumulative budget + `regen_rejected`. Provably bounded; no double-spend (remaining budget threaded).

## Phase 2 — python-code-refactor: **skipped** (freshly reviewed, fully typed, explicit degrade/error handling; no robustness gap beyond H1).

## Phase 3 — retrospective

### Extracted standard (Yokoten): **Effect-injected loop core**
An LLM-orchestration loop should take its **expensive / non-deterministic effects** (generation, deployment) as **injected callbacks** (`generate_fn`/`deploy_fn`), so the deterministic control logic — termination, cumulative budget, monotone stall, coverage/floor/`no_fitness`, the per-FR fitness verdicts, the Goodhart gate — is **fully testable at $0** without a real model. The real effects (Prime + `deploy_app_local`) are wired only at the CLI boundary (`cli_oracle.py`). This is REQ-08's "test the harness, not the model" made concrete as an architecture, and it's why this 2,138-line surface has 43 deterministic $0 tests. Reuse for any future generation/agent loop.

### Phase-2.5 dormant inventory
| Symbol | Evidence | Status |
|--------|----------|--------|
| `is_spec_satisfied` / `assertion_confirmed` (FR-7 gate) | `loop.py:301` consumes it; reads `assertion_confirmed==true` | **wired + real** (gate is not hollow) |
| `run_oracle` / grammar / gate / loop entry / CLI | all have non-test callers (reachability) | **wired** |
| **`_run_service_boot` / `run_oracle(server_cmd=…)` boot path** | ORACLE rung always calls with `live_port` (`deploy.py:72`); **no** prod caller, **no** test | **dormant + untested** → OL-EB-2 |

## Phase 4 — enhancement backlog (single-pass; NR-5 fork from CEP — bounded surface)

| ID | Effort | Row | Evidence |
|----|--------|-----|----------|
| **OL-EB-1** | M | The real-LLM end-to-end validation: `build-to-spec` **enabled** against a live model on a hand-authored generated-app spec (the deferred fidelity step — the build is $0 stub-validated). Gate behind `doppler run`. | `cli_oracle._build_generate_fn` wires real Prime but only structurally tested |
| **OL-EB-2** | S | The `server_cmd` boot-and-probe path (`_run_service_boot`) is dormant + untested — **either** wire it to a standalone `oracle-run --spec --app` CLI (the plausible use: run the oracle without the full deploy ladder) **or** remove it and require `live_port`. Don't leave test-only-dormant (the REQ-08 `topo_order` lesson). | Phase-2.5 above |
| **OL-EB-3** | S | The console-script resolution assumes the deploy harness produced an `app_root/bin/<script>` venv layout — validate/document that `deploy_app_local`'s venv actually populates `bin/` with the app's console-scripts, else no console-script clause resolves. | `runner._resolve_oneshot_cmd` |
| **OL-EB-4** | S | Richer inline probes (`matches=<json-path>`, headers, auth) are deferred to the `pytest` power path (a1 two-tier). If authors want declarative multi-assertion probes, extend the `probe` micro-grammar additively. | `grammar._PROBE_RE` |

## Phase 5 — bus: **skip** (`no bus peer`) — internal SDK capability, no cross-repo contract edge; the reusable standard is recorded here + in-repo.

---
*HTH harvest of the oracle-generation loop. 1 High security-hardening applied (H1); standard extracted (effect-injected loop core); 1 dormant path + 3 enhancement rows filed. Surface held up well — the CRP + reflective passes front-loaded most of the risk.*
