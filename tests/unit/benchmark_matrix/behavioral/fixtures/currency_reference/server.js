// CORRECT reference CurrencyService (Node.js) — the known-good oracle for the currency behavioral
// suite and the R3 fleet's currency backend. There was no currency fixture before; this is the
// minimal @grpc/grpc-js + @grpc/proto-loader server the M1 full-fleet (checkout's 6-dep fan-out)
// needs. Mirrors payment_reference/server.js: reuses ONLY the vendored offline closure (grpc-js +
// proto-loader — NO uuid needed here), binds 0.0.0.0:$PORT, builds/boots with no npm install.
//
// Implements the CurrencyService ground truth run_currency_suite asserts (baseline + hardened, all
// rate-independent):
//   - Convert identity: same-currency returns the input unchanged (units/nanos/code).
//   - Convert rejects an unknown ISO-4217 code (INVALID_ARGUMENT).
//   - Convert is deterministic (pure function of input + the fixed rate table).
//   - GetSupportedCurrencies returns a non-empty list.
//   - hardened: zero→zero, nanos in [-1e9, 1e9], nanos sign matches units sign, round-trip ≈ identity.
//
// Conversion uses a fixed EUR-base rate table (so it's deterministic, no external ECB fetch) and
// works in integer nano-units to guarantee the Money normalization invariants. Same-currency is
// special-cased to return the input EXACTLY (the identity/zero invariants need no rounding slack).
'use strict';

const path = require('path');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');

const PROTO_PATH = path.join(__dirname, 'demo.proto');
const packageDef = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true, longs: String, enums: String, defaults: true, oneofs: true,
});
const hipstershop = grpc.loadPackageDefinition(packageDef).hipstershop;

// Fixed EUR-base rates (units of currency per 1 EUR) — a representative ECB-style snapshot. Fixed =
// deterministic + offline. EUR is exactly 1 (the base).
const RATES = {
  EUR: 1.0,
  USD: 1.1305,
  GBP: 0.8618,
  JPY: 126.4,
  CAD: 1.4980,
  TRY: 19.520,
  AUD: 1.6072,
  CHF: 1.1360,
  CNY: 7.5727,
};
// NOTE: must cover the journey's setCurrency whitelist (fleet.journey.CURRENCY_WHITELIST:
// EUR/USD/JPY/CAD/GBP/TRY) so an Adapter-B setCurrency to any whitelisted code succeeds.

const NANOS = 1000000000; // 1e9, as an exact integer

// Normalize a non-negative integer nano-amount into a Money(units, nanos) for `code`.
function toMoney(code, totalNanos) {
  const units = Math.trunc(totalNanos / NANOS);
  const nanos = totalNanos - units * NANOS; // exact remainder; same sign as totalNanos
  return { currency_code: code, units, nanos };
}

function convert(call, callback) {
  const req = call.request || {};
  const fromMoney = req.from || {};
  const fromCode = String(fromMoney.currency_code || '');
  const toCode = String(req.to_code || '');

  // Validate both codes against the table (unknown -> reject, e.g. the suite's "ZZZ").
  if (!(fromCode in RATES) || !(toCode in RATES)) {
    return callback({ code: grpc.status.INVALID_ARGUMENT, message: `unsupported currency code` });
  }

  const units = Number(fromMoney.units || 0);
  const nanos = Number(fromMoney.nanos || 0);
  const totalNanos = units * NANOS + nanos;

  // Identity: same currency returns the input EXACTLY (no rounding slack -> identity & zero->zero).
  if (fromCode === toCode) {
    return callback(null, { currency_code: toCode, units, nanos });
  }

  // Convert via the EUR base, rounding to the nearest nano (integer) -> Money invariants hold.
  const eurNanos = totalNanos / RATES[fromCode];
  const outNanos = Math.round(eurNanos * RATES[toCode]);
  return callback(null, toMoney(toCode, outNanos));
}

function getSupportedCurrencies(call, callback) {
  return callback(null, { currency_codes: Object.keys(RATES) });
}

function main() {
  const port = process.env.PORT || '8080';
  const server = new grpc.Server();
  server.addService(hipstershop.CurrencyService.service, {
    Convert: convert,
    GetSupportedCurrencies: getSupportedCurrencies,
  });
  server.bindAsync(`0.0.0.0:${port}`, grpc.ServerCredentials.createInsecure(), (err, boundPort) => {
    if (err) {
      console.error(`failed to bind: ${err.message}`);
      process.exit(1);
    }
    console.log(`currencyservice (node reference) listening on ${boundPort}`);
  });
}

main();
