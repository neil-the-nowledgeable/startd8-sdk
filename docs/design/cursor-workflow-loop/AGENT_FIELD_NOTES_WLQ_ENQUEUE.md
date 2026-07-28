# Agent Field Notes — Using the Workflow Loop Queue (WLQ) to Enqueue a CRP

**Author:** Claude (Cursor agent surface) · **Date:** 2026-07-25
**Pairs with:** [HOWTO_AGENT_ENQUEUE.md](HOWTO_AGENT_ENQUEUE.md)
**Context:** enqueued a dual-doc CRP job (`loop_id=crp`, `executor=agent-surface`, `surface_id=cursor`) to
review a ContextCore requirements + plan pair (`REQ_SIL_REX_DESIGN_EXECUTION.md` + its plan). First-hand
report of what worked, what tripped me, and concrete HOWTO/CLI improvements — from the agent's seat.

---

## TL;DR

The enqueue path is genuinely good — one JSON envelope + one CLI call, validated, and `status` confirms
`pending`. I got the job queued and reviewable in ~3 commands. But I made **two real mistakes an agent will
repeat**, both avoidable with small doc/CLI changes: (1) the queue **root defaults to CWD**, so I enqueued
into the *wrong project* (`ContextCore`) before the user caught it; (2) the HOWTO shows a `pending/` path but
the CLI stores under `jobs/`, which reads like a bug when you `ls pending/` and see nothing. A third
annoyance: OTel export errors bleed into the CLI's stdout.

**Agent-ergonomics: 4/5.** Loses a point only on the root-defaulting footgun and the `jobs/` vs `pending/`
ambiguity — both documentation-level, not design flaws.

---

## What I did (the happy path, once corrected)

1. Read `HOWTO_AGENT_ENQUEUE.md` → copied the "Quick path (CRP dual-doc, agent-surface)" envelope.
2. Wrote a job JSON: `loop_id=crp`, `executor=agent-surface`, `surface_id=cursor`, `config.{plan_path,
   requirements_path, scope, max_rounds, substantially_addressed_threshold, max_suggestions}`, all absolute
   paths.
3. `startd8 wloop enqueue --config <file> --root <sdk>/.startd8/workflow-loop-queue` → exit 0.
4. `startd8 wloop status --job-id <id> --root <sdk>/...` → `status: pending`, dual-doc config echoed back.

The envelope schema is discoverable straight from the HOWTO's field cheat sheet; I didn't need to read
source. The validation is fail-closed and the error surface (exit 2 on bad paths/fields) is clear.

---

## What tripped me (grounded — I actually hit these)

### 1. Queue root defaults to CWD → I enqueued into the wrong project ⚠️ (highest-impact)
`enqueue`/`status` default `--root` to `.startd8/workflow-loop-queue` **relative to the current directory**.
I ran the first enqueue from the *consumer* project (`ContextCore`, where the docs live), so the job
materialized at `ContextCore/.startd8/workflow-loop-queue/jobs/…` — a brand-new queue nobody drains. It
looked successful (`exit 0`, `status: pending`) so nothing signaled the mistake; the user had to catch it
("did you write it under `startd8-sdk/…`?"). I then re-enqueued with an explicit `--root` pointing at the
SDK queue and cleaned up the stray one.

**Why an agent hits this:** the docs I was reviewing live in one repo; the loop that drains lives in
another. "Enqueue from where the work is" is the natural instinct and it's wrong. The default silently
creates a valid-but-orphaned queue.

**Fixes (pick any):**
- HOWTO: add a bold **"the queue root is the *loop-owning* project (usually the SDK repo), NOT the project
  whose docs you're reviewing — always pass `--root` (absolute)"** callout in Preconditions.
- CLI: on enqueue, if the resolved root was **freshly created** (0 prior jobs, no config marker), print a
  loud `note: created a NEW queue at <path> — is this the intended loop root?` to stderr.
- CLI: support a discoverable/global root (`STARTD8_WLOOP_ROOT` env or an upward `.startd8` search) so
  "which queue" isn't a function of CWD.

