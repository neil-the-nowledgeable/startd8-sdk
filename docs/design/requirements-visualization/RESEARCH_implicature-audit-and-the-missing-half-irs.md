# Research: the implicature audit, its logical inverse, and the missing half-IRs of the NLPS

**Date:** 2026-08-18 · **Type:** structure-completing meta-reflection (think-piece) · **Status:** research note — resolves the open §E thread, proposes the completing move

**Grounds in / extends:**
- `RESEARCH_AGENDA_open-threads-across-the-nlps.md` **§E** (the two-IR twin-seam reconciliation; "one unified IR vs two?") — this note is that thread's resolution.
- `NODE-SCHEMA.md` (dev-os) — the **specification-half IR** (Node/contract); `docs/design/deterministic-generation/ARCHITECTURE_sarif-determinism-ratchet.md` §1.1 — the **findings-half IR** (SARIF).
- The metabolization TWINS: `SYNTHESIS_crp-theme-metabolization-four-investigations.md` + `SYNTHESIS_crp-other-and-cli-mining.md` (review-side, shift *specification* left) and `ARCHITECTURE_sarif-determinism-ratchet.md` (generation-side, shift *generation* left). Both = findings-half IR drives a completeness loop.
- The reflective **septet** (`~/.claude/skills/reflective-{requirements,retrospective,abstraction,instantiation,adoption,dogfooding,analogy}`) + the audit **triad** (`~/.claude/skills/{survivorship-audit,generality-survivorship-audit,lacuna-audit}`) + `metabolize-finding` (audit→construction bridge).
- `VALUE_PROP_verification-that-cannot-silently-die.md` + `REQ-22-verify-liveness-not-presence.md` — the oracle/liveness angle.
- The firing seam: `REQ-32-draft-time-firing-wire.md` (the single seam every metabolized theme queues at).
- `project_natural_language_programming_system` (memory) — the compiler frame the whole NLPS names.

