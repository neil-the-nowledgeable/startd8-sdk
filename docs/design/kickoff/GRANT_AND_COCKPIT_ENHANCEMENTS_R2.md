# Grant & Cockpit Enhancements — R2 (post-ship leverage pass)

**Version:** 0.1 (R2 — the enhancement pass *after* FR-E14/E15/E16/E18 landed)
**Date:** 2026-07-20
**Status:** Living backlog — Top findings lead; full backlog below the fold.
**Predecessor (does not restate):** [`GRANT_AND_COCKPIT_ENHANCEMENTS.md`](./GRANT_AND_COCKPIT_ENHANCEMENTS.md) (v0.2).
That doc's shipped items (FR-E1…E22), its Non-Requirements (**NR-E1** no live in-dashboard chat ·
**NR-E2** no full tenancy/auth · **NR-E3** no change to grant security semantics), its Open
Questions (**OQ-E1** auto-provision default · **OQ-E2** metrics cardinality · **OQ-E3** SQLite-vs-file),
and the **REJECTED FR-E19** (trust-chain middleware) are cross-model memory — **not re-proposed here.**
**Scope:** the just-shipped kickoff-portal stack — **FR-E14** (exportable readout), **FR-E15**
(packaged remote onboarding), **FR-E16** (portfolio readiness board), **FR-E18** (capture/instantiate
grantable on cloud). Grounded against the shipped source, not the design docs.

> **The core insight.** The four engines are built and wired *for their default path* — but two of
> them ship a **surface that the code can't actually reach the way v0.2 advertises**: FR-E18 made
> `capture`/`instantiate` grantable, and FR-E15's `invite` accepts `--capability capture|instantiate`,
> but the **human door only ever redeems a `chat-write` grant** — so a human-facing capture/instantiate
> invite mints a dead link. And FR-E14's "what was captured" reached md/HTML but **not the JSON oracle**
> that the same file calls the drift-proof surface. The leverage is closing these reach gaps, not new
> engines.

---

## 🎯 Top findings — do these first (the whole point)

### 1. ⚠️ DEFECT (built-but-unwired) — a `capture`/`instantiate` invite link is un-redeemable by a human

`Confirmed:` FR-E18 made `capture` and `instantiate` grantable on cloud, and FR-E15's `invite`
command exposes `--capability` (`cli_cloud_grant.py:190`, `_DEFAULT_CAPABILITY = "chat-write"` at
`:30`) — so an operator following v0.2's FR-E18 guidance issues an invite for `capture`. But the
one-time **human door hardcodes the redeem target's capability to `"chat-write"`**
(`web.py:1311` — `target = GrantTarget(_deployment_id, _project_id, "chat-write")`), and
`redeem_link` denies on `grant.target != target` (`cloud_grant.py:318`, `TARGET_MISMATCH`). So a
grant whose capability is `capture`/`instantiate` **can never be redeemed via the link** — the remote
user gets the generic "link invalid" page with no diagnostic (no-oracle by design), and the grant is
reachable *only* by a programmatic client sending `X-API-Key` directly through `_cloud_capability`
(`web.py:862`, `:1153`) — i.e. **not the human the entire FR-E15 invite flow exists to serve.**

This means the FR-E15 × FR-E18 composition that v0.2 presents as shipped (`invite --capability
capture` → send link → human captures) **doesn't work end-to-end**; only `chat-write` invites do.

**How it cleared the verification gate** (`hardening.md §1`):
1. **Confirmed the negative by grep, not eyeball** — the only `redeem_link` / `/kickoff/enter`
   consumer in `src/` hardcodes `"chat-write"` (`web.py:1264`, `:1311`); no capability parameter
   threads to it anywhere.
2. **Traced both ends** — producer: `invite` issues `GrantTarget(dep, proj, capability)` with a
   `link_token` (`cli_cloud_grant.py:221`); consumer: `kickoff_enter` redeems against a fixed
   `chat-write` target (`web.py:1311-1312`). The wire's two ends carry different capabilities.
3. **Ran the cheapest oracle** — reproduced against the real store: an issued `capture` grant + link
   → `redeem_link(tok, GrantTarget(..., "chat-write"))` returns `allowed=False`; the same token
   against `GrantTarget(..., "capture")` returns `allowed=True`. The existing invite test
   (`test_cloud_grant_invite.py:58`) only ever redeems `chat-write`, so the mismatch is **untested**.
4. **Checked reachability beyond src/+tests** — the sole `redeem_link` call site outside the module is
   `web.py:1312`; no orchestrator, sibling surface, or worktree redeems a non-`chat-write` link.

— **S** (the engine exists; the fix is threading the grant's own capability into the redeem target, or
constraining `invite --capability` to `chat-write` for the human-door path). See CL row below.

### 2. 🌱 Latent capability — surface "what was captured" in the JSON oracle (the three surfaces have drifted)

