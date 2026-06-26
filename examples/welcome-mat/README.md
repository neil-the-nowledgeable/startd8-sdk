# Welcome Mat — the SDK's own kickoff, as a generated SDK project

This example dogfoods the **Welcome Mat** (interactive kickoff experience): the kickoff *input UI*
is produced by the deterministic `$0` cascade, and the project is itself kicked off by the SDK.

## What's here (committed source)
- `prisma/schema.prisma` — the kickoff INPUTS modeled as entities (enums → generated dropdowns).
- `docs/kickoff/` — Welcome Mat's **own** kickoff package (inputs + authoring docs) so it can be
  self-kicked-off.
- `export_inputs.py` — maps the generated app's DB rows → `docs/kickoff/inputs/*.yaml` via the
  M6 capture path (allow-listed, comment-preserving, round-trip-gated).

## Generate the deterministic input UI ($0, no LLM)
```bash
startd8 generate backend --schema examples/welcome-mat/prisma/schema.prisma --out <workdir>
cd <workdir> && DATABASE_URL=sqlite:///./wm.db uvicorn app.main:app --port 8770
# → http://127.0.0.1:8770/ui/conventioninput/new   (generated <select> dropdowns)
```

## Close the loop (collected values → kickoff grammar)
```bash
python examples/welcome-mat/export_inputs.py examples/welcome-mat <workdir>/wm.db
```

## Self-kickoff (Welcome Mat kicking off Welcome Mat)
```bash
startd8 kickoff inspect examples/welcome-mat --no-json
```
