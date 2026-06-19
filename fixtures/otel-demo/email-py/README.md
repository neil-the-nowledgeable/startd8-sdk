# email-py (Step 3)

FastAPI HTTP port of `src/email/email_server.rb` with OpenFeature/flagd.

OpenAPI overlay: `api.yaml` (Role 2). Deterministic backend emitted via:

```bash
startd8 generate backend --schema prisma/schema.prisma --out . --api api.yaml --app-manifest app.yaml
startd8 generate backend --schema prisma/schema.prisma --out . --api api.yaml --app-manifest app.yaml --check --gate
```

**Reference:** Ruby Sinatra @ otel-demo 2.2.0
