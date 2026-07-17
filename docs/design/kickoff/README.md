# Kickoff — Requirements Navigator

**What this is:** every kickoff requirement, rendered so you can **approve the whole system at a
glance** *and* **drill to a single clause** — using **one visual grammar at every level**.

> **North Star (fsn / Jurassic Park).** The SGI 3D file-system navigator rendered a filesystem as
> a landscape you *fly through*: directories are pedestals, files are objects whose height/color
> encode metadata, and the same objects appear at every zoom. This page is the static prototype of
> that idea for **requirements** — see [The navigator vision](#the-navigator-vision-fsn). The
> capability it previews (*requirements you browse and approve by looking*) is the product
> differentiator.

---

## The grammar (one node, every altitude)

Everything on this page — the whole system, a layer, a concept, a single clause — is the **same
node**, shown at different zoom:

```
<status>  <KEY>  <one-line WHAT>          ← collapsed (the glance / landscape view)
```
expandable to the full card:
```
DOES · WON'T · LIVES · [SHIPS-WHEN]  + status + KEY + WAS(aliases)
```

- **`<status>`** — the metadata encoding (fsn's height/color): `✅ built + wired` · `🟡 built, thin` · `📄 spec-only`
- **`<KEY>`** — the stable `FR-`prefix. **This is identity** and never changes; the branding is a mutable alias.
- **`SHIPS-WHEN`** appears **only when `LIVES` is empty** — the activation gate that distinguishes a *parked decision* from a *dormant defect*.

Roll-up and drill-down are the same grammar: a **layer**'s status is the min of its concepts; a
**concept**'s is the min of its clauses. Advertise the lowest open loop — no rounding up.

---

## Level 1 — The landscape (approve at a glance)

*Fly over the whole system. Grounded 2026-07-16 via `grep -rE 'FR-<p>-?[0-9]' src/`; number = code mentions.*

**Concierge** — agentic write-path engine · `src/startd8/concierge/`
```
✅ FR-C    Concierge MCP — safe, gated write-path core ................. 43
✅ FR-DC   Derive a contract from a live database ...................... 40
✅ FR-CDA  Fold deployment-awareness into the plan ..................... 19
✅ FR-PC   Per-project provider / model config ........................ 11
🟡 FR-CM   Concierge Mode — package-less view + serve .................. 3
🟡 FR-AC   Agentic propose → human-confirm → apply loop ................ 2
```
**Red Carpet** — guided staging / advisor flow · `kickoff_experience/red_carpet*.py`
```
✅ FR-RCA  Prescriptive advisor — suggests the next input ............. 25
✅ FR-RCT  Red Carpet Treatment — staged from-scratch build ........... 19
✅ FR-WD   Wizard-driver — walks the completion sequence .............. 17
```
**Welcome Mat** — user-facing kickoff UI · `kickoff_experience/web.py`
```
✅ FR-WM2  Welcome Mat 2.0 — template download + agentic chat ......... 33
✅ FR-NEW  Interactive Kickoff Experience (the umbrella) .............. 17
```
**Intelligence & UX**
```
✅ FR-MS   Manifest Suggester — grounded value recommendations ........ 37   · stakeholder_panel/
✅ FR-UX   Kickoff UX / information architecture ...................... 17   · presentation.py
✅ FR-NU   Next-recommendation unification ............................. 7   · ranking.py
📄 FR-KIT  Role-Kit CLI — the set's one open loop ................... spec   · (not built)
```

**Verdict:** 15 of 16 built and wired; only `FR-KIT` is spec-only. The system is *done* — it was
only illegible at the doc layer. This navigator is the fix.

---

## Level 2 — A concept, previewed

Click into any row and it expands to the full card. The grammar carries **both** a built concept
and a deferred one — `SHIPS-WHEN` appears only for the latter:

```
┌─ FR-WM2 · "Welcome Mat 2.0" ───────────────────────── ✅ built + wired ─┐
│  DOES    User lands → downloads a filled input template → refines via     │
│          agentic chat → confirms → kickoff inputs are applied.            │
│  WON'T   No autonomous writes (propose-then-confirm floor). No bespoke     │
│          per-project code. Oversized zip / message → fail closed.         │
│  LIVES   kickoff_experience/web.py · telemetry.py · concierge/writes.py    │
│  KEY     FR-WM2-*      WAS  "Welcome Mat" · "Welcome Mat 2.0"             │
│  APPROVE?  [ does DOES match intent? ] · [ is the WON'T floor right? ]     │
└──────────────────────────────────────────────────────────────────────────┘

┌─ FR-KIT · "Role Kit CLI" ───────────────────────── 📄 spec-only · DEFERRED ─┐
│  DOES    `startd8 kit <role>` renders one delivery role's kit — draft      │
│          templates + review checklist + named validation artifact (the     │
│          FR-J9 triad) for the 11 HITM roles; resolves each generic         │
│          template → this project's instance; machine-checks completeness.  │
│          `startd8 kit` (no arg) → the role × completeness matrix.          │
│  WON'T   $0 / read-only / advisory: no LLM, no network, no writes (bar     │
│          `--out`). Never a gate (exit 0 even when incomplete). Does NOT     │
│          fork the docs — a *view over* the canonical markdown kits.        │
│  LIVES   — nothing yet — the set's one unbuilt concept.                    │
│  SHIPS-WHEN  the docs-first kits stabilize (FR-KIT-4's anti-fork test has  │
│  (§5)        a fixed target) AND a real discovery/completeness demand       │
│              signal appears. Deliberately deferred (operator Q8, 06-05) —   │
│              a v2, not neglect.                                            │
│  KEY     FR-KIT-*      WAS  "Role Kit CLI" (no branding churn)             │
│  MIRRORS FR-W-* (wireframe) — same $0 / read-only / advisory CLI pattern   │
│  APPROVE?  [ is DOES the right v2 scope? ] · [ is SHIPS-WHEN the right      │
│            trigger to start? ]                                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Level 3 — Drill into a concept's clauses

Fly *inside* `FR-KIT` and its 9 clauses appear — **same grammar, one level down.** This is
browsability to the lowest spec level; each clause is itself a node you could expand:

```
FR-KIT · Role Kit CLI                                         📄 spec-only (9/9)
├─ 📄 FR-KIT-1  `kit <role>` + role×completeness matrix (11 HITM roles)
├─ 📄 FR-KIT-2  $0, read-only, advisory exit ............ (mirrors FR-W9)
├─ 📄 FR-KIT-3  kit view = FR-J9 triad (template + checklist + validation)
├─ 📄 FR-KIT-4  docs stay canonical; CLI is a view, not a fork (anti-fork test)
├─ 📄 FR-KIT-5  per-project resolution: generic template → this project's instance
├─ 📄 FR-KIT-6  machine completeness verdict → feeds FR-X1
├─ 📄 FR-KIT-7  Rich table + `--json` (schema-versioned) . (mirrors FR-W10)
├─ 📄 FR-KIT-8  optional read-only cap-dev-pipe hook ..... (mirrors FR-W11)
└─ 📄 FR-KIT-9  stable API: build_kit_view(role, project_root) -> KitView
```

## Level 4 — The leaf (code)

The bottom of every drill is `LIVES` → a real `file:line`. For a built concept it resolves
(`FR-WM2` → `kickoff_experience/web.py:659`); for `FR-KIT` it's empty, which is *why* the card
carries `SHIPS-WHEN` instead. The leaf is where preview meets territory — and where the wireframe
capability takes over, previewing what the code itself will build.

---

## The navigator vision (fsn)

The four levels above are one interactive navigator, drawn statically in markdown. The mapping
from the Jurassic Park file-system flythrough:

| fsn (Jurassic Park) | Requirements Navigator |
|---|---|
| Filesystem as a landscape you fly over | Level 1 — the system, all layers at a glance |
| Directory pedestal → its files | Level 2/3 — a concept → its clauses, same grammar |
| File **height / color** encodes size/type | **Status glyph** encodes built/thin/spec (min-rolls-up) |
| Fly *into* a directory to see contents | Drill-down: layer → concept → clause → code leaf |
| Same objects at every zoom | **One node grammar** at every altitude |
| "It's a UNIX system — I know this!" | One UI learned once, used everywhere |

**Why it's the differentiator:** competitors hand a reviewer a wall of prose and ask "is this
right?" — unanswerable at a glance, so approval is slow or rubber-stamped. A navigator lets the
person *whose intent the requirement encodes* approve **what will be built by looking**, at
whatever altitude they need, in a UI they learned once. The author gets the same gift: see and
approve your own intent, spot drift (an empty `LIVES`, a slipped `WON'T`) without re-reading.

**Status of the vision:** L1 — the grammar is proven across two concepts (`FR-WM2` built,
`FR-KIT` deferred) and four zoom levels *in markdown*. **Do not build the interactive/3D navigator
yet** — prove the static grammar across a few more doc sets first, then Hansei it into a real tool.
Building the flythrough now is the over-formalization shadow DEV-OS exists to counter.

---

## For new kickoff docs

1. Declare the **`FR-`prefix first**, before the title. Prefix = identity; title = presentation.
2. Write the **DOES / WON'T / LIVES** preview *before* the full spec. If `LIVES` will be empty,
   add **SHIPS-WHEN** (the activation gate) — a deferred requirement without one reads as a defect.
3. A rebrand = version bump + alias note in the body. **Never a new file.**
4. Add the concept to Level 1 as its code home appears; its clauses inherit the grammar for free.

Pattern done right from the start: `../wireframe/WIREFRAME_REQUIREMENTS.md` (`FR-W-*`, never rebranded).
