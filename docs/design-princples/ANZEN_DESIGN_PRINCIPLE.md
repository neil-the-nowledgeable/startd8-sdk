# Anzen Design Principle

Purpose: establish a cross-cutting design principle for the ContextCore + startd8-sdk pipeline — security correctness is a structural property of the pipeline, not an afterthought applied during review.

This document is intentionally living guidance. Update it as new security derivation opportunities are identified.

---

## The Principle

**Anzen** (安全) — "safety; security; freedom from danger." In Japanese, anzen describes not the absence of risk but the *presence of protection* — a state where harm cannot occur because the conditions that produce it do not exist.

Applied to the pipeline: **every service produced by the Capability Delivery Pipeline is secure by construction. Not because a reviewer caught an injection. Not because someone ran a security scan after the fact. Because the pipeline structurally cannot produce code with known vulnerability classes — the same way it structurally cannot produce a service without a dashboard (Hitsuzen) or without internal instrumentation (TODO Completion).**

---

## Relationship to the Design Principle Family

Anzen completes the pipeline's quality guarantee chain alongside the existing principles:

| Dimension | Mottainai | Kaizen | Warm Up | Hitsuzen | Anzen |
|-----------|-----------|--------|---------|----------|-------|
| **Scope** | Single run | Across runs | Across toolchains | Derivable outputs | Security-sensitive outputs |
| **Focus** | Don't discard artifacts | Don't discard lessons | Don't discard context | Don't generate what you can derive | Don't generate what you can't secure |
| **Waste eliminated** | Redundant regeneration | Repeated failures | Transition regressions | Unnecessary LLM calls | Security vulnerabilities |
| **Mechanism** | Artifact forwarding | PDCA feedback loop | Pre-flight protocol | Deterministic derivation | Security contract + verification gates |
| **Question** | "Has this already been computed?" | "Have we seen this problem before?" | "What changed while I was away?" | "Is this derivable without an LLM?" | "Can this code harm the system it runs in?" |

### Complementary Relationships

- **Anzen + Hitsuzen**: Parameterized query patterns are *derivable* — the database client library determines the safe syntax. Anzen says "this must be secure"; Hitsuzen says "and we can derive the secure form deterministically."
- **Anzen + Kaizen**: When a run produces a security finding, Kaizen's feedback loop injects it as a prompt hint in the next run. Anzen ensures the verification gate catches it regardless of whether the hint worked.
- **Anzen + Mottainai**: The security contract (like the instrumentation contract) is computed once at EXPORT and forwarded — not re-derived by the LLM. Discarding it would be mottainai.
- **Anzen + Keiyaku**: Security contracts between pipeline stages are typed, validated boundaries — the same Keiyaku principle that governs agent-to-agent handoffs.

---

## Why This Matters

### The Problem: Security as Review Finding

Today, security in the Capability Delivery Pipeline is discovered, not designed:

1. **Generation**: The LLM produces code. It may or may not use parameterized queries, may or may not log credentials, may or may not create connection pools correctly. The prompt says nothing about security because security requirements are not in the task spec.

2. **Review**: A T3 or T2 model reviews the code. It may or may not notice injection patterns. The C# Prime Contractor runs demonstrated that 5 rounds of multi-model review (Claude Opus, Gemini Pro) identified the AlloyDB injection but *accepted it* because "it matches the reference."

3. **Post-mortem**: The Kaizen post-mortem flags security issues. By this point the code is generated, reviewed, and potentially committed. The finding is a lesson for the *next* run, not a gate for *this* run.

This is the security equivalent of the observability problem that TODO Completion solved: the pipeline had all the information needed to produce secure code, but no derivation step computed a security contract and no verification gate enforced it.

### The Evidence: C# Prime Contractor Runs 078–079

| Finding | What Happened | What Anzen Prevents |
|---------|---------------|---------------------|
| AlloyDB SQL injection | Generator faithfully reproduced string interpolation from reference. 5 review rounds flagged it but accepted it for "structural equivalence." | Security contract specifies parameterized queries. Verification gate fails unconditionally on string interpolation in SQL context. Reference equivalence is subordinate to security. |
| Spanner false positives | Semantic validator flagged safe `@param` binding as injection. Trust in validator eroded. | Database-aware pattern modules distinguish safe from unsafe syntax per client library. False positive rate is a tracked Kaizen metric. |
| Credential leakage | `Console.WriteLine(connectionString)` reproduced from reference. No requirement prohibited it. | Security contract includes `credential_handling` rules. Verification gate detects logging of variables identified as credential-bearing. |
| Connection pool exhaustion | Per-call `NpgsqlDataSource.Create()` reproduced from reference. No lifecycle check existed. | Security contract includes `resource_lifecycle` rules. Verification gate detects resource creation inside per-request methods. |

