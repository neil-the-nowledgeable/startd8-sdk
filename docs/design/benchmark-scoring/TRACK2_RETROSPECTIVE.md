# Track 2 Behavioral Scoring — Retrospective

**Date:** 2026-06-15 · **Scope:** the full Track 2 arc — pilot (M-T2.1–4) → hardening → P1+P2 polyglot
expansion. **Status:** merged to main. This is the RETROSPECTIVE bookend (feed lessons back to the
data model / requirements / plan).

---

## 1. What we set out to do
Round 1 of the Summer 2026 benchmark **saturated**: structural compliance and the compile gate scored
~1.000 for every frontier model, so the leaderboard couldn't separate them. Static functional
analysis (Track 1) was **falsified** by a $0 spike (all models implement 100% of proto RPCs; finer
static signals reward verbosity). The only trustworthy discriminator left was **behavior**: run the
generated service and check it behaves correctly. Track 2 built that.

## 2. What we proved
- **Behavior discriminates frontier models where static analysis saturates.** The paymentservice
  pilot: **Opus 1.00** (validates cards — rejects invalid Luhn / expired) vs **gpt-5.5 / gemini 0.33**
  (lenient mocks that accept any card). Static analysis scored all three "complete." This is the whole
  thesis, demonstrated.
- **The harness works and is polyglot.** Node and Go both run end-to-end (Opus shippingservice scores
  1.0 over a `go build`+gRPC path), under a secure, egress-denied sandbox.
- **Generate-once, re-score-free (Mottainai).** Generation is the only real cost; behavioral scoring
  is $0 and re-runnable. We recovered 0→8→9 cells across three harness fixes **without re-paying** —
  the persist-then-rescore loop is real and load-bearing.

## 3. What it cost to learn (the gaps every step surfaced)
Each milestone's value came from what *running it* exposed — not the code:

| Stage | What running it revealed |
|-------|--------------------------|
| First pilot | Keys missing → **missing-key must be `infra_fail`, not the model's 0**; the secure seatbelt loopback profile **blocked the bind** (no `network-inbound`); models `require` undeclared deps (pino/uuid/pino-pretty); models load the proto from divergent paths |
| Hardening | Those were **requirements-completeness failures**, not bad code — the impl faithfully under-built v0.1 reqs (FR-T2-DEPS scoped "gRPC only", nothing on proto paths or durable artifacts) |
| P1+P2 reflective loop | "Install declared deps" is **useless** (models declare nothing → common-set is primary); the stateless RPCs lack a **universal** ground truth like Luhn → suites must assert **invariants** |
| CRP R1 | Provisioning runs untrusted installers **unsandboxed** → ACE re-opened (→ FR-P1-SEC-1..5) |
| Pilot-each-once | "Curated **stateless**" was wrong: currency loads a **data file**, shipping (Go) needs **generated stubs**, and the sandbox **kills `go run` compiles** (→ build-at-provision, serve-binary) |

## 4. The load-bearing lessons (feed these forward)
1. **Discriminators are validation-rich RPCs, not stateless compute.** paymentservice's `Charge`
   separated the flagships because card validation is a *universal* correctness standard (Luhn/expiry).
   `GetQuote`/`GetAds`/`GetSupportedCurrencies` only assert basic invariants (non-negative,
   deterministic) that any competent impl satisfies → they **likely saturate**. **Curate for
   validation/correctness-rich RPCs**, not for "stateless and easy."
2. **paymentservice was unusually self-contained.** No data file, no generated-stubs-as-a-module, pure
   validation. Most OB services need *something* provisioned (data, stubs, or a secure compiler path).
   **Behavioral expansion is per-service data/stub provisioning** — budget for that, not for "pick RPCs."
3. **The expensive thing is generation; everything else is $0 and re-runnable.** Always **persist** the
   generated artifacts and iterate the harness against them — never re-generate to fix a harness bug.
4. **Run it to find the truth.** Every real finding this arc came from *executing*, not reviewing —
   the reflective loop and CRP caught design errors cheaply, but the *empirical* gaps (seatbelt bind,
   undeclared deps, data files, go-build-under-sandbox) only showed up on a live run. Keep the
   pilot-each-once gate before funding N.
5. **Honest degrade is non-negotiable.** Every env failure (missing key, missing dep, sandbox
   violation, provisioning failure) degrades with a named reason and is *excluded*, never scored 0 —
   that's what kept the leaderboard truthful through all the gaps.

## 5. Where it stands & what's next
**Merged:** the behavioral harness (sandbox primitive, secure loopback, startup contract + Node/Go
serve hooks, dep closure + secure per-language provisioning, Go-stub provisioning, persist + $0
rescore, the composite functional term), three invariant suites, P1+P2 requirements (v0.4 with the
CRP-hardened security model), and this retrospective.

**Open (deliberately not chased mid-rabbit-hole):**
- **gemini per-model import robustness** for Go stubs (different module/import shape than Opus).
- **A fresh re-run** to confirm the **shipping-saturation hypothesis** (only Opus ran; N=1).
- **Java/C# secure launchers** (javac/restore over vendored jars, *not* gradle/msbuild).
- **Data-file provisioning** (P3) for currency/catalog.

**Recommended next move:** don't expand to more stateless services. **Target validation-rich RPCs**
(payment-like) — the ones that actually separate models — and treat per-service data/stub provisioning
as the real unit of work. Update the M-T2.5 scoping to lead with "discriminator quality," not "service
count."
