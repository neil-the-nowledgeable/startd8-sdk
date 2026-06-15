# Convergent Review Prompt — Track 2 P1+P2 (Dependency Provisioning Security) — Review Round R1

> **You are an AI reviewing agent with Write/Edit tools and filesystem access to the two source
> documents below.** Run **one** Convergent Review Protocol round (Review Round R1, model-agnostic)
> in **dual-document mode**. Your deliverable is **edits to the source files**, not a chat essay.
> Your chat reply is a short write-confirmation only.

---

## Orchestrator Note (for the human who generated this file — NOT instructions to the reviewer)

- **Triage is orchestrator-side and happens later.** You (the reviewer) do **not** triage. Do **not**
  produce ACCEPT/REJECT tables, do **not** rewrite existing prose, and do **not** modify any populated
  Appendix A or Appendix B. After you append your round, a human (or follow-up agent) will read your
  suggestions and route each to Appendix A (accepted, with where-merged) or Appendix B (rejected, with
  rationale). Those appendices are the cross-model memory later reviewers inherit.
- **Rounds / threshold are orchestrator workflow knobs**, not reviewer tasks. This is a single round
  (R1). Threshold for "substantially addressed" = 3 accepted suggestions per area.
- **Max suggestions:** up to 10 S-prefix (plan) + up to 10 F-prefix (requirements) for this round.
  Quality over quantity — deprioritize unanchored generics.
- The reviewer **must** have Write/Edit tools and filesystem access to both source docs. A chat-only
  model cannot satisfy this contract.

## Source Documents (write targets — use these absolute paths)

| Role | Absolute Path |
|------|---------------|
| **Requirements** (F-prefix → its Appendix C) | `/Users/neilyashinsky/Documents/dev/startd8-informative-knobs/docs/design/benchmark-scoring/TRACK2_P1P2_REQUIREMENTS.md` |
| **Plan** (S-prefix → its Appendix C; also gets the Requirements Coverage Matrix) | `/Users/neilyashinsky/Documents/dev/startd8-informative-knobs/docs/design/benchmark-scoring/TRACK2_P1P2_PLAN.md` |
| **CRP Guide** (reference, embedded below) | `/Users/neilyashinsky/Documents/dev/startd8-informative-knobs/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` |

Both source docs currently have **no** Appendix A/B/C scaffold — you are the **first** reviewer (R1).
Initialize the appendix scaffold on **each** doc (Phase 0 of the guide) before appending your round.

---

## Configuration

- **Mode:** dual-document (plan + requirements), Review Round **R1**, model-agnostic framing.
- **Scope of this review is DELIBERATELY NARROWED** to the **security / risk of P1 (dependency
  provisioning)** for the startd8-sdk Track 2 behavioral benchmark, with a secondary pass over P2
  invariant-suite discrimination. Spend the bulk of your suggestion budget on the **PRIMARY FINDING**
  below; then hunt for adjacent gaps. Do **not** dilute the round with generic architectural advice
  unrelated to provisioning safety, reproducibility, or invariant discrimination.
- **Persist** all suggestions to the source files' Appendix C as `R1-S{n}` (plan) / `R1-F{n}`
  (requirements). Append a `## Requirements Coverage Matrix — R1` section to the **plan** file.

---

## Focus — Where We Need Reviewer Input Most

Answer each focus ask near the **top** of your appended Appendix C block on the relevant doc, using
this 4-line template per ask: **Summary answer / Rationale / Assumptions / Suggested improvements**.
Then convert the concrete gaps into anchored `R1-S{n}` / `R1-F{n}` suggestions in the tables.

### PRIMARY FINDING TO PRESSURE-TEST — provisioning executes untrusted code unsandboxed

This is the single most important thing to scrutinize. **Direct your adversarial scrutiny here FIRST
AND FOREMOST**, then look for others.

