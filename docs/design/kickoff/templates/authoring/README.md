# Authoring sources — prose that extracts to manifests

**What this is.** A per-manifest **prose source** is a human-readable document that conforms to a
Kickoff Authoring Contract §-grammar and **deterministically extracts** to its YAML/Prisma manifest.
It is the readable, reviewable front door to a manifest — *"the format carries the truth; LLMs only
carry you to the format."* The emitted manifest is the round-trip acceptance target.

**Home convention.** A project's prose sources live in `<project>/docs/kickoff/authoring/`:

```
<project>/docs/kickoff/authoring/
├── views.md          → prisma/views.yaml        (contract §2.3 — extractor EXISTS today)
├── conventions.md    → kickoff/inputs/conventions.yaml   (contract §2.9 — extractor PENDING, FR-VIP)
└── …                 → one prose source per extractable manifest
```

**Templates here** (`docs/design/kickoff/templates/authoring/`) are project-agnostic skeletons —
copy one into your project's `docs/kickoff/authoring/`, replace the `<…>` placeholders, delete the
`▷` guidance lines, and author.

## Status — which manifests extract today

| Prose source | Manifest | Grammar | Extractor today? | Validate with |
|---|---|---|---|---|
| `pages.md` | `prisma/pages.yaml` | §2.2 | **yes** | `startd8 kickoff check docs/kickoff/authoring/pages.md` |
| `views.md` | `prisma/views.yaml` | §2.3 | **yes** | `startd8 kickoff check docs/kickoff/authoring/views.md` |
| `observability.md` | `inputs/observability.yaml` | §2.12 | **yes (Slice 1: Thresholds + Receivers)** | `startd8 kickoff check docs/kickoff/authoring/observability.md` |
| `conventions.md` | `inputs/conventions.yaml` | §2.9 | **no** — FR-VIP (`SDK_VALUE_INPUT_AUTHORING_REQUIREMENTS.md`) | round-trip-by-correspondence until `extract_conventions` ships |
| build-preferences / business-targets | `inputs/*.yaml` | §2.10+ | no — FR-VIP fan-out | — |

> The **assembly** manifests (schema/pages/views/…) have extractors (`manifest_extraction/`); the
> **value** inputs (conventions/build-prefs/…) do not yet — that gap is the FR-VIP capability. A
> prose source for a not-yet-extractable manifest is a valid *forward-looking* document, but its
> round-trip acceptance is blocked until its extractor exists.

## The authoring loop

1. **Author the contract first** (`prisma/schema.prisma`) — views/aggregates resolve `fk`/`root`
   against it (sequencing, contract §2.3).
2. **Copy the template** → `docs/kickoff/authoring/<manifest>.md`; fill it.
3. **Validate** — `startd8 kickoff check docs/kickoff/authoring/<manifest>.md` (writes nothing).
   Iterate until every value reports `extracted (from §X)`; non-conforming prose is **flagged**
   (`not_extracted(<reason>)`), never guessed.
4. **Extract** — let the pipeline emit the manifest; the emitted YAML is the round-trip target.
5. **Wireframe** — `startd8 wireframe` shows the resulting screens before any build.

*Provenance + traceability (FR-VIP-5/6) ride the existing report currency: every extracted value
records its source `(doc § / row / line)` and preserves the kickoff provisioning states.*
