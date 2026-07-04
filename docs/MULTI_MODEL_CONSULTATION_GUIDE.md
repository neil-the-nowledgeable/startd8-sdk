# Multi-Model Consultation — User Guide

Ask **one question of several AI models at once**, compare their answers side-by-side, and follow up
with the whole panel or a single model — from the terminal (TUI or CLI) or an offline web view, with
an optional live interactive mode.

> **In one line:** `startd8 consult run --prompt "…" --image-dir ./photos` → every model answers in
> parallel → `startd8 consult web <id> --open` to compare.

---

## Contents
1. [What it does](#1-what-it-does)
2. [Setup](#2-setup)
3. [Quick start](#3-quick-start)
4. [The CLI](#4-the-cli)
5. [The web view](#5-the-web-view)
6. [Interactive serve mode](#6-interactive-serve-mode)
7. [The TUI](#7-the-tui)
8. [Roster presets](#8-roster-presets)
9. [Cost](#9-cost)
10. [How it works (briefly)](#10-how-it-works-briefly)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. What it does

- **Parallel fan-out** — one prompt (and up to **2 images**) goes to N models at once.
- **Side-by-side comparison** — every model's answer is persisted and shown together for you to judge.
- **Follow-ups** — reply to **all** models or **one**, with each model's conversation remembered
  (real per-provider memory, and prior images re-sent).
- **Four surfaces** over one shared core: **TUI**, **CLI**, an **offline HTML** view, and an optional
  **interactive local server**.
- **Cost in dollars** per model and per session.

**Default roster** ("the council"): a cross-vendor trio — one Anthropic, one OpenAI, one Google model.
Only vision-capable models are used when you attach images.

It is **not** a benchmark or an automated judge — you compare the answers yourself.

---

## 2. Setup

**Keys.** Model calls need provider API keys in the environment. This project uses Doppler:
```bash
doppler run -p startd8 -c dev -- startd8 consult run …
```
(or export `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` yourself).

**Install.** With the SDK installed (`pip install -e .`) the command is just `startd8 consult …`.

> **Running from the feature worktree (pre-install):** if you're testing before a fresh install,
> point Python at the worktree source:
> ```bash
> source ~/Documents/dev/startd8-sdk/.venv/bin/activate
> export PYTHONPATH=~/Documents/dev/startd8-consult/src
> alias consult='python3 -m startd8.cli consult'
> ```
> Then use `consult …` in place of `startd8 consult …`.

**Interactive serve mode** additionally needs the server extras: `pip install startd8[server]`.

Sessions are stored under **`.startd8/consultations/<id>/`** relative to your **current directory** —
run `run`, then `show`/`web`/`cost` from the same folder.

---

## 3. Quick start

```bash
# 1) ask 3 models one question + two photos (parallel, ~a few cents)
doppler run -p startd8 -c dev -- startd8 consult run \
  --prompt "My front door won't open even when unlocked. Help me open it." \
  --image-dir ./door-photos
# → prints "session: 20260704T…"

# 2) compare the answers in a browser (free, offline)
startd8 consult web 20260704T… --open

# 3) follow up with one model
doppler run -p startd8 -c dev -- startd8 consult reply 20260704T… \
  --to gemini:gemini-2.5-pro --prompt "The latch is seized — what tool do I need?"

# 4) re-render to see the new turn
startd8 consult web 20260704T… --open
```

---

## 4. The CLI

`startd8 consult <command>`:

| Command | What it does |
|---------|--------------|
| `run` | Start a consultation (fan the prompt + images to the roster). |
| `reply <id> --to all\|<model>` | Follow up, routed to all models or one. |
| `show <id>` | Side-by-side comparison in the terminal. |
| `list` | List saved session ids. |
| `cost <id>` | Per-model and total USD for a session. |
| `web <id>` | Generate the HTML view (add `--serve` for interactive). |
| `roster list\|save\|delete` | Manage saved roster presets. |

### `run` options
| Option | Meaning |
|--------|---------|
| `--prompt` / `--prompt-file` | The prompt text, or read it from a file. |
| `--image <path>` (repeatable, ≤2) **or** `--image-dir <folder>` | Attach images (mutually exclusive). A folder auto-selects the first 2 valid images by name. |
| `--models <spec>` (repeatable) | Roster, e.g. `--models anthropic:claude-opus-4-8 --models openai:gpt-5.5`. Default = the council. |
| `--preset <name>` | Use a saved roster (see [presets](#8-roster-presets)). Mutually exclusive with `--models`. |
| `--save-preset <name>` | Save the roster you used under a name. |
| `--json` | Print the raw session JSON. |

Images must be **PNG/JPEG/WebP/GIF**, ≤ 5 MB, single-frame (validated by content, not extension).
Non-vision models are skipped with a warning when images are attached.

### `reply`
```bash
startd8 consult reply <id> --to all      --prompt "Summarize the safest next step."
startd8 consult reply <id> --to openai:gpt-5.5 --prompt-file followup.txt
```
Each targeted model continues **its own** conversation. A follow-up to `all` fans out in parallel; a
model that failed can be retried on a later turn.

---

## 5. The web view

```bash
startd8 consult web <id> [--out path.html] [--open]
```
Generates a **single self-contained, offline HTML file** (default `view.html` in the session dir).
No server, no network — copy it anywhere and it still opens.

You get:
- **All models side-by-side**, each panel independently **collapsible** (native keyboard-operable),
  plus **Collapse-all / Expand-all**.
- Each answer rendered as **markdown**, with per-turn badges: **`$cost`**, latency, and in/out tokens.
- A session header: the prompt, the roster, image indicators (filename + short hash), timestamps.
- An **"Ask a follow-up"** composer that builds the exact `consult reply` command to copy-paste
  (the static page never runs anything — see serve mode for click-to-send).

Model output is untrusted, so it's **escaped before rendering** — a `<script>` in an answer shows as
inert text, never executes.

---

## 6. Interactive serve mode

Turn the read-only page into a live one — follow-ups **Send from the page**:
```bash
doppler run -p startd8 -c dev -- startd8 consult web <id> --serve --open
```
- Runs a **loopback-only** local server (`127.0.0.1`). Opens a browser URL carrying a one-time token
  (auto-stripped from the address bar on load).
- Type a follow-up, choose **all** or **one** model, click **Send ▸** → the answer appears in place.
- **Ctrl-C** to stop; auto-shuts down after idle.

| Option | Default | Meaning |
|--------|---------|---------|
| `--port` | ephemeral | Loopback port. |
| `--max-turns` | 20 | Cap on follow-up turns (cost guard). |
| `--max-calls` | 60 | Hard ceiling on total model-calls. |
| `--timeout` | 180 | Per-follow-up timeout (seconds). |
| `--idle-timeout` | 1800 | Auto-shutdown after N idle seconds (`0` = off). |

**Safety, by design:** it binds loopback only (never `0.0.0.0`), requires the per-run token on every
request (constant-time checked), enforces a Host/Origin allowlist (blocks CSRF / DNS-rebinding), sets
a strict Content-Security-Policy so a page-XSS can't steal the token, rejects replayed requests, and
caps spend. If the server extras aren't installed it degrades to writing the static file.

---

## 7. The TUI

```bash
doppler run -p startd8 -c dev -- startd8 tui
# → choose "🗣️  Multi-Model Consultation"
```
Menu-driven over the same engine: **New** consultation or **Open a saved one** → prompt → image pick →
vision-only roster → run under a spinner → comparison table → follow-up loop (**All / One / Retry
failed / View / Done**).

---

## 8. Roster presets

Save a named "council" so you don't retype `--models`:
```bash
startd8 consult roster save myteam -m anthropic:claude-opus-4-8 -m openai:gpt-5.5 -m gemini:gemini-2.5-pro
startd8 consult roster list
startd8 consult run --prompt "…" --preset myteam
startd8 consult roster delete myteam
```
Presets live in `.startd8/consult-presets.json` (local). You can also save on the fly:
`consult run … --models … --save-preset myteam`.

---

## 9. Cost

Every model call is priced in dollars from its token usage:
```bash
startd8 consult cost <id>
#   anthropic:claude-opus-4-8        $0.0683
#   openai:gpt-5.5                   $0.0807
#   gemini:gemini-2.5-pro            $0.0155
# total $0.1646
```
The same `$cost` shows per-turn in the web view and the CLI comparison, with a session total. Tip:
images can dominate cost and providers count image tokens very differently — watch the per-model split.

---

## 10. How it works (briefly)

- Models run **in parallel**; one model failing never sinks the others (its error is recorded).
- Answers persist to `.startd8/consultations/<id>/session.json` (+ a human `summary.md`); images are
  referenced by path + hash, **never** stored as bytes.
- **Follow-up memory is native** — each model gets a real provider message array (not a text
  transcript), and prior images are re-sent after re-validating their hash (a moved/changed file
  degrades to an `[image unavailable]` note, never wrong bytes).
- Cost flows through the SDK's cost tracker; the continuity mode is pinned per session for consistency.

---

## 11. Troubleshooting

| Symptom | Fix |
|--------|-----|
| `no such command 'consult'` / `No module named startd8.consultation` | Install the SDK, or set `PYTHONPATH` to the worktree src (see [Setup](#2-setup)). |
| `no available models` | Provider keys missing — run under `doppler run -p startd8 -c dev --`. |
| `show`/`web`/`cost` say the session isn't found | Run them from the folder where you ran `run` (`.startd8/` is CWD-relative), or `startd8 consult list`. |
| Serve: "session is already being served" | A stale lock from a hard-killed server — it self-heals if that PID is dead, else `rm .startd8/consultations/<id>/.serve.lock`. |
| Serve won't start, "server extras missing" | `pip install startd8[server]` (it writes the static view instead until then). |
| An image is rejected | Must be PNG/JPEG/WebP/GIF, ≤ 5 MB, single-frame; a renamed/animated file is refused. |

---

*Multi-Model Consultation is part of the startd8 SDK. A styled offline version of this guide ships
alongside it as `MULTI_MODEL_CONSULTATION_GUIDE.html`.*