P1 (plan step **S1**, `provision_workdir`) runs **`npm install` / `go mod tidy` / `pip install` /
`dotnet restore`** on **model-generated manifests** at **PREPARE time**, which the requirements and
plan explicitly place **OUTSIDE the egress-denied sandbox** (FR-P1-3: *"provisioning (network) happens
at prepare time only; the scored server run stays egress-denied (loopback-only sandbox)"*; plan S1:
*"runs at prepare time (network allowed; the scored run stays sandboxed)"*).

The problem: **the package installers themselves execute arbitrary code on untrusted input.** This is
not a hypothetical:
- **npm** runs lifecycle / `postinstall` scripts from every declared (and transitively pulled) package.
- **Declared deps can be malicious or typosquatted** — a model can name (or hallucinate) a hostile package.
- **`go mod tidy`** fetches arbitrary modules from arbitrary hosts derived from import paths in
  model-written source.
- **pip** executes `setup.py` (and build backends) for sdist installs.
- **dotnet restore** runs NuGet restore with package-defined MSBuild targets.

This **re-opens the exact arbitrary-code-execution-against-untrusted-model-output threat (FR-44 of the
parent Summer 2026 benchmark)** that the run-time sandbox (`run_service_sandboxed`,
loopback-allowed/egress-denied) exists to contain. The merged pilot **avoided this entirely** by never
installing anything the model declared — it used a **hand-vendored Node closure** (`node_runtime/`,
pino→uuid→pino-pretty wired by hand). Generalizing provisioning to actually *install model-declared /
import-derived deps* is precisely the step that punctures that containment.

**FR-P1-3 names the prepare/run boundary but does NOT address that PROVISIONING ITSELF is the
untrusted-code surface.** Note the irony surfaced in requirements §0 / FR-P1-1: because models
*under-declare*, the design leans on a **curated common set** as primary — but the *secondary*
declared-install + Go's import-derived `go mod tidy` are exactly the untrusted-input paths.

**The reviewer must answer:** Is unsandboxed provisioning of model-authored manifests **acceptable**
for this benchmark? If not, which controls should the requirements **mandate** (not merely allow)?
Consider and rule on each:
- **No-scripts installs** — e.g. `npm install --ignore-scripts`, pip `--only-binary=:all:` / no-build-isolation
  policy, disabling NuGet/MSBuild restore targets, `GOFLAGS=-mod=...` constraints. What's the residual risk after this?
- **Network allowlist / egress proxy** at prepare time (registry hosts only) rather than open network.
- **Provisioning inside its own sandbox** (a prepare-time sandbox distinct from the run-time one) —
  is the asymmetry (sandbox the *run* but not the *install*) defensible?
- **Vendored-only / offline mode** — make the curated common set the *only* source and forbid network
  fetch of model-named deps entirely (closes the surface; costs breadth — is that the right trade for a benchmark?).
- **Dependency pinning + integrity hashes** (lockfiles, `--require-hashes`, `go.sum` verification,
  npm integrity) — both a security control and a reproducibility control.
- **Per-cell isolation** so one cell's install cannot poison another cell's cache / later cells.

### SECONDARY concerns to scrutinize (P1)

- **(a) Offline / airgapped behavior.** The broader benchmark may run headless with no network. Does
  provisioning **fail-closed** (degrade honestly per FR-P1-4/FR-P1-5) when fetch is impossible, or does
  it hang / silently fall back / score 0? Is "network allowed at prepare" an *assumption* the env may violate?
- **(b) Cross-cell cache poisoning.** S1 reuses a **warmed `GOMODCACHE`/`GOCACHE`** (and analogous
  npm/pip caches) across cells (FR-P1-2/FR-P1-6). Can a malicious or buggy cell **corrupt** that shared
  cache so a *later, innocent* cell builds against poisoned modules? Is the cache write-shared or
  copy-on-read? Does FR-P1-6's idempotency ("skip if already provisioned") trust a poisoned marker?
- **(c) Version pinning / non-determinism.** Unpinned installs make two cells with the *same spec*
  resolve **different** dependency versions, undermining **benchmark reproducibility** (parent FR-19).
  `go mod tidy` and floating npm/pip ranges are non-deterministic over time. Should the common set and
  any declared-install be **fully pinned + hash-locked**, and should the cache be content-addressed?