> **One-paragraph thesis.** The NLPS is a compiler whose source is prose. It already runs two intermediate representations — the **Node/contract** (spec-half: *what to build*) and **SARIF** (findings-half: *what's wrong/missing*) — and two metabolization loops that shift work left off the findings-half. But a compiler with a rich contract does more than *check what's written*: it **derives what the writing forces**. The missing capability is the audit that runs the contract's **deductive closure** — the entailments a spec commits to but leaves unstated ("you stated X, therefore Y is forced but absent"). Its logical inverse is the **presupposition audit** (what must *already* be true for X to make sense — the backward direction), with **falsification** (the Verify-oracle's dual) as the sharpest single sibling. And the half-IR lattice, once drawn, shows the NLPS carries the RED findings-half (SARIF: what's wrong) but is **missing its GREEN complement — a proven-evidence IR with liveness provenance**. The single highest-leverage completing move is **the implicature audit wired to the existing REQ-32 firing seam**, because the corpus's own fact-rungs are already a partial, hand-authored instance of it — the audit generalizes a proven path rather than inventing a new engine.

---

## 1. The implicature / entailment audit — "what is IMPLIED"

### 1.1 Definition and mechanism

**The implicature audit surfaces the logical CONSEQUENCES a spec/contract commits to but leaves unstated.** It runs the **deductive closure** of the contract's declared commitments: given a stated fact `X` in an FR, it derives the facts `Y₁…Yₙ` that `X` *forces* under the grammar's inference rules, then checks whether each forced `Yᵢ` is present. A missing forced consequence is the finding: **"You stated X, therefore Y is entailed — but Y is absent."**

The mechanism is **forward, deductive, spec-half**. It reads a *statement* and computes *its entailments*. Concretely, in the det-req grammar the inference rules are already latent in the metabolized themes:

| Stated commitment (the antecedent `X`) | Forced-but-often-absent consequence (`Y`) | Grounded in |
|---|---|---|
| an FR **emits** an artifact (`.json`/`manifest`/`model_dump`) | ⟹ it has a **schema**, a **version**, and a **round-trip** in `Verify:` | `Emits:` fact-rung (REQ-30) · four-investigation §2 |
| an FR **persists/resumes** state | ⟹ it declares **states**, **resume** semantics, **idempotency** under retry | `Lifecycle:` fact-rung (REQ-31) |
| an FR **touches an external input** (file/subprocess/upstream) | ⟹ it names a **failure behavior** (`fail-closed`/`degrade`/`typed-marker`/`retry`) | `onFailure:` fact-rung |
| an FR **derives a value** (infer/enrich/fingerprint) | ⟹ it names a **source** and whether it is **canonical** | `Provenance:` fact-rung · REQ-25 `source_id` |
| an FR **invokes an LLM pass** | ⟹ it declares a **budget** (token cap / cost ceiling) | `Budget:` fact-rung |
| an FR reads **≥2 config sources** | ⟹ it declares a **precedence** order | `Config: precedence=` (CLI-mining §1) |
| a **verify** is declared for an `llm`-realized node | ⟹ the verify is **REQUIRED** and its gate must be **live** | invariant 9 · REQ-22 |

Each row is an **entailment rule**: `antecedent-shape ⊢ required-consequence`. The audit is the engine that applies the whole rulebook to a draft and reports the forced consequences that are missing.

### 1.2 The grounded demand — the fact-rungs are already a PARTIAL implicature audit

This is the load-bearing grounding, and it makes the audit a *generalization of a proven path*, not an invention. `SYNTHESIS_crp-theme-metabolization §2` already ships **fact-rungs** with exactly this shape:

> *emit-shaped FR with no `Emits:` → GAP · persist-shaped FR with no `Lifecycle:` → GAP · input-bearing `Touches:` with no failure behavior named → GAP.*

Every one of those is an instance of **"stated commitment → forced-but-missing consequence."** The four-investigation sweep metabolized ~1,700 recurring review suggestions into these rules, and `SYNTHESIS_crp-other-and-cli-mining` added three more themes (dependency-ordering, provenance, cost/budget — 89–192-doc reach each). What the corpus calls "fact-rung theme lints" **is the implicature audit, discovered bottom-up, one entailment rule at a time.** The audit is the top-down name for what the metabolizer has been building. The demand signal is quantitative: 7,299 accepted review suggestions, of which the recurring themes are precisely the entailments reviewers keep re-deriving *by hand* because the draft didn't state its own forced consequences.

### 1.3 Where it plugs into the NLPS

The implicature audit runs **at authoring, on the spec-half**, and fires through the **same seam the fact-rungs already queue at**: `REQ-32`'s draft-time firing wire (`det-req-kit/extract.py::collect_findings`, advisory/exit-unchanged tier). It inherits the fact/judgment discipline (REQ-25): **a structural entailment fires loud (it cannot cry wolf — a persist-FR either has a `Lifecycle:` or it doesn't); a semantic entailment parks** behind the REQ-07 precision gate as a dismissible candidate. No new engine — the audit is the *organizing frame* over the predicate backlog REQ-30/31/32 already authorize, plus the discipline that new entailment rules are added as predicates, never as a per-theme engine.

### 1.4 The discriminating tests (its place in the family)

The implicature audit's **most-confused siblings are `/lacuna-audit` and `/reflective-instantiation`** — both also find "something that should be there but isn't." The distinctions are mechanical and must be crisp:

