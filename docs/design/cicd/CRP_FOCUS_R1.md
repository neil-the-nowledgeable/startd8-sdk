# CRP Focus — CI/CD Capability R1

Where reviewer input is needed most. Weight these over generic completeness checks.

## 1. Layer B credentialed provisioning (highest risk)
The `ci_provision` layer performs side effects against a real vendor (GitHub in v1): repo creation,
`git` push, secret registration, branch-protection rules. Pressure-test:
- **Auth-scope minimization** — what is the *minimum* token scope per operation? Is a single broad PAT
  assumed where fine-grained/OIDC would do?
- **Blast radius** — what is the worst outcome of a misfired provision (wrong repo, overwritten
  protection rules, leaked secret name collision)?
- **Partial-failure recovery** — repo created but secret-register fails midway: what state is the user
  left in, and is re-run safe (FR-PROV-3 idempotency claims this — does the plan actually deliver it)?
- **Token handling** — FR-PROV-4 says tokens never logged/disked/hydrated. Is that enforceable given
  the `secrets.get_secret` path, or just asserted?
- **Dry-run integrity** — is `--dry-run` (FR-PROV-2, the default) genuinely side-effect-free, or could
  a "preview" call mutate (e.g. an auth probe that creates state)?

## 2. Supply-chain posture of GENERATED pipelines
The emitted YAML is itself an attack surface. Validate:
- **SHA-pinning (FR-SUP-1)** — is pinning by commit SHA actually achievable for all referenced
  actions, and how are pins kept current without re-introducing floating tags?
- **OIDC vs stored creds (FR-SUP-2)** — is keyless auth viable across the registry choices, or does the
  fallback to long-lived creds undermine the posture?
- **SBOM/scan (FR-SUP-3, optional)** — is "optional, default off" the right call, or should a minimum
  scan be on-by-default for `deployed`?

## 3. Layer-A / Layer-B trust-boundary integrity
The invariant: Layer B consumes Layer A output and never authors pipeline content; it refuses on drift
(FR-PROV-5). Challenge:
- Is the drift-gate actually enforceable before side effects, or can provisioning race ahead of a stale
  generate?
- Is there any code path where Layer B could synthesize/patch YAML directly, breaking the boundary?

## 4. Secret-name handling after backend-enumeration was ruled out (D4)
FR-SEC-1 now derives names from the `cicd.secrets` manifest + the `.env.example` convention, deny-list
filtered. Validate this is complete and safe:
- Does the convention set cover the real secret surface, or will operators silently miss a required
  secret (pipeline references a name nothing provides)?
- Is the deny-list filter the right gate, or does it risk dropping a legitimately-needed name?

## 5. Per-vendor renderer/drift robustness (OQ-3)
The drift check re-renders and byte-compares emitted YAML. Stress:
- Vendor-side normalization/reformatting of committed YAML (or a UI edit) would flip drift to "1" —
  is owning files operators shouldn't hand-edit a sufficient mitigation, or does this generate false drift?
- Does flattening the vendor into the artifact-kind string (FR-GEN-4, D2) hold across all 5 vendors, or
  do CircleCI/Azure force a structural concession?