- **(d) Build cost vs per-cell timeout (OQ-7).** Cold `go mod tidy`+compile and gradle resolution can
  exceed the per-cell timeout — but the *mitigation* (warm shared caches) is exactly concern (b)'s
  attack surface. Is there a control that satisfies **both** (e.g., a pre-warmed **read-only** cache)?
- **(e) Curated-common-set-primary vs declared-install interaction.** Since models under-declare
  (FR-P1-1), the common set carries the load — but does layering declared-install on top create a
  **version conflict / shadowing** hazard (declared dep at version X vs common-set X′)? Does it widen
  the untrusted surface for marginal benefit (cf. OQ-8 import-scan)? Is declared-install worth its risk?
- **(f) Secret leakage during provisioning network use.** The parent benchmark mandates a scrubbed
  environment + Loki redaction (FR-45). Does that scrubbed-env discipline apply at **prepare** time
  too, or can a `postinstall` script / build backend read env vars / `.npmrc` / registry tokens and
  exfiltrate them over the open prepare-time network?

### Also briefly cover — P2 invariant suites

- Do the chosen invariants (**identity** for `Convert`, **validation/rejection**, **non-negativity** for
  `GetQuote`, **determinism**, **count limits** for `GetAds`) actually **discriminate** flagship models,
  or do they risk **saturating** (all models pass → non-discriminating, the Track-1 verbosity trap that
  FR-P2-5 warns of)? `GetAds` is flagged as the weakest expected discriminator.
- Is the **pilot-each-once gate (FR-P2-4 / plan S5)** *sufficient* to catch saturation before funding
  N reps, or does running each RPC only once across the roster risk a false "discriminates" / false
  "saturates" read on a single noisy draw? Should it require a known-broken reference (plan S3 fixtures)
  to confirm the suite can *detect* breakage, not just observe pass/fail variance?

---

## Reviewer Contract (read before writing)

1. **First, read both source files** and the embedded CRP guide. Both docs lack the appendix scaffold,
   so **initialize** the `## Appendix: Iterative Review Log (Applied / Rejected Suggestions)` structure
   (Appendix A / B / C, with the verbatim template from the guide's Phase 0b) at the end of **each** doc.
   Initialization is purely additive — **do not modify either document body.**
2. **Append exactly one round**, `#### Review Round R1 — <your literal model id> — <UTC date>`, under
   each doc's **Appendix C**:
   - **Plan doc** (`TRACK2_P1P2_PLAN.md`) — gets the **S-prefix** table (`R1-S{n}`) using the 7-column
     format, the **focus answers** (4-line template) at the top of the block, an optional
     `### Stress-test / adversarial pass` subsection (continue `R1-S{n}` ids), **and** a
     `## Requirements Coverage Matrix — R1` section mapping each requirements section to plan coverage
     (Full / Partial / Missing + Gaps).
   - **Requirements doc** (`TRACK2_P1P2_REQUIREMENTS.md`) — gets the **F-prefix** table (`R1-F{n}`) for
     issues *in the requirements themselves* (ambiguous / conflicting / incomplete / missing / untestable),
     wrapped in its own `#### Review Round R1` heading. Do **not** put S-prefix ids here, or F-prefix ids
     in the plan.
3. **Anchoring bar (dual-document):** at least **three** anchored `R1-S` suggestions and at least
   **three** anchored `R1-F` suggestions, each tied to a concrete FR id / plan step / line. Most should
   target the PRIMARY FINDING and the P1 secondary concerns. Deprioritize unanchored generics.
4. **Self-filter vague noise.** Every suggestion must be actionable, anchored, scoped, and testable
   when relevant. No ACCEPT/REJECT tables. No rewrites of existing prose. Do **not** triage.
5. **Table columns (exactly 7, plain text headers):** `ID`, `Area`, `Severity`, `Suggestion`,
   `Rationale`, `Proposed Placement`, `Validation Approach`. Area ∈ {Architecture, Interfaces, Data,
   Risks, Validation, Ops, Security} (title case); Severity ∈ {critical, high, medium, low} (lowercase).
   For this scope, most provisioning-safety findings will land under **Security** and **Risks**;
   reproducibility under **Validation** / **Data**; cache/cost/offline under **Ops**.
6. **Length budget:** ~500–1500 words across the appended appendices (more if you answer all focus asks).
7. **The persist-to-files scope WINS over the guide's Phases 5–7** (triage / merge / coverage-section
   maintenance). You **do** append to Appendix C and initialize the A/B/C scaffold if absent. You do
   **not** triage, do **not** populate Appendix A/B, and do **not** modify any populated A/B.