| Audit | What it reads | Mechanism | The gap it finds | The tell |
|---|---|---|---|---|
| **Implicature audit** (this) | a **STATEMENT** (an FR's stated commitment) | **deductive closure** — apply inference rules to a claim | a **CONSEQUENTIAL** gap: a fact *forced by* what was said, left unsaid | "You *said* X ⟹ Y is forced ⟹ Y is absent" |
| **`/lacuna-audit`** | a **STRUCTURE** (a table/lattice/symmetry) | **Mendeleev** — subtract present cells from demanded cells | a **POSITIONAL** gap: an empty coordinate the structure's *shape* demands | "The table has slot (row,col) ⟹ it's empty ⟹ fill it" |
| **`/reflective-instantiation`** | a **NAMED ABSTRACTION** (a product space `A×B×…`) | descend an existing algebra to unbuilt coordinates | a **VARIANT** gap: a concrete artifact the abstraction predicts | "The space predicts variant (a,b) ⟹ build it" |

**Implicature vs lacuna is the sharpest and the one the prompt flags.** A lacuna is a gap in a **table** — it needs a *pre-existing structure with coordinates* (N parallel CRUD branches, both poles of a dual, a coverage matrix), and the gap is *positional*: cell (i,j) is empty. The implicature audit needs no table — it operates on a **single statement** and the *inference rules of the grammar*, and the gap is *consequential*: the statement logically entails a fact that is not stated. You can run the implicature audit on **one FR in isolation** (an emit-FR with no schema); you cannot run a lacuna audit on one FR — you need the *set* whose shape reveals the empty cell. Put differently: **lacuna finds the missing ROW; implicature finds the missing IMPLICATION of a row that IS present.** They coincide only in a degenerate case (if you *tabulate* "every emit-FR × {schema, version, round-trip}" then the missing schema becomes a positional empty cell) — but that coincidence is the exception, and building the table is extra work the implicature audit skips.

**Implicature vs instantiation:** instantiation descends a *named algebra* to build *new concrete variants* (new skills, new renderers); implicature descends a *stated claim* to surface *its own missing entailments* within one artifact. Instantiation produces artifacts the abstraction predicts *should exist somewhere*; implicature produces the *unstated obligations of a claim that already exists*. Instantiation is generative (build the gallium); implicature is analytic (this molecule's formula forces a bond you didn't draw).

---

## 2. The logical inverse(s) — presupposition, contradiction, falsification

Entailment has three distinct logical duals, and the prompt is right that we should *pick the ones that genuinely round out the system* rather than manufacture symmetry. Here is each, placed and grounded, followed by the adjudication of which to build.

### 2.1 The three candidate inverses

| Inverse | The question it asks | Direction | Logical operation | vs the implicature audit |
|---|---|---|---|---|
| **Presupposition / abduction** | what must **already be true** for X to make sense? (the preconditions) | **backward** | given a claim, find its *unstated antecedents* | implicature runs the arrow forward (X⟹Y); presupposition runs it backward (X requires-P) |
| **Contradiction / consistency** | what does X **rule out**? does any other claim violate it? | **lateral** | pairwise consistency over the claim set | implicature is intra-claim (one X's closure); contradiction is inter-claim (X vs X') |
| **Falsification** | what **input would break** the stated guarantee? | **dual-of-oracle** | given a `Verify:`, find the counterexample it doesn't cover | implicature checks the *spec*'s closure; falsification checks the *oracle*'s coverage |

**These are genuinely different, not three names for one thing.** Presupposition is the deductive *reverse* (an entailment run backward): "FR-7 says *resume from checkpoint* — this **presupposes** a checkpoint exists, is written atomically, and survives the crash; are those stated?" Contradiction is *consistency-checking* across the set: "FR-3 declares `precedence: env > CLI`; FR-11 assumes `--flag` always wins — these **contradict**." Falsification is the *oracle's* dual: for a guarantee `G` with check `V`, find the input class `I` such that `G` holds on `V`'s cases but fails on `I` — the "edge-cases / negative-tests" theme.

### 2.2 The grounded demand for each

The prompt supplies the demand signals; the corpus confirms them:

- **Presupposition** ⟵ the **"make-explicit / implicit unstated-assumption" cluster** (157 rows / 100 docs, found in the "other"-bucket mining, `SYNTHESIS_crp-other-and-cli-mining §2a`). This cluster *is* reviewers repeatedly saying "this FR silently assumes P — state P." That is the presupposition audit, hand-run 157 times.
- **Contradiction** ⟵ the **"consistency / reconcile" theme** (the prompt cites 112 docs; the mining confirms `reconcile`/`parity`/`round-trip` as a ~150-row determinism-adjacent cluster). "Reconcile X with Y" is a reviewer detecting an inter-claim inconsistency.
- **Falsification** ⟵ the **"edge-cases / negative-tests" theme** — and, more sharply, the **verify-liveness** work (`VALUE_PROP_verification-that-cannot-silently-die`, REQ-22). A `Verify:` that "passes every structural check while its guarantee is dead" (the NetBSD Functional Spine Fracture) is *exactly* an oracle whose falsifying input was never sought.

### 2.3 The chosen inverse — and why

**Build presupposition as the primary inverse; fold falsification in as its sharpest special case; leave contradiction as a correct-partial-absence (§2.4).**

Reasoning:

1. **Presupposition is the true logical inverse** — the clean backward arrow to implicature's forward arrow. The pair *implicature ⊣ presupposition* completes the deductive axis (forward closure ⊣ backward closure), which is the axis the NLPS's spec-half most needs, because the spec-half is where the compiler's front-end lives. It also has the **cleanest grounded demand** (157 rows, a named cluster) and the **same firing mechanism** (a presupposition is a structural fact-rung: "FR names *resume* but no antecedent FR/field establishes the checkpoint → GAP" fires as loud as its forward twin).
2. **Falsification is not a separate audit but the presupposition audit pointed at the ORACLE.** A `Verify:` presupposes that its check *actually exercises the guarantee*; a dead gate is a *falsified presupposition of the oracle*. This is why the prompt calls it "the dual of the Verify oracle" — and why it doesn't need its own machinery: REQ-22's liveness check (resolve → run → provenance-fail) **is** the falsification probe for the oracle, already specced. So falsification = presupposition-audit ∘ oracle. We get it "for free" as a specialization, which is the honest, non-inflating way to include it.

The reflective-family placement of the pair:

| Skill | Direction | Reads | Produces |
|---|---|---|---|
| **implicature audit** (proposed) | forward / deductive | a stated claim | its forced-but-absent **consequences** |
| **presupposition audit** (proposed) | backward / abductive | a stated claim | its unstated-but-required **antecedents** |
| — falsification (specialization) | oracle-dual | a `Verify:` guarantee | the input that breaks it (= a violated presupposition of the check) |

The pair sits **beside** the audit triad, not inside it, because the triad's members are *census* audits (survivorship censuses done-markers; generality censuses generic-mechanisms; lacuna censuses structural cells). The implicature/presupposition pair are **inference** audits — they compute closure over *claims*, not census over *members*. That is a distinct fourth mechanism. (See the mechanism map in §3.4.)

### 2.4 The over-abstraction guard — contradiction is a correct-PARTIAL-absence

Symmetry says "entailment has a dual (presupposition), a negation-over-pairs (contradiction), and an oracle-dual (falsification), so build all three." The discipline (`/lacuna-audit` step 4, `/reflective-instantiation` phase 3, `/complexity-distiller`) says: **adjudicate each cell; some correct-absences are real.**

**Contradiction is adjudicated as a correct-PARTIAL-absence** — build it *narrowly* or not at all as a standalone audit:

- The **structurally-decidable slice already has a home**: `Config: precedence=` (REQ-32 / CLI-mining) is contradiction-detection for the *specific* case of ≥2 config sources with no declared order. A general contradiction audit over free-prose FRs would require **theorem-proving over natural-language claims** — precisely the semantic-judgment tier REQ-25 *parks* because it cries wolf. The four-investigation synthesis names this exact trap: "forcing them into lints would cry wolf."
- So the verdict is not "contradiction is useless" but "**contradiction is a judgment-rung, not a fact-rung.**" It ships as a parked candidate (like weasel-word detection), fires only past a precision gate, and its structurally-decidable instances (config precedence, enum-vs-enum) are *already* covered by targeted fact-rungs. **Building a general "consistency audit" as a first-class member would be symmetry-worship** — a framework for a use-case the fact-rungs already serve at their decidable core and the precision gate correctly refuses at their undecidable edge.

This is the honest correct-absence the prompt demands: **the deductive axis (implicature ⊣ presupposition) earns two members; the consistency axis earns one *field* (`Config: precedence=`) plus a parked judgment-rung, not a third audit.**

---

## 3. The half-IR lattice — which halves are BUILT, which are MISSING

### 3.1 The frame: every IR is half of a complementary dual

The NLPS runs two IRs today, and the open §E thread asks whether they reconcile onto one representation or stay dual. The answer emerges from seeing that **each IR is one pole of a complementary pair**, and the pairs are systematic. There are two *kinds* of half-IR:

- **STRUCTURAL half-IRs** — representations (data shapes the pipeline reads/writes). Node and SARIF are these.
- **PROCESS half-IRs** — the reflective operators that *move between* representations (the audits and loops). Implicature/presupposition are these.

### 3.2 The structural lattice

```
                    THE NLPS HALF-IR LATTICE (structural)

   SPEC-HALF (what to build)            FINDINGS-HALF (what's wrong/missing)
   ────────────────────────             ──────────────────────────────────
        ┌─────────────┐                       ┌─────────────┐
        │   NODE /    │◀────derivation edge───│    SARIF    │   RED: defects,
        │  CONTRACT   │     (REQ-16)           │  (findings) │   gaps, violations
        │  the IR ✅   │─────compiles-into────▶│    IR ✅    │
        └──────┬──────┘                       └──────┬──────┘
               │                                     │
   assertion   │                          refutation │
   (does)      │                          (a finding)│
               ▼                                     ▼
    ┌──────────────────┐                  ┌──────────────────────┐
    │ intent → FR →    │                  │ ??? GREEN-EVIDENCE IR │  ◀── MISSING
    │ contract (plan)  │                  │ what's PROVEN, with   │      the RED half
    │  = plan-half ✅   │                  │ liveness provenance   │      has no GREEN
    └────────┬─────────┘                  └───────────────────────┘      complement
             │                                     ▲
   intent ┌──┴──────────┐              realization │  (the same axis,
   (plan) │ realization- │─────────────────────────┘   opposite pole:
   vs     │ provenance   │   plan↔realization           what the plan SAID
   actual │  IR (REQ-19)✅│   = intent↔actual             vs what actually ran)
          └──────────────┘
```

The pairs, tabulated with their build status:

| # | Dual axis | Pole A (spec/assert/intent/red) | Pole B (its complement) | Status | Gap |
|---|---|---|---|---|---|
| **D1** | **spec ↔ findings** | Node/contract (*what to build*) ✅ | SARIF (*what's wrong*) ✅ | **both built** | reconciliation open (§3.5) |
| **D2** | **intent ↔ actual** | plan (`costClass`, *planned regime*) ✅ | realization-provenance (*measured regime*, REQ-19) ✅ | **both built** | the *delta model* is open (OQ-1) |
| **D3** | **entailment ↔ presupposition** | forced consequences (implicature) | required antecedents (presupposition) | **process-IR — §3.3** | both proposed here |
| **D4** | **assertion ↔ refutation** | `does` (a node asserts a capability) | a SARIF finding (refutes it) | **both built** | this is D1 at claim granularity |
| **D5** | **RED-findings ↔ GREEN-evidence** | SARIF (*what's wrong*, refutation) ✅ | **an evidence IR** (*what's PROVEN, live*) | **A built, B MISSING** ⭐ | **the biggest structural gap** |

### 3.3 The process lattice (the reflective operators as half-IRs)

The reflective septet + audit triad are themselves complementary duals — they are the *operators* that move a claim between representations. Mapping them onto the closure axes:

| Process dual | Forward pole | Backward/inverse pole | Built? |
|---|---|---|---|
| variants ↔ structure | `/reflective-instantiation` (structure→variants) | `/reflective-abstraction` (variants→structure) | both ✅ |
| forward ↔ backward (time) | `/reflective-requirements` (spec→imagined build) | `/reflective-retrospective` (actuals→standard) | both ✅ |
| present-quality ↔ absent-quality (census) | `/survivorship-audit` (done→secretly-broken) | `/lacuna-audit` (structure→missing-member) | both ✅ |
| **claim-closure (deductive)** | **implicature** (claim→forced consequence) | **presupposition** (claim→required antecedent) | **NEITHER — proposed here** ⭐ |

The process lattice has **one empty row**: the deductive-closure axis. Every other reflective dual has both poles built; the **inference axis has neither.** That is a lacuna in the reflective *family itself* — and it is the exact gap this note fills. (The audit triad does census; the reflective septet does variant/time/domain transfer; **nobody does inference over claims.** The implicature/presupposition pair is the missing method the family's own shape demands — a Mendeleev cell in the dev-os toolset, found by running `/lacuna-audit` on the skill-set.)

### 3.4 The four distinct mechanisms (so the audits don't collapse into each other)

| Mechanism | Reads | Operation | Members |
|---|---|---|---|
| **Census** | a *set of members* | subtract present from demanded / re-ground the greens | survivorship, generality-survivorship, lacuna |
| **Transfer** | *variants / domains* | up/down/across a structure | abstraction, instantiation, analogy, adoption |
| **Reflection-in-time** | *your own work* | forward-imagine / backward-extract | requirements, retrospective, dogfooding |
| **Inference** ⭐ | a *single claim* | deductive closure (fwd) / abductive closure (bwd) | **implicature, presupposition** (missing) |

This table is the crispest statement of *why the implicature audit is not lacuna-audit*: **different mechanism entirely** (inference over one claim vs census over a member-set). They can produce superficially similar outputs ("something is missing") from orthogonal machinery.

### 3.5 Resolving the open §E question: one unified IR or two?

**Position: two poles, ONE lattice — the IRs stay dual but reconcile through a shared node grammar, and the derivation edge is the reconciliation, not a merge.**

The §E thread asks whether SARIF is a *projection* of the Node findings or a *peer IR*. Both framings are half-right, and the lattice dissolves the tension:

- SARIF and Node are **not the same IR** and should not be merged into one — they answer opposite questions (*what to build* vs *what's wrong*), carry opposite polarity (assertion vs refutation), and have different consumers (the projector reads Node; the ratchet/reviewer reads SARIF). Collapsing them would re-entangle two things the pipeline correctly factored (a `/reflective-abstraction` FF: *don't weld the assertion axis to the refutation axis*).
- But they **share one node grammar** and are joined by the **derivation edge** (REQ-16): a SARIF finding is *about* a Node, and `sarif_to_req_stub` closes a recurring finding-class back into a Node/spec demand. So SARIF is a **peer IR in a shared lattice**, reconciled *by the edge*, not *by merger*. The Lesson↔SARIF and CRP-log↔SARIF twins (charter inv. 6/7) reconcile the same way: they are **findings-half nodes** with a `revises`/`derived-from` edge back to the spec-half node they concern — one grammar, two poles, an edge between.

The honest one-liner for the agenda: **"Two IRs, one lattice, reconciled by the derivation edge — not one merged IR, and not two forking representations. SARIF is the findings-half node; Node is the spec-half node; they share the grammar and are joined, not unified."**

### 3.6 The OTHER axis — narrow waists by DOMAIN (SARIF/OTel and their query + BI cousins)

§3.1–3.5 factor the IRs by **polarity** (spec↔findings, intent↔actual, red↔green). There is a second, orthogonal axis: the **domain narrow waist** — the "thin waist of the hourglass," the one interchange representation many producers and many consumers converge on (IP for the network, `SARIF` for static-analysis findings). The NLPS leans on `SARIF` and the contract IR as narrow waists but has adopted only a *subset* of the domains that have one:

| Domain | Narrow waist (the canonical interchange IR) | In our system | Status |
|---|---|---|---|
| spec · data-model · wire | Node/contract · `.prisma` · **proto** | the spec-half IR | ✅ adopted |
| findings · diagnostics | **SARIF** | the findings bus — repair/validators/security/contract/o11y/query all route in | ✅ adopted |
| telemetry | **OTel / OTLP** (query dialects: PromQL · TraceQL · LogQL) | *not a peer of SARIF here* — routes **into** SARIF via the o11y bridge (REQ-28); it's a source one layer up | ✅ as a source |
| query — relational | **SQL** · **Substrait** (a cross-engine **query-plan IR**, the exact SARIF-shaped cousin) · Arrow/ADBC (data/transport) | **Query Prime** *generates* queries and emits → SARIF | ⬜ waist not adopted |
| query — dimensional / OLAP | **MDX** (MultiDimensional eXpressions, over XMLA) | — | ⬜ absent |
| BI · metrics | **semantic / metrics layer** (dbt MetricFlow · Cube · Malloy); legacy: **MDX / OLAP cubes** | **dashboard_creator** *generates* dashboards (Grafana) | ⬜ waist not adopted |
| evidence · attestation | *(no industry standard)* → the proposed **GREEN-evidence IR** (D5) | — | ⬜ proposed |

**The finding this exposes.** We inventoried the polarity axis thoroughly but only the **spec** and **findings** domains on this axis (plus the proposed **evidence** one). The **query** and **BI** narrow waists are real, canonical, and **absent** — yet we already own the *generators* that would sit on them: **Query Prime** (query) and **dashboard_creator** (BI). They currently organize around SARIF (findings), **not** around a query-plan IR (Substrait/SQL) or a metrics IR (semantic layer). So the move, if wanted, is not "build generators" — it is **adopt the waist** and let the existing generator sit on it, exactly as `backend_codegen` sits on the `.prisma` contract.

**On MDX specifically** — it is the purest historical *unifier* of the two missing waists: an OLAP query language whose **calculated members** carry metric definitions inline, so it lives at the **query ∩ BI** intersection (a query IR that also *is* a metric IR). The modern **semantic layer** is its SQL-targeted successor (metrics-as-code compiled down to warehouse SQL, several tools still exposing an MDX face for BI-tool compatibility). MDX is thus the cleanest single illustration that "query waist" and "BI waist" are two faces of one dimensional IR. *(Disambiguation: this is MultiDimensional eXpressions — not the Markdown-plus-JSX doc format.)*

**Over-abstraction guard (the honest verdict).** Adopting a query or BI narrow waist is a **correct-absence today, not a gap** — it earns its place *only* when the NLPS wants **deterministic query/BI generation** (the way `backend_codegen` does deterministic app generation). Until that demand is named, Substrait/MDX/semantic-layer are the *right cousins to know* but the *wrong thing to build* — listing them as narrow waists is inventory, not a backlog. The one that IS on the critical path is the evidence half-IR (D5), because two independent tracks already converged on it.

### 3.6 The missing structural half-IR that most rounds out the NLPS

**D5 — the GREEN-evidence IR — is the single biggest structural gap, and it is the one to build.**

The reasoning is the lattice plus the value prop:

1. **SARIF carries only RED.** `findings_sarif.py` renders *what's wrong / missing / violated*. Its complement — *what's PROVEN, and provably still live* — has **no first-class IR.** Today "proven" is scattered: a green test, a `lives[]` evidence entry, a `verify.gate` result, a realization-provenance stamp. None of these is a *unified, liveness-carrying evidence representation* the way SARIF is a unified findings representation.
2. **This is exactly the verify-liveness lacuna.** `VALUE_PROP_verification-that-cannot-silently-die` names the failure: a requirement "reads green while its guarantee is dead." The reason it *can* read green falsely is that **there is no evidence-IR that binds a green to a live gate with provenance** — the green is a *presence* (the verify prose exists) not a *liveness* (the gate ran and attested). REQ-22 fixes this *per-node* (`verify.gate` + `verify_oracle` liveness). The **missing half-IR is the corpus-level generalization**: a GREEN-evidence IR that stands to "proven" as SARIF stands to "wrong" — every green carrying `{gate, last-run, provenance, liveness-verdict}`, so a dead green is *never a silent pass* but a **findable, censusable, degrade-to-human record**.
3. **It completes every dual at once.** D5's B-pole (green-evidence) is D1's missing complement viewed through polarity (findings-half has RED but not GREEN), D2's actual-side made *attesting* (realization-provenance says "it ran as `llm`"; evidence-IR says "and here's the live proof it ran *correctly*"), and D4's assertion-confirmation (a `does` asserted → a green-evidence node *confirms* it, the positive dual of a SARIF finding *refuting* it). One IR closes four lattice edges.

The GREEN-evidence IR is **honest-grounding applied to the pipeline's own greens** — the same principle (`a claim is cruft until grounded`) that the value-prop doc identifies as the effort's deepest. SARIF made *defects* first-class and censusable (enabling the two metabolization loops); the GREEN-evidence IR makes *proofs* first-class and censusable — enabling a **survivorship-audit loop that runs continuously** (the corpus's greens re-grounded against live gates, the Wald move mechanized).

---

## 4. The completing move

### 4.1 The single highest-leverage addition

**Build the implicature audit, wired to the REQ-32 firing seam, as the organizing frame over the fact-rung backlog — and specify the GREEN-evidence IR as its structural counterpart.**

The move is *one audit + one IR*, and they are the process-half and structural-half of the same completion:

- **The implicature audit** (process-half) is the highest-leverage *audit* because it is **already 60% built and mis-named.** REQ-30/31/32 and the two mining syntheses have been authoring entailment rules ("emit ⟹ schema", "persist ⟹ lifecycle") as isolated "theme lints." Naming them as the deductive-closure audit (a) gives the backlog a *generative frame* — new entailment rules are *derived from the grammar's inference rules*, not discovered ad-hoc from review census — and (b) supplies its inverse (presupposition) and its oracle-dual (falsification) as *the same machinery pointed backward and at the oracle*. This is the cheapest possible completion: it *unifies existing predicates under a principle* rather than building an engine.
- **The GREEN-evidence IR** (structural-half) is the highest-leverage *IR* because §3.6 shows it closes four lattice edges at once and delivers the effort's *central value prop* (verification-that-cannot-silently-die) at corpus scale, generalizing REQ-22 from per-node to a first-class representation.

### 4.2 How it composes with the existing machinery

The completing move is deliberately **all wiring, no new engine** — the tell (per the value-prop doc) that it is the effort's true purpose:

| The completion needs… | …and the machinery already provides it |
|---|---|
| a place to fire implicature findings at authoring | **REQ-32 firing seam** (`collect_findings`, advisory tier) — the fact-rungs already fire here |
| the inference rules (`X ⟹ Y`) | the **metabolized themes** (REQ-30/31, `Emits:`/`Lifecycle:`/`onFailure:`/`Provenance:`/`Budget:`/`Config:`) — each *is* an entailment rule |
| fact-vs-judgment discipline (fire loud vs park) | **REQ-25** — structural entailment = fact-rung; semantic = parked candidate |
| the backward inverse (presupposition) | the **same seam run in reverse** + the 157-row "implicit-assumption" cluster as its rule source |
| the oracle-dual (falsification) | **REQ-22 `verify_oracle`** liveness — falsification *is* the oracle-liveness probe |
| a GREEN-evidence representation | **`lives[]` typed evidence + `verify.gate` + realization-provenance** — lift these into one IR, don't rebuild them |
| closing findings back to spec | **`sarif_to_req_stub`** / the derivation edge (REQ-16) — the same finding→contract loop |
| the census/ratchet that consumes it | **the two metabolization loops** — implicature findings feed the CRP loop (spec-half); GREEN-evidence feeds a survivorship loop (the RED-loop's dual) |

**The bookends (`DATA MODEL` front, `RETROSPECTIVE` back)** frame it exactly: the implicature audit runs at the **DATA MODEL bookend** (it hardens the contract before compilation — "you designed X, so Y is forced; state it now"), and the GREEN-evidence IR feeds the **RETROSPECTIVE bookend** (it makes the actuals *attest*, so a `revises` that retires an invariant is gated on a *live* green, not a stale one). The pair completes the compiler's front-end (implicature = the type-checker that derives obligations from declarations) and its verification back-end (GREEN-evidence = the linker's proof that every symbol resolves to something that actually runs).

### 4.3 The over-abstraction guard, restated

- **Contradiction is NOT built as a third audit** (§2.4) — its decidable core is `Config: precedence=`, its undecidable edge is a parked judgment-rung. Correct-partial-absence.
- **SARIF and Node are NOT merged** (§3.5) — welding the assertion and refutation axes is a factorization failure. Two poles, one lattice, joined by the edge.
- **The implicature audit adds no engine** — it is a *frame + predicates on the proven REQ-32 path*. If it ever grew a bespoke inference engine separate from `collect_findings`, that would be the over-abstraction the whole discipline (rule-of-three, `/complexity-distiller`) forbids.
- **Falsification is a specialization, not a member** — it reuses REQ-22 wholesale. Giving it its own machinery would duplicate the oracle-liveness check.

---

## 5. One-line conclusion

*The NLPS already runs two IRs (the spec-half Node and the findings-half SARIF) and two loops that metabolize the findings-half to shift work left — but it lacks the inference audit that runs the contract's deductive closure: the **implicature audit** ("you stated X ⟹ Y is forced but absent"), which the corpus has been building bottom-up as isolated fact-rungs and which fires through the existing REQ-32 seam; its true logical inverse is the **presupposition audit** (the same seam run backward, grounded in the 157-row implicit-assumption cluster), with **falsification** as the oracle-liveness specialization of it and **contradiction** an honest correct-partial-absence (a `Config: precedence=` field plus a parked judgment-rung, not a third audit); and the half-IR lattice shows the one structural gap that most rounds out the system is the **GREEN-evidence IR** — SARIF's missing complement that makes *proofs* first-class and live-provenanced exactly as SARIF made *defects* first-class — so the single completing move is the implicature audit (frame over the proven fact-rung backlog, no new engine) plus the GREEN-evidence IR (a lift of `lives[]`/`verify.gate`/realization-provenance), together completing the compiler's front-end type-checker and its verification back-end at the two human bookends.*
