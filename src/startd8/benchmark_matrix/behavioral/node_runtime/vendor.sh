#!/usr/bin/env bash
# Vendor the offline Node gRPC runtime for the Track 2 behavioral pilot (FR-T2-DEPS).
#
# Run ONCE (with network) before the behavioral pilot. It populates ./node_modules from the pinned
# package.json + package-lock.json. node_modules is gitignored; the committed package-lock.json is
# the reproducible pin. At pilot time the harness copies this node_modules into each cell workdir so
# the model-generated Node server can `require('@grpc/grpc-js')` with NO network (dep quarantine).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f package-lock.json ]; then
  npm ci            # reproducible install from the committed lockfile
else
  npm install       # first run: resolve + write package-lock.json (commit it afterwards)
fi

echo "Vendored node_modules:"
ls node_modules/@grpc 2>/dev/null || { echo "ERROR: @grpc packages not installed"; exit 1; }
echo "OK — node_modules ready for the behavioral pilot."
