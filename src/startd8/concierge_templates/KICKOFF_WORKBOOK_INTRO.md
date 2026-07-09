The **Digital Project Workbook** — the shared, whole-project view of the foundational kickoff decisions. A dynamic, query-based evolution of Brooks' workbook (_The Mythical Man-Month_), which was static (paper/microfiche); this one is generated from live project state. State is the canonical `KickoffState` (the same `$0` extraction the web UI and TUI use) — projected into these panels. Re-run `startd8 kickoff portal` to refresh.
<!-- PLAIN -->
### Your Project Workbook

This board is a **live picture of your project's setup** — the handful of foundational decisions the
build needs before it can create your app. Think of it as a shared checklist everyone can see.

Each row is one **input**. The colored marker tells you where it stands:

- **✅ confirmed** — you (or your docs) supplied this. Done.
- **🟡 review** — the tool picked a sensible default; worth a quick look.
- **🔴 gap** — nothing set yet; this one needs your input.
- **🛡️ safe default set for you** — the tool filled this in on your behalf so you're not stuck. You can
  change it any time, but you don't have to.

Nothing here is final, and you can't break anything — the board just reflects what's on disk. When you
change an input and re-run `startd8 kickoff portal`, the board updates to match. Start with the 🔴 gaps.
<!-- /PLAIN -->