8. **Chat reply** = a short 1–3 line write-confirmation: which file paths you wrote, and the S / F
   suggestion counts. Do **not** repeat suggestion content in chat.

---

## Embedded Source — Requirements (`TRACK2_P1P2_REQUIREMENTS.md`, v0.2)

<details>
<summary>Requirements doc (full text)</summary>

```markdown
# Track 2 P1+P2 — Generalized Dep Provisioning + Polyglot Stateless Breadth (Requirements)

**Version:** 0.2 (Post-planning — self-reflective update)
**Scope:** the curated P1+P2 slice of TRACK2_M5_EXPANSION_SCOPING.md. Builds on the merged pilot.

## 0. Planning Insights (Self-Reflective Update)
- FR-P1-1: install each cell's declared deps fixes provisioning → FALSIFIED: pilot's Node services
  declare ZERO deps yet require pino/uuid/pino-pretty. Curated common set (FR-P1-2) is PRIMARY;
  declared-install is a secondary top-up.
- Provisioning is language-specific: Go `go mod tidy` derives deps from imports (self-provisioning);
  Node/Python need the common set (managers only install declared); Java gradle resolves build.gradle.
  → split into per-language strategy (FR-P1-1a).
- Convert/GetQuote lack crisp ground truth without pinned data → author suites around behavioral
  INVARIANTS, not exact values.
- All toolchains present on host (node/npm/go/java26/dotnet10/pip); FR-P1-5 degrade kept for portability.
- LanguageProfile has build_file_patterns / test_command / generate_dependency_file — NO serve hook.

## 1. Problem Statement
Pilot proved behavior discriminates flagships but works for one service, one language (Node), one RPC,
relying on a hand-vendored fixed dependency closure (node_runtime/). To expand: (P1) how deps get
provisioned, (P2) how non-Node services launch + score. Polyglot on curated stateless RPCs.

## 2. Requirements

### P1 — Generalized dependency provisioning
- FR-P1-1 (revised — D1): curated common set is PRIMARY: provision a generous per-language runtime set
  at prepare time covering what models require/import but don't declare. gRPC/proto runtime + common
  logging/util libs per language. Declared-manifest install is a secondary top-up.
- FR-P1-1a (new — D1): provisioning is language-specific:
  - Go — `go mod tidy` (derives deps from imports, self-provisioning) then build/run; common set =
    grpc/protobuf modules as fallback.
  - Node — copy/install the curated common set (npm only installs declared, which is empty); declared
    package.json deps installed on top.
  - Python — install curated common set (grpcio/protobuf) + requirements.txt if present.
  - Java — gradle resolves build.gradle; common set = grpc-java fallback.
- FR-P1-2 (narrowed): curated common set per language is maintained, versioned, offline-cacheable
  (Node keeps node_runtime/; analogous caches for other languages) so repeated cells/$0-rescores don't refetch.
- FR-P1-3: Dependency quarantine preserved: provisioning (network) happens at prepare time only; the
  scored server run stays egress-denied (loopback-only sandbox). (Assumption: prepare runs OUTSIDE the
  sandbox, so it may use the network — confirm.)
- FR-P1-4: Honest degrade (FR-T2-DEPS2, all languages): a server that still fails to start records the
  missing module/package + degrades (never scored 0).
- FR-P1-5: Toolchain-absent → degrade (FR-32): if a language's package manager (npm/go/pip/dotnet)
  isn't installed, the cell degrades with that reason — not scored 0.
- FR-P1-6: Provisioning is idempotent/cacheable: a $0 re-score must not re-install when deps are already
  present; provisioning cost is paid once per cell workdir.

### P2 — Polyglot stateless breadth
- FR-P2-1: additive per-language serve resolvers for Go and Java (NOT on the LanguageProfile Protocol);
  each returns a launch command with PORT injection + TCP readiness.
- FR-P2-2 (revised — D4): SDK-authored suites assert invariants checkable WITHOUT service-specific
  ground-truth data:
  - currencyservice.Convert (Node) — identity (USD→USD same amount), unknown code → error, neg/zero
    handling, determinism.
  - shippingservice.GetQuote (Go) — non-negative quote, valid currency code, determinism, quote present.
  - adservice.GetAds (Java) — ≥1 ad, ads non-empty, respects requested count.
- FR-P2-3: Add startup contracts to shipping/ad/currency seeds (via generator; byte-stable).
- FR-P2-4: Pilot-each-once: before funding N reps × roster, run each new RPC once across the roster to
  confirm it discriminates; only then scale.
- FR-P2-5 (reframed — D4): Invariant-not-verbosity: suites score on invariants satisfied, never output
  volume. An RPC whose invariants all pass for every model (saturates) is reported non-discriminating
  (drop/sharpen), not coverage-inflated. Convert = strongest expected discriminator; GetAds = weakest.

### Carried-forward
- FR-P-CF1: degrade-not-zero (FR-T2-2); persist-then-$0-rescore; behavioral scoring is $0/re-runnable.

## 3. Non-Requirements
- NR-1 Not all 9 services. NR-2 Stateful/downstream/orchestration/side-effect RPCs OUT. NR-3 No C#/Python
  serve hooks here. NR-4 No full Round-1 run. NR-5 Not abandoning node_runtime/.

## 4. Open Questions
- OQ-7 Go/Java build cost per cell under per-run timeout — may need warmed cache or longer timeout.
- OQ-8 Import-scan as Node/Python top-up — worth it, or does generous common set suffice?
- OQ-9 Whether Convert identity/validation invariants discriminate or saturate — FR-P2-4 gate answers empirically.
```

