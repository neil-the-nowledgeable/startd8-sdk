# Research Job — {{scope}}

You are draining a Workflow Loop Queue `research` job. Produce durable
findings from the investigation brief. Do **not** start CRP review or
implementation coding unless the brief's deliverables explicitly require a
small spike (and then keep spikes behind flags / gallery toggles).

## Inputs / outputs (absolute)

| Artifact | Path | Role |
|----------|------|------|
| Brief (read; may update status pointer) | `{{brief_path}}` | Investigation brief — trust **code** over stale prose |
| Findings (write) | `{{findings_path}}` | Ranked shortlist, open-question answers, API/spike notes |

Optional focus: `{{focus_file}}`

## Method

1. Read the brief end-to-end; verify claims against the real codebase.
2. Use a few parallel agents when the brief asks for multi-angle research
   (code inventory, candidate scoring, perf, boundary).
3. Write `{{findings_path}}` covering the brief's expected deliverables
   (ranked shortlist, spikes/status, deferred list, open questions).
4. Optionally update the brief's status line to point at the findings doc.
5. Do not invent a new WLQ recipe from inside this drain.

## Done when

1. `{{findings_path}}` exists as a non-empty `.md` file.
2. You write `drain-result.json` at the path from the Drain Hand-off with
   `ok: true`, `paths_written` containing exactly that findings path, and
   `round_number: 1`.
3. Chat/UI reply is a short confirmation only (paths + that research
   finished). Do not paste the full findings into chat.