### The Shift: From Intentional to Structural

The TODO Completion workflow established a pattern:

> The human declares "this service has 99.9% availability SLO" in the manifest. Everything downstream — the dashboard, the alerts, the metrics emission — is *derived*.

Anzen extends this:

> The pipeline knows the target database, the client library, and the external inputs. Everything downstream — the parameterization method, the credential handling pattern, the connection lifecycle — is *derived from a security contract*.

---

## The Security Contract

A **security contract** is a structured specification derived from the pipeline's accumulated context that declares what security properties generated code must have. It is the security analog of the instrumentation contract (REQ-TCW-000–003).

### What It Contains

```yaml
security_contract:
  service_id: "hipstershop.CartService"
  language: "csharp"

  query_security:
    databases:
      - id: "alloydb"
        client_library: "npgsql"
        parameter_syntax: "@paramName via NpgsqlParameter"
        unsafe_patterns:
          - "$\"...{variable}...\"  # string interpolation in SQL"
          - "\"...\" + variable + \"...\"  # concatenation in SQL"
        safe_patterns:
          - "cmd.Parameters.AddWithValue(\"@name\", value)"
          - "new NpgsqlParameter(\"@name\", value)"
        resource_lifecycle:
          singleton: ["NpgsqlDataSource"]
          per_request: ["NpgsqlCommand", "NpgsqlConnection"]
          dispose_pattern: "using/await using"

      - id: "spanner"
        client_library: "google-cloud-spanner"
        parameter_syntax: "@paramName via SpannerParameterCollection"
        unsafe_patterns:
          - "$\"...{variable}...\"  # string interpolation in SQL"
        safe_patterns:
          - "SpannerParameterCollection { { \"name\", SpannerDbType.X, value } }"
        resource_lifecycle:
          singleton: ["SpannerConnection"]
          per_request: ["SpannerCommand"]

      - id: "redis"
        client_library: "stackexchange-redis"
        parameter_syntax: "N/A (command-based, no SQL)"
        safe_patterns:
          - "cache.StringGetAsync(key)"
          - "cache.StringSetAsync(key, value)"
        resource_lifecycle:
          singleton: ["ConnectionMultiplexer", "IDatabase"]

  credential_handling:
    secret_sources:
      - type: "google_secret_manager"
        retrieval_pattern: "SecretManagerServiceClient.AccessSecretVersion"
        must_not_log: true
      - type: "environment_variable"
        names: ["ALLOYDB_PASSWORD", "REDIS_PASSWORD", "DB_PASSWORD"]
        must_not_log: true
    connection_string_rules:
      - "NEVER log the full connection string"
      - "Log host:port/database separately (without password)"
      - "Redact password field before any diagnostic output"

  health_checks:
    - store: "alloydb"
      operation: "SELECT 1"
      must_not_expose: ["connection_string", "credentials"]
    - store: "spanner"
      operation: "connection.Open()"
      must_not_expose: ["project_id", "instance_id"]
    - store: "redis"
      operation: "cache.PingAsync()"
      must_not_expose: ["connection_string"]
```

### How It's Derived

The security contract is computed — not written by hand — from data already in the pipeline:

| Source | Available at | What It Provides |
|--------|-------------|-----------------|
| `.contextcore.yaml` | Stage 0 (CREATE) | Service identity, declared data stores, external dependencies |
| Plan + requirements | Stage 2 (INIT-FROM-PLAN) | Database backends, client libraries, credential sources, API surface |
| Language profile | Stage 5/6 | Framework-specific parameter binding syntax, safe/unsafe patterns per client library |
| `onboarding-metadata.json` | Stage 4 (EXPORT) | Service metadata, dependency coordinates, configuration patterns |
| Kaizen history | Cross-run | Prior injection findings, false positive records, framework effectiveness |

### Where It Lives

The security contract is emitted alongside the instrumentation contract in `onboarding-metadata.json` at EXPORT (Stage 4), then forwarded through the pipeline like any other Mottainai artifact.

