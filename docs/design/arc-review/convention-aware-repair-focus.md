# CRP Focus — Convention-Aware Repair (v0.2 requirements + plan)

Pre-implementation architectural review of a design that changes **shared contracts** across the
codegen pipeline. Weight findings toward where a wrong abstraction is expensive to undo later.

## Where we need input most

1. **FR-CAR-0 abstraction (critical path).** The "PythonConventionAuthority derived from the generators"
   is the foundation everything else consumes. Is deriving convention rules *from* the generator renderers
   the right source of truth — vs. extending `project_knowledge`'s producer, vs. a generator-adjacent
   manifest? What breaks if the authority and the generators drift? Is "derive from generators" even
   mechanically clean (the renderers encode idioms in Python string templates, not a declarative form)?

2. **Escalation-contract change.** FR-CAR-6 adds `RepairOutcome.unrepaired_diagnostics` and a residual
   payload on `EscalationHandoff` (Keiyaku K-6). Does this compose with the existing iterative-repair
   "complete true residual" (`REPAIR_RETRY_ITERATIVE`) and the K-6 contract, or duplicate/conflict with it?
   Is there one residual concept or two?

3. **Verdict-term change.** FR-CAR-7 adds a convention factor / hard-gate to `compute_disk_quality_score`.
   Risks: double-counting against `semantic_issues`; destabilizing existing scores/thresholds; interaction
   with the corpus's req-score (are there now two semantic-compliance numbers that can disagree?). Hard-gate
   (any convention error → 0.0) vs. weighted term — which, and why?

4. **Polyglot retrofit (FR-CAR-8).** Bringing the existing hand-coded C#/Go/Java convention steps under the
   FR-CAR-0 authority+parity discipline is a refactor of *working* code. Is the value worth the regression
   risk? Should it be deferred behind the Python proof, or is the unified model load-bearing from day one?

5. **Safe-fix vs escalate boundary (FR-CAR-4).** False-positive risk on legitimately dual-pattern code
   (e.g. `app/ai/extract.py` supports both `session.query` and `select`). Is "authority-scoped, AST-local,
   single-symbol, revert-on-break" a sufficient guard, or does deterministic convention rewriting need a
   tighter contract before it's safe to enable?

6. **Sequencing / advisory ramp.** Phase A is advisory-only; B flips behavior (escalation + verdict). Is
   the advisory→gating ramp staged safely (false-positive measurement before any FAIL)? Is FR-CAR-0 truly
   the only critical-path blocker, or are the model-contract changes (FR-CAR-6) independently sequenceable?
