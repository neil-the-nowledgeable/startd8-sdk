# Deterministic Contract → Code Generation — Charter

**Date:** 2026-06-02
**Status:** Strategy / charter (not a requirements doc — sets direction; FRs come later)
**Supersedes the implementation of:** `DETERMINISTIC_FRONTEND_SPINE_*` (TS-Next route-handler
generator — retired). **Builds on:** the shipped `value-model.ts` Prisma→Zod renderer
(`frontend_codegen`, Inc 1–8b, merged) and the prime-contractor owned-file skip-hook.

> **Thesis.** The proven, shipped `value-model.ts` renderer — *schema → typed contract,
> deterministically, behind a build-verified gate* — is a **special case** of a broadly valuable,
> **language-agnostic** capability: **contract-first code generation**. Extract that kernel from
> the TS frontend special case and generalize it to the SDK's durable crown jewel — the **polyglot
> microservices contract layer** (online-boutique style: proto/gRPC + OpenAPI → typed stubs/DTOs
> across the existing 5 LanguageProfiles).

---

## 1. Why

The SDK's mature, defensible value is **polyglot microservices generation**. The maintained target
architectural style is the online-boutique demo: many services, multiple languages, talking over
well-defined contracts. That is where the SDK's existing strengths compound — the 5 `LanguageProfiles`
(Python/Go/Node.js/Java/C#), per-language build/repair gates, and the prime-contractor batch
orchestration.

The TS/Next/Prisma frontend work was a **narrow detour**: young, single-language, single-app-shape.
A TS-monolith frontend generator (the "spine") would be narrow tech debt — so its *implementation* is
retired. But the detour **proved a pattern** that is broadly valuable, and that pattern is the asset
worth keeping.

The shipped `value-model.ts` renderer is the proof: it takes a Prisma schema, emits a typed Zod
contract **deterministically** (pure Python, **no LLM**), and is **gated** by a real `tsc --noEmit`
project typecheck plus import-resolution checks. It eliminated an entire class of LLM
invention/compile errors (RUN-011…017) **by construction** for that one artifact. The insight: this
is not "a TS thing" — it is "a contract-first codegen thing" that happens to have been validated in
TS. Generalized, the same three-part kernel applies to **any** schema/contract → typed-code mapping.

---

## 2. The kernel — 3 reusable, language-agnostic parts

The `value-model.ts` renderer is one instantiation of three composable primitives. Stated
language-agnostically:

### (a) Deterministic contract → code generation
From a **schema/contract** emit **typed code deterministically** — no LLM, byte-stable, re-renderable.
- **Today (special case):** Prisma schema → Zod contract (`frontend_codegen.render_zod_schema`,
  driven by `languages/prisma_parser`).
- **Generalizes to:**
  - **protobuf / gRPC** `.proto` → cross-language stubs + message DTOs for the existing 5
    `LanguageProfiles` (Go, Java, C#, Python, Node.js). This is the online-boutique sweet spot.
  - **OpenAPI** spec → typed clients / request-response models.
- The output carries the existing **provenance header** convention (`// GENERATED from <source>`
  + `schema-sha256:<hash>`) so it is recognizable as owned and checkable for drift (see (c)).

### (b) By-construction verification gate
Every **owned** generated artifact must pass **its language's build/compile + import/contract-
resolution checks** before it counts as produced. A generated file that does not compile is not a
shortcut — it is a defect, caught at generation time, not by a downstream reviewer.
- **Today (special case):** `validators.ts_toolchain.run_project_typecheck` (real project-level
  `tsc --noEmit` with `prisma generate` first) + `validators.cross_file_imports`
  (`scan_unresolvable_imports`, `scan_missing_dependencies`). Note the load-bearing safety property
  already encoded in `ts_toolchain`: when the toolchain is **absent**, the result is
  `status="unavailable"` which callers MUST treat as **non-pass** — never a silent PASS.
- **Generalizes to:** the per-language build gates the `LanguageProfiles` already expose — Go build,
  `.NET build`, Gradle compile, `py_compile`, Node syntax check — via the protocol's
  `syntax_check_command` / `validate_syntax` and the per-language toolchain methods. The "absent
  toolchain ⇒ non-pass, never silent PASS" rule transfers verbatim and must be preserved per
  language.

### (c) Contractor owned-file skip-hook via a provider registry
The prime-contractor **skips the LLM** (marks the feature `GENERATED`, **cost $0.00**) when every
target file is deterministically provided **and currently in-sync** — header presence alone is not
enough; a stale or hand-edited owned file must fall through to the LLM (a safe failure). Today this
lives in `prime_contractor._try_deterministic_file_shortcut` (~line 3592) and reaches directly into
`frontend_codegen.drift.{is_owned_generated_file, owned_file_in_sync}` — **a language coupling we
must remove**.

**Generalize via a `DeterministicFileProvider` protocol + registry.** The core (prime_contractor)
depends only on the registry; each language/contract family registers a provider. The TS Prisma/Zod
logic becomes **one provider**; a future `ProtoStubProvider` registers for online-boutique services.

```python
# startd8/contractors/deterministic_providers.py  (new — illustrative shape, not final API)

@dataclass(frozen=True)
class ProviderContext:
    project_root: Path
    source_anchors: tuple[str, ...]   # e.g. the Prisma schema / .proto / OpenAPI spec paths

class DeterministicFileProvider(Protocol):
    name: str
    def owns(self, path: str, content: str) -> bool: ...
    def is_in_sync(self, path: str, content: str, context: ProviderContext) -> bool: ...

# Registry
def register_provider(provider: DeterministicFileProvider) -> None: ...
def discover() -> None: ...   # load providers from entry-point group below
def is_deterministically_provided(
    path: str, content: str, context: ProviderContext
) -> bool: ...               # True iff some registered provider owns(path) AND is_in_sync(...)
```

- **Entry-point group:** `startd8.contractors.deterministic_providers` (same plugin-discovery
  pattern as `startd8.providers` / `startd8.languages` — call `discover()` before use).
- **`PrismaZodFileProvider`** (in `frontend_codegen`) wraps the existing `is_owned_generated_file` /
  `owned_file_in_sync` logic and becomes the **reference implementation** behind the boundary.
- **`ProtoStubProvider`** (future) owns generated gRPC stub/DTO files for online-boutique services.
- The skip-hook in `prime_contractor` then calls `is_deterministically_provided(...)` instead of
  importing `frontend_codegen.drift` directly — **no language coupling in the core**.

---

## 3. What transfers vs what's retired

| Asset | Disposition |
|-------|-------------|
| The **deterministic contract→code pattern** (schema → typed code, no LLM, re-renderable, provenance header) | **Transfer + generalize** — the whole point of this charter |
| The **owned-file skip-hook** (`_try_deterministic_file_shortcut`, $0.00 GENERATED) | **Transfer + generalize** — keep behavior; decouple from `frontend_codegen` via the registry |
| The **by-construction verification gate** (build/compile + import resolution, "absent ⇒ non-pass") | **Transfer + generalize** — map onto each `LanguageProfile`'s build |
| The **drift / in-sync concept** (stale vs tampered vs missing; in-sync = byte-identical re-render) | **Transfer + generalize** — becomes `is_in_sync` per provider |
| The new **`DeterministicFileProvider` protocol + registry** | **New** — the decoupling seam that makes the above language-agnostic |
| `frontend_codegen`'s **Prisma→Zod renderer** (`schema_renderer`, `drift`, `gates`, `conventions`, `skeleton`) | **Keep as one provider / reference impl**, behind the registry boundary — no longer the special-cased core path |
| The **protobuf-version pin** + `cross_file_imports` hooks | **Keep** — directly reusable for proto/gRPC codegen and import verification |
| The **TS-Next route-handler "spine"** (route generators, input-schema/db/completeness/export templates, the codegen manifest) | **Retired** — see the superseded `DETERMINISTIC_FRONTEND_SPINE_*` docs |

---

## 4. Online-boutique application (where the kernel pays off)

Online-boutique is many services in multiple languages, integrated over **proto/gRPC service
contracts**. That contract layer is the **deterministic sweet spot**:

- **Deterministic (the kernel):** from each service's `.proto`, generate the **cross-language stubs
  and message DTOs** — Go/Java/C#/Python/Node — using primitive (a), verify each via primitive (b)'s
  per-language build gate, and let the prime-contractor skip the LLM for those files via primitive
  (c). These are exactly the files where an LLM invents drifting field names and signatures
  (the RUN-011-class failure) — eliminating that by construction across services is high leverage.
- **LLM (grounded + gated):** each service's **business logic** stays LLM-generated, but now grounded
  on a *correct, compiling* contract layer and verified by the same per-language build gate. The LLM
  spends its budget on the irreducible semantic core, not on re-deriving boilerplate it gets wrong.

This is precisely where the SDK is strongest (polyglot, build-gated, batch-orchestrated), so the
kernel compounds existing value rather than opening a new narrow front.

---

## 5. Non-goals

- **Service business logic, UX, or anything semantic.** The kernel generates the mechanical contract
  layer only; semantic code stays with the (grounded, gated) LLM path.
- **Running build toolchains.** The kernel *consults* verification results; the `LanguageProfile` /
  pipeline owns actually invoking `tsc` / `go build` / `dotnet build` / `gradle` / `py_compile`.
- **Generating the source schema/contract itself.** The `.proto` / OpenAPI spec / Prisma schema is
  the **hand-authored source of truth** — the kernel maps *from* it, never invents it.

---

## 6. Open questions

1. **Parser source.** For proto/gRPC and OpenAPI, reuse an existing library (e.g. a protobuf parser /
   `protoc` descriptor, an OpenAPI parser) vs. write a focused parser like `prisma_parser`? The Prisma
   case chose a small bespoke parser; proto/OpenAPI are larger and standardized, which argues for
   reuse — but reuse adds a dependency and a toolchain assumption.
2. **Gate mapping.** How does the by-construction gate map onto each `LanguageProfile`'s build? The
   protocol exposes `syntax_check_command` / `validate_syntax` and per-language build methods, but the
   *project-level* gate (like `run_project_typecheck`) is currently TS-specific. Define the
   per-language equivalent and preserve the "absent toolchain ⇒ non-pass" rule everywhere.
3. **Sequencing.** Likely order: (i) land the `DeterministicFileProvider` protocol + registry and
   re-home the Prisma/Zod logic as `PrismaZodFileProvider` (pure decoupling, no behavior change);
   (ii) add a `ProtoStubProvider` for one online-boutique service end-to-end (one language) to validate
   the gate-mapping; (iii) fan out across the 5 `LanguageProfiles`. Confirm this ordering and the
   first target service.
