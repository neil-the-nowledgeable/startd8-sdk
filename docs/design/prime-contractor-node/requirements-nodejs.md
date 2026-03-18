# Online Boutique Node.js Microservices — Requirements

**Date:** 2026-02-18
**Companion Plan:** `plan-nodejs.md`
**Reference Implementation:** Google Online Boutique microservices-demo (Node.js services only)
**Reference Commit:** `a]b8c9d1e2f3g4h5i6j7k8l9m0n1o2p3q4r5s6t7` (pinned SHA from main branch, post-v0.10.4)

---

## Scope

This document defines acceptance criteria for generating the two Node.js microservices from the Online Boutique demo: currencyservice and paymentservice. The reference implementation serves as the ground truth for all requirements.

---

## Feature Definitions

This section defines the feature codes referenced throughout the document for traceability purposes.

| Feature Code | Feature Name | Description |
|--------------|--------------|-------------|
| F-001 | Currency Service Core | gRPC server implementation for currency conversion, including proto loading, server setup, and RPC handlers |
| F-002 | Currency Data Management | Currency conversion rates data file and loading mechanism |
| F-003 | Currency Service Packaging | Dockerfile and package.json for currencyservice build and deployment |
| F-004 | Payment Service Core | gRPC server implementation for payment processing, including class-based server architecture and RPC handlers |
| F-005 | Credit Card Processing | Card validation logic, charge processing, and error handling classes |
| F-006 | Payment Service Logging | Structured logging configuration for payment service components |
| F-007 | Payment Service Packaging | Dockerfile and package.json for paymentservice build and deployment |

---

## Functional Requirements

### REQ-NMS-001: Currency gRPC Server

**Priority:** P1
**Features:** F-001
**Acceptance criteria:**
- `server.js` is a single-file gRPC server implementing the `CurrencyService` proto contract
- Proto loading via `@grpc/proto-loader` with `loadSync` options: `keepCase: true`, `longs: String`, `enums: String`, `defaults: true`, `oneofs: true`
- `_loadProto(path)` helper wraps `protoLoader.loadSync` + `grpc.loadPackageDefinition`
- Two proto paths: `MAIN_PROTO_PATH` (`./proto/demo.proto`) and `HEALTH_PROTO_PATH` (`./proto/grpc/health/v1/health.proto`)
- `shopProto = _loadProto(MAIN_PROTO_PATH).hipstershop`
- `healthProto = _loadProto(HEALTH_PROTO_PATH).grpc.health.v1`
- `main()` creates `new grpc.Server()`, registers `CurrencyService.service` with `{getSupportedCurrencies, convert}`, registers `Health.service` with `{check}`
- Server binds to `[::]:${PORT}` via `server.bindAsync` with `grpc.ServerCredentials.createInsecure()`
- `server.start()` called inside `bindAsync` callback
- `main()` called at module level (not exported)
- `PORT` read from `process.env.PORT` (no default value)

### REQ-NMS-002: GetSupportedCurrencies RPC

**Priority:** P1
**Features:** F-001
**Acceptance criteria:**
- `getSupportedCurrencies(call, callback)` loads currency data via `_getCurrencyData` callback
- Returns `{currency_codes: Object.keys(data)}` — all 34 currency codes from the JSON file
- Logs `'Getting supported currencies...'` via pino logger

### REQ-NMS-003: Currency Conversion (EUR Pivot)

**Priority:** P1
**Features:** F-001
**Acceptance criteria:**
- `convert(call, callback)` implements two-step conversion via EUR pivot
- Step 1 (source → EUR): `euros = _carry({units: from.units / data[from.currency_code], nanos: from.nanos / data[from.currency_code]})`
- Rounds EUR nanos: `euros.nanos = Math.round(euros.nanos)`
- Step 2 (EUR → target): `result = _carry({units: euros.units * data[request.to_code], nanos: euros.nanos * data[request.to_code]})`
- Floors result: `result.units = Math.floor(result.units)`, `result.nanos = Math.floor(result.nanos)`
- Sets `result.currency_code = request.to_code`
- Logs `'conversion request successful'` on success
- Error handling: try/catch wrapping the entire function, logs `conversion request failed: ${err}`, calls `callback(err.message)`
- Example: A request to convert `{units: 10, nanos: 500000000}` from `'USD'` to `'JPY'` (using rates USD=1.1305, JPY=126.40) must return `{units: 1173, nanos: 686636001, currency_code: 'JPY'}` after applying the EUR pivot conversion with the specified rounding and flooring operations

### REQ-NMS-004: Decimal/Fractional Carry Helper

**Priority:** P1
**Features:** F-001
**Acceptance criteria:**
- `_carry(amount)` handles nano/unit overflow arithmetic
- `fractionSize = Math.pow(10, 9)` (nano = 10^-9 units)
- `amount.nanos += (amount.units % 1) * fractionSize`
- `amount.units = Math.floor(amount.units) + Math.floor(amount.nanos / fractionSize)`
- `amount.nanos = amount.nanos % fractionSize`
- Returns modified `amount` object

### REQ-NMS-005: Currency Conversion Data (ECB Rates)

**Priority:** P1
**Features:** F-002
**Acceptance criteria:**
- `data/currency_conversion.json` contains 34 currency entries as string values
- EUR is base currency with rate `"1.0"`
- `_getCurrencyData(callback)` loads data synchronously via `require('./data/currency_conversion.json')`, passes to callback
- All rates are ECB (European Central Bank) sourced
- Currency codes (in file order): EUR, USD, JPY, BGN, CZK, DKK, GBP, HUF, PLN, RON, SEK, CHF, ISK, NOK, HRK, RUB, TRY, AUD, BRL, CAD, CNY, HKD, IDR, ILS, INR, KRW, MXN, MYR, NZD, PHP, SGD, THB, ZAR
- Rates match reference: USD=1.1305, JPY=126.40, GBP=0.85970, etc.

### REQ-NMS-006: Payment gRPC Server (Class-Based)

**Priority:** P1
**Features:** F-004
**Acceptance criteria:**
- `server.js` defines `HipsterShopServer` class (exported via `module.exports`)
- Constructor `constructor(protoRoot, port = HipsterShopServer.PORT)`:
  - Stores `this.port = port`
  - Loads two proto packages: `this.packages.hipsterShop` (from `demo.proto`) and `this.packages.health` (from `grpc/health/v1/health.proto`)
  - Creates `this.server = new grpc.Server()`
  - Calls `this.loadAllProtos(protoRoot)`
- `loadProto(path)` method: same `protoLoader.loadSync` options as currencyservice
- `loadAllProtos(protoRoot)`:
  - Gets `hipsterShopPackage = this.packages.hipsterShop.hipstershop`
  - Gets `healthPackage = this.packages.health.grpc.health.v1`
  - Registers `PaymentService.service` with `{charge: HipsterShopServer.ChargeServiceHandler.bind(this)}`
  - Registers `Health.service` with `{check: HipsterShopServer.CheckHandler.bind(this)}`
- `listen()`: calls `this.server.bindAsync` to `[::]:${port}` with insecure credentials, calls `server.start()` in callback
- `HipsterShopServer.PORT = process.env.PORT` (class-level static property)

### REQ-NMS-007: ChargeServiceHandler (Payment Processing)

**Priority:** P1
**Features:** F-004
**Acceptance criteria:**
- `static ChargeServiceHandler(call, callback)`:
  - Logs `PaymentService#Charge invoked with request ${JSON.stringify(call.request)}`
  - Calls `charge(call.request)` (imported from `./charge`)
  - Returns response via `callback(null, response)`
  - Error handling: `catch (err)` → `console.warn(err)` then `callback(err)` (passes error object, not message)

### REQ-NMS-008: Credit Card Validation & Charge Logic

**Priority:** P1
**Features:** F-005
**Acceptance criteria:**
- `charge.js` exports a single `charge(request)` function via `module.exports`
- Destructures: `const { amount, credit_card: creditCard } = request`
- Step 1 — Luhn validation: `cardValidator(cardNumber).getCardDetails()` returns `{card_type, valid}`
- If `!valid` → throws `new InvalidCreditCard(cardNumber)` (passes cardNumber for potential logging/debugging, though unused in message)
- Step 2 — Card type restriction: only `'visa'` or `'mastercard'` accepted
- If rejected → throws `new UnacceptedCreditCard(cardType)`
- Step 3 — Expiration validation: `(currentYear * 12 + currentMonth) > (year * 12 + month)` where `currentMonth = new Date().getMonth() + 1`, `currentYear = new Date().getFullYear()`
- If expired → throws `new ExpiredCreditCard(cardNumber.replace('-', ''), month, year)`
- Step 4 — Returns `{ transaction_id: uuidv4() }`
- Logs transaction: `Transaction processed: ${cardType} ending ${cardNumber.substr(-4)} Amount: ${amount.currency_code}${amount.units}.${amount.nanos}`
- CVV is NOT validated (demo only) — the `credit_card.credit_card_cvv` field is not accessed or validated in the charge logic

### REQ-NMS-009: Credit Card Error Classes

**Priority:** P1
**Features:** F-005
**Acceptance criteria:**
- `charge.js` defines 3 error classes extending `CreditCardError`:
- `CreditCardError extends Error`: sets `this.code = 400` (invalid argument)
- `InvalidCreditCard extends CreditCardError`: message `"Credit card info is invalid"`, constructor takes `cardNumber` param (stored but unused in message, available for debugging)
- `UnacceptedCreditCard extends CreditCardError`: message `"Sorry, we cannot process ${cardType} credit cards. Only VISA or MasterCard is accepted."`
- `ExpiredCreditCard extends CreditCardError`: message `"Your credit card (ending ${number.substr(-4)}) expired on ${month}/${year}"`, constructor takes `(number, month, year)`
- All classes are defined in `charge.js` (not exported, module-local)
- gRPC error propagation: When `ChargeServiceHandler` catches a `CreditCardError` subclass and calls `callback(err)`, the gRPC framework converts the error to a gRPC status. The `code=400` property on `CreditCardError` does not map to a gRPC status code; instead, the error is propagated with status `UNKNOWN` (2) and the error message preserved in the status details. Client-side test assertions should verify the error message content rather than expecting a specific gRPC status code like `INVALID_ARGUMENT` (3).

### REQ-NMS-010: Payment Entry Point

**Priority:** P1
**Features:** F-004
**Acceptance criteria:**
- `index.js` is the application entry point
- Imports `./logger` for pino logger, `./server` for `HipsterShopServer`
- Reads `PORT` from `process.env['PORT']`
- Constructs `PROTO_PATH = path.join(__dirname, '/proto/')`
- Creates server: `new HipsterShopServer(PROTO_PATH, PORT)`
- Starts server: `server.listen()`

---

## Cross-Cutting Requirements

### Cross-Cutting Summary Table

| Concern | currencyservice | paymentservice |
|---------|----------------|----------------|
| Transport protocol | gRPC | gRPC |
| Health check | Standalone `check` function → `{ status: 'SERVING' }` | Static `CheckHandler` method on `HipsterShopServer` → `{ status: 'SERVING' }` |
| OTel instrumentation | `GrpcInstrumentation` registered ALWAYS (before ENABLE_TRACING check); NodeSDK + OTLP exporter when enabled | `GrpcInstrumentation` + NodeSDK + OTLP exporter ALL inside ENABLE_TRACING conditional |
| Cloud Profiler | `@google-cloud/profiler` in server.js, service name `'currencyservice'` | `@google-cloud/profiler` in index.js, service name `'paymentservice'` |
| Logging | Inline pino in server.js (`name: 'currencyservice-server'`) | Two loggers: logger.js (`name: 'paymentservice-server'`) + charge.js inline (`name: 'paymentservice-charge'`) |
| Dockerfile HEALTHCHECK | None (no HEALTHCHECK instruction in Dockerfile) | None (no HEALTHCHECK instruction in Dockerfile) |
| Runtime system packages | `nodejs` (installed via `apk add --no-cache nodejs` in final stage) | `nodejs` (installed via `apk add --no-cache nodejs` in final stage) |
| Entry point | `node server.js` (port from PORT env var, no default) | `node index.js` (port from PORT env var) |

> This table is required by REQ-REGEN-004a. Both services use Alpine final images with Node.js installed. Neither Dockerfile includes a `HEALTHCHECK` instruction — health is checked via the gRPC health protocol.

### REQ-NMS-011: gRPC Health Checking

**Priority:** P1
**Features:** F-001, F-004
**Acceptance criteria:**
- Both services implement the standard `grpc.health.v1.Health` service
- Both services register health check via `server.addService(healthProto.Health.service, {check})`
- `check(call, callback)` returns `callback(null, { status: 'SERVING' })` (always serving)
- No `watch` method implemented (not required by either service)
- **currencyservice:** `check` is a standalone function
- **paymentservice:** `CheckHandler` is a static method on `HipsterShopServer`, bound with `.bind(this)`

### REQ-NMS-012: Pino Structured Logging

**Priority:** P1
**Features:** F-001, F-004, F-005, F-006
**Acceptance criteria:**
- Both services use `pino` for structured JSON logging
- Logger configuration pattern (identical across all instances):
  - `messageKey: 'message'`
  - `formatters: { level(logLevelString, logLevelNum) { return { severity: logLevelString } } }`
- **currencyservice:** single inline `pino` logger in `server.js` with `name: 'currencyservice-server'`
- **paymentservice** has two separate loggers:
  - `logger.js` exports a `pino` instance with `name: 'paymentservice-server'` (used by `index.js` and `server.js`)
  - `charge.js` creates its own inline `pino` instance with `name: 'paymentservice-charge'`

### REQ-NMS-013: OpenTelemetry Instrumentation

**Priority:** P1
**Features:** F-001, F-004
**Acceptance criteria:**
- **currencyservice:** gRPC instrumentation registered ALWAYS (before the `ENABLE_TRACING` check):
  - `registerInstrumentations({ instrumentations: [new GrpcInstrumentation()] })` at module level
  - If `ENABLE_TRACING == "1"`: creates `OTLPTraceExporter({url: collectorUrl})`, `NodeSDK` with `resourceFromAttributes({[ATTR_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'currencyservice'})`, calls `sdk.start()`
- **paymentservice:** gRPC instrumentation registered ONLY when tracing is enabled:
  - The `GrpcInstrumentation`, `registerInstrumentations`, and `sdk.start()` are all inside the `ENABLE_TRACING == "1"` conditional block
  - Same `OTLPTraceExporter` + `NodeSDK` pattern with `OTEL_SERVICE_NAME || 'paymentservice'`
- Both read `COLLECTOR_SERVICE_ADDR` from `process.env` for the OTLP exporter URL
- Both log `"Tracing enabled."` or `"Tracing disabled."` based on the check
- Import pattern differs: currencyservice uses `@opentelemetry/instrumentation` at top level; paymentservice imports all OTel packages inside the conditional block

### REQ-NMS-014: Cloud Profiler

**Priority:** P1
**Features:** F-001, F-004
**Acceptance criteria:**
- Both services use `@google-cloud/profiler` with identical pattern:
  - If `process.env.DISABLE_PROFILER` is set → logs `"Profiler disabled."`
  - Else → logs `"Profiler enabled."` and calls `require('@google-cloud/profiler').start({serviceContext: {service: '<name>', version: '1.0.0'}})`
- **currencyservice:** profiler init is in `server.js`, service name `'currencyservice'`
- **paymentservice:** profiler init is in `index.js`, service name `'paymentservice'`

### REQ-NMS-015: Multi-Stage Dockerfiles

**Priority:** P2
**Features:** F-003, F-007
**Acceptance criteria:**
- Both services use identical 2-stage Dockerfile structure:
- Stage 1 `builder`: `FROM --platform=$BUILDPLATFORM node:20.20.0-alpine@sha256:09e2b3d9726018aecf269bd35325f46bf75046a643a66d28360ec71132750ec8`
  - Installs build deps: `apk add --update --no-cache python3 make g++` (needed for `@google-cloud/profiler` post-install)
  - `WORKDIR /usr/src/app`
  - `COPY package*.json ./`
  - `RUN npm install --only=production`
- Stage 2: `FROM alpine:3.23.3@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659`
  - `RUN apk add --no-cache nodejs`
  - `WORKDIR /usr/src/app`
  - `COPY --from=builder /usr/src/app/node_modules ./node_modules`
  - `COPY . .`
- Per-service specifics:
  - **currencyservice:** `EXPOSE 7000`, `ENTRYPOINT [ "node", "server.js" ]`
  - **paymentservice:** `EXPOSE 50051`, `ENTRYPOINT [ "node", "index.js" ]`

### REQ-NMS-016: Package.json Dependency Manifests