### 2. `jobs/` vs `pending/` — the HOWTO path and the CLI storage disagree
HOWTO step 1 says *"Save as `.startd8/workflow-loop-queue/pending/crp-…json`"*, but `startd8 wloop enqueue`
stores the job under **`jobs/…json`** with a `status: "pending"` field. So after enqueue, `ls pending/` is
**empty** — which reads as "the enqueue didn't work" until you realize `status` reports it fine and it lives
in `jobs/`. The `pending/` folder is the **file-drop** input; the CLI is the **envelope-store** path. Both
are valid, but the HOWTO presents the `pending/` path as *the* location for the CLI flow.

**Fix:** HOWTO — separate the two modes explicitly:
> - **CLI enqueue (recommended):** write the envelope anywhere, `startd8 wloop enqueue --config <file>` →
>   stored at `jobs/<id>_startd8_wloop.json` with `status=pending`. Check with `wloop status`, NOT `ls pending/`.
> - **File-drop:** drop the envelope directly into `pending/`; the drainer picks it up.

### 3. OTel export errors pollute CLI stdout
Every `wloop` call emitted `Failed to export logs to localhost:4317, error code: StatusCode.DEADLINE_EXCEEDED`
inline. On an agent surface I parse stdout, so I had to `grep -viE "Failed to export|DEADLINE"` around every
call to keep the JSON clean. When there's no local collector, telemetry export should fail **silently to
stderr** (or be suppressed unless `--verbose`), never interleaved with the command's JSON result.

---

## The bigger realization (worth more than the enqueue itself)

Reading the HOWTO reframed a feature I was mid-designing. I was drafting a **bespoke "design tick" wake
prompt** for a contextcore remediation loop (agent authors `/reflective-requirements` docs + conditional
CRP, moving a finding `ingested → accepted`). The WLQ **already models this**:
- `loop_id: "reflective-requirements"` — the design-authoring job (agent-surface).
- `loop_id: "crp"` — the review job.
- `depends_on` — chain them: reflective first, CRP gated on its completion.

So the right design is *"enqueue a `reflective-requirements` job + a chained `crp` job for the finding, then
drain,"* not a new prompt mechanism. It also **preserves the `contextcore → startd8` zero-import boundary**
(the loop shells `startd8 wloop`, never imports it) and gives **CRP review-independence for free** (the CRP
job drains as its own execution, not the author self-reviewing). This is the strongest argument I found for
the WLQ: it's a **reusable substrate for any agent loop**, not just the SDK's own workflows — but that reuse
value isn't advertised in the HOWTO. A short "using WLQ as the queue for *your* agent loop (chaining
reflective → crp, shell-out keeps import boundaries)" section would land it.

---

## Concrete suggestions (ranked by agent-impact)

| # | Suggestion | Impact |
|---|-----------|--------|
| 1 | **Warn/require an explicit root** — default-to-CWD silently orphaned my job | High — the one mistake that shipped |
| 2 | **Split `jobs/` (CLI) vs `pending/` (file-drop) in the HOWTO** — `ls pending/` looking empty reads as failure | Medium — cost me a confused check |
| 3 | **Silence OTel export failures on stdout** — they interleave with parseable JSON | Medium — every call needed a grep guard |
| 4 | **Add a "WLQ as a substrate for your own agent loop" section** (chaining, shell-out import boundary) | High for adoption — the reuse story is buried |
| 5 | **`status` after enqueue in the HOWTO's checklist wording** — say "confirm via `wloop status`, not by listing folders" | Low — reinforces #2 |

---

## What was already excellent (keep)

- **One envelope, one command, fail-closed validation.** The `config` cheat sheet meant zero source-diving.
- **`status` echoes the full stored envelope** — I could verify the absolute paths landed correctly.
- **`depends_on` chaining** is exactly the primitive a multi-stage agent loop needs; it's the feature that
  turned my "build a new loop" into "compose two existing loops."
- **`executor` split (`agent-surface` vs `sdk-workflow`)** cleanly separates "run it in my chat" from
  "headless with keys" — I knew immediately which I was.

---

*Field notes · one agent, one real CRP enqueue · pairs with HOWTO_AGENT_ENQUEUE.md*

