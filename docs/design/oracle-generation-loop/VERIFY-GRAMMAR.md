# Runnable `Verify:` Grammar for Generated Apps (FR-2)

**Project:** startd8-sdk **Pairs with:** `REQ-seat-verify-oracle-as-generation-fitness-rung.md` (FR-2)
**Grammar id:** `a1` (locked, REQ v0.4.1)
**Home:** `src/startd8/oracle_loop/grammar.py`

> This is the **closed convention** for a det-req spec whose target is a **generated app**. It has
> its OWN parser (`oracle_loop.grammar.parse_verify_clause`), deliberately distinct from
> `navigator/verify_oracle.classify()` — whose `_classify_clause` only promotes a `startd8`-verb
> span to `command` (`_ALLOWED_VERBS = {"startd8"}`), so a `pytest`/`probe` clause classifies as
> `assertion` there and would yield ZERO runnable descriptors (REQ D-2 / R1-F2). FR-1's runner
> extracts through THIS parser, never `classify()`.

## The three verdict kinds a clause resolves to

Every FR's `Verify:` clause is parsed into exactly one of:

| kind        | runnable? | how it runs |
|-------------|-----------|-------------|
| `one-shot`  | yes       | a backtick span → `benchmark_matrix.sandbox.run_sandboxed` (rc0 = pass) |
| `service`   | yes       | a `probe` micro-grammar → a DATA-ONLY struct → a FIXED loopback httpx call via `run_service_sandboxed` |
| `assertion` | no        | prose acceptance — human-gate residue (never executed) |
| `manual`    | no        | a runnable-looking span that is rejected (multi-command, injection, malformed) — residue |

`assertion` and `manual` are the non-runnable **residue** (FR-6). Only `one-shot`/`service` are the
fitness.

## Form 1 — one-shot (`run_sandboxed`, pass = rc 0)

A clause is a **one-shot** iff it contains exactly one backtick span whose **first token** is a
runnable verb:

- `pytest` (the power path — arbitrarily complex behavioral checks live in the generated test file)
- `python` / `python3` (e.g. `python -m app.checks`)
- a **resolved generated console-script** — a bare first token (no `/`, no `.`) that the spec's
  target app exposes as a console entry point. Resolution is the runner's job (FR-1); the grammar
  records the token as `console_script` and the runner maps it to the venv/app binary. It is NOT a
  host-`PATH` lookup.

Examples (runnable):

```
Verify: `pytest tests/test_health.py -q` exits 0 proving the health route returns ok.
Verify: `python -m app.selfcheck` exits 0.
```

Rejected → `manual`:

- more than one runnable backtick span → `manual` ("multi-command")
- a span joined by `;` / `&&` / `||` / `|` → `manual` ("multi-command")
- a first token not in the runnable-verb set and not a bare console-script token → not a one-shot

The one-shot span is tokenised with `shlex` to an argv tuple. A leading `$` prompt marker is
stripped. An untokenisable span → `manual`.

## Form 2 — service probe (`run_service_sandboxed`, DATA-ONLY)

> **Security (R1-F3 / R1-S2):** `run_service_sandboxed` invokes its `client(port)` callback **in the
> host process** (`sandbox.py:334`), NOT inside the sandbox. Therefore a service clause may **never**
> contribute executable client code. It contributes only a **declarative probe struct** that the
> runner renders into a FIXED, hard-coded loopback `httpx` call. Clause text is never `eval`/`exec`/
> imported.

A clause is a **service** probe iff it contains the keyword `probe` immediately followed by a
backtick span matching the micro-grammar:

```
METHOD /path [body={<json>}] -> STATUS
```

- `METHOD` ∈ {`GET`, `POST`, `PUT`, `PATCH`, `DELETE`} (upper-case; the closed verb set)
- `/path` — a leading-slash request path, no spaces, no scheme/host (loopback is fixed by the runner)
- `body={...}` — **optional**; the `{...}` must parse as a JSON object (`json.loads`). Anything that
  is not valid JSON → `manual` ("probe body not JSON")
- `-> STATUS` — the expected HTTP status, an integer 100–599

The parser emits a data-only struct:

```python
ProbeSpec(method="GET", path="/health", body=None, expected_status=200)
```

Examples (runnable):

```
Verify: probe `GET /health -> 200` — the health endpoint is live.
Verify: probe `POST /items body={"name":"x"} -> 201` creates an item.
```

Rejected → `manual` (the parse fails, so nothing runs):

- `probe` followed by anything other than the closed micro-grammar
- a `body=` that is not a JSON object
- a `METHOD` outside the closed set, a non-integer / out-of-range status, a path without a leading `/`
- **injection attempts** — the parser accepts ONLY the fixed token shape; a clause embedding a lambda,
  a `client=`, backticked Python, or shell text does not match the micro-grammar and yields `manual`.
  There is no code path from clause text to an executable object.

## Authoring target (the coverage lever, R1-F1 / FR-6)

> Every FR whose intent is **machine-checkable** SHOULD carry a runnable clause (a `one-shot` or a
> `service` probe). Prose-only FRs are legitimate (design constraints, human-judgement acceptance)
> but they count against **coverage** (runnable / total). An operator sets a `--min-coverage` floor
> (FR-8) below which the loop fails closed with terminal cause `coverage_below_floor`.

Coverage is `len(one-shot ∪ service) / len(all FRs)`. An **empty** runnable set is `no_fitness`
(FR-6) — never a vacuous green.

## Non-goals

- The grammar does **not** reinterpret any existing `Verify:` clause. Existing SDK specs ride the
  separate navigator-oracle path (`startd8`-verb clauses) which this loop never touches (FR-11).
- The grammar does **not** support shell pipelines, multi-command chains, or arbitrary client code.
  The `pytest` power path is the escape hatch for complex checks — put the logic in the test file.
