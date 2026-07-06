# CRP Focus — Value-Input Confirmation

**Least-reviewed target:** both docs are new (Requirements v0.3, Plan v1.0); neither has had external review.

**SETTLED — do NOT relitigate** (record any disagreement in Appendix C only, do not re-open):
- OQ-1 = **additive ledger** (`docs/kickoff/inputs/.confirmed.yaml`, `value_path → {value, at}`) — a user decision.
- **Per-field provenance does not exist today** — verified by code investigation, not an oversight.
- $0 / no-LLM kernel posture; all writes go through `concierge/safe_write.py`.
- Byte-identical guarantee is over the **domain input files**; the `assess` output intentionally gains the honest count.
- MVP scope = CLI verb + honest count; the guided multi-field flow is deferred (NR-1).

**Weight the review on these concerns:**

1. **Ledger ↔ existing scanners.** Does `drift.py` / wireframe / `instantiate` / `_assess_cascade` need to explicitly ignore `.confirmed.yaml`? Does placing it under `docs/kickoff/inputs/` risk it being read as an input domain or hashed into drift? Is a different location safer (e.g. `.startd8/` vs `inputs/`)?
2. **Ledger ↔ hand-edit drift (plan R2).** A user hand-edits a value the ledger recorded. Is "confirmation = a decision act, not a value-lock" the right model, or does assess need a "stale confirmation" signal?
3. **`--as-is` confirm semantics (OQ-3).** Confirming the current default unchanged — recorded how, and does it read honestly in the count?
4. **Confirmable-set vs confirmed-ness separation (plan R4).** Any remaining conflation of the static `default_config()` set with project-state confirmed-ness?
5. **Atomicity of the two-write sequence** (field value, then ledger) in `apply_confirm` — partial-failure behavior; is value-first correct; should it be one transaction?
6. **FR-7 — fully remove vs delegate** the legacy `"REVIEW"` sentinel prefill.

**Dual-mode:** ≥3 F-prefix (requirements) and ≥3 S-prefix (plan) anchored suggestions; append a Requirements Coverage Matrix to the plan.