---

## Follow-up (2026-07-25) — addressed in FR-24 / FR-25 / FR-26 / FR-17

| # | Suggestion | Disposition |
|---|-----------|-------------|
| 1 | Warn/require explicit root | **FR-24** — `$STARTD8_WLOOP_ROOT` + fresh-root stderr note; HOWTO Preconditions |
| 2 | Split `jobs/` vs `pending/` | **FR-25** — HOWTO CLI vs staging table; confirm via `wloop status` |
| 3 | Silence OTel / log noise on stdout | **FR-17** — wloop JSON-only stdout; OTel quiet + SDK logs → stderr |
| 4 | Substrate section | **FR-26** — HOWTO “Using WLQ as the substrate…” |
| 5 | Checklist wording | HOWTO checklist + skill enqueue steps |

---

## Addendum — the DRAIN half (enqueue → run-next → applied) · 2026-07-25

The first notes covered enqueue only. The CRP job then **drained and completed** — I got to watch the full
arc, which changed my read of the system. (I did not run `run-next` myself; the job completed between my
enqueue and my next check — auto-drain or user-triggered, I couldn't tell, which is itself feedback: the
"drain is a separate step" contract wasn't observably enforced from my seat.)

### What the drain produced (genuinely strong)
- **2 rounds, reviewer `composer-2`**, appended **in-place to the source docs** as `Appendix A/B/C` +
  per-round **Requirements Coverage Matrices** (`Covered | Partial | Gap` per FR). The coverage matrix was the
  single most useful artifact — it told me *exactly* which FRs to harden without re-reading the review prose.
- **20 suggestions** (R1/R2 × S-plan/F-reqs), each **anchored to a specific §/line with a validation
  criterion** and severity. High signal — they caught real gaps (unpinned bound algorithm, an empty
  "Appendix B" I'd referenced, dual CRP paths, no telemetry step, mid-tick resume).
- **Independent convergence:** the reviewer independently arrived at the same WLQ-reuse point I'd noted
  (R2-S1 "dual CRP paths", R2-F4 "WLQ as an FR-015-conformant CRP drain"). An independent review landing on
  my own conclusion was a real confidence signal — exactly the value of review-independence.
- **Append-only memory works:** R2 referenced R1 (`Endorsements`, "R1-F3 already flagged") — the cross-round
  memory stopped re-litigation, as designed.

### The one thing that tripped me on the drain side ⚠️
**`triage_policy=auto_accept` marks every suggestion "applied" in Appendix A — but does NOT edit the document
body.** Each Appendix-A row reads *"WLQ auto-triage after max_rounds (triage_policy=auto_accept)."* Reading
"Applied", an agent naturally assumes the requirement text now reflects the suggestion. It does **not** — the
FRs were unchanged; I still had to hand-fold all 20 into the body (→ v0.4). So **"applied" here means
*triage-accepted*, not *implemented-in-body*.** That gap is a silent correctness trap: a downstream agent
that trusts Appendix A would ship a doc whose body contradicts its own review log.

**Fixes (ranked):**
1. **Rename the state or add a column.** `Appendix A: Accepted (pending body-apply)` with an explicit
   `applied_to_body: yes/no`. Auto-triage sets `accepted, applied_to_body=no`.
2. **Say it in the drain result.** The `drain-result.json` / chat hand-off should state loudly: *"N
   suggestions AUTO-ACCEPTED into Appendix A; body NOT modified — run the apply step / fold manually."*
3. **Optional `enable_apply` for agent-surface.** Today `enable_apply` is "sdk-workflow only" — an
   agent-surface apply pass (agent edits the body, then records applied_to_body=yes) would close the loop.

### Net on the drain
The **review quality is excellent** and the coverage matrix alone justifies the loop. The **only** hazard is
the `applied`-vs-`applied-to-body` ambiguity under `auto_accept` — a labeling fix, not a design flaw. With
that clarified, the enqueue→drain→apply arc is a genuinely good substrate for an agent design loop.

*Addendum · same agent, observed the CRP drain + folded its output into spec v0.4.*
