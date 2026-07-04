# Multi-Model Consultation — Enhancement Analysis

Post-merge review of the shipped feature (TUI, CLI `run`/`reply`/`show`/`list`/`web`, static web
view + copy-command composer, interactive `--serve` server). Suggestions to raise end-user value and
surface functional / architectural quick wins and operational enhancements. Effort: **S**(mall) /
**M**(edium) / **L**(arge). Grounded against the actual code.

---

## 🏆 Top 5 — highest value, low effort

| # | Enhancement | Why | Effort |
|---|-------------|-----|--------|
| 1 | **Dollar cost, not just tokens** | We persist input/output tokens per turn but only display tokens. `costs/pricing.PricingService.calculate_total_cost(model, in, out)` converts tokens→USD (with an unknown-model fallback). Show $ per panel + a session total in the comparison view, web view, and a `consult cost <id>`. Answers users' #1 question and surfaces the per-provider image-token asymmetry seen live (gpt-5.5 20K vs gemini 631). | **S** |
| 2 | **CLI concurrency guard** | Two concurrent `consult reply` on one session do a read-modify-write on `session.json` with **no lock** (only `--serve` has a guard). Add a cross-process advisory lock to the CLI mutating path. Pure correctness. | **S** |
| 3 | **Native multi-turn continuity** | Biggest *quality* lever. Continuity today flattens prior turns into a transcript string (the OQ-10 shortcut). An optional `messages=` path on the 3 providers' `agenerate` gives real conversation memory + prior-image re-send, and closes the `AgenticSession` gap. | **M** |
| 4 | **OTel tracing** | The Grafana/Loki/Tempo stack exists but consultation runs emit no spans. Wrap `engine.follow_up` + each model call in spans (cost/latency/failure attribution). Cost already reaches the cost DB — this makes it observable. | **M** |
| 5 | **`startd8_consult` MCP tool** | Mirror `concierge.core.handle_concierge_tool` so *agents* can run consultations programmatically — human-only → agent-to-agent capability. | **M** |

## ⚡ Functional quick wins

- **Session re-open in the TUI (FR-MMC-12)** — an "open saved consultation" path: list `store.list_sessions()`, load, rebuild roster via `build_roster`, drop into the existing follow-up loop. **S**
- **Roster presets (OQ-9)** — save/load named councils so users don't retype `--models`; small JSON under `.startd8`. **S**
- **`consult retry <id>`** — `engine.retry_failed` exists (re-runs only failed models); just expose it. **S**
- **Markdown export** — `consult export <id> --md`; complements the shareable `render_html`. **S**
- **Per-model persona / system prompt** — assign a role per model (agents already accept `system_prompt`); diversifies answers. **M**
- **Agreement / divergence view** — the heart of "comparison": highlight where models agree vs differ. Structural/embedding overlap keeps it $0 (respects the no-auto-judge stance NR-2); an opt-in LLM consensus pass is the richer form. **M–L**

## 🏗 Architectural low-hanging fruit

- **Rate-limit resilience** — the fan-out can hit provider 429s but `build_roster` constructs agents without a `retry_config`; wire the SDK's retry/backoff in. **S**
- **Uniform serve error bodies** — the one cosmetic FR-SRV-4f gap (middleware 401/403 empty vs route 402/409/429 generic JSON). Unify. **S**
- **Unify the async core** — the facade's `asyncio.run` can't nest, so `--serve` bypasses it and calls the engine directly; make the engine the single async truth, facade a thin sync wrapper. **S**
- **Golden-hash brittleness** — the static-view hash test trips on any whitespace change; hash a normalized structure instead. **S** (minor).

## 🔧 Operational

- **Capability-index + wireframe entry** — the feature isn't in the capability manifest yet (pre-merge leftover); adding it makes it discoverable. **S**
- **Cost-analytics integration** — consultations already write the cost DB (FR-MMC-5); surface per-consultation spend + model-cost-over-time in the `/cost-intelligence` dashboards. **S–M**
- **Streaming in serve mode (SSE)** — token-by-token answers; high perceived value, real effort (NR-5 deferred). **L**
- **Full-suite / CI on the new `main`** — the merge was gated on affected surfaces + collection, not the entire 16,869-test suite; a CI run closes that. **S**

---

## Recommended first batch (this doc's implementation target)

The four **S**-effort, high-ROI, non-security-path items: **#1 dollar cost**, **#2 CLI concurrency
guard**, **session re-open in TUI**, **roster presets**. Then **#3 native continuity** as the one
**M** investment that most improves answer quality. Requirements: `QUICKWINS_BATCH1_REQUIREMENTS.md`.
