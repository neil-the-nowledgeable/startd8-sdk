# CRP Focus — Deployment Environments (R1)

Weight suggestions toward these:

1. **Determinism / SOTTO boundary.** One env-agnostic base + per-env overlays; env-varying values in
   overlays only, never baked into the base. No environments declared → byte-identical to today. Is
   the base/overlay split airtight? Any value that leaks into the base?

2. **Secrets-per-environment.** Environment ↔ Doppler config (dev→dev, prod→prd) via per-env
   ExternalSecret/SecretStore ref. Any path where a per-env secret VALUE or Doppler project/config
   gets baked into a $0 artifact (FR-CND-9 leak)? Is the env→config mapping safe and explicit?

3. **Orthogonality to mode.** Environment vs deployment.mode must stay independent. Any coupling that
   conflates them? Is "installed = single-local, environments deployed-only" the right call?

4. **kustomize mechanism (OQ-1 resolved → OQ-8 open).** Base + overlays under deploy/overlays/{env}/.
   Robust? What about clusters without kustomize (kubectl -k assumed)? Overlay patch correctness
   (strategic-merge vs JSON patch) for ConfigMap/replicas/ExternalSecret?

5. **The "already env-driven" claim.** Planning concluded no app/settings.py change is needed because
   the app reads all values from os.environ. Stress-test: is there ANY env-varying value the app does
   NOT already read from env (so an overlay couldn't bind it)?

6. **Drift / byte-stability.** Overlays registered for $0 drift; deterministic. Any per-env ordering
   or naming nondeterminism?

7. **OQ-7 (per-env DB ref in overlay vs contract) and OQ-8 (kustomize fallback).** Recommendations.
