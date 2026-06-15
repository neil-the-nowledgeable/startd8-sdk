# Vendored Node gRPC runtime (Track 2 behavioral pilot — FR-T2-DEPS)

Model-generated Node Online Boutique services (e.g. `paymentservice/server.js`) `require`
`@grpc/grpc-js` and `@grpc/proto-loader`. The behavioral harness runs them under a
**no-egress sandbox** (loopback allowed, external network denied — dependency quarantine), so the
deps cannot be fetched at run time. They must be **vendored offline** ahead of the pilot.

## Setup (run once, with network, before the pilot)

```bash
./vendor.sh        # npm ci from the committed package-lock.json (or npm install on first run)
```

This populates `node_modules/` (gitignored). The committed `package.json` + `package-lock.json`
are the reproducible pin.

## How it's used

At pilot time, `behavioral.execute.prepare_node_workdir(workdir)` copies this `node_modules/` and
the benchmark `demo.proto` into each cell's workdir, so the generated server starts fully offline.

## Caveat (pilot-time reconciliation)

The model chooses where it loads the proto from and how it imports gRPC. `prepare_node_workdir`
places `node_modules/` at the workdir root and `demo.proto` at both the workdir root and `protos/`
(the two common conventions). If a generated server references a different path, that cell will
fail readiness and be recorded **degraded** (FR-32) — not scored 0. This is expected partial
coverage in the pilot; see OQ-T2-2.
