# Anti-Pattern: Exploratory Coupling Drift

**Added to Lessons Learned:** 2026-01-26
**Severity:** Medium (recoverable with discipline)
**Domain:** SDK Development, Multi-Package Architecture

---

## The Pattern

When exploring whether two projects should be coupled (e.g., SDK as expansion of a platform vs standalone), development work oscillates between locations without a clear canonical source, leading to:

1. **Scattered artifacts** - Task definitions, dashboards, and code split across repos
2. **Duplicate integration paths** - Multiple ways to do the same thing
3. **Unclear ownership** - "Where does this belong?" questions slow decisions
4. **Merge burden** - Eventually reconciling divergent work

---

## Your Situation

### Two Development Locations

| Location | Purpose | Contents |
|----------|---------|----------|
| `startd8-sdk/` | Main SDK (canonical) | Core SDK, `contextcore-integration/` subfolder, integration code in `src/startd8/integrations/` |
| `contextcore-startd8/` | Separate expansion package | Wrapper code, Grafana dashboards, session logs |

### Scattered Artifacts Found

| Artifact Type | startd8-sdk | contextcore-startd8 |
|--------------|-------------|---------------------|
| Task execution results | `contextcore-integration/*.json` | - |
| Task definitions (YAML) | `scripts/example_tasks.yaml` | - |
| Integration code | `src/startd8/integrations/contextcore.py` | `src/contextcore_startd8/` |
| Grafana dashboards | `dashboards/startd8-metrics.json` | `dashboards/beaver-lead-contractor-progress.json` |
| Session logs | - | `SESSION_LOG.md` |

---

## The Underlying Decision

**Question:** Should the ContextCore integration be:

| Option | Trade-offs |
|--------|------------|
| **(A) Inside startd8-sdk** | Simpler dependency, single repo, but couples SDK to ContextCore |
| **(B) Separate contextcore-startd8 package** | Clean separation, optional dependency, but more repos to maintain |
| **(C) Hybrid** | Integration interfaces in SDK, ContextCore-specific code in separate package |

**Decision (2026-01-28):** **Option A - All inside SDK** selected.

Rationale:
- Simpler single-repo maintenance
- SDK and ContextCore are typically used together
- Reduces context switching during development
- One `pip install` for full functionality

---

## Symptoms of This Anti-Pattern

1. **"Where did I put that?"** - Searching multiple folders for the same type of artifact
2. **Duplicate implementations** - Similar code in both locations
3. **Stale copies** - One location gets updated, the other doesn't
4. **Context switching overhead** - Jumping between repos mid-task
5. **Unclear onboarding** - New contributors don't know which repo to use

---

## Recovery Strategy

### Phase 1: Inventory and Decide (Do This Now)

1. **List all scattered artifacts** (done in this document)
2. **Make the coupling decision** - Pick A, B, or C
3. **Define canonical locations** for each artifact type

### Phase 2: Consolidate

1. **Move artifacts to canonical locations**
2. **Create redirects/symlinks if needed** during transition
3. **Update CLAUDE.md** with clear guidance

### Phase 3: Prevent Recurrence

1. **Add a "Location Decision" section** to task specs
2. **Use a single task registry** (see below)
3. **Document the coupling strategy** in architecture docs

---

## Adopted Architecture (Option A - All Inside SDK)

```
startd8-sdk/                          # Single canonical location
├── src/startd8/
│   ├── integrations/
│   │   ├── __init__.py               # Integration exports
│   │   └── contextcore.py            # ContextCore adapter (full implementation)
│   └── workflows/
│       └── builtin/
│           ├── lead_contractor_workflow.py
│           └── lead_contractor_contextcore_workflow.py  # ContextCore variant
├── dashboards/                       # All Grafana dashboards
│   └── lead-contractor-progress.json # Migrated from contextcore-startd8
└── docs/
    └── PRIME_CONTRACTOR_WORKFLOW_GUIDE.md

contextcore-startd8/                  # DEPRECATED - redirect to startd8-sdk
└── (Consider archiving or making thin re-export wrapper)
```

**Migration Tasks:**
1. ✅ Integration code already in `src/startd8/integrations/`
2. ⏳ MIGRATE-001: Move dashboard to `startd8-sdk/dashboards/`
3. ⏳ SDK-102: Complete MetricsHandler enhancements
4. ⏳ SDK-105: Add integration tests

---

## Checklist for New Work

Before starting work, answer:

- [ ] **Where does this artifact canonically live?** (Check this document)
- [ ] **Am I creating something that already exists elsewhere?**
- [ ] **If I'm exploring a coupling option, have I noted it in a decision log?**
- [ ] **Will someone else know where to find this?**

---

## Related Patterns

- **Monorepo vs Polyrepo** - Architectural decision that prevents this
- **Feature Flags** - Enable coupling exploration without code scatter
- **Strangler Fig** - Gradual migration pattern for consolidation

---

## Tags

`anti-pattern`, `architecture`, `multi-package`, `coupling`, `sdk`, `contextcore`, `validated`
