// CORRECT reference PaymentService (Node.js) — the known-good oracle for the charge behavioral
// suite and the Node lane's M0 build/boot target. There was no Node fixture before R3-M0; this is
// the minimal @grpc/grpc-js + @grpc/proto-loader server the containerization milestone needs.
//
// Launched by the Node startup contract (``node server.js`` with ``$PORT`` in the env), it serves
// ``PaymentService.Charge`` over the co-located ``demo.proto`` (loaded by proto-loader — the OB Node
// convention) and binds ``0.0.0.0:$PORT`` so it is reachable when published from a container.
//
// It reuses ONLY the vendored offline closure (``@grpc/grpc-js`` + ``@grpc/proto-loader`` + ``uuid``
// — the exact set ``execute.prepare_node_workdir`` copies), so it builds and boots with NO npm
// install. It implements the Charge ground truth ``run_charge_suite`` asserts:
//   - Luhn-valid card + future expiry → a non-empty, UNIQUE transaction_id (uuid v4).
//   - invalid-Luhn card               → INVALID_ARGUMENT (rejected, no transaction).
//   - expired card                    → INVALID_ARGUMENT (rejected).
//   - non-positive amount / empty card → INVALID_ARGUMENT (hardened-suite invariants).
'use strict';

const path = require('path');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const { v4: uuidv4 } = require('uuid');

// Load the co-located OB contract (proto-loader resolves it from cwd / next to this server — the
// harness stages demo.proto at both conventional locations).
const PROTO_PATH = path.join(__dirname, 'demo.proto');
const packageDef = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const hipstershop = grpc.loadPackageDefinition(packageDef).hipstershop;

// Luhn check digit validation (the suite's _VALID_PAN 4111111111111111 passes, _INVALID_PAN
// 4111111111111112 fails).
function luhnValid(number) {
  const digits = String(number).replace(/\D/g, '');
  if (digits.length < 12) return false;
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i -= 1) {
    let d = Number(digits[i]);
    if (alt) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    alt = !alt;
  }
  return sum % 10 === 0;
}

function charge(call, callback) {
  const req = call.request || {};
  const amount = req.amount || {};
  const card = req.credit_card || {};

  // Non-positive amount → reject (hardened invariant).
  const units = Number(amount.units || 0);
  const nanos = Number(amount.nanos || 0);
  if (units < 0 || (units === 0 && nanos <= 0)) {
    return callback({ code: grpc.status.INVALID_ARGUMENT, message: 'non-positive amount' });
  }

  // Empty / Luhn-invalid card → reject.
  const pan = String(card.credit_card_number || '');
  if (!pan || !luhnValid(pan)) {
    return callback({ code: grpc.status.INVALID_ARGUMENT, message: 'invalid credit card' });
  }

  // Expired card → reject. The suite sends year=2000 for the expired case.
  const year = Number(card.credit_card_expiration_year || 0);
  const month = Number(card.credit_card_expiration_month || 1);
  const now = new Date();
  const expired =
    year < now.getFullYear() ||
    (year === now.getFullYear() && month < now.getMonth() + 1);
  if (expired) {
    return callback({ code: grpc.status.INVALID_ARGUMENT, message: 'card expired' });
  }

  // Valid → a fresh, unique transaction id (uuid v4 → distinct per call, satisfies the hardened
  // uniqueness invariant).
  return callback(null, { transaction_id: uuidv4() });
}

function main() {
  const port = process.env.PORT || '8080';
  const server = new grpc.Server();
  server.addService(hipstershop.PaymentService.service, { Charge: charge });
  // Bind 0.0.0.0 so the port published from a container is reachable from the host.
  server.bindAsync(`0.0.0.0:${port}`, grpc.ServerCredentials.createInsecure(), (err, boundPort) => {
    if (err) {
      console.error(`failed to bind: ${err.message}`);
      process.exit(1);
    }
    console.log(`paymentservice (node reference) listening on ${boundPort}`);
  });
}

main();
