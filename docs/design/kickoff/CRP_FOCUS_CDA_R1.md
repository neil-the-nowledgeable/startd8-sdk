# CRP Focus — Concierge Deployment-Awareness (R1)

Weight suggestions toward:

1. **assist-not-operate boundary (FR-CDA-6).** The Concierge must stay read-only over MCP — never run
   the deploy, apply manifests, or record a gate. Does adding deployment-readiness + the
   check_deploy_coherence tool risk crossing into "operate"? Any write/exec path introduced?

2. **FR-C10 no-recompute.** assess delegates to the wireframe and must NOT recompute provisioning
   state. Does surfacing the coherence verdict + per-env unbound bindings stay delegation, or sneak
   in a recompute?

3. **posture → mode DEFAULT-not-force (FR-CDA-3).** Seeding `deployment.mode` from posture only when
   unset; explicit mode wins. Any silent-override path? What if posture=production but mode declared
   installed (conflict) — advisory vs error? Is the prototype→installed / production→deployed mapping
   right, or too coupled (a production desktop tool is legitimately installed)?

4. **MCP tool delegation (FR-CDA-5 / OQ-7).** subprocess (matches cap-dev-pipe's returncode+JSON
   Keiyaku) vs in-process call. Fail-closed behavior on a bad project. No reimplementation of coherence.

5. **Readiness vs presence (OQ-6).** Should assess distinguish "deploy declared but not generated"
   from "generated"? Does presence-only mislead an operator?

6. **Determinism / staleness.** assess/wireframe read the manifest + on-disk deploy/ + infra-contract;
   a stale on-disk deploy/ vs current app.yaml could misreport readiness. Guard?

7. **Template/posture coherence.** Kickoff templates explain mode/deploy/environments — do they stay
   consistent with the strict app.yaml grammar (no inputs the parser rejects)?
