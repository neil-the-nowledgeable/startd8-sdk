# CRP Focus — Stakeholder Input Recommendations (Teian)

## Ground findings in the live code (fresh-context, code-grounded)

You have filesystem access. Do **not** review the docs in isolation — verify claims against the
actual implementation before proposing changes:

- `src/startd8/stakeholder_panel/` — especially `models.py` (`PanelAnswer`, `Grounding`, `Roster`,
  `PersonaBrief`), `vipp_bridge.py` (the pass template being mirrored), `panel.py`
  (`ask`/`ask_all`/`preflight_budget`), `routing.py` (`route`), `provenance.py` (the OBSERVED-synthetic
  path this feature must **not** reuse), `grounding_guard.py`, `cli_panel.py` (the CLI-as-writer +
  atomic-write + round-trip-gate template).
- `src/startd8/kickoff_inputs/` — `business_targets.py`, `conventions.py`, `build_preferences.py`
  (the strict parsers the round-trip gate reuses). Note there is **no** `observability` parser.

## Run a phantom-reference audit against §6 of the requirements

The requirements carry a §6 reference-audit table (exists / to-be-created). **Re-verify every row by
grep** and flag any symbol the spec assumes that does not exist as written (Leg 6 #12), and any
to-be-created symbol whose contract is under-specified.

## Highest-value concerns to weight

1. **Provenance integrity** — a `Recommendation` is an `estimate`, never the reactive
   `OBSERVED (project, synthetic)` claim. Verify no path can launder an estimate into an OBSERVED or
   an `authored` value; verify the domain-level-only in-file provenance (the strict schemas reject
   per-field keys) does not silently over- or under-report approval (OQ-KIR-7).
2. **The strict round-trip gate (FR-KIR-11)** — can a drafted value produce a YAML that the strict
   parser rejects? Is rejection surfaced, never silently written?
3. **Routing correctness (FR-KIR-3)** — no-owner skip, heuristic fallback, never drafted by a
   non-owning persona. Cross-check against `route()` semantics.
4. **Budget/degradation (FR-KIR-12/13)** — preflight-before-spend, cap, persona-failure leaves the
   field unchanged and never aborts the pass. Cross-check the `vipp_bridge.consult_panel` pattern.
5. **Staging artifact (OQ-KIR-1/2)** — is the out-of-band `proposals-<session>.json` the right seam,
   and does it carry enough (brief hash, roster version, disposition, origin) for an honest audit?

## SETTLED — do NOT relitigate (rejected-memory)

- The **panel v0.3 FRs** in `STAKEHOLDER_PANEL_REQUIREMENTS.md` (FR-1..FR-20) — already CRP-hardened;
  cite them, don't re-review them.
- The **`estimate` / `authored` / `config-default` provenance vocabulary** — owned by
  `KICKOFF_INPUT_PACKAGE_GUIDE.md` §3 (D-KIR-1). Do not propose a competing vocabulary.
- **Observability exclusion (NR-KIR-7)** — operator/lessons-decided (no parser; `config-default`;
  un-draftable owners). Do not re-propose drafting it.
- **Native-primitives / no-LangChain** and **CLI-as-writer / not-on-the-$0-read-floor** — settled by
  the panel doc (NR-4/NR-7).
