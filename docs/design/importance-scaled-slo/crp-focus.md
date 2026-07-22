# CRP Focus — Importance-Scaled SLO Thresholds

## Least-reviewed target
Both documents are **brand-new v0.3.1** and have had **no external review** — only the internal
reflective loop (planning + lessons + design-principle hardening). Weight review accordingly.

## Where we most need independent input
1. **OQ-A — the number table.** Are the proposed `(criticality × deployment_mode) → thresholds`
   starting values defensible from an SRE standpoint (`deployed+high → 99.9/300ms`, etc.), and is a
   config-overridable table the right home vs. hardcoding?
2. **OQ-B — should `throughput` scale by importance at all**, or is it a capacity fact that should
   stay flat unless authored?
3. **OQ-C — inference-confidence threshold (FR-5).** Below what confidence should `deployment_mode`
   stay *unset* rather than guess `deployed` (which tightens SLOs)? Conservative vs. eager.
4. **Cross-repo sequencing** (Increment 2 spans ContextCore + startd8-sdk) — is the "SDK reads
   optional field first, ContextCore adds it second" ordering actually decoupled, or is there a
   hidden hard dependency?
5. **Provenance honesty enforcement** — is the `default:importance` tier + no-manifest-write-back
   (FR-3/NR-4) sufficient to keep derived values from masquerading as authored, or is there a leak
   path (e.g. via `load_importance_thresholds` overrides, or downstream re-serialization)?

## Settled — do NOT relitigate (decided in §0 / §0.1 / §0.2)
- **Criticality-first increment split** (FR-8): criticality-scaled defaults ship first (zero
  plumbing); deployment_mode is the second, orthogonal increment. Not up for reordering.
- **Provenance honesty**: derived thresholds live in a distinct `default:importance` tier and are
  **never written back into the manifest** (NR-4). Settled.
- **Single overridable table** (FR-7): one canonical `(criticality, mode) → thresholds` source, not
  scattered per-generator constants. Settled.
- **`deployment.mode` ≠ OTel `deployment_environment`** (NR-2, OQ-5): distinct axes. Settled.
- **Authored thresholds always win** (NR-1): explicit/manifest tiers unchanged. Settled.
- **Reuse `_resolve_threshold`'s existing default tier**, no parallel resolver (Accidental-Complexity
  hardening). Settled.