</details>

## Embedded Source — Plan (`TRACK2_P1P2_PLAN.md`, v1.0)

<details>
<summary>Plan doc (full text)</summary>

```markdown
# Track 2 P1+P2 — Implementation Plan (v1.0, paired with requirements v0.2)

## Approach
Extend the proven pilot machinery. Python gRPC client stubs already generated from full demo.proto
(CurrencyServiceStub/ShippingServiceStub/AdServiceStub) → suites are language-agnostic over the wire;
only the serve hook (per language) and provisioning (per language) are new. Pilot-each-once gates spend.

## Steps

### S1 — P1 provisioning (FR-P1-1/1a/2, FR-P1-4/5/6)
Generalize behavioral/execute.py:prepare_node_workdir → a per-language provision_workdir(workdir,
language, target_files) that runs at PREPARE time (network allowed; the scored run stays sandboxed):
- Node — keep the node_runtime/ curated closure copy; top-up declared package.json.
- Go — `go mod tidy` in the service dir (derives deps from imports) then `go build`; reuse a warmed
  GOMODCACHE/GOCACHE (FR-P1-6). Curated fallback = grpc/protobuf modules if tidy under-resolves.
- Python — pip install the curated set (grpcio, protobuf) into a venv/target + requirements.txt if present.
- Java — gradle build (resolves build.gradle); curated fallback = grpc-java.
Toolchain absent (shutil.which) → return degrade reason (FR-P1-5). Idempotent: skip if already provisioned.
Files: behavioral/provision.py (new) + execute.run_behavioral_cell calls it by seed language;
prepare_node_workdir becomes the Node branch.

### S2 — P2 serve hooks (FR-P2-1)
Extend behavioral/contract.py:_DEFAULTS + resolve_serve_command (additive, NOT the Protocol):
- Go — ["go","run","<entry.go>"] (or the built binary), PORT via env/arg.
- Java — gradle run or ["java","-cp","<build>","<MainClass>"], PORT via env/arg.
Each keeps the seed startup contract authoritative; default is the per-language fallback.

### S3 — P2 invariant suites (FR-P2-2/5)
New suites reusing generated stubs, registered in execute._SUITES by service:
- currency_suite.py — Convert: identity, unknown code → error, neg/zero, determinism; GetSupportedCurrencies non-empty.
- shipping_suite.py — GetQuote: non-negative, valid currency code, deterministic.
- ad_suite.py — GetAds: ≥1 ad, non-empty text, respects requested count.
Each returns SuiteResult (coverage = invariants passed / total) like charge_suite. No exact-value asserts.
Tests: known-good + known-broken reference server per RPC (Python, over wire) proving discrimination.

### S4 — P2 seeds (FR-P2-3)
Add startup blocks to shipping/ad/currency in scripts/gen_ob_benchmark_seeds.py; regenerate; --check
byte-stable; update test_ob_benchmark_seeds.

### S5 — Pilot-each-once + discrimination gate (FR-P2-4)
Extend scripts/run_behavioral_pilot.py to accept --service/--services; each new RPC runs once across the
roster first; report flags RPC non-discriminating if all models pass all invariants (saturated).

### S6 — $0 re-score unaffected
rescore_behavioral.py already iterates cells.json by service → picks up new suites for free.

## Risks
- Build cost/timeout (OQ-7): Go tidy+build, Java gradle can exceed per-cell timeout on cold cache →
  warm GOMODCACHE/gradle cache + raise timeout.
- Invariant saturation (OQ-9): curated invariants may all pass → FR-P2-4 gate; report and drop.
- Provisioning network at prepare: confirmed prepare runs BEFORE run_service_sandboxed (only sandboxed
  step), so install network use is fine; assert the scored run is still egress-denied.
- Cross-language wire compat: Python client + polyglot server agree on proto (same demo.proto).

## Test strategy
Unit (no LLM): per-language toolchain-absent degrade + common-set present; serve-command construction;
each suite vs known-good/known-broken reference (discrimination proof); seed byte-stability.
Integration: pilot-each-once dry-run shape. No live-model test in CI.

## Sequencing
S1 (unblocks all) → S2 + S3 (parallel per language) → S4 → S5. Land Go/shipping vertical slice first.

## Out of scope
Stateful, downstream, orchestration, Python/C# serve hooks, full Round-1 run — later phases (P3–P6).
```

