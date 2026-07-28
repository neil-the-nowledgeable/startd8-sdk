# Reflective Requirements — {{scope}}

You are draining a Workflow Loop Queue `reflective-requirements` job.
**Read and follow the full `reflective-requirements` skill** (do not improvise
a shorter loop from this bundle alone). Required phases before stop:

1. Draft requirements (v0.1)
2. Plan implementation
3. Reflect — planning insights vs assumptions
4. Update requirements (v0.2) + plan — include §0 Planning Insights
5. **Phase 4.5 — Lessons-Learned Hardening (v0.3)** — §0.1; consult the
   project's lessons base; record applied lessons or an explicit "checked;
   none applicable"
6. **Phase 4.6 — Design-Principle Hardening (v0.3.1)** — §0.2; consult
   design principles (e.g. `startd8-sdk/docs/design-princples/`); record
   applied principles or an explicit "checked; none applicable"

Do **not** start CRP review (Phase 5) or implementation (Phase 6) in this drain.

## Write targets (absolute)

| Artifact | Path |
|----------|------|
| Requirements | `{{requirements_path}}` |
| Plan | `{{plan_path}}` |

Create or update both markdown files. Prefer the project's existing
requirements/plan shape when present.

## Done when

1. Both paths exist as non-empty `.md` files.
2. Requirements reach **v0.3.1** (or equivalent): §0 Planning Insights,
   §0.1 Lessons-Learned Hardening, §0.2 Design-Principle Hardening present
   (or documented no-op checks), and the plan matches the hardened reqs.
3. You write `drain-result.json` at the path from the Drain Hand-off with
   `ok: true`, `paths_written` exactly matching those two paths, and
   `round_number: 1`.
4. Chat/UI reply is a short confirmation only (paths + that reflective loop
   finished through v0.3.1). Do not paste the full documents into chat.
