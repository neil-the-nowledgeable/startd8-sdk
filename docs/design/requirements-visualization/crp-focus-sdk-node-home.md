# CRP focus — SDK Node Home (Phase 1)

**Least-reviewed target:** the REQ/PLAN pair itself (first CRP; reflective loop only so far).

**Do not re-litigate (settled in REQ §0 / PLAN discoveries):**
- Port ContextCore Node field-compatibly into SDK — do not invent a parallel grammar.
- No second HTML renderer; reuse `wireframe_view` + RenderProfile.
- CLI group is `navigator`, not `nav` (collision with app top-nav).
- startd8 must not import ContextCore (dependency direction).
- FR-6 is **minimal** det-req (NR-8 defers full V-1..V-5).
- Honest-skip via `route_state` / `is_gap` — do not overload app `GAP_STATUSES`.

**Where we need input most:**
1. **Port vs shared package** — copy Node into `startd8.navigator` now, or extract a tiny shared module both repos consume? Architecture risk if fields drift.
2. **extract.py coupling** — import det-req-kit from a filesystem path vs vendoring a thin lives parser vs subprocess — which keeps SCHEMA single-sourced without making SDK depend on a sibling checkout?
3. **WireframeItem additive fields vs companion dict** — frozen dataclass growth vs `attributes`/`node_meta` bag; byte-identity and compose consumers.
4. **CC follow-on** — is "SDK owns Node; CC later imports" an acceptable Phase-1 incomplete state, or must the plan name a CC thin-shim iteration?
