# CRP Focus — Cloud-Native Deployment Artifacts (R1)

Where we most need independent review. Weight suggestions toward these:

1. **Security — secrets path.** Doppler-as-default-backend behind the vendor-neutral ESO
   `ExternalSecret` seam (FR-CND-5). Is the `eso-doppler` default sound? Is the Doppler
   service-token bootstrap (chicken-and-egg, FR-CND-11) handled safely? Any leak path where an
   operator-bound secret/value gets baked into a deterministic artifact (violating FR-CND-9)?

2. **Security — identity behind the gateway.** The Bearer/JWT decode-only seam (FR-CND-6,
   auth-seam-jwt) trusts agentgateway to have verified the token. Is "no app change between direct
   and behind-gateway" safe? What happens if the app is exposed WITHOUT a gateway in front (direct
   internet) — is there a fail-closed story, or a footgun?

3. **Vendor-neutrality boundary.** Core = standard Kubernetes + Gateway API (`v1` HTTPRoute) + ESO;
   vendor-specific (Gloo CRDs, Doppler-operator CRD, agentgateway/kagent) is opt-in (FR-CND-3/7,
   `deploy.secrets.backend`). Is the line clean? Any place a vendor CRD leaks into the neutral core?

4. **Bucket-1/bucket-4 line (Mottainai).** SDK emits app-layer manifests + infra-needs contract
   (bucket 1); Terraform/StackGen provision (bucket 4); Kestra/Argo orchestrate. Is the infra-needs
   contract (FR-CND-11) a sufficient, well-specified seam? Is render-only `startd8 deploy k8s`
   (no kubectl/build/push) the right boundary, or does it leave a gap the operator can't close?

5. **Determinism / drift.** All artifacts owned/$0/drift-checked via the ScaffoldFileProvider
   pattern; `deployed`-only emission must stay byte-identical-when-absent (SOTTO). Risk: manifest
   layer drifts from app reality (port, `/health` path, env names) — is the cross-check (plan §4)
   adequate?

6. **Ops prerequisites.** Cluster prereqs (Gateway-API CRDs, ESO/Doppler operator, OTLP collector,
   IdP issuer, SecretStore). Are they all enumerated in the infra-needs contract? Anything an
   operator would hit at deploy time that the contract doesn't surface?

7. **StartDate (strtd8) pilot acceptance (FR-PILOT-1).** Is the graded boot ladder (local harness
   extended to a cluster-smoke rung, operator-run) a sufficient acceptance gate for "deploy to
   AWS/GCP soon"? What's the minimum proof that the pilot actually validates the capability?

8. **OQ-9 (open).** Should v1 render a Terraform variables stub, or stay tool-neutral YAML only?
   Recommendation welcome.
