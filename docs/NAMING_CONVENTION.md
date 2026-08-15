# Naming Convention — semantic names, not integer+type alone

**Rule (standing):** every development artifact — requirements, plans, features, code files, configs,
scripts, tests, project documents, and any other software artifact — carries a **semantic name** that
says what it *means* or *does*. Identifying something by an **integer + content-type alone** is an
anti-pattern.

Grounded in `DETERMINISTIC_INTENT_DELIVERY_LANGUAGE` (§"How the naming works"): a short integer key
is fine **as a reference**, but it must never be the *only* name.

## The anti-pattern

A bare `<TYPE>-<n>` or `<type><n>` identity with no meaning attached:

| Anti-pattern | Why it fails |
|--------------|--------------|
| `FR-1` with no name | you must open it to know what it is |
| `REQ-01.md`, `PLAN-03.md` | filename carries no subject |
| `test_2.py`, `script1.sh`, `util3.py` | content type + integer, zero meaning |
| `Component1.tsx`, `config-2.yaml` | ditto |

## The pattern — four forms (keep the key AND a name)

For a requirement/feature, the four deterministic forms (the key is retained as a short ref):

| Form | Example (FR-1) | Purpose |
|------|----------------|---------|
| **Local key** | `FR-1` | short reference inside one doc |
| **Semantic name** | `SDK exposes a NODE-SCHEMA-compatible Node · NodeEvidence · derive_status surface …` | meaning (actor · action · object · outcome) |
| **Readable handle** | `requirement/sdk-exposes-a-node-schema-compatible-node-5a728ad3` | recognition + compact deterministic correlation (kebab slug + 8-hex digest) |
| **Canonical ref** | `cc:intent:sdk-node-home:requirement:fr-1` | stable machine identity, wording-independent |

For files/scripts/tests/configs/docs, the equivalent is a **descriptive slug** filename:

| Good | Anti-pattern |
|------|--------------|
| `REQ-01-sdk-node-home.md` (key prefix **+ subject slug**) | `REQ-01.md` |
| `navigator_pilot_loop.py`, `PILOT_IMPROVEMENT_LOOP.md`, `LOOP_CATALOG.md` | `script1.py`, `doc2.md` |
| `test_metabolize_app_shape.py` | `test_2.py` |

## How it's enforced in the det-req grammar

`Name:` is a first-class det-req field (`det_req.parse_name`): an authored
`Name: <actor·action·object·outcome>.` on an FR is parsed into `attributes.name`, and
`sources_requirements._name_forms` derives the `handle` + `canonical` ref deterministically. The
navigator render shows **NAME →** / **HANDLE:** at the top of each node's detail. A node with **no**
`Name:` is surfaced as a content gap by the pilot loop's content sibling (see `LOOP_CATALOG.md`).

**Authoring an FR name:** `- **FR-N — <short title>.** <behavior>. Name: <actor action object outcome>. Touches: … Lives: … Verify: … Serves: …`

## Applying it going forward

New reqs/plans/features → author a `Name:`. New files/scripts/tests/docs → descriptive slug, never
`type+integer` alone. When you encounter a bare integer-typed identity, add the semantic name rather
than leave it.