`Confirmed:` FR-E14 added the **"What was captured"** section (the actual field *values*, the
substance a project owner shares) to md (`readout.py:129`) and HTML (`readout.py:332`), computed by
`_captured_fields(view)` from `state.fields` (`readout.py:75`). But the machine-readable JSON oracle
`AgenticView.to_dict()` (`agentic_view.py:234`) exposes only `attention_counts` + `field_count`
(**counts**, `:245`) — **not the captured values.** So `kickoff readout --format json` / `kickoff
status --json` / the `startd8_kickoff_status` MCP tool return counts while md/HTML now return
substance — the exact drift the readout docstring claims is impossible ("one oracle, so the three
surfaces cannot drift", `readout.py:6`). Add a `captured` key to `to_dict()` reusing the existing
`_captured_fields` shape → so an **agent/CI/MCP consumer** can read *what a project actually decided*
(not just how many inputs are set) **without scraping the HTML.** — **S**

### 3. 🚀 Capability — a `readout --format md` on every row of the portfolio board

`Confirmed:` FR-E16's `scan_portfolio` already builds an `AgenticView` per project
(`portfolio.py:79`) — the *same* oracle `render_markdown` consumes (`readout.py:253`) — but the board
throws the view away after reading `readiness_percent` + `next_step` (`portfolio.py:50-58`). The
board answers "who's stuck"; it can't yet answer "**why**, in one shareable doc per project." A
`kickoff portal --index --scan <ws> --readouts <dir>` that writes one `readout.md` per scanned project
reuses the view already in hand → so a **portfolio owner** can triage a workspace *and* hand each
project lead their own readout in one `$0` offline pass. — **M**

**Sharpest single move:** finding **#1** — it's **S**, and it's the difference between v0.2's
"remote capture is shipped" being true or false. Everything else is additive value; #1 is a
correctness gap in a flow the predecessor doc marks ✅ SHIPPED.

### Closure-Ledger rows (defects only — paste into CLOSURE-LEDGER.md)

| ID | Artifact | What it is | Now | Gate to next level | Value if closed |
|----|----------|------------|-----|--------------------|-----------------|
| CL-NN | `kickoff_experience/web.py::kickoff_enter` (redeem target) | Human door hardcodes redeem capability to `chat-write` (`web.py:1311`); a `capture`/`instantiate` invite grant (FR-E18 × FR-E15) mismatches on `redeem_link` (`cloud_grant.py:318`) → dead link. Reproduced: `capture` link redeems `allowed=False`. | **L2** *(built + unit-tested for `chat-write` only; the non-`chat-write` path is unwired + untested — `test_cloud_grant_invite.py:58` only redeems `chat-write`)* | **→ L3:** thread the grant's own capability into the enter-handler target (or gate `invite --capability` to `chat-write` and file the human capture/instantiate door as a separate spec); add a redeem test for a `capture` grant (**S**) | A human-facing `capture`/`instantiate` invite actually works end-to-end — the FR-E15×E18 composition v0.2 marks shipped becomes true |

---

<details>
<summary><b>Full backlog</b> — the supporting appendix (drawn from over later increments)</summary>

Effort key: **XS** trivial · **S** small · **M** medium · **L** large.
Value audience: **user** (end-user/operator) · **dev** (maintainer). Status: `backlog`/`speccing`/`building`/`done`.

> **Grounding note — where grounding *changed the answer* (the discipline working):**
>
> | What I first believed | What the code actually showed | So the finding is |
> |---|---|---|
> | FR-E18 fully wired capture/instantiate for cloud users | `_cloud_capability` gates them for **programmatic** clients (`web.py:862`), but the **human door** redeems only `chat-write` (`web.py:1311`) — humans can't reach them | Top finding #1 (verified defect) |
> | FR-E14 made the readout drift-proof ("one oracle, three surfaces") | md/HTML render captured *values*; `to_dict()` returns only *counts* (`agentic_view.py:245`) — the surfaces drifted | Top finding #2 (latent, not a defect — JSON is a *superset gap*, not broken) |
> | The portfolio board reuses the full readout | It builds the view then discards all but readiness/next-step (`portfolio.py:50-58`) | Top finding #3 (cheap reuse) |

### ⚡ Quick wins (small, high-value — built on what exists)

| # | Enhancement | Why it helps | Leverages | Effort | Value | Status |
|---|-------------|--------------|-----------|:------:|:-----:|:------:|
| QW-1 | **`kickoff portal --index --scan <ws> --out <file>`** — write the readiness board to a file, not just stdout | The board is a shareable artifact (like `readout --out`); today it's stdout-only (`cli_concierge.py:1313`) so piping/attaching is a manual redirect | `render_portfolio_markdown` + `portfolio_to_dict` (`portfolio.py:107`) already return strings/dicts | XS | user | ☐ |
| QW-2 | **`readout --open`** — open the written HTML in a browser after `--out` | HTML readout exists (`readout.py:485`) but the operator must find + open the file; one `webbrowser.open` closes the papercut (no `webbrowser` import today, confirmed) | the `--out` write path (`cli_concierge.py:1470`) | XS | user | ☐ |
| QW-3 | **Diagnostic on a mismatched invite link** (paired with Top-#1) — when `--capability` ≠ `chat-write`, `invite` warns "the human door only opens chat-write; this link won't redeem in a browser" | Prevents the silent dead-link footgun *even before* the full fix; on-ethos with FR-E1's "print the required target" | the `invite` capability option (`cli_cloud_grant.py:190`) | XS | user | ☐ |

### 🌱 Low-hanging fruit

- **LH-1 — captured values in the JSON oracle** → the fidelity jump in Top-#2. `_captured_fields` (`readout.py:75`) already computes the exact list; add a `captured: [{value_path, value}]` key to `AgenticView.to_dict()` (`agentic_view.py:234`). Byte-additive to existing consumers. — **S**
- **LH-2 — portfolio deep-nesting** → `discover_projects` globs only immediate children (`portfolio.py:65`, `workspace.glob("*/docs/kickoff")`), so a workspace of *grouped* repos (`ws/team-a/proj/docs/kickoff`) scans as empty. A depth flag or `**/docs/kickoff` with a bound would cover real multi-team layouts. Confirm the intended depth first (see Honest gaps). — **S**

### 🏗️ Architectural quick wins

- **AR-1 — one `_captured_fields` / `_snippet` home shared by readout + the JSON oracle.** If LH-1 lands, `to_dict()` and `readout.py` both need the "fields with a value, value_path-sorted, snippet-truncated" shape. Extract the one helper (currently `readout.py:69-82`) so the JSON surface and the md/HTML surface read the *same* projection — closing the drift Top-#2 names at the source, not per-renderer. Distiller smell: **S7 dormant/duplicated projection**; hand deeper cleanup to `/complexity-distiller`. — **S**

### 🚀 Enhanced capabilities

- **EC-1 — per-project readouts from the portfolio scan** → Top-#3. `scan_portfolio` holds each `AgenticView` (`portfolio.py:79`); `--readouts <dir>` renders one `readout.md` each via the existing `render_markdown` (`readout.py:253`). One offline pass triages *and* documents a whole workspace. — **M**
- **EC-2 — the human capture/instantiate door (the *right* fix behind Top-#1).** Once the redeem target is capability-aware, a `capture`/`instantiate` invite can drop a human straight into the capture form (not chat), so a non-technical stakeholder fills fields directly. This is net-new UX (a capture landing page, not just chat), so it's the L-sized version of the CL fix — file it as its own spec after the S-sized correctness fix. Respects **NR-E2** (still coarse session-mint, no per-principal identity). — **L**

### 🔭 Operational / observability *(optional)*

- **OP-1 — a `denied{reason=target_mismatch}` alert would have caught Top-#1 in the wild.** FR-E22's alert rules already fire on `denied{reason}` (`cloud_grant_alerts.py`); `target_mismatch` is an emitted reason (`cloud_grant.py`, GrantDeny). A rule on a spike of `target_mismatch` surfaces "operators are issuing links that don't redeem" — the runtime signal of the Top-#1 footgun. — **S** (rides FR-E22's existing rule group; note OQ-E2 cardinality still holds — `reason` is bounded).

### Honest gaps surfaced while grounding (product decisions, not bugs)

1. **Is the human door *meant* to be chat-only?** The hardcoded `chat-write` (`web.py:1311`) may be a deliberate scope line — "the magic link opens the chat concierge; capture/instantiate are programmatic-only for now." If so, Top-#1 is a **doc/UX defect** (v0.2 implies humans can capture via invite) rather than a code defect, and the fix is QW-3 + a v0.2 note, not EC-2. **Confirm the intended shape** — this decides whether CL-NN closes at **S** (constrain + document) or **L** (build the human capture door).
2. **Portfolio scan depth is deliberately 1 (`portfolio.py:65`).** Flat-workspace-only may be the intended target (one dir of sibling repos). LH-2 is only worth it if grouped/nested workspaces are a real layout — confirm before adding glob depth (over-generalizing the scan is its own accidental complexity).
3. **The JSON oracle omitting captured *values* may be intentional privacy/size scoping** — counts are cheap + safe to expose broadly; values may carry sensitive project content. LH-1 should confirm whether the MCP/CI surface *should* carry raw captured values or a redacted projection.

### 🚫 Deprioritize / out of scope (considered and rejected)

- **Re-proposing FR-E19 (shared trust-chain middleware)** — REJECTED in v0.2 with a grounded ADR (`ADR_E19_SURFACE_AUTH.md`); the three surfaces' auth is deliberately divergent. Not reopened. The capability-aware redeem in Top-#1 is *narrow* (one target field), not a middleware unification — it does not resurrect FR-E19.
- **Live in-dashboard chat / full tenancy** — **NR-E1 / NR-E2** territory; unchanged.
- **A new readiness engine for the portfolio** — the board already reuses the `AgenticView` oracle (`portfolio.py:79`); building a second scorer would be the exact feature-factory anti-pattern this pass exists to avoid.

</details>

## ✅ Delivered (append as items ship — the backlog is living)

*This pass (2026-07-20): building the Top findings. Strike items to ✅ in place as each lands.*

- *(none yet — R2 opened 2026-07-20)*
