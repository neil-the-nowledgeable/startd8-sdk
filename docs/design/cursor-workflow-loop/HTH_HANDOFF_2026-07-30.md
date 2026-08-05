## harden-then-harvest handoff — value-path + dormant inventory

**From:** dev-os (HTH dogfood 2026-07-30)
**To:** ContextCore + startd8-sdk owners

### Insights to leverage (plan against remaining score gaps)

1. **Value-path audit** is now mandatory in `/code-review` §1.5 for shipped / post-implement /
   `--fix` — catches built-but-unwired, claim>gate, presence defaults, dual-surface, skip-forever
   guards, orchestrator-test holes, missing OQ escape hatches *before* CEP.
2. **Phase 2.5 dormant inventory** is now mandatory in `/reflective-retrospective` — Touches →
   `wired|dormant|soft-only|unexercised`; Phase 3 must include ≥1 artifact row.
3. **Composition operator docs invent CLI flags** the same way code invents unwired fns — HTH
   dogfood caught `--body-file` (bus only has `--body`) via value-path before any user run.
4. **Live `wloop list-loops` is not a reliable Verify** when the CLI hangs — prefer static
   `recipes.py` registry absence for "not a loop_id" (REQ-22 FR-2 rewritten).

### Remaining score gaps (please plan)

| Team | Gap class (from recent CEP) | Leverage |
|------|-----------------------------|----------|
| ContextCore | Auto-promote / PICR soft≠hard / Done-when overclaim (EC-AP-*, EC-PICR-*, EC-PC-*) | Run HTH (or at least §1.5 + Phase 2.5) on next shipped remediation unit before CEP |
| ContextCore | JSON≠human Summary omissions (PQO dual-surface) | Value-path item 4 on every new result field |
| startd8-sdk | Skip-forever guards (CH-1 `importorskip`); claim ceiling on recipe Done-when | §1.5 items 2+5 on WLQ prompt-config / contract-health follow-ons |
| startd8-sdk | Human-door vs programmatic FR wiring (grant/cockpit class) | Reachability audit on FR-named capabilities |

### Artifacts

- `dev-os/cursor-loops/howto/HARDEN_THEN_HARVEST.md`
- `dev-os/cursor-loops/REQ-22-Composition-Harden-Then-Harvest.md`
- `dev-os/cursor-loops/HARDEN_THEN_HARVEST_RETROSPECTIVE.md`
- `dev-os/cursor-loops/HARDEN_THEN_HARVEST_ENHANCEMENT_BACKLOG.md`
- `~/.claude/skills/code-review/SKILL.md` (§1.5)
- `~/.claude/skills/reflective-retrospective/SKILL.md` (Phase 2.5)

---

## SDK RESPONSE — 2026-08-05 (startd8-sdk)

Both startd8-sdk score-gap rows audited (survivorship + reachability discipline: verify, don't
manufacture; whole-tree) and addressed. Landed in this PR.

**Gap 1 — Skip-forever guards + claim ceiling (WLQ prompt-config / contract-health).**
- *Skip-forever guards:* audited `tests/unit/workflows/loop_queue/` — **none found**. The one
  `importorskip("jsonschema")` is a legit dev-extra (runs under `.[dev]`, jsonschema is in pyproject).
- *Claim ceiling:* **found + fixed.** The reflective-requirements recipe's `completion`
  (`recipes.py:117`) claimed *"requirements anti-skip **hardened** through v0.3.1 markers"*, but the
  gate (`reflective_hardening_gaps`) only checks marker **presence** — its own docstring says *"not
  proof that lessons or principles were actually applied."* Reworded the claim to match the gate.

**Gap 2 — Human-door vs programmatic FR wiring (grant/cockpit).**
- *Reachability audit* of the FR-E capabilities: **no unwired FRs** — every FR-E is reachable
  end-to-end. The FR-E18×FR-E15 "dead link" gap was already found + fixed (BY-DESIGN, fail-closed
  before minting).
- *Found + fixed one dual-surface drift:* **FR-E14** — the md/HTML/terminal surfaces render the
  captured **values**, but the JSON `AgenticView.to_dict()` exposed only **counts**, contradicting
  `readout.py`'s *"one oracle, so the three surfaces cannot drift (parity, FR-3)"* claim. Added a
  `captured` list to `to_dict()` (additive, value_path-sorted, omitted-when-empty) — closing the
  drift for real, so the no-drift claim is now true.

The remaining rows (ContextCore auto-promote / PICR / Done-when overclaim; PQO dual-surface) are
ContextCore-side.
