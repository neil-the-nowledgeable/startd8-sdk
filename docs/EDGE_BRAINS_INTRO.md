# edge-brains — an intro from the startd8-sdk perspective

**Audience:** startd8-sdk developers/agents. **What this is:** how the
[`edge-brains`](../../edge-brains) project relates to this SDK, and how the two plug
together. **Repo:** `/Users/neilyashinsky/Documents/dev/edge-brains` (pre-implementation /
PoC phase as of 2026-06-03).

---

## What edge-brains is (one paragraph)

edge-brains does **applied QLoRA fine-tuning of small open-weight code models
(Mistral-7B-class) on real customer codebases, run on edge hardware** — a single Jetson
Orin Nano Super 8 GB ($499). The product framing: an *"edge QLoRA training pod for
code-style transfer onto a customer's private codebase — on-prem, $0 inference, no data
leaves the building, single-tenant by design."* It both **trains** house-style LoRAs and
**serves** them from a hand-rolled **FastAPI inference server** (vLLM was a Tegra build
blocker). Status: requirements + PoC done, no production training fired yet.

## Why the SDK cares — a symbiotic, two-directional relationship

```
                 PrimeContractor + kaizen artifacts  (the RFT scoring signal)
   startd8-sdk  ───────────────────────────────────────────────▶  edge-brains
        ▲                                                              │
        │     edge-brains-trained LoRA  =  a local/edge inference      │
        │     backend  (upgraded replacement for ollama:startd8-coder) │
        └──────────────────────────────────────────────────────────◀─┘
```

**Direction 1 — SDK is edge-brains' scorer (already designed).**
edge-brains uses this SDK's **PrimeContractorWorkflow + cap-dev-pipe kaizen layer as the
RFT (rejection-sampling fine-tuning) scoring signal** — a far richer reward than the
ast.parse/ruff/mypy local gates. It consumes our per-feature `disk_quality_score`,
`review_score`/`review_verdict`, `root_cause`, `assembly_quality_delta`, the
`PrimePostMortemReport` aggregates, and the cross-run `kaizen-trends.json`. See
edge-brains `docs/notes/REQUIREMENTS_PRIME_CONTRACTOR_VALIDATION_SIGNAL_2026_05_01.md`
and `scripts/rft_scorer_poc.py`. **Implication for SDK devs:** the postmortem/kaizen
artifact *schema is a consumed contract* — breaking field names/ranges breaks the
edge-brains scorer.

**Direction 2 — edge-brains is a future SDK inference backend (the new capability).**
An edge-brains-trained model, served from the Jetson (eventually a **Jetson + Mac hybrid
cluster**), is meant to become a **local/edge inference backend for the SDK** — an
upgraded replacement for / alternative to `ollama:startd8-coder` in micro-prime, and a
selectable provider in the first-class model-config surface. This is the new capability
being scoped; see `docs/design/MICRO_PRIME_BACKEND_ABSTRACTION_REQUIREMENTS.md`.

## What an SDK dev needs to know about the serving interface

From `edge-brains/scripts/fastapi_serve.py`:

| Property | Value | SDK consequence |
|---|---|---|
| API shape | **OpenAI-compatible** (`/v1/chat/completions`, `/v1/models`, `/health`) | Target it via the existing `openai` provider with a `base_url` override — **no bespoke `edge` provider needed for v1**. |
| Structured output / tool-use | **None** (`ChatRequest` has no `tools`/`tool_choice`/`response_format`) — freeform text only | The hard blocker: micro-prime leans on `generate_structured`. An edge backend needs a **freeform-and-parse fallback**. → **deferred**. |
| Concurrency | **single-tenant** (one `model.generate()` at a time; second request blocks) | Don't over-issue concurrent calls to one edge node; the backend must declare `concurrency=1`. |
| `max_tokens` | default 512, cap 2048 (KV-cache + bnb-NF4 on 8 GB; LoRA OOD past training horizon) | Respect a per-backend `max_safe_tokens`. |
| Cold start | **bnb #1936 reboot race** — a warm-up forward pass runs before first load | Health-check must distinguish "warming up" from "down" (retry/backoff), not just a TCP probe. |
| Models | Mistral-7B-v0.3 + bnb-NF4 + LoRA (iter-002/003), code-style transfer; seq_len 512→1024 | Tier mapping vs `startd8-coder` is an open question. |

## How it plugs into what we just built

The **first-class model-config capability** (`docs/design/MODEL_CONFIG_FIRST_CLASS_REQUIREMENTS.md`)
already makes this possible-by-construction:

- The unified resolver `startd8.model_roles.resolve_role_spec` is **backend-agnostic** — a
  role's spec may name `anthropic:`/`gemini:`/`openai:`/`ollama:`/a future `edge:` (or an
  `openai:`+base_url) identically. No provider special-casing.
- `MODEL_PROVIDER` / `--provider` / `--ai-agent-spec` and the `default_provider` ingestion
  injection mean a single knob can point the whole pipeline (or just the micro-prime local
  role) at an edge endpoint when one exists.

So enabling edge-brains is mostly **config + a base_url'd OpenAI-compatible spec**, plus
the deferred freeform-and-parse fallback for its lack of structured output.

## Status & what's deferred

- **Ready now:** the backend-agnostic resolver + model-config surface (edge plugs in as a
  spec/provider when the cluster is real).
- **Deferred (final/subsequent phase — the "hard questions"):** the no-structured-output
  freeform+parse fallback, de-Ollama-ifying micro-prime's internals, cold-start health
  handling, and Jetson+Mac hybrid-cluster routing. Tracked in
  `MICRO_PRIME_BACKEND_ABSTRACTION_REQUIREMENTS.md` §0 (Phasing).

## Pointers

- edge-brains: `README.md`, `CLAUDE.md`,
  `docs/notes/REQUIREMENTS_PRIME_CONTRACTOR_VALIDATION_SIGNAL_2026_05_01.md`,
  `docs/notes/REQUIREMENTS_ITERATIVE_LORA_PYTHON_STYLE_2026_05_01.md`,
  `scripts/fastapi_serve.py`, `scripts/rft_scorer_poc.py`.
- SDK: `docs/design/MODEL_CONFIG_FIRST_CLASS_REQUIREMENTS.md`,
  `docs/design/MICRO_PRIME_BACKEND_ABSTRACTION_REQUIREMENTS.md`,
  `src/startd8/model_roles.py`.