---

## The Verification Pipeline

Anzen verification is **deterministic where possible, LLM-assisted where necessary**:

```
Stage                           Method              Tolerance
─────                           ──────              ─────────
1. Parameterization check       Deterministic       Zero (hard fail)
2. Credential leakage check     Deterministic       Zero (hard fail)
3. Resource lifecycle check     Deterministic       Warning → fail (after Kaizen data)
4. Health check exposure check  Deterministic       Zero (hard fail)
5. Semantic security review     LLM (T3)            Advisory → fail (for COMPLEX tier)
6. Reference deviation audit    Deterministic       Informational (log deviations)
```

**Key property:** Steps 1–4 require **no LLM calls**. They are pattern-matching against the security contract's `safe_patterns` and `unsafe_patterns` per database. This means:

- Security verification can run during **profile generation** (before any code is generated) as a dry-run against the contract
- Security verification adds **zero cost** to TRIVIAL/SIMPLE queries
- False positives are database-specific and correctable without retraining a model

---

## Security TODOs: The Query-as-TODO Pattern

The TODO Completion workflow introduced three TODO categories:

| Category | Description | Resolution |
|----------|-------------|------------|
| A | Commented-out implementation | Uncomment |
| B | Contract-derivable stub | Implement from instrumentation contract |
| C | Insufficient context | Defer |

Anzen introduces a fourth category and a new TODO type:

### Category S: Security-Sensitive Code

A TODO is Category S when it involves code that handles external input in a database context. Category S is orthogonal to A/B/C — a TODO can be both Category B (contract-derivable) and Category S (security-sensitive):

| Combined | Meaning | Example |
|----------|---------|---------|
| A+S | Commented-out query code | Uncomment + verify parameterization |
| B+S | Contract-derivable query implementation | Implement from security contract + verify |
| C+S | Underspecified query code | Flag for human review — security gap |
| S only | Generated query code (not a TODO) | Post-generation security verification |

### Security TODO Lifecycle

```
TODO Scanner (REQ-TCW-100)
  ├── Detects query-bearing TODOs
  ├── Cross-references against security_contract.query_security.databases
  └── Tags as Category S when: target file contains database client imports
          │
          ▼
Security Contract Resolution
  ├── For each Category S TODO:
  │   ├── Resolve database → client_library → parameter_syntax
  │   ├── Resolve credential_sources → handling rules
  │   └── Resolve resource_lifecycle → singleton vs per-request
  └── Inject security contract context into task spec
          │
          ▼
Generation (via Query Prime or Prime Contractor)
  ├── Prompt includes security contract constraints
  ├── T3 drafts query spec with parameterization requirement
  └── T1/T2 generates code (if needed)
          │
          ▼
Security Verification (pre-EXPORT gate)
  ├── Deterministic checks (steps 1-4) — zero tolerance
  ├── LLM review (step 5) — advisory/fail by tier
  └── Produces SecurityVerificationResult per query method
          │
          ▼
EXPORT Phase
  ├── Only code that passes security verification is exported
  ├── Security gaps reported in postmortem
  └── Kaizen feedback loop for next run
```

---

## Pipeline Integration Points

### Stage 0 (CREATE): Security Profile Declaration

The `.contextcore.yaml` manifest gains an optional `spec.security` section:

```yaml
spec:
  security:
    data_stores:
      - id: alloydb
        type: sql
        client: npgsql
        credentials: google_secret_manager
      - id: spanner
        type: sql
        client: google-cloud-spanner
        credentials: service_account
      - id: redis
        type: nosql
        client: stackexchange-redis
        credentials: environment_variable
    sensitivity: high  # low/medium/high — determines verification strictness
```

This is the security analog of `spec.observability`. It declares *what* the service connects to; the pipeline derives *how* to secure those connections.

### Stage 4 (EXPORT): Security Contract Emission

Like the instrumentation contract (REQ-TCW-003), the security contract is computed at EXPORT and emitted in `onboarding-metadata.json`:

- `security_contracts` key: dict keyed by service ID
- Each contract includes: `query_security`, `credential_handling`, `health_checks`
- Contract is checksummed and included in provenance chain

### Stage 5 (PLAN-INGESTION): Security-Aware Task Enrichment

During plan ingestion, tasks that target database-facing files are enriched with security contract context:

- Task metadata gains `security_sensitive: true` flag
- `gen_context` includes the relevant `security_contract` section
- Complexity classification treats `security_sensitive` tasks as minimum MODERATE (never TRIVIAL/SIMPLE) for the *generation* tier, even if the query itself is simple

### Stage 6 (CONTRACTOR): Security-Aware Generation

The Prime Contractor (and Query Prime when invoked) uses the security contract in spec/draft prompts:

- Spec prompt includes database-specific parameterization patterns
- Draft prompt includes `SECURITY CONSTRAINT: Use parameterized queries` as P0 section
- Review prompt includes security checklist derived from the contract

### Pre-EXPORT Gate: Security Verification

Before generated code is exported, a security verification pass runs:

- Uses the deterministic verification pipeline (steps 1-4)
- Queries that fail are flagged in the postmortem
- Configurable strictness: `sensitivity: high` = hard fail, `sensitivity: medium` = warning + human review, `sensitivity: low` = advisory only

### Post-EXPORT: Kaizen Security Metrics

Security outcomes feed the Kaizen loop:

| Metric | Type | Description |
|--------|------|-------------|
| `injection_found_pre_export` | counter | Injections caught by verification gate |
| `injection_escaped` | counter | Injections found in post-mortem (verification gap) |
| `false_positive_rate` | gauge | Safe patterns incorrectly flagged |
| `security_todo_completion_rate` | gauge | Category S TODOs resolved |
| `credential_leak_prevented` | counter | Credential logging patterns caught |
| `security_contract_coverage` | gauge | % of declared data stores with complete contracts |

---

## The Bigger Picture: Security as a Pipeline Property

When Anzen is fully implemented, the pipeline guarantees:

1. **If a service has a database, it has a security contract.** (Derived from `spec.security` + language profile)
2. **If it has a security contract, generated queries use parameterized binding.** (Enforced by verification gate)
3. **If it handles credentials, it doesn't log them.** (Enforced by credential leakage check)
4. **If it creates database connections, it manages their lifecycle correctly.** (Enforced by lifecycle check)
5. **If a prior run had a security finding, the next run addresses it.** (Kaizen feedback loop)

Combined with TODO Completion's observability guarantees:

6. **If it has an SLO, it has a dashboard.** (REQ-CDP-OBS-002)
7. **If it has a dashboard, its code emits the metrics.** (REQ-TCW-302)
8. **If it has RPCs, its code propagates trace context.** (REQ-TCW-001)

The service is observable *and* secure — not because someone remembered, but because the pipeline cannot produce anything else.

---

## Phasing

### Phase 1: Security Contract Derivation (ContextCore EXPORT) — PLANNED

Extend `onboarding-metadata.json` with `security_contracts` section. Derive from `.contextcore.yaml` `spec.security` + language profile pattern databases.

### Phase 2: Security TODO Detection (StartD8 SDK) — PLANNED

Extend `todo_scanner.py` with Category S classification. Cross-reference against `security_contracts` for database-bearing files.

### Phase 3: Query Prime Module (StartD8 SDK) — PLANNED

Implement `src/startd8/query_prime/` as the dedicated query generation domain instantiation of the Prime paradigm. See [QUERY_PRIME_REQUIREMENTS.md](../query-prime/QUERY_PRIME_REQUIREMENTS.md).

### Phase 4: Pre-EXPORT Security Gate (StartD8 SDK) — PLANNED

Deterministic security verification pipeline. Zero-tolerance injection and credential leakage checks. Wired as a gate before the EXPORT stage.

### Phase 5: Kaizen Security Feedback Loop — PLANNED

Security metrics in postmortem. Prompt hint injection for prior security findings. False positive tracking and suppression.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Over-restrictive verification blocks valid code | Medium | High | Database-specific pattern modules with explicit safe patterns; false positive tracking with auto-suppression after 3 confirmations |
| Security contract derivation misses a data store | Medium | Medium | Fallback: any file importing a database client library triggers minimum security verification |
| LLM ignores security constraints in prompt | Medium | High | Deterministic verification gate catches violations regardless of LLM behavior — the gate is the guarantee, not the prompt |
| Reference implementation deviations rejected by stakeholders | Low | Medium | Security deviation comments (`// SECURITY: ...`) document rationale; `sensitivity` config allows per-project override |
| Performance overhead of security verification | Low | Low | Steps 1-4 are regex pattern matching (~ms); only step 5 uses LLM |