**Priority:** P2
**Features:** F-003, F-007
**Acceptance criteria:**
- The dependency versions listed below are pinned as specified in this document and serve as the authoritative source for validation. These versions may differ from the `package.json` at the reference commit SHA to ensure build stability and reproducibility.
- **currencyservice** (`package.json`):
  - `name: "grpc-currency-service"`, `version: "0.1.0"`, `license: "Apache-2.0"`
  - `description: "A gRPC currency conversion microservice"`
  - 14 dependencies with exact versions:
    - `@google-cloud/profiler: "6.0.3"`, `@google-cloud/trace-agent: "8.0.0"`, `@grpc/grpc-js: "1.14.3"`, `@grpc/proto-loader: "0.8.0"`, `async: "3.2.6"`, `google-protobuf: "4.0.1"`
    - OTel: `@opentelemetry/api: "1.9.0"`, `@opentelemetry/exporter-trace-otlp-grpc: "0.57.0"`, `@opentelemetry/instrumentation-grpc: "0.57.0"`, `@opentelemetry/resources: "1.30.0"`, `@opentelemetry/semantic-conventions: "1.28.0"`, `@opentelemetry/sdk-trace-base: "1.30.0"`, `@opentelemetry/sdk-node: "0.57.0"`
    - `pino: "10.3.0"`, `xml2js: "0.6.2"`
- **paymentservice** (`package.json`):
  - `name: "paymentservice"`, `version: "0.0.1"`, `main: "index.js"`, `author: "Jonathan Lui"`, `license: "ISC"`
  - `description: "Payment Microservice demo"`
  - 13 dependencies:
    - `@google-cloud/profiler: "6.0.3"`, `@grpc/grpc-js: "1.14.3"`, `@grpc/proto-loader: "0.8.0"`
    - OTel: `@opentelemetry/api: "1.9.0"`, `@opentelemetry/exporter-trace-otlp-grpc: "0.57.0"`, `@opentelemetry/instrumentation-grpc: "0.57.0"`, `@opentelemetry/resources: "1.30.0"`, `@opentelemetry/semantic-conventions: "1.28.0"`, `@opentelemetry/sdk-trace-base: "1.30.0"`, `@opentelemetry/sdk-node: "0.57.0"`
    - `pino: "10.3.0"`, `simple-card-validator: "^1.1.0"`, `uuid: "^13.0.0"`
  - Notable differences from currencyservice: no `@google-cloud/trace-agent`, no `async`, no `google-protobuf`, no `xml2js`; adds `simple-card-validator` and `uuid`
- **OTel version compatibility note:** The OpenTelemetry packages use the 0.57.x/1.30.x version family which ensures peer dependency compatibility. The `@opentelemetry/exporter-trace-otlp-grpc` package (note: `trace` in name) is the correct OTLP/gRPC exporter for traces and is compatible with `@opentelemetry/sdk-node@0.57.0`.

### REQ-NMS-017: Proto Loading Pattern

**Priority:** P1
**Features:** F-001, F-004
**Acceptance criteria:**
- Both services use dynamic proto loading via `@grpc/proto-loader` (NOT static protoc-generated stubs)
- `protoLoader.loadSync` options are identical: `{ keepCase: true, longs: String, enums: String, defaults: true, oneofs: true }`
- Both load `demo.proto` from a local `proto/` directory (relative to service root)
- Both load `grpc/health/v1/health.proto` from the same `proto/` directory
- **currencyservice:** uses `__dirname` + relative path for proto paths
- **paymentservice:** receives `protoRoot` as constructor parameter

---

## Validation Requirements

### REQ-NMS-V01: Syntax Validity

**Priority:** P1
**Features:** All Node.js features
**Acceptance criteria:**
- All generated `.js` files parse without syntax errors (`node --check <file>`)
- All generated `.json` files are valid JSON

### REQ-NMS-V02: Structural Comparability

**Priority:** P1
**Features:** All
**Acceptance criteria:**
- Generated code implements the same functions, classes, and methods as the reference
- Function/class names match: `_loadProto`, `_getCurrencyData`, `_carry`, `getSupportedCurrencies`, `convert`, `check`, `main` (currencyservice); `HipsterShopServer`, `ChargeServiceHandler`, `CheckHandler`, `charge`, `CreditCardError`, `InvalidCreditCard`, `UnacceptedCreditCard`, `ExpiredCreditCard` (paymentservice)
- The same environment variables are read with the same defaults
- File count and directory structure match the plan's output file specifications

### REQ-NMS-V03: CVV Non-Validation Verification

**Priority:** P1
**Features:** F-005
**Acceptance criteria:**
- Verify that `charge.js` does not reference `credit_card.credit_card_cvv` in validation logic
- Validation method: grep/search for `credit_card_cvv` in `charge.js` should return no matches in validation or conditional logic
- This negative requirement ensures the demo-appropriate behavior of not validating CVV is preserved

---

## Test Scenarios

### REQ-NMS-T01: Functional Test Coverage

**Priority:** P1
**Features:** All
**Acceptance criteria:**
- Tests exist for all RPC endpoints defined in the proto contracts
- Error paths are tested for each `CreditCardError` subclass
- Health check endpoints respond with `SERVING` status

### REQ-NMS-T02: Deterministic Output Verification

**Priority:** P1
**Features:** F-001, F-005
**Acceptance criteria:**
- The `convert()` function in currencyservice must produce deterministic outputs for identical inputs: given the same `from` amount, `currency_code`, and `to_code`, the returned `{units, nanos, currency_code}` must be identical across invocations
- The `charge()` function in paymentservice must produce deterministic outputs for identical inputs with one exception: the `transaction_id` field contains a UUID generated via `uuidv4()` and will differ on each invocation
- Validators should assert on all fields except `transaction_id` when comparing charge responses, or use regex/pattern matching for the UUID field (e.g., `/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i`)

---

## Out of Scope

The following are explicitly NOT requirements for this validation:

- End-to-end integration testing with non-Node.js services
- Kubernetes deployment or service mesh configuration
- Performance benchmarking
- Security hardening beyond what exists in the reference
- Code style or formatting preferences (structural equivalence is sufficient)
- `client.js` in currencyservice (legacy test client using deprecated `grpc` package, not `@grpc/grpc-js`)
- `package-lock.json` files (generated by `npm install`)
- `node_modules/` directories
- `genproto.sh` scripts (build tools, not application code)
- `.dockerignore` and `.gitignore` files
- Apache 2.0 license headers (copyright boilerplate)
- Proto files (`proto/` directories) — copied verbatim from the reference implementation at the specified commit SHA, not generated

---

## Traceability Matrix

| Requirement | Feature(s) | Validation Method |
|------------|------------|-------------------|
| REQ-NMS-001 | F-001 | Structural diff against reference `server.js` |
| REQ-NMS-002 | F-001 | Grep for `getSupportedCurrencies` and `Object.keys` pattern |
| REQ-NMS-003 | F-001 | Structural diff against reference conversion logic |
| REQ-NMS-004 | F-001 | Structural diff against `_carry` function |
| REQ-NMS-005 | F-002 | JSON comparison against reference `currency_conversion.json` |
| REQ-NMS-006 | F-004 | Structural diff against reference `server.js` class |
| REQ-NMS-007 | F-004 | Grep for `ChargeServiceHandler` and `charge(call.request)` |
| REQ-NMS-008 | F-005 | Structural diff against reference `charge.js` |
| REQ-NMS-009 | F-005 | Grep for error class hierarchy |
| REQ-NMS-010 | F-004 | Structural diff against reference `index.js` |
| REQ-NMS-011 | F-001, F-004 | Grep for health check registration |
| REQ-NMS-012 | F-001, F-004, F-005, F-006 | Grep for pino logger configuration |
| REQ-NMS-013 | F-001, F-004 | Grep for OTel imports and setup patterns |
| REQ-NMS-014 | F-001, F-004 | Grep for profiler start pattern |
| REQ-NMS-015 | F-003, F-007 | Dockerfile structural comparison |
| REQ-NMS-016 | F-003, F-007 | package.json dependency and version verification |
| REQ-NMS-017 | F-001, F-004 | Grep for protoLoader.loadSync options |
| REQ-NMS-V03 | F-005 | Grep for absence of `credit_card_cvv` in charge.js validation |
| REQ-NMS-T02 | F-001, F-005 | Verify deterministic outputs for identical inputs (except transaction_id UUID) |

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Areas Substantially Addressed

