# Retrospective — REQ-06 Corpus Governance Delivery (Hansei)

**Pilot:** the REQ-06 corpus-governance delivery (`govern.py`, the `gate_spec` consolidation, the
`navigator govern` CLI, LOOP_CATALOG #7) + the HTH P1/P2 hardening over it. **Window:** 2026-08-15.
**Method:** `/reflective-retrospective` as HTH-on-REQ-06 Phase 3 (grounded in code + the reachability probe).

## Phase 2.5 — Dormant inventory (grounded via the reachability probe)

| Touch | Grep / evidence | Status |
|-------|-----------------|--------|
| `gate_spec` (lifted into govern.py) | consumed by `scripts/navigator_spec_delivery_loop.py` | **wired 1/0** (after P1 scan-root fix) |
| `govern_corpus` | CLI `navigator govern` + tests | wired 2/0 |
| `Finding` | 9 refs | wired |
| `render_govern_text` / `render_govern_json` / `recurring_finding_classes` | CLI `govern` command | wired |
| `_check_{name_block,single_line_fr,dangling_xref,coverage,index_freshness,orphans}` | all called in `govern_corpus` L482-492 | wired |
| `GovernReport` | constructed in `govern_corpus`, returned; consumers use the instance not the name | **dormant (benign)** — return-type dataclass; accepted probe limitation |

Scanned 7 public + 6 check symbols; **all wired** except the benign `GovernReport` return-type class.

## Phase 3 — Reflection (belief → actual)

| Kind | What I believed | What the actuals revealed | So the standard is… |
|------|-----------------|---------------------------|---------------------|
| **process** | the EB-3 reachability probe reliably detects dormants | it scanned **`src/` only** → false-flagged `gate_spec` (wired from `scripts/`) as DORMANT | a wiring probe must scan **every real consumer root** (product + tooling = `src/` + `scripts/`); `tests/` excluded (test-only ≠ wired). **The dormant-detector had its own detection blind spot.** |
| **process** | REQ-06 needs a *new* governance mechanism | the loop's stage-0 gate **was** governance-in-embryo; REQ-06 consolidated it (lifted `gate_spec` into `govern.py`, script re-exports) | the **script→src consolidation pattern**: lift the checker into the importable home (Kagami), the script becomes a thin importer + re-exporter (keeps `sdl.X` callers and monkeypatch targets green). |
| **artifact** | every govern public symbol is wired | `GovernReport` shows DORMANT 0/0 | benign — a return-type dataclass; the probe's name-based heuristic can't see instance-only use. Accept, don't over-engineer the probe. |

## Phase 4 — The standard this delivery PROVED

1. **Script→src consolidation.** When a driver script accretes logic a `src/` module also needs,
   **lift it into `src/`** (the importable home) and refactor the script to `import` + **re-export at
   module scope** — this satisfies the CLAUDE.md "when splitting a module, forward all symbols + fix
   patch targets" rule, keeping existing `sdl.gate_spec` callers and `monkeypatch(sdl, ...)` targets
   resolving unchanged. Proven: `gate_spec` lifted, `test_spec_delivery_loop.py` passed **unedited**.
2. **Probe-scan-completeness (extends the EB-3 "wired, not just built" clause).** A reachability/wiring
   probe must cover **every real consumer surface** or it cries wolf. Scan `src/` + `scripts/` (product +
   tooling); exclude `tests/` (a test-only consumer is the very "tested but not wired" dormant the probe
   exists to catch). Proven: `gate_spec` DORMANT → wired once `scripts/` entered the scan.

## Phase 5 — Lessons

- **The dormant-detector needs its own coverage audit.** A tool that flags "unwired" must itself scan
  all wiring surfaces, or it emits false dormants that erode trust — the exact crying-wolf risk REQ-06
  names. Detection: run the probe on a symbol you *know* is wired-from-`scripts/`; a DORMANT verdict
  means the probe's scan is incomplete. (This session: `gate_spec`.)
- **Recursive hardening is real.** HTH-on-REQ-06 hardened the EB-3 probe that a *prior* HTH pass built.
  The harvest improves its own instruments — worth running HTH on tooling deliveries, not just features.

## Phase 6 — Yokoten + feed-forward

- **Yokoten:** the script→src consolidation pattern applies to the other loop scripts
  (`navigator_pilot_loop`/`_content_loop`/…) if their logic is ever wanted in `src/`. The probe-scan
  clause is already shipped (P1) and now guards every future `--reachability` run.
- **Feed-forward:** no open dormants (all wired; `GovernReport` benign). The probe-scan-completeness
  clause becomes an input to the next `/reflective-requirements` touching wiring/governance tooling.
