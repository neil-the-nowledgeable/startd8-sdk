# Multi-Model Consultation — Testing Guide

How to exercise every surface of the consultation feature yourself: TUI, CLI (`run`/`reply`/`show`/
`list`/`web`), the static web view, and the interactive `--serve` local server.

> **Cost:** everything that does **not** call a model is **$0** — `list`, `show`, `web` (static
> render), and the security-guard curls. Real spend happens only on `run`, `reply`, and serve-mode
> **Send** (each hits the model roster). Wrap those in `doppler run -p startd8 -c dev --` for keys.

---

## 0. One-time setup (per terminal)

The feature currently lives on the `feat/multi-model-consultation` branch / worktree, so pin
`PYTHONPATH` to its `src` (otherwise Python loads the pre-feature code from the main checkout):

```bash
source ~/Documents/dev/startd8-sdk/.venv/bin/activate
export PYTHONPATH=~/Documents/dev/startd8-consult/src
alias consult='python3 -m startd8.cli consult'
```

Sessions are stored under `.startd8/consultations/<id>/` **relative to your current directory**, so
run `list`/`show`/`web` from the same folder you ran `run` in.

> Once this branch is merged and installed (`pip install -e .`), the `PYTHONPATH` line and the
> `python3 -m startd8.cli` prefix are unnecessary — just use `startd8 consult ...`.

---

## 1. Zero-cost — inspect an existing session

```bash
consult list                 # saved session ids in ./.startd8/consultations/
consult show <id>            # side-by-side comparison, in the terminal
consult web  <id> --open     # generate the standalone static HTML view + open it
```

In the **static page**: every model is a panel side-by-side; click a panel header (or Tab→Enter)
to **collapse/expand** it; **Collapse-all / Expand-all** in the toolbar. The "Ask a follow-up" box
builds a **copy-paste `consult reply` command** (the static page never executes anything).

The page is fully self-contained — copy the `.html` anywhere and it still opens offline.

---

## 2. Full fresh consultation (costs a few cents)

```bash
mkdir -p ~/consult-test && cd ~/consult-test
doppler run -p startd8 -c dev -- consult run \
  --prompt "My front door is broken — the handle won't open it even when unlocked. Help me open it." \
  --image-dir ~/Documents/dev/benchmarking/Summer2026/docs/images
# note the "session: <id>" it prints
```

- `--prompt` / `--prompt-file`, `--image <path>` (≤2) **or** `--image-dir <folder>`, `--models` (repeatable;
  default = cross-vendor council), `--json`.
- Non-vision models are skipped with a warning when images are attached.

Then view / follow up:
```bash
consult web  <id> --open
consult reply <id> --to gemini:gemini-2.5-pro --prompt "The latch is seized — what tool should I buy?"
consult reply <id> --to all --prompt "Summarize the safest single next step."
consult web  <id> --open      # re-render to see the new turns
```

---

## 3. ⭐ Interactive serve mode (`--serve`) — click-to-Send

Runs a **loopback-only** local server so follow-ups Send from the page and answers appear in place.
Real (paid) model calls happen **only when you click Send**.

```bash
doppler run -p startd8 -c dev -- consult web <id> --serve --open
```

- Opens the browser to a `127.0.0.1` URL carrying a one-time token (auto-stripped from the address
  bar on load).
- Type a follow-up, pick **all models** or **one** (chips), click **Send ▸** → the targeted panel(s)
  gain a new turn live.
- **Ctrl-C** to stop. Auto-shuts down after 30 min idle (`--idle-timeout`, `0` = off).
- Flags: `--port` (default ephemeral), `--max-turns` (default 20), `--max-calls` (hard model-call
  ceiling, default 60), `--timeout` (per-follow-up seconds), `--idle-timeout`.

### Poke the security model (no cost)

While it's running, from another terminal (use the port it printed):

```bash
curl -s -o /dev/null -w "no-token GET  -> %{http_code}\n" http://127.0.0.1:<PORT>/
curl -s -o /dev/null -w "wrong token   -> %{http_code}\n" "http://127.0.0.1:<PORT>/?t=nope"
curl -s -o /dev/null -w "foreign Host  -> %{http_code}\n" -H "Host: evil.com" "http://127.0.0.1:<PORT>/?t=whatever"
curl -s -D - -o /dev/null "http://127.0.0.1:<PORT>/?t=<real-token>" | grep -i "content-security-policy"
```

Expect `401` (no/wrong token), `403` (foreign Host), and a strict `Content-Security-Policy:
… script-src 'nonce-…'; … connect-src 'self'`. The token is loopback-only, constant-time compared,
and validated before any session work; a follow-up "auto-submit" hidden in a model's answer can't
fire (CSP + Origin + the required click all block it).

---

## 4. The TUI (menu-driven, same engine)

```bash
doppler run -p startd8 -c dev -- python3 -m startd8.cli tui
# → choose "🗣️  Multi-Model Consultation"
```

Prompt → image pick → vision-only roster → run under a spinner → comparison table → follow-up loop
(**Follow up with ALL / ONE / Retry failed / View / Done**).

---

## 5. Run the automated tests

```bash
cd ~/Documents/dev/startd8-consult
PYTHONPATH=$PWD/src python3 -m pytest tests/unit/consultation/ tests/unit/agents/test_multimodal.py -q
```

Covers: multimodal image threading + byte-identity across all 3 providers; session model / store /
fan-out engine; selection trust boundary + roster + view; CLI + the TUI≡CLI golden fixture; the web
renderer (XSS-inert, no path leak, golden static hash); and serve-mode security (loopback, token,
Host/Origin, upgrade-reject, caps, replay nonce, idle watchdog, cross-process lock).

---

## Gotchas

- `no such command 'consult'` / `No module named startd8.consultation` → `PYTHONPATH` not pointed at
  `~/Documents/dev/startd8-consult/src`.
- `no available models` on `run`/`--serve` → provider keys missing; run under `doppler run -p startd8 -c dev --`.
- Serve won't start: `session … is already being served` → a stale `.serve.lock` from a hard-killed
  server; it self-heals if that PID is dead, else `rm .startd8/consultations/<id>/.serve.lock`.
- `web`/`show`/`list` read `.startd8/` relative to CWD — run them where the session was created.