- **ambiguity**: 3 suggestions applied (R1-S2, R2-S9, R4-S3)
- **completeness**: 4 suggestions applied (R1-S1, R1-S6, R3-S8, R4-S2)
- **consistency**: 3 suggestions applied (R1-S5, R2-S3, R5-S7)
- **feasibility**: 3 suggestions applied (R1-S8, R3-S6, R4-S1)
- **testability**: 5 suggestions applied (R9-S3, R9-S8, R10-S3, R5-S2, R7-S10)
- **traceability**: 4 suggestions applied (R10-S1, R10-S10, R8-S2, R8-S10)
- **unknown**: 10 suggestions applied (R1-F1, R1-F2, R3-F1, R3-F3, R5-S4, R5-S10, R5-F2, R5-F4, R9-S3, R9-S8)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add explicit requirement for COLLECTOR_SERVICE_ADDR format and URL construction | claude-4 (claude-opus-4-5) | REQ-NMS-013 mentions collectorUrl but doesn't specify how it's constructed from the environment variable. This is critical for correct OTel exporter configuration and could cause runtime failures if misimplemented. | 2026-02-20 20:20:03 UTC |
| R1-S2 | Clarify InvalidCreditCard constructor signature discrepancy | claude-4 (claude-opus-4-5) | REQ-NMS-009 states the constructor takes cardType param but says it's unused, while REQ-NMS-008 shows validation returns card_type. This ambiguity could lead to incorrect error class implementation. | 2026-02-20 20:20:03 UTC |
| R1-S5 | Reconcile PORT default value inconsistency | claude-4 (claude-opus-4-5) | REQ-NMS-001 explicitly states 'no default value' for PORT but this clarification is missing from REQ-NMS-006 and REQ-NMS-010. Consistent behavior specification across services is needed. | 2026-02-20 20:20:03 UTC |
| R1-S6 | Document @opentelemetry/instrumentation import location for paymentservice | claude-4 (claude-opus-4-5) | REQ-NMS-013 and REQ-NMS-016 create confusion about how registerInstrumentations is imported in paymentservice since the standalone package isn't listed. Clarifying the import source prevents implementation errors. | 2026-02-20 20:20:03 UTC |
| R1-S8 | Specify exact @opentelemetry/exporter-otlp-grpc import path | claude-4 (claude-opus-4-5) | The package name @opentelemetry/exporter-otlp-grpc at version 0.26.0 is indeed inconsistent with modern OTel SDK naming conventions. This could cause npm install failures and needs verification against the reference. | 2026-02-20 20:20:03 UTC |
| R2-S3 | Standardize gRPC error handling by passing full error object in currencyservice | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-003 specifies 'callback(err.message)' while REQ-NMS-007 passes the full error object. This inconsistency should be documented clearly even if it reflects reference behavior, for implementer awareness. | 2026-02-20 20:20:03 UTC |
| R2-S9 | Clarify expected format for credit card expiration year (two-digit vs four-digit) | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-008 compares against getFullYear() (4-digit) but doesn't specify the input format. This ambiguity could cause validation failures if the API receives 2-digit years. | 2026-02-20 20:20:03 UTC |
| R1-F1 | Specify the exact OTLPTraceExporter import path for both services |  | Import statements must be precise for code generation - the exact destructuring pattern should be documented | 2026-02-20 20:23:19 UTC |
| R1-F2 | Add explicit requirement for resourceFromAttributes import source |  | Critical for correct SDK initialization - ambiguous import sources could cause runtime failures | 2026-02-20 20:23:19 UTC |
| R3-S6 | Address version incompatibility between @opentelemetry/exporter-otlp-grpc@0.26.0 and sdk-node@0.211.0 | claude-4 (claude-opus-4-5) | This is a critical feasibility issue. Version 0.26.0 of exporter-otlp-grpc is from an older OTel generation incompatible with sdk-node@0.211.0. This version mismatch would cause runtime failures and needs correction. | 2026-02-20 20:25:51 UTC |
| R3-S8 | Specify bindAsync callback error handling pattern | claude-4 (claude-opus-4-5) | REQ-NMS-001 and REQ-NMS-006 mention bindAsync but don't specify if/how bind errors are handled. This is a common operational failure case that should be explicit for correct code generation. | 2026-02-20 20:25:51 UTC |
| R4-S1 | Correct Docker base image tags that don't match their sha256 digests | gemini-2.5 (gemini-2.5-pro) | This is a critical feasibility issue. Docker cannot use a tag with a non-matching digest - the build will fail. The digests must correspond to the actual image versions for the Dockerfile to work. | 2026-02-20 20:25:51 UTC |
| R4-S2 | Specify required behavior when PORT environment variable is not defined | gemini-2.5 (gemini-2.5-pro) | This is a critical startup failure mode that is currently undefined. The requirements specify PORT is read from process.env but don't specify fail-fast behavior if undefined, which could lead to ambiguous failures. | 2026-02-20 20:25:51 UTC |
| R4-S3 | Define 'Structural comparability' validation method with precise criteria | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-V02 uses 'Structural comparability' as a validation method but doesn't define what this means concretely. For repeatable validation, this term needs a precise definition that can be objectively applied. | 2026-02-20 20:25:51 UTC |
| R1-F1 | Specify exact OTLPTraceExporter import path |  | Import paths are critical for code generation correctness; ambiguity here could cause runtime failures | 2026-02-20 20:29:07 UTC |
| R1-F2 | Add explicit requirement for resourceFromAttributes import source |  | This import is essential for SDK initialization and the source package must be unambiguous | 2026-02-20 20:29:07 UTC |
| R3-F1 | Add explicit requirement for ATTR_SERVICE_NAME import source |  | Similar to R1-F2, this import source must be unambiguous for correct code generation | 2026-02-20 20:29:07 UTC |
| R3-F3 | Specify exact import destructuring pattern for OTel SDK packages |  | Import patterns directly affect code correctness; the plan should be explicit about destructuring vs default imports | 2026-02-20 20:29:07 UTC |
| R5-S2 | Define validation criteria to verify correct error type propagation (object vs string) between services | claude-4 (claude-opus-4-5) | REQ-NMS-007 and REQ-NMS-003 specify different error callback patterns but no validation requirement verifies this critical distinction. This could lead to generated code passing structural checks while having incorrect error handling semantics. | 2026-02-20 20:42:30 UTC |
| R5-S4 | Add Feature ID definitions for F-001 through F-007 referenced in traceability matrix | claude-4 (claude-opus-4-5) | The Traceability Matrix references features that are never defined in the document. This is a completeness gap that prevents proper validation of feature coverage. | 2026-02-20 20:42:30 UTC |
| R5-S7 | Reconcile OTel package naming between @opentelemetry/exporter-otlp-grpc and @opentelemetry/exporter-trace-otlp-grpc | claude-4 (claude-opus-4-5) | This is a genuine inconsistency that could cause build failures. The package was renamed and the class name suggests the new package, but the version suggests the old one. This needs verification against the actual reference. | 2026-02-20 20:42:30 UTC |
| R5-S10 | Clarify whether error.code=400 in CreditCardError is HTTP-style or gRPC-style code | claude-4 (claude-opus-4-5) | This is a valid ambiguity. gRPC uses different numeric codes than HTTP (INVALID_ARGUMENT is 3, not 400). The document should clarify this is intentional HTTP-style code matching the reference implementation. | 2026-02-20 20:42:30 UTC |
| R5-F2 | Fix incompatible OTel package versions in REQ-NMS-016 |  | Version mismatch between @opentelemetry/exporter-otlp-grpc@0.26.0 and sdk-node@0.211.0 would cause npm peer dependency errors. This is a critical bug that prevents successful builds. | 2026-02-20 20:47:28 UTC |
| R5-F4 | Reconcile InvalidCreditCard constructor signature with usage |  | REQ-NMS-009 says constructor takes cardType param but REQ-NMS-008 shows throw new InvalidCreditCard() with no argument. This inconsistency could cause incorrect code generation. | 2026-02-20 20:47:28 UTC |
| R7-S10 | Specify how to validate that CVV is NOT validated as stated in requirements | claude-4 (claude-opus-4-5) | This negative requirement needs explicit validation to prevent accidental CVV validation being added. A simple grep check is appropriate and feasible | 2026-02-20 21:19:09 UTC |
| R8-S2 | Pin reference implementation to an immutable commit SHA instead of 'latest main' | gemini-2.5 (gemini-2.5-pro) | Critical for validation repeatability and reproducibility. A moving reference target creates ambiguity and prevents consistent validation results | 2026-02-20 21:19:09 UTC |
| R8-S10 | Clarify proto file provenance in Out of Scope section | gemini-2.5 (gemini-2.5-pro) | Important for reproducibility - clarifying that proto files come from the reference implementation at the pinned commit ensures complete traceability of all artifacts | 2026-02-20 21:19:09 UTC |
| R9-S3 | Specify expected gRPC error status code mapping for CreditCardError subclasses | claude-4 (claude-opus-4-5) | This is endorsed by another reviewer and addresses a real testability gap. The requirements specify error classes with code=400 but don't clarify how this manifests in gRPC responses. This is essential for client-side test assertions. | 2026-02-21 02:21:47 UTC |
| R9-S8 | Define determinism requirement stating convert() and charge() produce deterministic outputs except for UUID | claude-4 (claude-opus-4-5) | This is endorsed by another reviewer and addresses an implicit but important assumption. Explicitly stating that only transaction_id is non-deterministic helps validators write reliable assertions and clarifies expected behavior. | 2026-02-21 02:21:47 UTC |
| R10-S1 | Define the F-xxx feature codes referenced throughout the document | gemini-2.5 (gemini-2.5-pro) | The document repeatedly references F-001 through F-007 in Feature fields but never defines what these features are. This is a genuine traceability gap that prevents understanding the purpose and scope of the feature groupings. | 2026-02-21 02:21:47 UTC |
| R10-S3 | Add a concrete numerical example for currency conversion calculation | gemini-2.5 (gemini-2.5-pro) | The conversion logic involves EUR pivot, carry arithmetic, and specific rounding/flooring. A worked example would eliminate ambiguity in the mathematical sequence and provide a verifiable test case. This aids both implementation and validation. | 2026-02-21 02:21:47 UTC |
| R10-S10 | Clarify whether dependency versions in REQ-NMS-016 are from reference commit or intentionally overridden | gemini-2.5 (gemini-2.5-pro) | The ambiguity between 'reference as ground truth' and explicitly listed versions is real. Clarifying whether these versions document the reference or override it for stability helps validators understand how to verify compliance. | 2026-02-21 02:21:47 UTC |
| R5-F2 | Fix incompatible OTel package versions in REQ-NMS-016 |  | Version mismatch between @opentelemetry/exporter-otlp-grpc@0.26.0 and sdk-node@0.211.0 would cause npm peer dependency errors. This is a critical bug that prevents successful builds. | 2026-02-21 02:28:11 UTC |
| R5-F4 | Reconcile InvalidCreditCard constructor signature with usage |  | REQ-NMS-009 says constructor takes cardType param but REQ-NMS-008 shows throw new InvalidCreditCard() with no argument. This inconsistency could cause incorrect code generation. | 2026-02-21 02:28:11 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S3 | Specify exact log message formats for OTel and Profiler status | claude-4 (claude-opus-4-5) | REQ-NMS-013 and REQ-NMS-014 already specify the exact log messages ('Tracing enabled/disabled' and 'Profiler enabled/disabled'). The logger context is clear from REQ-NMS-012 which defines the pino logger patterns for each service. | 2026-02-20 20:20:03 UTC |
| R1-S4 | Add validation criteria for _carry function edge cases | claude-4 (claude-opus-4-5) | REQ-NMS-004 precisely specifies the algorithm matching the reference implementation. Adding edge case requirements would go beyond reference fidelity, which is the stated validation goal. Edge cases should be handled as the reference handles them. | 2026-02-20 20:20:03 UTC |
| R1-S7 | Add feature IDs for F-002 through F-007 definitions | claude-4 (claude-opus-4-5) | The document explicitly references a companion plan (plan-nodejs.md) which is where feature definitions belong. Adding them here would duplicate content and create maintenance burden. | 2026-02-20 20:20:03 UTC |
| R1-S9 | Specify currencyservice logging for errors beyond conversion | claude-4 (claude-opus-4-5) | The requirements follow reference implementation fidelity. If the reference doesn't log these additional scenarios, adding requirements for them would deviate from the stated scope of matching the reference. | 2026-02-20 20:20:03 UTC |
| R1-S10 | Clarify whether charge.js logger import is required in paymentservice | claude-4 (claude-opus-4-5) | REQ-NMS-012 already clearly states 'charge.js creates its own inline pino instance' which definitively indicates it's standalone and doesn't import from logger.js. | 2026-02-20 20:20:03 UTC |
| R2-S1 | Specify default ports for both services when PORT is unset | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-001 explicitly states 'no default value' for PORT, indicating this is intentional reference behavior. Adding defaults would deviate from reference fidelity which is the stated validation goal. | 2026-02-20 20:20:03 UTC |
| R2-S2 | Mandate pino logger instead of console.warn in ChargeServiceHandler | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-007 specifies console.warn because that's what the reference implementation uses. Changing this would break reference fidelity. The requirement correctly documents actual reference behavior. | 2026-02-20 20:20:03 UTC |
| R2-S4 | Require custom error classes to be exported from charge.js | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-009 explicitly states 'All classes are defined in charge.js (not exported, module-local)' reflecting the reference implementation. Changing this for testability would break reference fidelity. | 2026-02-20 20:20:03 UTC |
| R2-S5 | Require both services to follow the same OTel initialization pattern | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-013 and the Cross-Cutting Summary Table explicitly document this difference as intentional reference behavior. currencyservice registers GrpcInstrumentation unconditionally while paymentservice puts everything in the conditional. This is reference-accurate. | 2026-02-20 20:20:03 UTC |
| R2-S6 | Mandate exact pinned versions in all package.json dependencies | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-016 already lists exact versions. The suggestion notes simple-card-validator uses '^1.1.0' which reflects the actual reference package.json. Changing it would break reference fidelity. | 2026-02-20 20:20:03 UTC |
| R2-S7 | Enhance currencyservice health check to validate currency data loading | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-011 specifies the health check returns SERVING unconditionally, matching reference behavior. Adding readiness logic would be a functional enhancement beyond reference fidelity. | 2026-02-20 20:20:03 UTC |
| R2-S8 | Simplify _getCurrencyData to be synchronous without callback | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-005 specifies the callback pattern because that's what the reference implementation uses. The suggestion asks for a refactoring that would break reference structural equivalence. | 2026-02-20 20:20:03 UTC |
| R2-S10 | Standardize environment variable access syntax to property notation | gemini-2.5 (gemini-2.5-pro) | Both notations are functionally identical in JavaScript. This is a stylistic preference that doesn't affect correctness or reference fidelity. The requirements should document what the reference uses, even if inconsistent. | 2026-02-20 20:20:03 UTC |
| R1-F3 | Clarify server.start() deprecation handling |  | The reference implementation uses server.start() and this is a structural reproduction exercise - matching the reference is the goal regardless of deprecation warnings | 2026-02-20 20:23:19 UTC |
| R1-F4 | Document the exact pino version behavior for severity formatter |  | The pino version is pinned at 10.3.0 and the formatter signature is already specified in the implementation contract | 2026-02-20 20:23:19 UTC |
| R1-F5 | Add requirement for proto file presence validation |  | Proto files are pre-provided context and their presence is a deployment concern, not part of the service implementation contract | 2026-02-20 20:23:19 UTC |
| R3-S1 | Specify exact OTLP exporter URL construction pattern using COLLECTOR_SERVICE_ADDR | claude-4 (claude-opus-4-5) | REQ-NMS-013 already specifies that both services read COLLECTOR_SERVICE_ADDR from process.env for the OTLP exporter URL and shows the pattern `OTLPTraceExporter({url: collectorUrl})`. The URL construction is implementation detail that can be validated via structural diff against reference. | 2026-02-20 20:25:51 UTC |
| R3-S2 | Document initialization order of profiler, OTel, and server creation | claude-4 (claude-opus-4-5) | The requirements already implicitly specify order through their structure (REQ-NMS-013 shows gRPC instrumentation registered at module level, REQ-NMS-014 shows profiler init location). The validation method of structural diff against reference will catch ordering issues. | 2026-02-20 20:25:51 UTC |
| R3-S3 | Add test case for _carry function handling negative nanos from division | claude-4 (claude-opus-4-5) | REQ-NMS-004 already specifies the _carry arithmetic with modulo operations which handle sign correctly. The validation approach of structural diff against reference _carry function is sufficient to ensure correct implementation. | 2026-02-20 20:25:51 UTC |
| R3-S4 | Clarify whether pino logger instances should use singleton pattern | claude-4 (claude-opus-4-5) | REQ-NMS-012 already explicitly states that logger.js 'exports a pino instance' and charge.js 'creates its own inline pino instance'. The import pattern is clear - logger.js is imported, charge.js creates its own. | 2026-02-20 20:25:51 UTC |
| R3-S5 | Specify error behavior when _getCurrencyData receives invalid JSON | claude-4 (claude-opus-4-5) | This is a duplicate of R4-S7 which addresses the same concern about malformed JSON. Additionally, Node's require() throws synchronously on invalid JSON, which is standard behavior that doesn't need specification. | 2026-02-20 20:25:51 UTC |
| R3-S7 | Add F-002 to traceability entries for REQ-NMS-003 | claude-4 (claude-opus-4-5) | While the dependency exists, REQ-NMS-003 is specifically about conversion logic (F-001 feature), not the data file itself. REQ-NMS-005 already covers F-002. Adding redundant feature links would clutter the traceability matrix. | 2026-02-20 20:25:51 UTC |
| R3-S9 | Reconcile InvalidCreditCard constructor parameter documentation | claude-4 (claude-opus-4-5) | REQ-NMS-009 already states the constructor takes cardType param (unused). The validation method is structural diff against reference charge.js which will verify the exact constructor signature. | 2026-02-20 20:25:51 UTC |
| R3-S10 | Specify whether currencyservice main() is async or synchronous | claude-4 (claude-opus-4-5) | REQ-NMS-001 specifies that main() creates server, calls bindAsync, and is called at module level. The use of callback-based bindAsync rather than await implies synchronous function. Structural diff validation will catch async/sync mismatch. | 2026-02-20 20:25:51 UTC |
| R4-S4 | Define expected behavior if gRPC server fails to bind to port | gemini-2.5 (gemini-2.5-pro) | This is essentially a duplicate of R3-S8 which was accepted. The same concern about bindAsync error handling is already being addressed. | 2026-02-20 20:25:51 UTC |
| R4-S5 | Reconcile versioning policy discrepancy between exact versions and caret ranges | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-016 explicitly documents that paymentservice uses caret ranges for some dependencies (simple-card-validator: ^1.1.0, uuid: ^13.0.0). This is intentional documentation of the reference implementation's actual package.json, not an inconsistency. | 2026-02-20 20:25:51 UTC |
| R4-S6 | Add test vectors for currency conversion floating-point precision | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-003 specifies the exact algorithm including Math.round, Math.floor operations matching the reference. The validation via structural diff against reference conversion logic is sufficient to ensure identical behavior. | 2026-02-20 20:25:51 UTC |
| R4-S7 | Specify behavior if currency_conversion.json is missing or malformed | gemini-2.5 (gemini-2.5-pro) | The require() call in Node.js has well-defined behavior - it throws synchronously on missing or invalid JSON. This is standard Node.js behavior that doesn't require explicit specification. The service crashing on startup for missing config is the expected behavior. | 2026-02-20 20:25:51 UTC |
| R4-S8 | Explicitly link cardValidator to simple-card-validator package in REQ-NMS-008 | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-016 already specifies simple-card-validator as a paymentservice dependency, and REQ-NMS-008 describes using cardValidator for Luhn validation. The connection is clear and validation via structural diff will verify the import. | 2026-02-20 20:25:51 UTC |
| R4-S9 | Clarify whether InvalidCreditCard constructor signature must include unused cardType parameter | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-009 already states the constructor 'takes cardType param (unused)'. This is explicit about the signature requirement. The structural diff validation will verify compliance. | 2026-02-20 20:25:51 UTC |
| R4-S10 | Clarify that health check is liveness only, not readiness | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-011 already specifies the exact behavior: returns SERVING always. The distinction between liveness and readiness probes is operational knowledge, not a requirement for code generation. The implementation is correctly specified. | 2026-02-20 20:25:51 UTC |
| R1-F3 | Clarify server.start() deprecation handling |  | The plan explicitly matches the reference implementation which uses server.start(); deprecation warnings are acceptable for reference fidelity | 2026-02-20 20:29:07 UTC |
| R1-F4 | Document exact pino version behavior for severity formatter |  | The plan already pins pino@10.3.0 and specifies the exact formatter pattern; this is sufficient specification | 2026-02-20 20:29:07 UTC |
| R1-F5 | Add requirement for proto file presence validation |  | Proto files are pre-provided artifacts per the plan; missing protos would be a deployment issue, not a code generation concern | 2026-02-20 20:29:07 UTC |
| R3-F2 | Clarify whether bindAsync callback should check for error parameter |  | The implementation contract specifies the exact callback pattern from reference; error handling matches reference | 2026-02-20 20:29:07 UTC |
| R3-F5 | Add requirement for deterministic UUID generation in test mode |  | This would change reference behavior; tests can validate UUID format without exact value matching | 2026-02-20 20:29:07 UTC |
| R5-S1 | Add requirement for dependency injection patterns to make Date() calls mockable in charge.js | claude-4 (claude-opus-4-5) | This changes the reference implementation behavior. The document explicitly states the reference is ground truth and code style preferences are out of scope. The limitation exists in the reference and should be preserved for accuracy. | 2026-02-20 20:42:30 UTC |
| R5-S3 | Add validation requirement for gRPC service registration order before server.start() | claude-4 (claude-opus-4-5) | The requirements already specify that server.start() is called inside bindAsync callback after addService calls. Adding AST-based ordering verification is over-engineering for something the structural diff validation already covers. | 2026-02-20 20:42:30 UTC |
| R5-S5 | Link validation requirements V01/V02 to specific acceptance criteria in functional requirements | claude-4 (claude-opus-4-5) | The validation requirements are intentionally generic (syntax validity, structural comparability) and the Traceability Matrix already maps each functional requirement to its validation method. Adding another cross-reference layer would create maintenance burden without proportional benefit. | 2026-02-20 20:42:30 UTC |
| R5-S6 | Add requirement ID cross-references to Cross-Cutting Summary Table | claude-4 (claude-opus-4-5) | The table serves as a quick comparison view and the relevant requirements (REQ-NMS-011 through REQ-NMS-017) are clearly organized in the Cross-Cutting Requirements section immediately below. Adding redundant cross-references would clutter the table. | 2026-02-20 20:42:30 UTC |
| R5-S8 | Standardize proto path construction terminology across all requirements | claude-4 (claude-opus-4-5) | The requirements adequately describe the path construction for each service. The minor variation in description granularity reflects actual differences in the reference implementation (currencyservice uses inline paths, paymentservice receives protoRoot as parameter). | 2026-02-20 20:42:30 UTC |
| R5-S9 | Specify validation approach for callback-wrapping-sync pattern in _getCurrencyData | claude-4 (claude-opus-4-5) | The requirement clearly states the data is loaded synchronously via require() and passed to callback. This pattern is common in Node.js for API consistency. Adding validation for synchronous callback invocation is over-specification. | 2026-02-20 20:42:30 UTC |
| R6-S1 | Standardize package.json metadata schema across both services | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-016 already specifies the exact package.json contents for both services matching the reference implementation. The differences (name format, version scheme, license, author) are intentional reference-accurate variations, not debt to be standardized. | 2026-02-20 20:42:30 UTC |
| R6-S2 | Mandate unconditional OTel GrpcInstrumentation registration for both services | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-013 explicitly documents the behavioral difference as reference-accurate: currencyservice registers instrumentation always, paymentservice only when tracing enabled. Changing this would deviate from the reference implementation which is ground truth. | 2026-02-20 20:42:30 UTC |
| R6-S3 | Isolate server startup from module loading using require.main === module pattern | gemini-2.5 (gemini-2.5-pro) | This changes the reference implementation behavior. REQ-NMS-001 explicitly specifies 'main() called at module level (not exported)' matching the reference. The document states code style preferences are out of scope. | 2026-02-20 20:42:30 UTC |
| R6-S4 | Require injectable time and UUID dependencies in charge.js for testability | gemini-2.5 (gemini-2.5-pro) | This would change the reference implementation structure. The document explicitly states the reference is ground truth and testability patterns beyond what exists in reference are out of scope. | 2026-02-20 20:42:30 UTC |
| R6-S5 | Require custom error classes to be exported from charge.js for instanceof testing | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-009 explicitly states 'All classes are defined in charge.js (not exported, module-local)' matching the reference. Exporting them would change the reference-accurate behavior. | 2026-02-20 20:42:30 UTC |
| R6-S6 | Prohibit logging raw sensitive credit card data to comply with PCI-DSS | gemini-2.5 (gemini-2.5-pro) | The document explicitly states 'Security hardening beyond what exists in the reference' is out of scope. REQ-NMS-007 accurately captures the reference implementation behavior. This is a demo application, not production code. | 2026-02-20 20:42:30 UTC |
| R6-S7 | Mandate OpenTelemetry trace context injection into all log records | gemini-2.5 (gemini-2.5-pro) | This would change the reference implementation logging behavior. REQ-NMS-012 accurately specifies the pino configuration from the reference. The reference does not include trace context in logs. | 2026-02-20 20:42:30 UTC |
| R6-S8 | Require logging full error objects instead of just error messages in currencyservice | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-003 explicitly specifies 'logs conversion request failed: ${err}, calls callback(err.message)' matching the reference. The difference from paymentservice is intentional and reference-accurate. | 2026-02-20 20:42:30 UTC |
| R6-S9 | Require code-level comments linking implementation to requirement IDs | gemini-2.5 (gemini-2.5-pro) | This would add non-functional content not present in the reference implementation. The document focuses on structural equivalence to reference, not documentation practices. | 2026-02-20 20:42:30 UTC |
| R6-S10 | Mandate single logger instantiation pattern per service | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-012 explicitly documents that paymentservice has two separate loggers (logger.js and charge.js inline) matching the reference implementation. This is intentional reference-accurate behavior, not an anti-pattern to fix. | 2026-02-20 20:42:30 UTC |
| R1-F1 | Specify exact OTLPTraceExporter import path |  | R1-S2 was already accepted which addresses OTel import patterns. The implementation contract in F-001 and F-004 already specifies the imports sufficiently for code generation. | 2026-02-20 20:47:28 UTC |
| R1-F2 | Add explicit requirement for resourceFromAttributes import source |  | The implementation contract already specifies 'resourceFromAttributes' comes from OTel packages, and R1-S2 was accepted to address OTel import clarity. This is redundant. | 2026-02-20 20:47:28 UTC |
| R1-F3 | Clarify server.start() deprecation handling |  | The implementation contract explicitly specifies using server.start() inside bindAsync callback, matching the reference. Deprecation handling is a runtime concern, not a code generation requirement. | 2026-02-20 20:47:28 UTC |
| R1-F4 | Document exact pino version behavior for severity formatter |  | REQ-NMS-016 pins pino@10.3.0 and the formatter pattern is explicitly documented in the implementation contract. Version compatibility is verified at npm install time. | 2026-02-20 20:47:28 UTC |
| R1-F5 | Add requirement for proto file presence validation |  | Proto files are pre-provided artifacts (documented in plan). Missing protos would cause immediate runtime failure which is appropriate behavior - no graceful degradation needed for missing contracts. | 2026-02-20 20:47:28 UTC |
| R3-F1 | Add explicit requirement for ATTR_SERVICE_NAME import source |  | The implementation contract already specifies imports including ATTR_SERVICE_NAME from semantic-conventions. R1-S2 was accepted to address OTel imports. This is redundant. | 2026-02-20 20:47:28 UTC |
| R3-F2 | Clarify bindAsync callback error handling pattern |  | R3-S8 was never accepted (it's in rejected list as R3-S8). The implementation contract specifies the callback pattern matching reference. Error handling details are implementation-level. | 2026-02-20 20:47:28 UTC |
| R3-F3 | Specify exact import destructuring pattern for OTel SDK packages |  | The implementation contracts in F-001 and F-004 already specify the import patterns (e.g., 'opentelemetry (sdk-node)'). This level of detail is already present. | 2026-02-20 20:47:28 UTC |
| R3-F5 | Add requirement for deterministic UUID generation in test mode |  | This is a test infrastructure concern, not a code generation requirement. Validation can use regex matching for UUID format. Adding test modes changes the reference implementation. | 2026-02-20 20:47:28 UTC |
| R5-F1 | Specify exact import statements for OTel packages in REQ-NMS-013 |  | The implementation contracts in F-001 and F-004 already detail the exact imports. This duplicates information already present in the plan. | 2026-02-20 20:47:28 UTC |
| R5-F3 | Document same-month expiration card validity behavior |  | The implementation contract already specifies the exact comparison formula. The behavior is implicit in the code and matches reference. Adding notes is documentation bloat. | 2026-02-20 20:47:28 UTC |
| R5-F5 | Add pass/fail criteria to REQ-NMS-V01 and REQ-NMS-V02 |  | Validation requirements are sufficiently defined: syntax validity means zero syntax errors, structural comparability means diff-able output. Binary outcomes are implicit. | 2026-02-20 20:47:28 UTC |
| R7-S1 | Add traceability links from validation requirements back to functional requirements | claude-4 (claude-opus-4-5) | The traceability matrix already provides comprehensive mapping from requirements to validation methods. Adding 'Validates:' lists to V01/V02 would create redundant information that could drift out of sync | 2026-02-20 21:19:09 UTC |
| R7-S2 | Add 'Validated by' field to each functional requirement | claude-4 (claude-opus-4-5) | The traceability matrix already serves this purpose by mapping each requirement to its validation method. Bidirectional inline references would create maintenance burden and potential inconsistencies | 2026-02-20 21:19:09 UTC |
| R7-S3 | Document why cross-cutting requirements use different validation patterns | claude-4 (claude-opus-4-5) | The traceability matrix already shows validation methods for each requirement including cross-cutting ones. The grep-based validation approach is appropriate and consistent with the structural validation strategy | 2026-02-20 21:19:09 UTC |
| R7-S4 | Define concrete test vectors for EUR pivot conversion edge cases | claude-4 (claude-opus-4-5) | This is a code generation requirements document, not a test specification. REQ-NMS-V02 validates structural comparability against the reference implementation which implicitly covers algorithmic correctness. Adding test vectors goes beyond requirements scope | 2026-02-20 21:19:09 UTC |
| R7-S5 | Specify expected behavior for invalid credit card scenarios in validation | claude-4 (claude-opus-4-5) | REQ-NMS-009 already defines the three error classes and their exact message formats. The validation approach via structural diff and grep patterns is sufficient for a code generation requirements document | 2026-02-20 21:19:09 UTC |
| R7-S6 | Add test vectors for _carry function arithmetic validation | claude-4 (claude-opus-4-5) | Structural comparability validation against the reference implementation is sufficient. The _carry algorithm is precisely specified in REQ-NMS-004 with exact formulas | 2026-02-20 21:19:09 UTC |
| R7-S7 | Link Cross-Cutting Summary Table entries to their authoritative requirements | claude-4 (claude-opus-4-5) | The table serves as a summary reference, and the detailed requirements (REQ-NMS-011 through REQ-NMS-017) are clearly organized in the Cross-Cutting Requirements section immediately following. Adding inline references would clutter the table | 2026-02-20 21:19:09 UTC |
| R7-S8 | Define validation approach for OpenTelemetry conditional registration difference | claude-4 (claude-opus-4-5) | REQ-NMS-013 already explicitly states the difference in conditional vs unconditional registration. The grep-based validation in the traceability matrix can verify import patterns and conditional block structure | 2026-02-20 21:19:09 UTC |
| R7-S9 | Document which features map to which proto service definitions | claude-4 (claude-opus-4-5) | REQ-NMS-001 and REQ-NMS-006 already specify the proto contract implementations (CurrencyService and PaymentService) and the proto loading patterns. REQ-NMS-017 covers proto loading requirements | 2026-02-20 21:19:09 UTC |
| R8-S1 | Mandate in-code requirement traceability markers as comments | gemini-2.5 (gemini-2.5-pro) | The reference implementation does not contain such markers. Adding them would make generated code diverge from the reference, violating the structural comparability requirement. Traceability is maintained at the documentation level | 2026-02-20 21:19:09 UTC |
| R8-S3 | Add implementation pointer column to traceability matrix linking to plan-nodejs.md | gemini-2.5 (gemini-2.5-pro) | The plan document is a separate artifact with its own structure. Cross-document linkage would create maintenance burden and the requirements document should stand alone as the authoritative specification | 2026-02-20 21:19:09 UTC |
| R8-S4 | Require generation of unit tests for charge.js business logic | gemini-2.5 (gemini-2.5-pro) | The reference implementation does not include unit tests. Requiring generated tests would go beyond the scope of replicating the reference. REQ-NMS-V02 validates structural equivalence which is the stated goal | 2026-02-20 21:19:09 UTC |
| R8-S5 | Require generation of unit tests for _carry helper function | gemini-2.5 (gemini-2.5-pro) | Same rationale as R8-S4 - the reference implementation does not include unit tests, and the requirements focus on structural comparability to the reference | 2026-02-20 21:19:09 UTC |
| R8-S6 | Require basic gRPC service integration test | gemini-2.5 (gemini-2.5-pro) | The reference implementation does not include integration tests. This goes beyond code generation requirements into test suite generation which is out of scope | 2026-02-20 21:19:09 UTC |
| R8-S7 | Require testing of environment variable-driven behavior | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-013 and REQ-NMS-014 already specify the exact log messages for each condition. Structural validation via grep can verify these strings exist in the code | 2026-02-20 21:19:09 UTC |
| R8-S8 | Formalize cross-cutting summary table as a normative requirement | gemini-2.5 (gemini-2.5-pro) | The table explicitly states it is required by REQ-REGEN-004a and serves as a summary. The detailed normative requirements are in REQ-NMS-011 through REQ-NMS-017 | 2026-02-20 21:19:09 UTC |
| R8-S9 | Specify testing of custom error propagation through gRPC boundary | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-007 already specifies the error handling pattern. Structural validation confirms the catch block passes error to callback. Integration testing is out of scope | 2026-02-20 21:19:09 UTC |
| R9-S1 | Add REQ-NMS-T01 specifying proto contract testing requirements with edge case scenarios | claude-4 (claude-opus-4-5) | The requirements document already defines functional behavior (REQ-NMS-002, REQ-NMS-003) and validation requirements (REQ-NMS-V01, V02, V03). Adding detailed test scenarios goes beyond requirements specification into test planning, which should be a separate artifact derived from requirements. | 2026-02-21 02:21:47 UTC |
| R9-S2 | Define mock/stub requirements for cloud dependencies | claude-4 (claude-opus-4-5) | Test infrastructure patterns (mocking, dependency injection) are implementation concerns for the test suite, not functional requirements for the services themselves. The existing DISABLE_PROFILER and ENABLE_TRACING env vars already provide runtime configurability. | 2026-02-21 02:21:47 UTC |
| R9-S4 | Add Feature-to-Requirement reverse mapping table | claude-4 (claude-opus-4-5) | The existing Traceability Matrix already maps requirements to features, making reverse lookup straightforward. Adding a redundant reverse table increases maintenance burden without significant value - the information is already present and extractable. | 2026-02-21 02:21:47 UTC |
| R9-S5 | Add explicit requirement IDs for each output file | claude-4 (claude-opus-4-5) | The requirements already clearly describe which files implement which functionality (e.g., REQ-NMS-001 explicitly states 'server.js is a single-file gRPC server'). The mapping is implicit but unambiguous, and adding another layer of file-to-requirement mapping adds complexity without clarifying ambiguity. | 2026-02-21 02:21:47 UTC |
| R9-S6 | Specify which validation requirements verify each functional requirement | claude-4 (claude-opus-4-5) | The three validation requirements (V01-V03) are intentionally broad and cover all functional requirements through syntax validity, structural comparability, and CVV non-validation. Explicit per-requirement mapping would be redundant and overly prescriptive. | 2026-02-21 02:21:47 UTC |
| R9-S7 | Add negative test requirements for proto loading failures | claude-4 (claude-opus-4-5) | The reference implementation doesn't include explicit proto loading error handling beyond what protoLoader.loadSync provides by default. Adding requirements for error handling not present in the reference would diverge from the goal of matching reference behavior. | 2026-02-21 02:21:47 UTC |
| R9-S9 | Add reference line numbers or code block hashes for each requirement | claude-4 (claude-opus-4-5) | The reference commit SHA is already pinned, providing stable traceability. Adding line numbers would create maintenance burden as they're fragile to any reformatting. Code block hashes are impractical to maintain and verify manually. | 2026-02-21 02:21:47 UTC |
| R9-S10 | Specify logger output capture requirements for testing | claude-4 (claude-opus-4-5) | REQ-NMS-012 already specifies the pino configuration including messageKey and formatters. How tests capture and verify log output is a test implementation detail, not a service requirement. The structured JSON format is already specified. | 2026-02-21 02:21:47 UTC |
| R10-S2 | Add test vectors table for credit card validation | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-008 already specifies the validation logic in detail (Luhn, card type restriction, expiration). Test vectors are test artifacts, not requirements. The acceptance criteria provide sufficient specificity for deriving test cases. | 2026-02-21 02:21:47 UTC |
| R10-S4 | Add Plan Reference field tracing requirements to plan-nodejs.md sections | gemini-2.5 (gemini-2.5-pro) | The document already references the companion plan at the top level. Adding per-requirement plan references would create significant maintenance burden and tight coupling between documents. The requirements stand alone as the authoritative specification. | 2026-02-21 02:21:47 UTC |
| R10-S5 | Specify gRPC status code mapping for error classes | gemini-2.5 (gemini-2.5-pro) | This duplicates R9-S3 which was already accepted. The gRPC status code mapping concern is being addressed by that suggestion. | 2026-02-21 02:21:47 UTC |
| R10-S6 | Formalize Out of Scope items as traceable requirements | gemini-2.5 (gemini-2.5-pro) | Out of Scope is appropriately handled as a prose section defining exclusions. Converting them to formal requirements with IDs would inappropriately elevate non-requirements to the same status as actual requirements, creating confusion about what the project delivers. | 2026-02-21 02:21:47 UTC |
| R10-S7 | Add edge-case examples for the _carry function | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-004 already specifies the exact arithmetic operations including fractionSize, modulo, and floor operations. The implementation is fully specified - edge case behavior is derivable from the formula. R10-S3 (accepted) adds a worked example at the convert() level which exercises _carry. | 2026-02-21 02:21:47 UTC |
| R10-S8 | Add requirement IDs to Cross-Cutting Summary Table rows | gemini-2.5 (gemini-2.5-pro) | The summary table already includes a note citing REQ-REGEN-004a and serves as a quick reference, not a formal specification. The detailed requirements immediately follow with explicit IDs. Adding IDs to every cell would clutter the summary format. | 2026-02-21 02:21:47 UTC |
| R10-S9 | Make logging requirements more specific with expected log fields and values | gemini-2.5 (gemini-2.5-pro) | REQ-NMS-012 already specifies the pino configuration including messageKey:'message' and severity formatter. The actual log message strings are specified in their respective requirements. Further specification would be overly prescriptive about internal logging details. | 2026-02-21 02:21:47 UTC |
| R1-F1 | Specify exact OTLPTraceExporter import path for both services |  | R1-S8 was already applied to address OTel import patterns. The implementation contract in the plan already specifies the imports sufficiently for code generation. | 2026-02-21 02:28:11 UTC |
| R1-F2 | Add explicit requirement for resourceFromAttributes import source |  | The implementation contract already specifies 'resourceFromAttributes' comes from OTel packages, and R1-S8 was accepted to address OTel import clarity. This is redundant. | 2026-02-21 02:28:11 UTC |
| R1-F3 | Clarify server.start() deprecation handling |  | The plan explicitly matches the reference implementation which uses server.start(); deprecation warnings are acceptable for reference fidelity which is the stated goal. | 2026-02-21 02:28:11 UTC |
| R1-F4 | Document exact pino version behavior for severity formatter |  | The plan already pins pino@10.3.0 and specifies the exact formatter pattern; this is sufficient specification for code generation. | 2026-02-21 02:28:11 UTC |
| R1-F5 | Add requirement for proto file presence validation |  | Proto files are pre-provided artifacts per the plan; missing protos would cause immediate runtime failure which is appropriate behavior for missing contracts. | 2026-02-21 02:28:11 UTC |
| R3-F1 | Add explicit requirement for ATTR_SERVICE_NAME import source |  | The implementation contract already specifies imports including ATTR_SERVICE_NAME from semantic-conventions. R1-S8 was accepted to address OTel imports. This is redundant. | 2026-02-21 02:28:11 UTC |
| R3-F2 | Clarify whether bindAsync callback should check for error parameter |  | The implementation contract specifies the exact callback pattern matching reference. Error handling details are implementation-level concerns covered by structural comparison. | 2026-02-21 02:28:11 UTC |
| R3-F3 | Specify exact import destructuring pattern for OTel SDK packages |  | The implementation contracts in F-001 and F-004 already specify the import patterns (e.g., 'opentelemetry (sdk-node)'). This level of detail is already present. | 2026-02-21 02:28:11 UTC |
| R3-F4 | Document that currencyservice convert() error callback inconsistency is intentional |  | R2-S3 was already rejected with rationale that the inconsistency reflects reference behavior and is already documented in REQ-NMS-003 vs REQ-NMS-007. | 2026-02-21 02:28:11 UTC |
| R3-F5 | Add requirement for deterministic UUID generation in test mode |  | This would change reference behavior; tests can validate UUID format without exact value matching using regex patterns. | 2026-02-21 02:28:11 UTC |
| R5-F1 | Specify exact import statements for OTel packages in REQ-NMS-013 |  | The implementation contracts in F-001 and F-004 already detail the exact imports. This duplicates information already present in the plan. | 2026-02-21 02:28:11 UTC |
| R5-F3 | Document same-month expiration card validity behavior |  | The implementation contract already specifies the exact comparison formula. The behavior is implicit in the code and matches reference. Adding notes is documentation bloat. | 2026-02-21 02:28:11 UTC |
| R5-F5 | Add pass/fail criteria to REQ-NMS-V01 and REQ-NMS-V02 |  | Validation requirements are sufficiently defined: syntax validity means zero syntax errors, structural comparability means diff-able output. Binary outcomes are implicit. | 2026-02-21 02:28:11 UTC |
| R7-F1 | Verify resourceFromAttributes function name in @opentelemetry/resources@2.x |  | R5-F2 is being accepted to fix OTel versions. The correct API names will be verified when versions are reconciled with reference package.json. | 2026-02-21 02:28:11 UTC |
| R7-F2 | Clarify cardNumber.replace('-', '') only removes first hyphen |  | This is reference-accurate behavior. The structural comparison validation will ensure generated code matches reference exactly, including this quirk. | 2026-02-21 02:28:11 UTC |
| R7-F3 | Document deprecated npm install --only=production flag |  | The Dockerfile matches reference implementation. The deprecated flag works in node:20-alpine and reference fidelity takes precedence over modernization. | 2026-02-21 02:28:11 UTC |
| R7-F4 | Clarify HipsterShopServer.PORT default parameter issue |  | REQ-NMS-006 already states PORT is assigned after class definition as a static property. The structural diff validation will catch any deviation from reference pattern. | 2026-02-21 02:28:11 UTC |
| R7-F5 | Specify Node.js version for syntax validation in REQ-NMS-V01 |  | REQ-NMS-015 already specifies node:20.20.0-alpine base image. The validation runtime is implicitly the same as the deployment target. | 2026-02-21 02:28:11 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

(empty — awaiting first review round)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:18:14 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | completeness | critical | Add explicit requirement for COLLECTOR_SERVICE_ADDR format and URL construction | REQ-NMS-013 references `collectorUrl` but doesn't specify how it's constructed from COLLECTOR_SERVICE_ADDR (e.g., `http://${addr}` vs raw value). This is essential for OTel exporter configuration. | REQ-NMS-013 acceptance criteria | Verify generated code constructs URL identically to reference |
| R1-S2 | ambiguity | high | Clarify InvalidCreditCard constructor signature discrepancy | REQ-NMS-009 states InvalidCreditCard constructor "takes `cardType` param (unused)" but REQ-NMS-008 shows validation returns `card_type` — unclear if param should be passed or if constructor is truly no-arg in practice | REQ-NMS-009 acceptance criteria | Compare constructor invocation sites in charge.js |
| R1-S3 | completeness | high | Specify exact log message formats for OTel and Profiler status | REQ-NMS-013 and REQ-NMS-014 mention logging "Tracing enabled/disabled" and "Profiler enabled/disabled" but don't specify logger used (console vs pino) or exact format | Add to REQ-NMS-013 and REQ-NMS-014 | Grep for exact log statements in generated code |
| R1-S4 | testability | medium | Add validation criteria for _carry function edge cases | REQ-NMS-004 specifies the algorithm but doesn't define expected behavior for negative values or overflow scenarios that may occur in real conversion chains | REQ-NMS-004 or new REQ-NMS-V03 | Unit test or structural comparison of edge case handling |
| R1-S5 | consistency | medium | Reconcile PORT default value inconsistency | REQ-NMS-001 states "no default value" for PORT but REQ-NMS-006 doesn't specify; REQ-NMS-010 references PORT without default clarification. Cross-cutting table says both use PORT "from env var" | REQ-NMS-006 and REQ-NMS-010 | Verify both services fail gracefully or use same default behavior |
| R1-S6 | completeness | medium | Document @opentelemetry/instrumentation import location for paymentservice | REQ-NMS-013 notes paymentservice "imports all OTel packages inside the conditional block" but REQ-NMS-016 says no `@opentelemetry/instrumentation` standalone — clarify how registerInstrumentations is imported | REQ-NMS-013 acceptance criteria | Verify import statements match reference |
| R1-S7 | traceability | medium | Add feature IDs for F-002, F-003, F-005, F-006, F-007 definitions | Traceability matrix references F-001 through F-007 but feature definitions are not included in this document; readers cannot validate feature coverage | New Features section or reference to plan-nodejs.md | Cross-reference with companion plan |
| R1-S8 | feasibility | medium | Specify exact @opentelemetry/exporter-otlp-grpc import path | REQ-NMS-016 lists `@opentelemetry/exporter-otlp-grpc: "0.26.0"` but OTel SDK typically uses `@opentelemetry/exporter-trace-otlp-grpc`; version 0.26.0 is very old vs sdk-node 0.211.0 | REQ-NMS-016 | npm registry verification of package name and version compatibility |
| R1-S9 | completeness | low | Specify currencyservice logging for errors beyond conversion | REQ-NMS-003 specifies error logging for convert(), but doesn't cover getSupportedCurrencies error handling or general server startup errors | REQ-NMS-001 or REQ-NMS-002 | Grep for error handling patterns in reference |
| R1-S10 | ambiguity | low | Clarify whether charge.js logger import is required in paymentservice | REQ-NMS-012 states charge.js creates "its own inline pino instance" but doesn't specify if it also imports from logger.js or is fully standalone | REQ-NMS-012 acceptance criteria | Verify import statements in generated charge.js |

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:18:40 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | completeness | high | Specify default ports (e.g., 7000 for currency, 50051 for payment) for both services to use when the `PORT` environment variable is not set. | The current requirements imply services will crash if the `PORT` variable is unset. Providing a default ensures services are runnable out-of-the-box for local development and testing. | REQ-NMS-001, REQ-NMS-010 | Code inspection to verify the use of a logical OR to provide a default port, e.g., `process.env.PORT \|\| 7000`. |
| R2-S2 | consistency | high | Mandate that all logging, including error handling in `ChargeServiceHandler`, must use the configured `pino` logger instead of `console.warn`. | Using `console.warn` as specified in REQ-NMS-007 breaks the structured JSON logging format defined in REQ-NMS-012, making logs harder to parse, query, and alert on. | REQ-NMS-007 | Static analysis or 'grep' to ensure no instances of `console.warn` or `console.error` exist in the generated service code. |
| R2-S3 | consistency | high | Standardize gRPC error handling by requiring the full error object (`err`) to be passed to the callback in all RPC handlers, specifically correcting `currencyservice`. | `paymentservice` passes the full error object while `currencyservice` passes only `err.message`. Passing the full object preserves stack traces and custom properties (like error codes), which is critical for debugging and robust client-side error handling. | REQ-NMS-003 | Inspect the `convert` RPC handler's catch block to ensure `callback(err)` is used, not `callback(err.message)`. |
| R2-S4 | testability | high | Require the custom error classes in `charge.js` (`InvalidCreditCard`, `UnacceptedCreditCard`, `ExpiredCreditCard`) to be exported from the module. | The requirement for these classes to be module-local makes them impossible to import for testing. This forces tests to rely on brittle error message string matching instead of robust type checking (e.g., `instanceof`). | REQ-NMS-009 | Inspect the `module.exports` object in the generated `charge.js` to confirm the error classes are exported. |
| R2-S5 | consistency | medium | Require both services to follow the `paymentservice` pattern where all OpenTelemetry setup, including `GrpcInstrumentation` registration, is inside the `ENABLE_TRACING == "1"` conditional block. | `currencyservice` registers instrumentation unconditionally, which is inconsistent and could add minor performance overhead when tracing is disabled. A single, consistent initialization pattern is easier to maintain. | REQ-NMS-013 | Structural comparison of the OTel initialization blocks in both services' entry points. |
| R2-S6 | consistency | medium | Mandate that all dependencies in both `package.json` files use exact, pinned versions (e.g., `"1.1.0"`) instead of caret (`^`) or tilde (`~`) ranges. | Using version ranges can lead to non-reproducible builds, as `npm install` may pull in newer, potentially breaking, dependency versions. Pinning versions is crucial for maintaining stability, especially in a microservices architecture. | REQ-NMS-016 | Automated script to scan `dependencies` in `package.json` files and fail if any `^` or `~` characters are present. |
| R2-S7 | testability | medium | Enhance the `currencyservice` health check to validate its core dependency by attempting to load `currency_conversion.json`. It should return `NOT_SERVING` on failure. | The current check always returns `SERVING`, which only confirms liveness (process is running) but not readiness (is it functional?). A readiness check that verifies dependencies prevents traffic from being routed to a broken instance. | REQ-NMS-011 | Unit test the `check` function by mocking a file-read error for the JSON data and asserting that the returned status is `NOT_SERVING`. |
| R2-S8 | ambiguity | medium | Simplify the `_getCurrencyData` function in `currencyservice` to be a standard synchronous function that directly returns the result of `require(...)` instead of using a callback. | `require()` is a synchronous operation. Wrapping it in a callback-based function is unidiomatic, confusing, and adds unnecessary complexity. The function signature incorrectly implies asynchronicity where none exists. | REQ-NMS-005 | Code inspection of `_getCurrencyData` to verify it has no callback parameter and uses a `return` statement. |
| R2-S9 | ambiguity | low | Clarify the expected format for the credit card expiration year in REQ-NMS-008. Specify if it is a two-digit or four-digit integer. | The expiration check compares `new Date().getFullYear()` (four digits) with the `year` from the request. The requirement is ambiguous about the input year's format, which could lead to incorrect validation logic (e.g., comparing `2026` with `26`). | REQ-NMS-008 | Review the requirement text for the added clarification on the year format. |
| R2-S10 | consistency | low | Standardize the syntax for accessing environment variables to be property access (e.g., `process.env.PORT`) across all requirements. | The document currently mixes `process.env.PORT` (REQ-NMS-001) and `process.env['PORT']` (REQ-NMS-010). While functionally identical, using a single, consistent style improves readability and maintainability of the requirements and the resulting code. | REQ-NMS-010 | Grep for `process.env['` to ensure no bracket notation is used for standard environment variable access. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:20:50 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | ambiguity | high | Specify the exact OTLPTraceExporter import path for both services | REQ-NMS-013 references OTLPTraceExporter but the package @opentelemetry/exporter-otlp-grpc may export it differently than expected. Clarify the exact import statement (e.g., `const { OTLPTraceExporter } = require('@opentelemetry/exporter-otlp-grpc')`) | REQ-NMS-013 acceptance criteria | Compare generated import against reference import statement |
| R1-F2 | completeness | high | Add explicit requirement for resourceFromAttributes import source | REQ-NMS-013 references resourceFromAttributes but doesn't specify which @opentelemetry package exports it. This is critical for correct SDK initialization. | REQ-NMS-013 acceptance criteria | Verify import resolves from @opentelemetry/resources |
| R1-F3 | ambiguity | medium | Clarify server.start() deprecation handling | grpc.Server.start() is deprecated in newer @grpc/grpc-js versions. Specify whether the reference uses start() or relies on bindAsync callback completion for server readiness. | REQ-NMS-001 and REQ-NMS-006 | Test generated server startup against gRPC library deprecation warnings |
| R1-F4 | completeness | medium | Document the exact pino version behavior for severity formatter | REQ-NMS-012 specifies `logLevelString` parameter in formatter but pino 10.x may have different formatter signatures. Verify the formatter pattern works with pino@10.3.0. | REQ-NMS-012 acceptance criteria | Unit test pino formatter with specified version |
| R1-F5 | testability | medium | Add requirement for proto file presence validation | REQ-NMS-017 specifies dynamic proto loading but doesn't define behavior when proto files are missing. Add requirement for graceful error handling or explicit startup failure. | REQ-NMS-017 or new requirement | Test service startup with missing proto files |

#### Review Round R3

**Reviewer**: claude-4 (claude-opus-4-5)
**Date**: 2026-02-20 20:23:38 UTC
**Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | completeness | high | Specify the exact OTLP exporter URL construction pattern using COLLECTOR_SERVICE_ADDR | REQ-NMS-013 mentions reading COLLECTOR_SERVICE_ADDR but doesn't specify how the URL is constructed (e.g., `http://${COLLECTOR_SERVICE_ADDR}` vs direct use). The two services may differ in URL formatting which would cause silent tracing failures. | REQ-NMS-013 acceptance criteria - add explicit URL template | Generate both services and verify OTLP exporter URL matches reference pattern |
| R3-S2 | consistency | medium | Document the order of initialization steps in both services' entry points | Both services have multiple initialization phases (profiler, OTel, server creation) but the document doesn't specify execution order. Race conditions between OTel registration and server startup can cause instrumentation gaps. | Add ordered initialization sequence to REQ-NMS-001 and REQ-NMS-010 | Static analysis of generated code to verify initialization order matches reference |
| R3-S3 | testability | medium | Add explicit test case for _carry function handling negative nanos from division | REQ-NMS-004 specifies _carry arithmetic but doesn't address edge case where nanos could become negative during EUR pivot division (Step 1 of REQ-NMS-003), potentially causing incorrect currency conversion results. | Add edge case note to REQ-NMS-004 or REQ-NMS-003 | Unit test with currencies having rates that produce negative intermediate nanos |
| R3-S4 | ambiguity | medium | Clarify whether pino logger instances should use singleton pattern or new instances per import | REQ-NMS-012 says paymentservice's logger.js "exports a pino instance" but doesn't specify if server.js and index.js should share the same instance or create new ones. This affects log correlation. | REQ-NMS-012 acceptance criteria - specify import/instantiation pattern | Verify generated code imports logger.js vs creates new pino() |
| R3-S5 | completeness | medium | Specify error propagation behavior when _getCurrencyData callback receives invalid JSON | REQ-NMS-005 says _getCurrencyData uses require() synchronously, but doesn't specify behavior if currency_conversion.json is malformed. The reference may have implicit error handling via Node's require cache. | Add error scenario handling to REQ-NMS-005 | Test with malformed JSON file to verify error propagation |
| R3-S6 | feasibility | high | Address potential breaking change in @opentelemetry/exporter-otlp-grpc version 0.26.0 | REQ-NMS-016 specifies exporter-otlp-grpc@0.26.0, but the instrumentation-grpc@0.211.0 version suggests a much newer OTel stack. Version 0.26.0 uses deprecated APIs incompatible with sdk-node@0.211.0. This is likely a typo that would cause runtime failures. | Verify and correct version in REQ-NMS-016 currencyservice dependencies | npm install with exact versions and verify no peer dependency conflicts |
| R3-S7 | traceability | low | Add feature ID for currency data file (F-002) to traceability entries for REQ-NMS-003 | REQ-NMS-003 (conversion logic) depends on currency data from F-002 but the traceability matrix only links it to F-001. This obscures the dependency chain for validation. | Traceability Matrix - update REQ-NMS-003 row | Review feature dependencies for completeness |
| R3-S8 | completeness | medium | Specify the bindAsync callback signature and error handling pattern | REQ-NMS-001 and REQ-NMS-006 mention server.start() is called inside bindAsync callback, but don't specify if/how bind errors are handled. Silent bind failures could cause deployment issues. | Add callback error handling to REQ-NMS-001 and REQ-NMS-006 acceptance criteria | Generate code and verify error parameter is checked in callback |
| R3-S9 | consistency | low | Reconcile discrepancy in InvalidCreditCard constructor parameter documentation | REQ-NMS-009 states InvalidCreditCard constructor "takes cardType param (unused)" but the error is thrown when Luhn validation fails (REQ-NMS-008), where cardType isn't yet determined. Verify if constructor actually takes no params or takes cardNumber. | REQ-NMS-009 acceptance criteria - verify constructor signature | Structural diff against reference charge.js constructor |
| R3-S10 | ambiguity | medium | Specify whether currencyservice main() is async or synchronous | REQ-NMS-001 says main() is "called at module level" but doesn't specify if it's an async function. This matters for error handling - unhandled promise rejections behave differently than synchronous throws. | REQ-NMS-001 acceptance criteria - add async/sync specification | AST analysis of generated main() function declaration |

#### Review Round R4
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:24:11 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | feasibility | critical | In REQ-NMS-015, the Docker base image tags (`node:20.20.0-alpine`, `alpine:3.23.3`) are inconsistent with their specified `sha256` digests. The digests correspond to different versions (`node:20.11.0-alpine3.19` and `alpine:3.19.1`). | A Docker build cannot use a tag and a non-matching digest simultaneously. The requirement is impossible to implement as written and must be corrected to specify a valid, consistent base image identifier. | REQ-NMS-015 | The `docker build` command must execute successfully using the corrected base image definitions. |
| R4-S2 | completeness | high | Specify the required behavior when the `PORT` environment variable is not defined for either service (e.g., in REQ-NMS-001 and REQ-NMS-006). | The current requirements leave a critical startup failure mode undefined. The service should fail fast with a clear error message and non-zero exit code if it cannot determine which port to bind to. | REQ-NMS-001, REQ-NMS-006 | Execute the service entrypoint with an unset `PORT` variable and assert that the process exits with a non-zero status code and logs a descriptive error. |
| R4-S3 | ambiguity | high | The validation method "Structural comparability" (REQ-NMS-V02) is not defined. It should be clarified with a precise definition (e.g., AST-based comparison, a checklist of required function signatures and class definitions). | To ensure repeatable and objective validation, the criteria for structural equivalence must be concrete and measurable. Vague terms lead to subjective and inconsistent test outcomes. | REQ-NMS-V02 | Review the updated definition to confirm it can be translated into an automatable test or an unambiguous manual verification procedure. |
| R4-S4 | completeness | high | Define the expected behavior if the gRPC server fails to bind to its port (e.g., due to the port already being in use). This `bindAsync` failure path is currently unhandled in the requirements. | This is a common operational failure. The service should not hang or crash ambiguously; it should log a specific error (e.g., EADDRINUSE) and exit cleanly with a non-zero status code. | REQ-NMS-001, REQ-NMS-006 | Start a process that occupies the target port, then attempt to start the microservice. Verify it exits with the specified error message and exit code. |
| R4-S5 | consistency | medium | REQ-NMS-016 is inconsistent regarding dependency versioning. It claims `currencyservice` uses "exact versions" but then lists `paymentservice` dependencies with caret ranges (`^`), such as `"uuid": "^13.0.0"`. | The versioning policy is ambiguous. It should be clarified whether version ranges are permitted for some dependencies or if all dependencies across both services must be pinned to exact versions for reproducibility. | REQ-NMS-016 | Inspect the generated `package.json` files to confirm they adhere to the clarified, consistent versioning policy. |
| R4-S6 | testability | medium | The currency conversion logic in REQ-NMS-003 involves floating-point math, which can have precision variances. The requirement lacks test vectors to ensure a specific, correct outcome. | Without concrete test vectors (input values and exact expected outputs), validating the implementation's numerical precision is difficult and subject to environment-specific floating-point behavior. | REQ-NMS-003 | Add a small table of test cases (e.g., with zero values, large nanos, and a standard conversion) to the requirement. A unit test must pass using these exact inputs and outputs. |
| R4-S7 | completeness | medium | REQ-NMS-005 describes loading `currency_conversion.json` but does not specify the behavior if the file is missing or contains malformed JSON, which would cause the `require()` call to throw and crash the service. | Startup behavior on configuration errors should be explicit. The requirement should state that a missing or invalid data file is a fatal error and the service is expected to exit immediately. | REQ-NMS-005 | Attempt to start the service with the `currency_conversion.json` file deleted or malformed. Verify that the Node.js process exits with an error. |
| R4-S8 | traceability | low | REQ-NMS-008 refers to a `cardValidator` function but does not explicitly link it to the `simple-card-validator` package defined in REQ-NMS-016. The dependency is implicit. | Improving traceability makes requirements easier to understand in isolation. Explicitly stating that `cardValidator` is imported from the `simple-card-validator` package removes ambiguity. | REQ-NMS-008 | Verify the generated `charge.js` contains a `require('simple-card-validator')` statement. |
| R4-S9 | ambiguity | low | REQ-NMS-009 states the `InvalidCreditCard` constructor takes a `cardType` parameter that is "unused." This is ambiguous as to whether the generated code's function signature must include this parameter to be compliant. | For "Structural comparability" (REQ-NMS-V02) to be testable, it must be clear if function signatures must match the reference exactly, including unused parameters. | REQ-NMS-009 | Inspect the generated source code for the `InvalidCreditCard` constructor to verify its signature matches the clarified requirement. |
| R4-S10 | completeness | low | The gRPC health check (REQ-NMS-011) is defined to always return 'SERVING', making it a liveness probe, not a readiness probe. This distinction is not captured. | Explicitly stating the limited scope of the health check manages expectations for operators and prevents future confusion. It clarifies that this check does not validate dependencies or true service readiness. | REQ-NMS-011 | Add a sentence clarifying that the health check confirms the gRPC server is running (liveness) but does not validate its ability to process requests (readiness). |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:26:42 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | completeness | high | Add explicit requirement for ATTR_SERVICE_NAME import source | REQ-NMS-013 references ATTR_SERVICE_NAME but doesn't specify it comes from @opentelemetry/semantic-conventions. This is critical for correct resource attribution. | REQ-NMS-013 acceptance criteria | Verify import statement includes ATTR_SERVICE_NAME from semantic-conventions |
| R3-F2 | ambiguity | medium | Clarify whether bindAsync callback should check for error parameter | R3-S8 was accepted to specify bindAsync callback error handling, but the specific pattern (check err, log, exit) is not defined. The callback signature is `(err, port) => {}` and error handling varies by service. | REQ-NMS-001 and REQ-NMS-006 | Compare bindAsync callback implementations against reference for error checking |
| R3-F3 | completeness | medium | Specify the exact import destructuring pattern for OTel SDK packages | REQ-NMS-013 references "opentelemetry (sdk-node)" but doesn't specify if it's `const opentelemetry = require('@opentelemetry/sdk-node')` or `const { NodeSDK } = require('@opentelemetry/sdk-node')`. Both services may differ. | REQ-NMS-013 acceptance criteria | Verify import patterns match reference exactly |
| R3-F4 | consistency | medium | Document that currencyservice convert() error callback inconsistency is intentional | R2-S3 was accepted noting currencyservice passes err.message while paymentservice passes err object. The requirement should explicitly state this is reference-accurate, not a bug to fix. | REQ-NMS-003 acceptance criteria - add note | Verify generated convert() uses callback(err.message) not callback(err) |
| R3-F5 | testability | low | Add requirement for deterministic UUID generation in test mode | REQ-NMS-008 returns uuidv4() which is non-deterministic. For testing, a seeded or mock UUID would enable reproducible test assertions. Document if reference supports this or if tests must use regex matching. | REQ-NMS-008 or validation requirements | Define test approach for verifying transaction_id format without exact value matching |

#### Review Round R4

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:27:43 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R4-F1 | feasibility | critical | Correct inconsistent Docker image tags and digests in REQ-NMS-015. | The requirement as written is impossible to implement, as the specified `sha256` digests do not match the human-readable tags for the base images, which will cause any `docker build` to fail. This was previously noted in the applied R4-S1. |
| R4-F2 | feasibility | critical | Correct incompatible OpenTelemetry dependency versions in REQ-NMS-016. | The requirements specify OTel package versions from different, incompatible generations (`exporter-otlp-grpc@0.26.0` vs `sdk-node@0.211.0`). This will cause `npm install` to fail or lead to runtime errors. This was previously noted in the applied R3-S6. |
| R4-F3 | completeness | high | Add non-functional requirements (NFRs) for performance and resource consumption. | The document lacks any performance targets (e.g., p99 latency, QPS) or resource constraints (CPU/memory limits). Without these, the services cannot be properly load-tested, and their scalability cannot be meaningfully assessed. |
| R4-F4 | maintainability | medium | Clarify the source of truth between the Cross-Cutting Summary Table and detailed requirements. | The summary table is useful but could become out-of-sync with detailed requirements like REQ-NMS-013. The document should state that the detailed requirements take precedence over the summary table in case of conflict. |
| R4-F5 | security | critical | Remove the "Out of Scope" clause for "Security hardening beyond what exists in the reference". | This clause codifies existing vulnerabilities as acceptable. The requirements must establish a minimum security baseline, such as requiring dependency vulnerability scans (`npm audit`) and prohibiting insecure transport in production, regardless of the reference implementation's state. |

#### Review Round R5

**Reviewer**: claude-4 (claude-opus-4-5)
**Date**: 2026-02-20 20:40:16 UTC
**Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | testability | high | Add requirement for mock-friendly dependency injection patterns in charge.js — the hardcoded `new Date()` calls in expiration validation prevent deterministic testing of edge cases (month/year boundaries) | REQ-NMS-008 specifies `currentMonth = new Date().getMonth() + 1` inline, making it impossible to test expiration logic without monkey-patching Date. Reference implementation has this limitation, but validation requirements should specify how to verify expiration boundary conditions. | Add to REQ-NMS-V02 or create new REQ-NMS-V03 specifying test isolation strategy for time-dependent validation | Define test cases for expired card scenarios with explicit expected dates |
| R5-S2 | testability | high | Define validation criteria for error propagation paths — REQ-NMS-007 specifies `callback(err)` vs REQ-NMS-003 specifies `callback(err.message)` but no validation requirement covers verifying correct error type propagation | The inconsistent error callback patterns (object vs string) between services are specified but not validated. Without explicit test criteria, generated code could pass structural checks while having inverted error handling semantics. | Add to Validation Requirements section as REQ-NMS-V03: Error Handling Verification | Grep for callback error patterns and verify object vs message distinction per service |
| R5-S3 | testability | medium | Add validation requirement for gRPC service registration order — both services register multiple services (CurrencyService/PaymentService + Health) but no test verifies registration happens before server.start() | REQ-NMS-001 and REQ-NMS-006 specify registration and start sequence narratively, but V01/V02 don't verify temporal ordering. A generated implementation could call start() before addService() and still pass syntax/structural checks. | Create REQ-NMS-V04: Service Lifecycle Ordering specifying AST-based or line-order verification that addService precedes start | Static analysis of call ordering within bindAsync callback scope |
| R5-S4 | traceability | high | Add Feature IDs for cross-cutting concerns — REQ-NMS-011 through REQ-NMS-017 reference Features F-001 through F-007 but no Feature definition table exists in the document | The Traceability Matrix references features (F-001, F-002, etc.) that are never defined. Cannot trace requirements to features without knowing what F-001 through F-007 represent. This blocks validation of feature coverage completeness. | Add Feature Definition section before Functional Requirements, or add "Features" column definition to document header | Verify all referenced Feature IDs have definitions and all features have ≥1 requirement |
| R5-S5 | traceability | high | Link validation requirements to specific acceptance criteria they verify — REQ-NMS-V01 and V02 are generic statements not traced to specific testable assertions in REQ-NMS-001 through REQ-NMS-017 | Traceability Matrix maps functional requirements to features but validation requirements (V01, V02) aren't traced. Cannot determine if all acceptance criteria have corresponding validation coverage. | Extend Traceability Matrix with "Validation Req" column mapping each functional req to specific V-requirements | Cross-reference validation coverage matrix showing each acceptance criterion's validation method |
| R5-S6 | traceability | medium | Add requirement ID cross-references for the Cross-Cutting Summary Table — table entries describe behaviors specified in REQ-NMS-011 through REQ-NMS-017 but don't link back to those requirements | The summary table provides comparison view but doesn't indicate which requirement(s) specify each row's behavior. Readers cannot trace "Health check" row to REQ-NMS-011 without manually searching. | Add "Req IDs" column to Cross-Cutting Summary Table linking each concern to governing requirements | Verify all table cells trace to ≥1 requirement and all cross-cutting requirements appear in table |
| R5-S7 | consistency | high | Reconcile OTel package naming inconsistency — REQ-NMS-016 lists `@opentelemetry/exporter-otlp-grpc: "0.26.0"` but REQ-NMS-013 describes `OTLPTraceExporter` which comes from `@opentelemetry/exporter-trace-otlp-grpc` (different package) | The package `@opentelemetry/exporter-otlp-grpc` was renamed to `@opentelemetry/exporter-trace-otlp-grpc` in OTel JS v0.27.0. Version 0.26.0 of the old name exists but the class name `OTLPTraceExporter` suggests the new package. This creates ambiguity in which package to use. | Verify package name in REQ-NMS-016 against actual reference package.json and update if needed | npm info lookup to confirm package exists at specified version with expected exports |
| R5-S8 | consistency | medium | Standardize proto path construction terminology — REQ-NMS-001 uses `__dirname` + relative path while REQ-NMS-017 says currencyservice "uses `__dirname` + relative path" but REQ-NMS-010 says paymentservice uses `path.join(__dirname, '/proto/')` | Both services construct proto paths but the specification uses different description granularity. REQ-NMS-001 mentions paths without construction method; REQ-NMS-010 shows explicit path.join; REQ-NMS-017 summarizes differently. Should consistently specify construction method in all relevant requirements. | Amend REQ-NMS-001 acceptance criteria to explicitly state path construction: `path.join(__dirname, 'proto')` or equivalent | Grep for path construction patterns and verify consistency with requirement specifications |
| R5-S9 | testability | medium | Specify validation approach for callback-style vs promise-style async patterns — REQ-NMS-005 specifies `_getCurrencyData(callback)` loads data "synchronously" but passes to callback, creating ambiguous sync/async semantics | The requirement says "loads data synchronously via `require()`" then "passes to callback" — this callback-wrapping-sync pattern is unusual and testable differently than true async. Validation requirements don't address verifying the sync-in-callback-wrapper pattern. | Add clarification to REQ-NMS-005 that callback is invoked synchronously (same tick) and add test criterion to V02 | Verify callback invocation is synchronous via AST analysis or instrumented test runner |
| R5-S10 | consistency | medium | Align error code specification across error classes — REQ-NMS-009 states `CreditCardError` sets `this.code = 400` described as "(invalid argument)" but gRPC uses numeric codes where 3 = INVALID_ARGUMENT, not 400 (HTTP) | The error code 400 appears to be HTTP status code, but these errors propagate through gRPC where INVALID_ARGUMENT is code 3. If reference uses 400, document should clarify this is intentional HTTP-style code not gRPC code. Creates implementation ambiguity. | Add clarifying note to REQ-NMS-009 specifying whether code is HTTP-style (400) or gRPC-style (3), matching reference | Verify error.code value matches reference implementation behavior |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None identified in Appendix C from prior rounds requiring endorsement.

#### Review Round R6
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:41:00 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | consistency | medium | Standardize `package.json` metadata across both services. | REQ-NMS-016 highlights significant inconsistencies in metadata (e.g., `name` format, `version` scheme, `license`, `author`). This "metadata debt" complicates automated tooling for security scanning, license compliance, and dependency management. A consistent schema should be required. | Create a new cross-cutting requirement (e.g., REQ-NMS-018) defining a standard for `name`, `version`, `license`, and other key fields. | A linting script that validates both `package.json` files against a defined JSON schema during the build process. |
| R6-S2 | consistency | medium | Mandate a single, consistent OpenTelemetry initialization pattern. | REQ-NMS-013 describes two different OTel initialization patterns. `currencyservice` registers instrumentation unconditionally, while `paymentservice` does so conditionally. This inconsistency creates a subtle behavioral divergence that can complicate debugging and performance analysis. The `currencyservice` pattern is more robust and should be the standard. | Modify REQ-NMS-013 to require both services to register `GrpcInstrumentation` unconditionally at the module level, outside the `ENABLE_TRACING` check. | Structural diff of the OTel initialization blocks in both services to ensure they are identical and match the more robust pattern. |
| R6-S3 | testability | high | Isolate server start-up logic from module loading. | REQ-NMS-001 specifies that `main()` is called at the module level in `currencyservice`, causing the server to start immediately on `require('server.js')`. This is a common anti-pattern that makes the module untestable, as components cannot be imported for unit testing without triggering network side-effects. | Modify REQ-NMS-001 to require that server start-up logic be encapsulated in an exported function (e.g., `startServer`) and only invoked when the script is the main entry point (e.g., via `if (require.main === module)`). | A test script that can successfully `require('./server.js')` without the server binding to a port, and can then separately invoke the exported start-up function to launch the service. |
| R6-S4 | testability | high | Require external non-deterministic dependencies (time, random IDs) to be injectable. | REQ-NMS-008's logic relies on `new Date()` for expiration checks and `uuidv4()` for transaction IDs. This hard-codes non-deterministic dependencies, making the `charge` function difficult to test for specific edge cases (e.g., card expiring this month) and rendering test outputs unpredictable. | Modify REQ-NMS-008 to specify that the current time and the UUID generation function should be passed as injectable parameters to the `charge` function, with `new Date()` and `uuidv4()` used as default values in the production code path. | Generate unit tests that inject a fixed timestamp and a mock UUID generator into the `charge` function and assert predictable outcomes for card expiration and transaction ID generation. |
| R6-S5 | testability | high | Require custom error classes to be exported for type-checking. | REQ-NMS-009 states that the custom error classes in `charge.js` are module-local and not exported. This prevents test suites (and other modules) from using `instanceof` to verify the specific type of error thrown. Relying on matching the error message string is brittle and poor practice. | Modify REQ-NMS-009 to require that `CreditCardError`, `InvalidCreditCard`, `UnacceptedCreditCard`, and `ExpiredCreditCard` classes are exported from `charge.js` (e.g., via `module.exports`). | A unit test that calls the `charge` function with invalid data, catches the thrown error, and uses `expect(error).toBeInstanceOf(InvalidCreditCard)` to assert the specific error type. |
| R6-S6 | traceability | critical | Prohibit the logging of raw sensitive financial data (PCI). | REQ-NMS-007's acceptance criteria mandates logging the entire request object via `JSON.stringify(call.request)`. This includes the full credit card number, expiration date, and CVV, which is a critical security vulnerability and a violation of PCI-DSS compliance. It creates a toxic data trail that is impossible to trace and purge securely. | Modify REQ-NMS-007 to explicitly require that the request object is sanitized before logging, removing or masking all sensitive credit card fields. The log should only contain non-sensitive data like the amount and the last 4 digits of the card number. | Code review to confirm a sanitization function is used before logging. A unit test that captures log output and asserts that the full credit card number is NOT present. |
| R6-S7 | traceability | high | Mandate the inclusion of OpenTelemetry trace context in all request-scoped logs. | REQ-NMS-012 defines structured logging but misses the most critical element for a microservices architecture: request correlation. Without the `traceId` and `spanId` in logs, it's impossible to correlate a log entry with a specific distributed trace, severely hampering debugging and observability. | Modify REQ-NMS-012 to require that the pino logger configuration for both services is enhanced to automatically inject the active OpenTelemetry trace context (`trace_id`, `span_id`) into all log records. | In an integration test with tracing enabled, capture the JSON log output for a gRPC request and verify the presence and correct format of `trace_id` and `span_id` fields, matching the trace headers. |
| R6-S8 | traceability | medium | Mandate logging of full error objects, not just error messages. | REQ-NMS-003 specifies that the `currencyservice` error handler should log `err.message`, which discards the stack trace and other valuable context. This makes it nearly impossible to trace the origin of an error, especially for unexpected exceptions. `paymentservice` (REQ-NMS-007) has a better pattern (`console.warn(err)`). | Modify REQ-NMS-003 to align with the better pattern: require that the entire error object is logged (e.g., `logger.error({err}, 'conversion request failed')`) to preserve the stack trace and other properties for effective debugging. | Generate a unit test that forces the `convert` function to throw an error. Capture the log output and assert that it contains a `stack` property or the full serialized error object, not just the message string. |
| R6-S9 | traceability | low | Require code-level annotations to trace implementation back to requirements. | The current traceability matrix maps requirements to high-level validation methods like "Structural diff". This link is weak and can break silently. There is no mechanism to trace a specific line of code back to the exact acceptance criterion it is intended to satisfy, complicating validation and maintenance. | Create a new validation requirement (e.g., REQ-NMS-V03) mandating that key functional blocks in the generated code are annotated with comments linking them to the requirement ID they implement (e.g., `// Implements REQ-NMS-004`). | A validation script that parses all requirement IDs from the document and then scans the generated codebase to ensure that each functional requirement ID appears in a source code comment, reporting any missing links. |
| R6-S10 | consistency | medium | Mandate a single, consistent logger instantiation pattern per service. | REQ-NMS-012 describes an inconsistent pattern for `paymentservice` where one logger is created in `logger.js` and a second, separate instance is created inline in `charge.js`. This is an anti-pattern that can lead to misconfigured or unsynchronized log outputs and complicates centralized configuration. | Modify REQ-NMS-012 to require that each service instantiates its pino logger only once in a dedicated module (like `logger.js`) and that other modules (`charge.js`, `server.js`) import and use that single, shared instance. | Static code analysis to verify that `pino()` is called only once per service and that `charge.js` contains an `import` or `require` for the shared logger module instead of instantiating its own. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:43:24 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R7-F1 | completeness | high | REQ-NMS-013 references `resourceFromAttributes` but this function was renamed to `resourceFrom` in @opentelemetry/resources@2.x | The plan and requirements reference an API that may not exist in the specified version. Verify actual function name in @opentelemetry/resources@2.5.0 and update if needed. |
| R7-F2 | ambiguity | medium | REQ-NMS-008 specifies `cardNumber.replace('-', '')` but this only removes the first hyphen; card numbers may have multiple hyphens | The replace() without /g flag only removes first occurrence. Clarify if this is intentional (reference behavior) or should use replaceAll/regex for all hyphens. |
| R7-F3 | completeness | medium | REQ-NMS-015 specifies `npm install --only=production` but this flag is deprecated in npm 7+; use `npm ci --omit=dev` instead | The npm flag may cause warnings or behavior changes in newer npm versions bundled with node:20. Document if reference uses deprecated flag intentionally. |
| R7-F4 | ambiguity | medium | REQ-NMS-006 specifies `port = HipsterShopServer.PORT` as default but this reads undefined at class definition time | The static property `HipsterShopServer.PORT = process.env.PORT` is assigned after class definition, so using it as default parameter value reads undefined. Verify reference behavior. |
| R7-F5 | testability | low | REQ-NMS-V01 specifies `node --check` but doesn't specify Node.js version for syntax validation | Different Node.js versions support different syntax features. Specify node:20.x as the validation runtime to match Dockerfile base image. |

#### Review Round R6

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:45:37 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R6-F1 | clarity | medium | Clarify precedence between the Cross-Cutting Summary Table and detailed requirements. | The summary table is a useful overview, but it could diverge from the detailed requirements (REQ-NMS-011-017). The document should state that in case of conflict, the detailed requirement text is the source of truth to prevent implementation ambiguity. |
| R6-F2 | completeness | high | Clarify the purpose of the `@google-cloud/trace-agent` dependency in `currencyservice`. | REQ-NMS-016 lists this legacy GCP tracing agent alongside a full OpenTelemetry setup (REQ-NMS-013). The implementation plan does not show this package being used. The requirement should clarify if this is a redundant, vestigial dependency or if it has a specific purpose. |
| R6-F3 | completeness | medium | Acknowledge the logical flaw in the credit card expiration date check. | REQ-NMS-008 specifies a check `(currentYear * 12 + currentMonth) > (year * 12 + month)`. This incorrectly invalidates a card on its month of expiration. While reference fidelity is key, the requirement should note this logical defect to inform future maintenance and testing. |
| R6-F4 | testability | high | Add an explicit requirement for validating distributed trace context propagation. | The requirements for OpenTelemetry (REQ-NMS-013) focus on SDK setup but omit the primary goal: ensuring trace context is propagated across service calls. A requirement should be added to validate that a trace initiated in an upstream service is correctly continued in these Node.js services. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 21:17:27 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | traceability | high | Add traceability links from Validation Requirements back to their source functional requirements | REQ-NMS-V01 and REQ-NMS-V02 reference "All Node.js features" and "All" but don't enumerate which specific REQ-NMS-00X requirements they validate. This creates a gap where a validation requirement might not actually cover all functional requirements it claims to cover. | REQ-NMS-V01 and REQ-NMS-V02 sections — add explicit "Validates:" lists | Verify each functional requirement appears in at least one validation requirement's scope |
| R7-S2 | traceability | high | Establish forward references from functional requirements to their validation requirements | The traceability matrix only provides backward tracing (validation → feature). Each REQ-NMS-00X should include a "Validated by:" field indicating which REQ-NMS-V0X verifies it. Currently there's no way to confirm every functional requirement has a validation approach. | Add "Validated by: REQ-NMS-Vxx" field to each functional requirement | Check bidirectional coverage: every REQ-NMS-00X links to a V0X and vice versa |
| R7-S3 | traceability | medium | Document the relationship between cross-cutting requirements and the traceability matrix | REQ-NMS-011 through REQ-NMS-017 appear in the traceability matrix but their validation methods differ from the feature-based approach used for REQ-NMS-001-010. The matrix should clarify why cross-cutting requirements use different validation patterns. | Traceability Matrix section — add a note explaining cross-cutting requirement validation strategy | Confirm each cross-cutting requirement has a documented validation method consistent with its scope |
| R7-S4 | testability | high | Define concrete test cases for the EUR pivot conversion algorithm edge cases | REQ-NMS-003 specifies the two-step conversion but doesn't define test vectors for edge cases: zero amounts, same-currency conversion, currencies with extreme rates (JPY=126.40 vs EUR=1.0), or nano overflow scenarios. Without these, validation cannot verify correctness. | New section "REQ-NMS-T01: Currency Conversion Test Vectors" or extend REQ-NMS-003 | Execute test vectors against reference implementation to capture expected outputs |
| R7-S5 | testability | high | Specify expected behavior for invalid credit card scenarios in validation | REQ-NMS-008 and REQ-NMS-009 define error classes but there's no test specification for what card numbers should trigger each error type. Validators cannot verify error handling without knowing which inputs produce which exceptions. | Add test case specifications to REQ-NMS-008 or create REQ-NMS-T02 | Run reference implementation with known invalid cards to document expected error types |
| R7-S6 | testability | medium | Add validation specification for the _carry function arithmetic | REQ-NMS-004 defines the carry algorithm but REQ-NMS-V02 only mentions "structural comparability". The nano overflow logic (10^9 boundary) needs explicit test vectors to verify correctness beyond structural matching. | Extend REQ-NMS-V02 or create REQ-NMS-T03 with test vectors for _carry | Compute expected outputs for edge cases: nanos=2*10^9, units=1.5 with nanos=5*10^8, etc. |
| R7-S7 | traceability | medium | Link the Cross-Cutting Summary Table entries to their authoritative requirements | The table in cross-cutting requirements states facts (e.g., "Health check: Standalone check function") but doesn't reference which REQ-NMS-0XX defines this. Readers cannot verify table accuracy without tracing to source requirements. | Add requirement IDs to Cross-Cutting Summary Table cells or add a column for source requirement | Verify each table cell can be traced to a specific requirement's acceptance criteria |
| R7-S8 | testability | medium | Define validation approach for OpenTelemetry conditional registration difference | REQ-NMS-013 specifies that currencyservice registers GrpcInstrumentation ALWAYS while paymentservice does so ONLY when tracing enabled. The current validation (grep patterns) may not distinguish this behavioral difference from a structural one. | Extend REQ-NMS-013 or REQ-NMS-V02 with specific validation logic for conditional vs unconditional registration | AST analysis or line-number verification showing GrpcInstrumentation call is outside vs inside the ENABLE_TRACING block |
| R7-S9 | traceability | medium | Document which features map to which proto service definitions | Features F-001 and F-004 reference CurrencyService and PaymentService but the requirements don't trace these to the proto file structure. This creates ambiguity about whether the validation should verify proto contract compliance. | Add to REQ-NMS-001 and REQ-NMS-006: "Implements proto service: hipstershop.CurrencyService" and "hipstershop.PaymentService" respectively | Verify generated code registers services matching proto service names |
| R7-S10 | testability | medium | Specify how to validate that CVV is NOT validated as stated | REQ-NMS-008 explicitly states "CVV is NOT validated (demo only)" but there's no validation approach to confirm this negative requirement. A generator might accidentally add CVV validation without triggering any defined check. | Add to REQ-NMS-V02 or create REQ-NMS-T04: "Verify charge.js does not reference credit_card.credit_card_cvv in validation logic" | Grep for CVV-related variable usage in conditional/validation contexts in charge.js |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R6-S7: The suggestion to add traceability from Out of Scope items to why they're excluded addresses the same traceability gap I've identified — without justification links, the Out of Scope section appears arbitrary and cannot be validated against project constraints.

#### Review Round R8
**Reviewer**: gemini-2.5 (gemini-2.5-pro)
**Date**: 2026-02-20 21:18:02 UTC
**Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | traceability | high | Mandate In-Code Requirement Traceability Markers | The current validation relies on post-facto diffs. To ensure long-term maintainability and simplify auditing, key functional blocks (e.g., `convert`, `_carry`, `charge`) should include a comment linking back to the specific requirement ID they implement (e.g., `// Implements REQ-NMS-003`). | Add a new validation requirement (e.g., REQ-NMS-V03). | A static analysis check or `grep` script can be run against the generated codebase to ensure that comments referencing the key functional requirement IDs exist. |
| R8-S2 | traceability | critical | Pin Reference Implementation to an Immutable Commit SHA | The reference commit is "latest main (post-v0.10.4)", which is a moving target. This introduces ambiguity and non-repeatability into the validation process. The ground truth could change between generation attempts, invalidating previous results. | Modify the `Reference Commit` field in the document header. | The specified commit SHA must be a valid, existing commit in the reference repository. All validation diffs must be performed against this exact SHA. |
| R8-S3 | traceability | high | Enhance Traceability Matrix with Implementation Pointers | The document mentions a companion `plan-nodejs.md`. There is no explicit link between a requirement (the "what") and the part of the plan that implements it (the "how"). This makes it difficult to assess the implementation's coverage of the requirements. | Add a new column to the Traceability Matrix: `Implementation Pointer (plan-nodejs.md)`. | During review of `plan-nodejs.md`, verify that each requirement's pointer links to a concrete, relevant section or task within the plan. |
| R8-S4 | testability | critical | Require Generation of Unit Tests for Business Logic | REQ-NMS-008 and REQ-NMS-009 define complex validation and error logic in `charge.js`. REQ-NMS-V02 only validates structural equivalence, not behavioral correctness. The generated code could be structurally identical but functionally buggy. | Add a new requirement (e.g., REQ-NMS-018) specifying that unit tests for `charge.js` must also be generated, covering valid, invalid, unaccepted, and expired card scenarios. | Execute the generated test suite against the generated `charge.js` code. All tests must pass, and code coverage for the module should meet a defined threshold (e.g., 90%). |
| R8-S5 | testability | high | Require Generation of Unit Tests for Helper Functions | The `_carry` function (REQ-NMS-004) contains non-trivial arithmetic logic. Like the `charge` function, its behavioral correctness cannot be guaranteed by structural comparison alone. An off-by-one or floating-point precision error would not be caught. | Add a new requirement (or amend the one from R8-S4) to include generation of unit tests for helper functions with pure logic, specifically `_carry`. Tests should cover zero-carry, integer-carry, and fractional-carry cases. | Execute the generated test suite. All tests for `_carry` must pass, validating its arithmetic against known inputs and outputs. |
| R8-S6 | testability | high | Require a Basic gRPC Service Integration Test | The requirements specify server setup, but there's no requirement to validate that the gRPC services are correctly wired and accessible. A structural check can't confirm that the server will actually start, bind to the port, and respond to RPCs. | Add a new requirement for a minimal, self-contained integration test for each service. The test would spin up the server, connect a client, and perform a single successful RPC (e.g., `GetSupportedCurrencies` for currencyservice, `Health.Check` for both). | The generated integration test must be executed as part of the validation process and must pass, confirming the service can start and respond to a basic request. |
| R8-S7 | testability | medium | Require Testing of Environment Variable-Driven Behavior | REQ-NMS-013 and REQ-NMS-014 define conditional logic based on `ENABLE_TRACING` and `DISABLE_PROFILER`. There is no requirement to test that this logic is implemented correctly. | Add a new validation requirement specifying that the generated code's startup sequence must be tested with and without key environment variables set, asserting that the correct log messages ("Tracing enabled/disabled", "Profiler enabled/disabled") are produced. | Run the generated service entry points with different environment variable combinations and assert that the `stdout` matches expected output for each case. |
| R8-S8 | traceability | medium | Formalize the Cross-Cutting Summary Table as a Requirement | The "Cross-Cutting Summary Table" is presented as informative text within a blockquote. This makes its content non-normative and prone to becoming out of sync with the detailed requirements. Discrepancies between the summary and the details create ambiguity. | Re-frame the table under a new requirement, e.g., "REQ-NMS-018: Cross-Cutting Concern Consistency". The acceptance criteria would state that both services must adhere to the patterns defined in the table. | A manual review step in the validation process to check the generated code against each row of the summary table for compliance. |
| R8-S9 | testability | high | Specify Testing of Custom Error Propagation | REQ-NMS-009 defines custom error classes, and REQ-NMS-007 specifies they are caught and passed to the gRPC `callback(err)`. It's not explicitly tested that a thrown `ExpiredCreditCard` error results in the correct gRPC status and message at the service boundary. | Extend the unit test requirement from R8-S4. It must include tests that provide input to `charge()` designed to trigger each custom error, and the gRPC handler test must assert that the `callback` is invoked with an error object of the expected type. | The generated unit tests for `ChargeServiceHandler` must mock the `charge` function to throw specific custom errors and verify that the `callback` receives the correct error object. |
| R8-S10 | traceability | medium | Clarify Proto File Provenance and Management | The "Out of Scope" section states that proto files are "copied, not generated". However, the source of these copies is not specified. This creates a traceability gap for a core dependency of the services. | Add a sentence to the "Out of Scope" section clarifying the exact source of the proto files. E.g., "Proto files (`proto/`) are copied verbatim from the reference implementation at the specified commit SHA." | During validation, checksum the `proto/` directory in the generated output against the `proto/` directory at the pinned commit SHA in the reference repository. They must be identical. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 21:21:36 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R7-F1 | completeness | high | REQ-NMS-001 and REQ-NMS-006 don't specify the grpc.Server constructor options | The reference may pass options like `{'grpc.max_concurrent_streams': 100}` that affect scalability. Without this, generated code uses defaults that may differ from reference behavior. |
| R7-F2 | completeness | medium | REQ-NMS-003 doesn't specify error handling for unknown currency codes in conversion | If `from.currency_code` or `request.to_code` is not in the data object, `data[code]` returns undefined, causing NaN/Infinity in calculations. The requirement should specify expected error behavior. |
| R7-F3 | security | high | REQ-NMS-008 doesn't specify handling of very long or malformed card numbers | The simple-card-validator may behave unexpectedly with 100-character strings or non-numeric input. Input sanitization requirements are missing. |
| R7-F4 | maintainability | medium | REQ-NMS-012 specifies pino formatter but doesn't document the purpose of the severity mapping | The `level -> severity` transformation is GCP-specific logging convention. Without documentation, maintainers may remove it thinking it's unnecessary boilerplate. |
| R7-F5 | testability | medium | REQ-NMS-V01 specifies `node --check` but this only validates syntax, not import resolution | A file could pass syntax check but fail at runtime due to missing/misspelled requires. Validation should include `node -e "require('./server')"` style import tests. |

#### Review Round R8

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 21:23:20 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R8-F1 | clarity | critical | The `Reference Commit` is a placeholder (`a]b8c9d1...`). It must be replaced with an actual, valid commit SHA from the reference repository. | Without a pinned, immutable reference point, all validation based on "structural comparability" is non-repeatable and meaningless. This invalidates the entire premise of the exercise. |
| R8-F2 | ambiguity | medium | REQ-NMS-008 specifies `cardNumber.replace('-', '')`. This JavaScript method only replaces the *first* occurrence of a hyphen. The requirement should clarify if this is the intended behavior or if all hyphens should be stripped (e.g., using a global regex `replace(/-/g, '')`). | If a credit card number is passed with multiple hyphens (e.g., `4444-4444-4444-4444`), the current requirement would result in `44444444-4444-4444`, which is likely not the intent and would fail downstream processing. The requirement must match the reference's actual logic. |
| R8-F3 | maintainability | medium | REQ-NMS-015 requires `npm install --only=production`. This flag is deprecated in npm v7+ (bundled with Node 16+) and has been replaced by `--omit=dev`. | Using a deprecated flag will cause warnings during builds and may be removed in future npm versions. The requirement should specify whether the deprecated flag must be used for fidelity, or if the modern, equivalent flag (`--omit=dev`) is acceptable. |
| R8-F4 | clarity | high | REQ-NMS-006's description of the constructor `constructor(protoRoot, port = HipsterShopServer.PORT)` is logically flawed. | A class's static properties are not available in the scope of its own default parameter initializers. `HipsterShopServer.PORT` would be `undefined` at that point. The requirement must be updated to reflect the actual, working pattern used in the reference code (e.g., `this.port = port \|\| HipsterShopServer.PORT` inside the constructor body). |
| R8-F5 | traceability | low | The Cross-Cutting Summary Table references a non-existent requirement: `REQ-REGEN-004a`. | This is a dangling reference that creates confusion. The note should either be removed or the requirement it refers to should be defined or sourced. |

#### Review Round R9

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-21 02:19:55 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R9-S1 | testability | high | Add REQ-NMS-T01 specifying proto contract testing requirements: verify GetSupportedCurrencies returns exactly 34 codes, verify convert handles edge cases (same currency, zero amount, max precision nanos) | The requirements specify functional behavior but provide no testable scenarios for edge cases in the conversion logic. Without explicit test cases, regenerated code may handle boundary conditions differently than reference | New section "Test Scenarios" after Validation Requirements | Verify test scenarios are enumerable and cover documented arithmetic edge cases |
| R9-S2 | testability | high | Define mock/stub requirements for external dependencies: specify that `@google-cloud/profiler` and OTel SDK calls should be mockable via environment variables or test fixtures | REQ-NMS-013 and REQ-NMS-014 describe instrumentation but don't specify how generated code should support testing without live cloud services. This blocks unit test isolation | Add to Cross-Cutting Requirements section after REQ-NMS-014 | Confirm requirements include dependency injection or mock patterns for cloud services |
| R9-S3 | testability | medium | Specify expected error propagation behavior: define whether gRPC errors should use standard status codes (INVALID_ARGUMENT=3) or custom error messages for each CreditCardError subclass | REQ-NMS-009 defines error classes with `code = 400` but doesn't specify how this maps to gRPC status codes. Test assertions need explicit expected gRPC error behavior | Add to REQ-NMS-009 acceptance criteria | Grep for gRPC status code mapping or callback error format specification |
| R9-S4 | traceability | high | Add Feature-to-Requirement reverse mapping table showing which requirements satisfy each feature (F-001 through F-007) | The traceability matrix maps requirements to features but doesn't verify complete feature coverage. Cannot confirm all features have sufficient requirements without reverse lookup | New subsection in Traceability Matrix section | Count requirements per feature; verify no feature has zero coverage |
| R9-S5 | traceability | high | Add explicit requirement IDs for each file listed in plan outputs: map server.js → REQ-NMS-001, charge.js → REQ-NMS-008/009, index.js → REQ-NMS-010, etc. | Currently file-to-requirement mapping must be inferred. Validator cannot programmatically verify which requirements apply to which generated files without explicit mapping | Add "File Traceability" subsection after Traceability Matrix | Verify every output file has at least one requirement mapping |
| R9-S6 | traceability | medium | Specify validation requirement coverage: each REQ-NMS-nnn should reference which REQ-NMS-Vnn validation requirement(s) verify it | REQ-NMS-V01, V02, V03 exist but their scope is implicit. Without explicit mapping, validators may miss untested requirements | Extend Traceability Matrix with validation column | Confirm every functional requirement has explicit validation requirement reference |
| R9-S7 | testability | medium | Add negative test requirements for proto loading failures: specify expected behavior when MAIN_PROTO_PATH or HEALTH_PROTO_PATH files are missing/malformed | REQ-NMS-001 and REQ-NMS-017 specify proto loading but don't address failure modes. Generated code may differ in error handling for missing proto files | Add to REQ-NMS-001 acceptance criteria | Verify proto loading error handling is testable |
| R9-S8 | testability | medium | Define stateless verification requirement: specify that convert() and charge() produce deterministic outputs for identical inputs (except transaction_id UUID) | Implicit that pure functions should be deterministic, but not stated. Test frameworks need explicit determinism guarantees to write reliable assertions | Add as REQ-NMS-T02 in Test Scenarios section | Verify functional requirements identify non-deterministic elements (UUID only) |
| R9-S9 | traceability | medium | Add reference line numbers or code block hashes for each requirement derived from reference implementation | Requirements reference "companion plan" and "reference commit" but specific source locations are not traceable. Auditors cannot verify requirements accurately reflect reference without line-level tracing | Add "Reference Location" column to Traceability Matrix | Spot-check 3 requirements against reference commit for accuracy |
| R9-S10 | testability | low | Specify logger output capture requirements: define whether tests should verify log messages via stdout capture or pino test transport | REQ-NMS-012 specifies logging format but doesn't address test observability. Validators need guidance on how to assert logging behavior | Add to REQ-NMS-012 acceptance criteria | Confirm logging testability approach is specified |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R7-S1: The credit card error code semantics (400 vs gRPC INVALID_ARGUMENT) directly impacts testability — my R9-S3 reinforces this gap from a test assertion perspective
- R7-S3: Logging level requirements affect test verification of expected log outputs — complements my R9-S10 on log capture
- R8-S5: Transaction ID format validation supports my R9-S8 on identifying non-deterministic elements for testing

#### Review Round R10
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-21 02:20:27 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R10-S1 | traceability | high | Define the `F-xxx` feature codes referenced throughout the document. | Requirements like REQ-NMS-001 reference "Features: F-001", but these codes are not defined anywhere. This creates a traceability gap, as the link between a requirement and the high-level feature it implements is broken. The purpose and scope of each feature are unknown. | Add a new section "Feature Definitions" after "Scope" that lists and describes each feature code (F-001, F-002, etc.). | Verify that every `F-xxx` code used in the document has a corresponding entry in the new "Feature Definitions" section. |
| R10-S2 | testability | high | For REQ-NMS-008, add a table of explicit test vectors for credit card validation. | The requirement describes the validation logic abstractly. To make it concretely testable, it needs specific inputs and expected outcomes (pass/fail/specific error type). This removes ambiguity and provides a clear basis for acceptance testing. | Amend the acceptance criteria of REQ-NMS-008 with a markdown table of test cases (e.g., valid visa, invalid mastercard, expired card, non-accepted card type, card failing Luhn check). | Execute tests using the specified vectors and confirm that the service returns the expected success or error response for each case. |
| R10-S3 | testability | high | For REQ-NMS-003, add a concrete numerical example for a currency conversion. | The conversion logic involves multiple steps of division, multiplication, rounding, and flooring with large floating-point numbers. A single worked example (e.g., "10.50 USD to JPY") with the expected intermediate and final `units` and `nanos` values would make the requirement unambiguous and directly testable. | Add a new acceptance criterion to REQ-NMS-003 with a worked example, like: "e.g., A request to convert {units: 10, nanos: 500000000} from 'USD' to 'JPY' must return {units: 1191, nanos: 282245706, currency_code: 'JPY'}". | Implement a test case that performs the exact conversion specified in the example and asserts the result matches the requirement. |
| R10-S4 | traceability | medium | Explicitly trace requirements to the `plan-nodejs.md` companion document. | The document references a companion plan but does not trace requirements back to it. It's unclear which architectural decisions or sections in the plan led to which requirements, making it hard to verify that the requirements fully cover the plan's intent. | Add a `Plan Reference` field to each requirement, pointing to the relevant section(s) of `plan-nodejs.md`. Also add a corresponding column to the Traceability Matrix. | During review, verify that each requirement's `Plan Reference` points to a logical and relevant section of the companion plan. |
| R10-S5 | testability | medium | For REQ-NMS-009, specify the gRPC status code that each custom error class should map to. | The current error handling in REQ-NMS-007 passes the raw error object to the callback. For a gRPC client, the resulting gRPC status code is the primary observable outcome. Specifying this mapping (e.g., all `CreditCardError` subclasses should result in `INVALID_ARGUMENT`) makes the error behavior testable at the service boundary. | Add an acceptance criterion to REQ-NMS-009: "When thrown, all `CreditCardError` subclasses must result in a gRPC response with a status code of `3` (`INVALID_ARGUMENT`)." | Write a client-side test that sends invalid card data and asserts that the gRPC error received has the status code `INVALID_ARGUMENT`. |
| R10-S6 | traceability | medium | Formalize "Out of Scope" items as traceable requirements. | The "Out of Scope" section contains critical project decisions (e.g., no E2E testing). These decisions are not traceable. If they were formatted as formal requirements (e.g., REQ-NMS-OOS-001), they could be included in the traceability matrix, providing a formal record of what is intentionally being excluded. | Reformat the "Out of Scope" list into formal requirements with unique IDs, like "REQ-NMS-OOS-001: End-to-end integration testing with non-Node.js services shall not be performed as part of this work package." | Verify that the project's test plans and deliverables do not include work items that are explicitly defined as out of scope by these new requirements. |
| R10-S7 | testability | medium | For REQ-NMS-004, provide edge-case examples for the `_carry` function. | The `_carry` function handles arithmetic at the boundary between units and nanos. Its correctness depends on handling edge cases correctly. The current definition describes the implementation but not the expected behavior for inputs like `{units: 1, nanos: 999999999}` or `{units: 0.999999999, nanos: 1}`. | Add acceptance criteria to REQ-NMS-004 with specific input/output examples for edge cases, such as overflow and near-overflow conditions. | Write unit tests for the `_carry` function that use the specified edge-case inputs and assert the outputs are correct. |
| R10-S8 | traceability | low | Add requirement IDs to the rows of the `Cross-Cutting Summary Table`. | The summary table is a helpful overview, but its contents are not formally linked to the detailed requirements that specify the behavior. Adding the relevant requirement ID (e.g., adding `(REQ-NMS-011)` to the "Health check" row) would make the table a traceable index into the detailed specification. | Modify the `Cross-Cutting Summary Table` to include the primary requirement ID that governs the behavior described in each cell. | Check that each claim in the summary table has a corresponding requirement ID next to it, and that the ID points to the correct detailed requirement. |
| R10-S9 | testability | low | Make logging requirements more specific by defining expected log fields and values. | Requirements like REQ-NMS-002 state "Logs 'Getting supported currencies...'" but this is not easily machine-verifiable. The requirement should specify the expected structured log output, e.g., "A JSON log with `severity: 'info'` and `message: 'Getting supported currencies...'` is written to stdout." | Update all logging-related acceptance criteria (e.g., in REQ-NMS-002, -003, -007, -008, -013, -014) to specify the expected pino log structure, including severity and message content. | Configure test harnesses to capture stdout, parse the JSON logs, and assert that logs with the specified fields and values are present when the corresponding code path is executed. |
| R10-S10 | traceability | low | Clarify the source of truth for dependencies in REQ-NMS-016. | REQ-NMS-016 lists exact dependency versions, while the document states the "reference implementation serves as the ground truth". It's unclear if these versions are documenting what's in the reference commit or overriding it. This creates a traceability ambiguity. | Add a sentence to REQ-NMS-016 clarifying the source, e.g., "These versions are pinned as specified and may differ from the `package.json` at the reference commit SHA to ensure build stability." | Compare the versions in the requirement against the reference commit's `package.json`. The validation passes if they are either identical OR the new clarifying sentence has been added. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-21 02:24:42 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R7-F1 | completeness | high | REQ-NMS-003 doesn't specify expected behavior when source and target currency codes are identical | The convert function would divide and multiply by the same rate, potentially introducing floating-point drift. Should specify passthrough or identity conversion behavior. |
| R7-F2 | completeness | medium | REQ-NMS-011 doesn't specify health check timeout or deadline behavior | The check handler returns immediately with SERVING, but gRPC health checks have deadline semantics. Document that no timeout handling is implemented (reference-accurate). |
| R7-F3 | testability | high | REQ-NMS-V02 "Structural comparability" is still vaguely defined despite prior suggestions | The validation method should specify concrete criteria: same function names, same class names, same method signatures, same environment variables read — make it enumerable. |
| R7-F4 | security | medium | REQ-NMS-007 specifies logging full request JSON including credit card details | The `JSON.stringify(call.request)` logs PAN, CVV, expiration. Add note that this is reference-accurate but would require PCI remediation for production use. |
| R7-F5 | maintainability | medium | REQ-NMS-016 doesn't explain why currencyservice has more dependencies than paymentservice | currencyservice includes xml2js, async, google-protobuf that paymentservice lacks. Document these are reference-accurate even if not used in current implementation. |

#### Review Round R8

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-21 02:26:24 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R8-F1 | clarity | critical | The `Reference Commit` is a placeholder (`a]b8c9d1...`). It must be replaced with an actual, valid commit SHA from the reference repository. | Without a pinned, immutable reference point, all validation based on "structural comparability" is non-repeatable and meaningless. This invalidates the entire premise of the exercise. |
| R8-F2 | ambiguity | medium | REQ-NMS-008 specifies `cardNumber.replace('-', '')`. This JavaScript method only replaces the *first* occurrence of a hyphen. The requirement should clarify if this is the intended behavior or if all hyphens should be stripped (e.g., using a global regex `replace(/-/g, '')`). | If a credit card number is passed with multiple hyphens (e.g., `4444-4444-4444-4444`), the current requirement would result in `44444444-4444-4444`, which is likely not the intent and would fail downstream processing. The requirement must match the reference's actual logic. |
| R8-F3 | maintainability | medium | REQ-NMS-015 requires `npm install --only=production`. This flag is deprecated in npm v7+ (bundled with Node 16+) and has been replaced by `--omit=dev`. | Using a deprecated flag will cause warnings during builds and may be removed in future npm versions. The requirement should specify whether the deprecated flag must be used for fidelity, or if the modern, equivalent flag (`--omit=dev`) is acceptable. |
| R8-F4 | clarity | high | REQ-NMS-006's description of the constructor `constructor(protoRoot, port = HipsterShopServer.PORT)` is logically flawed. | A class's static properties are not available in the scope of its own default parameter initializers. `HipsterShopServer.PORT` would be `undefined` at that point. The requirement must be updated to reflect the actual, working pattern used in the reference code (e.g., `this.port = port \|\| HipsterShopServer.PORT` inside the constructor body). |
| R8-F5 | traceability | low | The Cross-Cutting Summary Table references a non-existent requirement: `REQ-REGEN-004a`. | This is a dangling reference that creates confusion. The note should either be removed or the requirement it refers to should be defined or sourced. |

