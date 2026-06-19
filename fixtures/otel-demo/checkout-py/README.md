# checkout-py (Step 3g — Role 3 consumer)

Python checkout **consumer** that pins the **email-py** HTTP producer contract via
`prisma/contexts.yaml` (OpenAPI Role 3 M5 cross-repo seam).

**Flow:** PlaceOrder orchestration calls `clients/email_client.py` → `POST /send_order_confirmation`.

**Producer contract:** `../openapi/email.json` (export from email-py):

```bash
cd ../email-py
startd8 generate backend --schema prisma/schema.prisma --out . --api api.yaml \
  --app-manifest app.yaml --export-openapi
cp openapi.json ../openapi/email.json
```

**Consumer codegen:**

```bash
startd8 generate backend --schema prisma/schema.prisma --contexts prisma/contexts.yaml \
  --out . --app-manifest app.yaml
startd8 generate backend --schema prisma/schema.prisma --contexts prisma/contexts.yaml \
  --out . --app-manifest app.yaml --check --gate
```

**Reference:** Go checkout @ otel-demo 2.2.0 (`src/checkout/main.go` — email call path).