</details>

---

## Background Context (for the reviewer)

- This slice **builds on a merged pilot** at `src/startd8/benchmark_matrix/behavioral/`.
- The **run-time sandbox is proven**: `run_service_sandboxed` runs the scored server loopback-allowed /
  egress-denied. It exists specifically to contain arbitrary-code execution from model-generated servers
  (parent benchmark FR-44, kernel-isolation + dep-quarantine).
- **Provisioning today = a hand-vendored Node closure** (`node_runtime/`) — it never installs anything
  the model declared. P1 is the work to **generalize** that into real per-language installs
  (`provision.py`), which is the change that introduces the untrusted-install surface.
- Parent benchmark also mandates **reproducibility (FR-19)** and **secret/Loki redaction (FR-45)** —
  both bear on the focus asks above.

---

## Embedded Reference — CRP Agent Execution Guide

> The persist-to-files instructions above **win** over Phases 5–7 below (triage / merge / coverage
> maintenance). Use this guide for the appendix scaffold template (Phase 0b), the output format
> (Phase 3 / Phase 3-DD), the dual-document routing (Phase 4-DD), area/column aliases, and severity
> rules. **Do not triage. Do not populate Appendix A/B.**

<details>
<summary>CONVERGENT_REVIEW_AGENT_GUIDE.md (full reference)</summary>

See `/Users/neilyashinsky/Documents/dev/startd8-informative-knobs/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md`
on disk (you have filesystem access). The load-bearing pieces you must follow:

- **Phase 0b — Appendix scaffold template (append verbatim to each doc that lacks it):**

  ```markdown
  ---

  ## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

  This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions
  to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or
  Appendix B (rejected with rationale).

  ### Reviewer Instructions (for humans + models)

  - **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items
    already applied or explicitly rejected.
  - **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
  - **When endorsing prior suggestions**: list them in an **Endorsements** section after your table.
  - **When validating**: append a row to Appendix A (if applied) or Appendix B (if rejected) by ID.
  - **If rejecting**: record **why** (specific rationale).

  ### Appendix A: Applied Suggestions

  | ID | Suggestion | Source | Implementation / Validation Notes | Date |
  |----|------------|--------|----------------------------------|------|
  | (none yet) |  |  |  |  |

  ### Appendix B: Rejected Suggestions (with Rationale)

  | ID | Suggestion | Source | Rejection Rationale | Date |
  |----|------------|--------|---------------------|------|
  | (none yet) |  |  |  |

  ### Appendix C: Incoming Suggestions (Untriaged, append-only)
  ```

- **Phase 3 / 3-DD — Output format (strict).** Round heading `#### Review Round R1 — <model-id> — <UTC date>`;
  metadata (Reviewer, Date UTC, Scope); 7-column table with **exactly** these headers (plain text):
  `ID`, `Area`, `Severity`, `Suggestion`, `Rationale`, `Proposed Placement`, `Validation Approach`.
  IDs `R1-S{n}` (plan) / `R1-F{n}` (requirements), sequential from 1. Area ∈ {Architecture, Interfaces,
  Data, Risks, Validation, Ops, Security} (title case). Severity ∈ {critical, high, medium, low}
  (lowercase). Escape literal `|` in cells as `\|`. Plan round also includes a
  `## Requirements Coverage Matrix — R1` mapping every requirements section → plan step(s) →
  Full/Partial/Missing → Gaps; Partial/Missing rows should each spawn an `R1-S{n}` suggestion.

- **Phase 4-DD — Routing.** S-prefix round + coverage matrix → **plan** doc Appendix C. F-prefix table
  (wrapped in its own `#### Review Round R1` heading) → **requirements** doc Appendix C. Never mix prefixes.

- **Area aliases** (normalize to canonical): auth/authentication/authorization → Security;
  risk/reliability/resilience/fault tolerance/error handling → Risks; testing/testability/quality/
  completeness → Validation; operations/deployment/observability/performance/infrastructure → Ops;
  data model/storage/database/persistence → Data; api/contracts/integration → Interfaces;
  design/structure/modularity/scalability/maintainability → Architecture.

- **Endorsements** are N/A for R1 (no prior untriaged rounds exist). Optional `### Stress-test /
  adversarial pass` subsection may continue `R1-S{n}` ids within this same round (no triage).

- **Phase 7 invariants you must preserve:** append-only; this is R1 (monotonic); no body modification;
  consider all 7 areas (even if the scope concentrates suggestions in Security/Risks/Validation/Ops);
  unique IDs; no S-ids in the requirements doc, no F-ids in the plan doc.

</details>

---

## Closing Checklist (reviewer — confirm before your chat reply)

- [ ] Read both source docs + this embedded guide; confirmed neither has an appendix scaffold.
- [ ] Initialized the A/B/C scaffold (Phase 0b template, verbatim) on **both** docs — body untouched.
- [ ] Answered the focus asks (4-line template) at the top of each doc's Appendix C block.
- [ ] Appended one `#### Review Round R1 — <model-id> — <UTC date>` to the **plan** doc (S-prefix table,
      ≥3 anchored, most targeting the PRIMARY FINDING + P1 secondary concerns) **and** a
      `## Requirements Coverage Matrix — R1`.
- [ ] Appended one `#### Review Round R1` to the **requirements** doc (F-prefix table, ≥3 anchored,
      flagging ambiguous/incomplete/missing/untestable provisioning-safety + reproducibility reqs).
- [ ] No S-ids in requirements, no F-ids in plan; no triage; no populated A/B; no prose rewrites.
- [ ] Chat reply is a short 1–3 line write-confirmation (paths + S/F counts) — no content repeated.
