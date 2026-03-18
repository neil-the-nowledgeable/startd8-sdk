# Online Boutique C# Microservice — Requirements

**Date:** 2026-02-18
**Companion Plan:** `plan-csharp.md`
**Reference Implementation:** Google Online Boutique microservices-demo (C# service only)
**Reference Commit:** latest main (post-v0.10.4)

---

## Scope

This document defines acceptance criteria for generating the single C# microservice from the Online Boutique demo: cartservice. The reference implementation serves as the ground truth for all requirements.

---

## Functional Requirements

### REQ-CMS-001: ASP.NET Core Host (Program.cs)

**Priority:** P1
**Features:** F-001
**Acceptance criteria:**
- `Program.cs` uses top-level statements (C# 9+ minimal hosting pattern)
- `using Microsoft.AspNetCore.Hosting`, `using Microsoft.Extensions.Hosting`, `using cartservice`
- Calls `CreateHostBuilder(args).Build().Run()`
- `static IHostBuilder CreateHostBuilder(string[] args)` is a local function returning `Host.CreateDefaultBuilder(args).ConfigureWebHostDefaults(webBuilder => { webBuilder.UseStartup<Startup>(); })`

### REQ-CMS-002: Startup Configuration (Startup.cs)

**Priority:** P1
**Features:** F-001
**Acceptance criteria:**
- `Startup.cs` in namespace `cartservice`
- `public class Startup` with constructor accepting `IConfiguration configuration` and public property `IConfiguration Configuration { get; }`
- `ConfigureServices(IServiceCollection services)`:
  - Reads 3 config keys: `REDIS_ADDR`, `SPANNER_PROJECT`/`SPANNER_CONNECTION_STRING`, `ALLOYDB_PRIMARY_IP`
  - Cart store selection priority:
    1. If `REDIS_ADDR` is not empty: `services.AddStackExchangeRedisCache(options => { options.Configuration = redisAddress })` + `services.AddSingleton<ICartStore, RedisCartStore>()`
    2. Else if `SPANNER_PROJECT` or `SPANNER_CONNECTION_STRING` is not empty: `services.AddSingleton<ICartStore, SpannerCartStore>()`
    3. Else if `ALLOYDB_PRIMARY_IP` is not empty: logs `"Creating AlloyDB cart store"` via `Console.WriteLine` + `services.AddSingleton<ICartStore, AlloyDBCartStore>()`
    4. Else (fallback): logs `"Redis cache host(hostname+port) was not specified. Starting a cart service using in memory store"` via `Console.WriteLine` + `services.AddDistributedMemoryCache()` + `services.AddSingleton<ICartStore, RedisCartStore>()`
  - `services.AddGrpc()` at end
- `Configure(IApplicationBuilder app, IWebHostEnvironment env)`:
  - If `env.IsDevelopment()`: `app.UseDeveloperExceptionPage()`
  - `app.UseRouting()`
  - `app.UseEndpoints(endpoints => { ... })`:
    - `endpoints.MapGrpcService<CartService>()`
    - `endpoints.MapGrpcService<cartservice.services.HealthCheckService>()`
    - `endpoints.MapGet("/", async context => { await context.Response.WriteAsync("Communication with gRPC endpoints must be made through a gRPC client. To learn how to create a client, visit: https://go.microsoft.com/fwlink/?linkid=2086909") })`

### REQ-CMS-003: CartService gRPC Implementation

**Priority:** P1
**Features:** F-002
**Acceptance criteria:**
- `services/CartService.cs` in namespace `cartservice.services`
- `public class CartService : Hipstershop.CartService.CartServiceBase`
- Fields:
  - `private readonly static Empty Empty = new Empty()` (cached singleton)
  - `private readonly ICartStore _cartStore` (injected via constructor DI)
- Constructor: `public CartService(ICartStore cartStore)` stores `_cartStore = cartStore`
- `public async override Task<Empty> AddItem(AddItemRequest request, ServerCallContext context)`:
  - `await _cartStore.AddItemAsync(request.UserId, request.Item.ProductId, request.Item.Quantity)`
  - Returns `Empty`
- `public override Task<Cart> GetCart(GetCartRequest request, ServerCallContext context)`:
  - Returns `_cartStore.GetCartAsync(request.UserId)` (no await — returns Task directly)
- `public async override Task<Empty> EmptyCart(EmptyCartRequest request, ServerCallContext context)`:
  - `await _cartStore.EmptyCartAsync(request.UserId)`
  - Returns `Empty`

### REQ-CMS-004: ICartStore Interface

**Priority:** P1
**Features:** F-003
**Acceptance criteria:**
- `cartstore/ICartStore.cs` in namespace `cartservice.cartstore`
- `public interface ICartStore` with 4 methods:
  - `Task AddItemAsync(string userId, string productId, int quantity)`
  - `Task EmptyCartAsync(string userId)`
  - `Task<Hipstershop.Cart> GetCartAsync(string userId)`
  - `bool Ping()`

### REQ-CMS-005: RedisCartStore (IDistributedCache Backend)

**Priority:** P1
**Features:** F-003
**Acceptance criteria:**
- `cartstore/RedisCartStore.cs` in namespace `cartservice.cartstore`
- `public class RedisCartStore : ICartStore`
- Field: `private readonly IDistributedCache _cache` (injected via constructor)
- `AddItemAsync(string userId, string productId, int quantity)`:
  - Logs via `Console.WriteLine($"AddItemAsync called with userId={userId}, productId={productId}, quantity={quantity}")`
  - Gets existing cart via `_cache.GetAsync(userId)`
  - If `value == null`: creates new `Hipstershop.Cart()`, sets `UserId`, adds new `CartItem`
  - If exists: parses via `Hipstershop.Cart.Parser.ParseFrom(value)`, finds existing item via `cart.Items.SingleOrDefault(i => i.ProductId == productId)`, either adds new item or increments `existingItem.Quantity += quantity`
  - Saves via `_cache.SetAsync(userId, cart.ToByteArray())`
  - Catches `Exception ex`: throws `new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"))`
- `EmptyCartAsync(string userId)`:
  - Logs via `Console.WriteLine`
  - Creates new empty `Hipstershop.Cart()`, sets via `_cache.SetAsync(userId, cart.ToByteArray())`
  - Does NOT delete the key — overwrites with empty cart
  - Same exception pattern
- `GetCartAsync(string userId)`:
  - Logs via `Console.WriteLine`
  - Gets via `_cache.GetAsync(userId)`
  - If `value != null`: returns `Hipstershop.Cart.Parser.ParseFrom(value)`
  - If null: returns `new Hipstershop.Cart()` (empty cart, no error)
  - Same exception pattern
- `Ping()`: try block returns `true`, catch returns `false`

### REQ-CMS-006: SpannerCartStore (Cloud Spanner Backend)

**Priority:** P1
**Features:** F-004
**Acceptance criteria:**
- `cartstore/SpannerCartStore.cs` in namespace `cartservice.cartstore`
- `public class SpannerCartStore : ICartStore`
- Static fields: `TableName = "CartItems"`, `DefaultInstanceName = "onlineboutique"`, `DefaultDatabaseName = "carts"`
- Instance field: `private readonly string databaseString`
- Constructor `SpannerCartStore(IConfiguration configuration)`:
  - Reads `SPANNER_PROJECT`, `SPANNER_INSTANCE`, `SPANNER_DATABASE`, `SPANNER_CONNECTION_STRING`
  - If `SPANNER_CONNECTION_STRING` is not empty: uses it directly via `SpannerConnectionStringBuilder`
  - Else: builds connection string from `projects/{project}/instances/{instance}/databases/{database}` with defaults for instance/database
  - Logs connection string via `Console.WriteLine`
- `AddItemAsync`: uses `SpannerConnection.RunWithRetriableTransactionAsync` with SELECT for current quantity, then `CreateInsertOrUpdateCommand` with parameters
- `GetCartAsync`: uses `SpannerConnection.CreateSelectCommand` with `WHERE userId = @userId`, iterates reader to build `Cart` with `CartItem` objects
- `EmptyCartAsync`: uses `SpannerConnection.CreateDmlCommand` with `DELETE FROM {TableName} WHERE userId = @userId`
- All methods use `SpannerParameterCollection` with `SpannerDbType.String`/`Int64`
- All catch `Exception ex` → throw `new RpcException(new Status(StatusCode.FailedPrecondition, ...))`
- `Ping()`: try returns `true`, catch returns `false`

### REQ-CMS-007: AlloyDBCartStore (Npgsql/PostgreSQL Backend)

**Priority:** P1
**Features:** F-004
**Acceptance criteria:**
- `cartstore/AlloyDBCartStore.cs` in namespace `cartservice.cartstore`
- `public class AlloyDBCartStore : ICartStore`
- Fields: `private readonly string tableName`, `private readonly string connectionString`
- Constructor `AlloyDBCartStore(IConfiguration configuration)`:
  - Creates `SecretManagerServiceClient.Create()`
  - Reads `PROJECT_ID`, `ALLOYDB_SECRET_NAME` from configuration
  - Fetches password via `client.AccessSecretVersion(new SecretVersionName(projectId, secretId, "latest"))`
  - Converts payload: `result.Payload.Data.ToStringUtf8().TrimEnd('\r', '\n')`
  - User hardcoded: `alloyDBUser = "postgres"`
  - Reads `ALLOYDB_DATABASE_NAME`, `ALLOYDB_PRIMARY_IP`
  - Builds connection string: `"Host=" + primaryIPAddress + ";Username=" + alloyDBUser + ";Password=" + alloyDBPassword + ";Database=" + databaseName`
  - Reads `ALLOYDB_TABLE_NAME`
- `AddItemAsync`: uses `NpgsqlDataSource.Create(connectionString)`, SELECT for current quantity, then `INSERT ... ON CONFLICT (userId, productId) DO UPDATE SET quantity = {total}`
- `GetCartAsync`: SELECT productId/quantity, iterates reader with `GetString(0)`/`GetInt32(1)`
- `EmptyCartAsync`: `DELETE FROM {tableName} WHERE userID = '{userId}'`
- All use inline SQL (string interpolation, not parameterized — matches reference)
- Error message pattern: `"Unable to access cart storage due to an internal error. {ex}"`
- `Ping()`: try returns `true`, catch returns `false`

### REQ-CMS-008: HealthCheckService (gRPC Health)

**Priority:** P1
**Features:** F-002
**Acceptance criteria:**
- `services/HealthCheckService.cs` in namespace `cartservice.services`
- `internal class HealthCheckService : HealthBase` (uses `static Grpc.Health.V1.Health` import for `HealthBase`)
- Field: `private ICartStore _cartStore { get; }` (property, not field — injected via constructor)
- Constructor: `public HealthCheckService(ICartStore cartStore)` stores `_cartStore = cartStore`
- `public override Task<HealthCheckResponse> Check(HealthCheckRequest request, ServerCallContext context)`:
  - Logs `"Checking CartService Health"` via `Console.WriteLine`
  - Returns `Task.FromResult(new HealthCheckResponse { Status = _cartStore.Ping() ? ServingStatus.Serving : ServingStatus.NotServing })`
- No `Watch` method (only `Check`)
- Health depends on cart store `Ping()` result (not hardcoded SERVING)

---

## Cross-Cutting Requirements

### REQ-CMS-009: ASP.NET Core Configuration (appsettings.json)

**Priority:** P1
**Features:** F-005
**Acceptance criteria:**
- `appsettings.json` with:
  - `Logging.LogLevel`: `Default: "Information"`, `Microsoft: "Warning"`, `Microsoft.Hosting.Lifetime: "Information"`
  - `AllowedHosts: "*"`
  - `Kestrel.EndpointDefaults.Protocols: "Http2"` (required for gRPC)

### REQ-CMS-009a: No OpenTelemetry Instrumentation

**Priority:** P1
**Features:** All
**Acceptance criteria:**
- cartservice does NOT use OpenTelemetry instrumentation. The reference implementation has no OTel imports, no TracerProvider, no span exporter, and no instrumentation middleware.
- Do NOT add OTel instrumentation as an improvement. Incomplete OTel (e.g., TracerProvider without exporter) produces silent failures that are worse than no instrumentation.
- If OTel is desired in the future, it requires a separate requirement specifying the complete instrumentation chain: TracerProvider, exporter, batch processor, and ASP.NET Core instrumentation middleware.
- The Dockerfile does NOT include a `HEALTHCHECK` instruction. Health checking is handled by the gRPC health protocol via `HealthCheckService` (REQ-CMS-008).

### REQ-CMS-010: .csproj Project File

**Priority:** P1
**Features:** F-005
**Acceptance criteria:**
- `cartservice.csproj` with SDK `Microsoft.NET.Sdk.Web`
- `<TargetFramework>net10.0</TargetFramework>`
- Package references:
  - `Grpc.AspNetCore` version `2.76.0`
  - `Grpc.HealthCheck` version `2.76.0`
  - `Microsoft.Extensions.Caching.StackExchangeRedis` version `10.0.2`
  - `Google.Cloud.Spanner.Data` version `5.12.0`
  - `Npgsql` version `10.0.1`
  - `Google.Cloud.SecretManager.V1` version `2.7.0`
- Protobuf item: `<Protobuf Include="protos\Cart.proto" GrpcServices="Both" />`

### REQ-CMS-011: Solution File

**Priority:** P2
**Features:** F-005
**Acceptance criteria:**
- `cartservice.sln` — Visual Studio Solution Format Version 12.00
- 2 projects:
  - `cartservice` (src) with GUID `{2348C29F-E8D3-4955-916D-D609CBC97FCB}` referencing `src\cartservice.csproj`
  - `cartservice.tests` with GUID `{59825342-CE64-4AFA-8744-781692C0811B}` referencing `tests\cartservice.tests.csproj`
- Both use `FAE04EC0-301F-11D3-BF4B-00C04F79EFBC` project type GUID (C#)
- Configuration platforms: Debug/Release × Any CPU/x64/x86

### REQ-CMS-012: Unit Tests (xUnit)

**Priority:** P2
**Features:** F-006
**Acceptance criteria:**
- `tests/CartServiceTests.cs` in namespace `cartservice.tests`
- `public class CartServiceTests` with `private readonly IHostBuilder _host` field
- Constructor sets up `HostBuilder` with `ConfigureWebHost` using `UseStartup<Startup>()` and `UseTestServer()`
- 3 test methods using `[Fact]` attribute:
  - `GetItem_NoAddItemBefore_EmptyCartReturned`:
    - Creates test server, `GrpcChannel.ForAddress` with `HttpClient` from `server.GetTestClient()`
    - Random `userId = Guid.NewGuid().ToString()`
    - Calls `GetCartAsync`, asserts `Assert.NotNull(cart)` and `Assert.Equal(new Cart(), cart)`
  - `AddItem_ItemExists_Updated`:
    - Adds same item (productId "1", quantity 1) twice
    - Verifies `cart.UserId == userId`, `Assert.Single(cart.Items)`, `cart.Items[0].Quantity == 2`
    - Cleanup: `EmptyCartAsync`
  - `AddItem_New_Inserted`:
    - Adds item, verifies single item in cart
    - Empties cart, verifies `Assert.Empty(cart.Items)`

### REQ-CMS-013: Test Project File

**Priority:** P2
**Features:** F-006
**Acceptance criteria:**
- `tests/cartservice.tests.csproj` with SDK `Microsoft.NET.Sdk`
- `<TargetFramework>net10.0</TargetFramework>`, `<IsPackable>false</IsPackable>`
- Package references:
  - `Grpc.Net.Client` version `2.76.0`
  - `Microsoft.AspNetCore.TestHost` version `10.0.2`
  - `Microsoft.NET.Test.Sdk` version `18.0.1`
  - `xunit` version `2.9.3`
  - `xunit.runner.visualstudio` version `3.1.5`
- Project reference: `<ProjectReference Include="..\src\cartservice.csproj" />`

### REQ-CMS-014: Multi-Stage Dockerfile

**Priority:** P2
**Features:** F-007
**Acceptance criteria:**
- 2-stage Dockerfile:
- Stage 1 `builder`: `FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0.100-noble@sha256:c7445f141c04f1a6b454181bd098dcfa606c61ba0bd213d0a702489e5bd4cd71 AS builder`
  - `ARG TARGETARCH`
  - `WORKDIR /app`
  - `COPY cartservice.csproj .`
  - `RUN dotnet restore cartservice.csproj -a $TARGETARCH`
  - `COPY . .`
  - `RUN dotnet publish cartservice.csproj -p:PublishSingleFile=true -a $TARGETARCH --self-contained true -p:PublishTrimmed=true -p:TrimMode=full -c release -o /cartservice`
- Stage 2: `FROM mcr.microsoft.com/dotnet/runtime-deps:10.0.0-noble-chiseled@sha256:b857c8cb8d929183cfe4c6dd9994abba92a2639dd2dbaf06005379f815991604`
  - `WORKDIR /app`
  - `COPY --from=builder /cartservice .`
  - `EXPOSE 7070`
  - `ENV DOTNET_EnableDiagnostics=0 ASPNETCORE_HTTP_PORTS=7070`
  - `USER 1000` (non-root)
  - `ENTRYPOINT ["/app/cartservice"]`

### REQ-CMS-015: Cart Proto Definition

**Priority:** P1
**Features:** F-002
**Acceptance criteria:**
- `protos/Cart.proto` defines package `hipstershop` with `proto3` syntax
- Service `CartService` with 3 RPCs: `AddItem(AddItemRequest) returns (Empty)`, `GetCart(GetCartRequest) returns (Cart)`, `EmptyCart(EmptyCartRequest) returns (Empty)`
- Messages: `CartItem` (product_id string, quantity int32), `AddItemRequest` (user_id string, item CartItem), `EmptyCartRequest` (user_id string), `GetCartRequest` (user_id string), `Cart` (user_id string, repeated CartItem items), `Empty` (empty)
- Note: This is a service-specific proto, NOT the shared `demo.proto` — cartservice uses its own proto definition

---

## Validation Requirements

### REQ-CMS-V01: Syntax Validity

**Priority:** P1
**Features:** All C# features
**Acceptance criteria:**
- All generated `.cs` files compile without syntax errors
- All generated `.csproj` files are valid XML
- `appsettings.json` is valid JSON

### REQ-CMS-V02: Structural Comparability

**Priority:** P1
**Features:** All
**Acceptance criteria:**
- Generated code implements the same classes, interfaces, and methods as the reference
- Class names match: `Startup`, `CartService`, `HealthCheckService`, `ICartStore`, `RedisCartStore`, `SpannerCartStore`, `AlloyDBCartStore`, `CartServiceTests`
- The same configuration keys are read with the same fallback logic
- File count and directory structure match the plan's output file specifications

---

## Out of Scope

The following are explicitly NOT requirements for this validation:

- End-to-end integration testing with non-C# services
- Kubernetes deployment or service mesh configuration
- Performance benchmarking
- Security hardening beyond what exists in the reference
- Code style or formatting preferences (structural equivalence is sufficient)
- `.dockerignore` files
- `Dockerfile.debug` (development-only Dockerfile)
- Apache 2.0 license headers (copyright boilerplate)

---

## Traceability Matrix

| Requirement | Feature(s) | Validation Method |
|------------|------------|-------------------|
| REQ-CMS-001 | F-001 | Structural diff against reference `Program.cs` |
| REQ-CMS-002 | F-001 | Structural diff against reference `Startup.cs` |
| REQ-CMS-003 | F-002 | Structural diff against reference `CartService.cs` |
| REQ-CMS-004 | F-003 | Structural diff against reference `ICartStore.cs` |
| REQ-CMS-005 | F-003 | Structural diff against reference `RedisCartStore.cs` |
| REQ-CMS-006 | F-004 | Structural diff against reference `SpannerCartStore.cs` |
| REQ-CMS-007 | F-004 | Structural diff against reference `AlloyDBCartStore.cs` |
| REQ-CMS-008 | F-002 | Grep for `HealthBase` and `Ping()` integration |
| REQ-CMS-009 | F-005 | JSON comparison against reference `appsettings.json` |
| REQ-CMS-009a | All | Grep for absence of OpenTelemetry imports |
| REQ-CMS-010 | F-005 | XML comparison of `.csproj` package references |
| REQ-CMS-011 | F-005 | Content comparison against reference `.sln` |
| REQ-CMS-012 | F-006 | Structural diff against reference `CartServiceTests.cs` |
| REQ-CMS-013 | F-006 | XML comparison of test `.csproj` |
| REQ-CMS-014 | F-007 | Dockerfile structural comparison |
| REQ-CMS-015 | F-002 | Proto comparison against reference `Cart.proto` |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **ambiguity**: 3 suggestions applied (R1-S2, R3-S2, R4-S1)
- **completeness**: 3 suggestions applied (R1-S5, R2-S2, R2-S3)
- **consistency**: 4 suggestions applied (R4-S5, R5-S1, R5-S2, R6-S1)
- **feasibility**: 8 suggestions applied (R7-S1, R7-S2, R7-S3, R8-S1, R8-S2, R8-S4, R1-S6, R3-S6)
- **testability**: 3 suggestions applied (R1-S4, R2-S6, R3-S8)
- **unknown**: 15 suggestions applied (R1-S8, R1-S9, R2-S7, R1-F2, R1-F3, R1-F5, R3-S9, R1-F1, R3-F1, R3-F2, R3-F3, R3-F4, R3-F5, R3-F6, R3-F8)

### Areas Needing Further Review

- **traceability**: 2 accepted (R4-S9, R4-S10) — needs 1 more to reach threshold of 3

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S2 | Clarify the protos/ directory location relative to project structure | claude-4 (claude-opus-4-5) | The ambiguity between REQ-CMS-015's 'protos/Cart.proto' and REQ-CMS-010's 'protos\Cart.proto' creates genuine confusion about whether this is relative to src/ or the repository root. This affects both the .csproj Include path and Dockerfile COPY behavior, which are critical for successful builds. | 2026-02-20 19:21:06 UTC |
| R1-S4 | Define expected behavior when Spanner/AlloyDB configuration is incomplete | claude-4 (claude-opus-4-5) | REQ-CMS-002 defines fallback priority but leaves ambiguous what happens with partial configuration (e.g., SPANNER_PROJECT set but SPANNER_INSTANCE missing). This is a real operational scenario that could cause silent failures or unexpected fallback behavior. | 2026-02-20 19:21:06 UTC |
| R1-S5 | Specify gRPC channel options for test client in REQ-CMS-012 | claude-4 (claude-opus-4-5) | TestServer requires specific HttpHandler configuration for HTTP/2 over non-TLS connections. Without this, tests will fail at runtime. This is a common pitfall in gRPC testing that should be explicitly addressed. | 2026-02-20 19:21:06 UTC |
| R1-S6 | Verify SecretManager API availability in test/local environments | claude-4 (claude-opus-4-5) | REQ-CMS-007 requires SecretManagerServiceClient.Create() which needs GCP credentials. Without guidance on local development or CI testing strategy, developers cannot run the AlloyDBCartStore code path in non-GCP environments. | 2026-02-20 19:21:06 UTC |
| R1-S8 | Clarify IDistributedCache injection path for fallback RedisCartStore | claude-4 (claude-opus-4-5) | The DI registration sequence in REQ-CMS-002 case 4 is subtle - AddDistributedMemoryCache() provides IDistributedCache which RedisCartStore's constructor expects. This relationship should be explicit to prevent confusion during implementation. | 2026-02-20 19:21:06 UTC |
| R1-S9 | Add Feature ID definitions to document | claude-4 (claude-opus-4-5) | The Traceability Matrix references F-001 through F-007 but these are never defined. This makes the traceability matrix unusable for understanding feature coverage and impacts requirements validation. | 2026-02-20 19:21:06 UTC |
| R2-S2 | Specify the concrete operation performed within Ping() method's try block | gemini-2.5 (gemini-2.5-pro) | The Ping() methods in REQ-CMS-005/006/007 only specify 'try block returns true, catch returns false' without defining what operation verifies connectivity. A meaningful health check requires an actual operation (e.g., SELECT 1). This makes the requirement untestable. | 2026-02-20 19:21:06 UTC |
| R2-S3 | Define behavior if AlloyDBCartStore constructor fails to retrieve credentials from Secret Manager | gemini-2.5 (gemini-2.5-pro) | Secret retrieval can fail due to network issues, missing permissions, or misconfiguration. The requirement should specify whether this causes a startup crash (fast-fail) or some other behavior. This is critical for operational predictability. | 2026-02-20 19:21:06 UTC |
| R2-S6 | Clarify required scope of test coverage including negative test cases | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-012 specifies only three happy-path tests. The requirements should clarify whether this is intentionally minimal (matching reference) or if additional edge case/failure mode tests are expected. This affects test completeness assessment. | 2026-02-20 19:21:06 UTC |
| R2-S7 | Correct the fallback log message to reflect actual implementation | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-002 specifies logging 'using in memory store' but the fallback uses RedisCartStore with IDistributedMemoryCache. This mismatch between log message and actual behavior would hinder debugging. Should verify against reference and correct accordingly. | 2026-02-20 19:21:06 UTC |
| R1-F2 | Specify HTTP/2 handler configuration requirements for test client |  | Same as R1-S1 - the HTTP/2 handler configuration is technically required for gRPC tests to function | 2026-02-20 19:24:20 UTC |
| R1-F3 | Add Ping() operation specifics to REQ-CMS-005, 006, 007 |  | Same as R1-S2 - concrete health check operations are needed for meaningful validation | 2026-02-20 19:24:20 UTC |
| R1-F5 | Specify AlloyDBCartStore startup failure behavior when credentials unavailable |  | Same as R1-S5 - fast-fail behavior should be explicitly stated for operational clarity | 2026-02-20 19:24:20 UTC |
| R3-S2 | Clarify whether UserId must be set in all cart store return values for empty carts | claude-4 (claude-opus-4-5) | This is a genuine ambiguity that affects functional correctness. AddItemAsync explicitly sets UserId on new carts, but GetCartAsync's empty cart return doesn't specify this. Consistent behavior is needed for client code expectations. | 2026-02-20 19:50:27 UTC |
| R3-S6 | Specify behavior when Secret Manager access fails in AlloyDBCartStore constructor | claude-4 (claude-opus-4-5) | Constructor failures during DI would crash the entire service at startup. This is a critical operational concern that needs explicit specification for how to handle secret access failures gracefully or fail fast. | 2026-02-20 19:50:27 UTC |
| R3-S8 | Define expected test behavior when Redis is unavailable in in-memory fallback mode | claude-4 (claude-opus-4-5) | REQ-CMS-012 doesn't specify which cart store backend tests run against, which is important for CI environments. Clarifying that tests use in-memory cache fallback ensures reproducible test execution without external dependencies. | 2026-02-20 19:50:27 UTC |
| R3-S9 | Add Feature IDs to the Feature list or define features referenced in traceability matrix | claude-4 (claude-opus-4-5) | The traceability matrix references F-001 through F-007 but these are never defined. This breaks bidirectional traceability, which is a fundamental requirement for proper requirements management. | 2026-02-20 19:50:27 UTC |
| R4-S1 | Define the concrete implementation of the Ping() method for each ICartStore implementation | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-005/006/007 only state 'try block returns true, catch returns false' without specifying what operation verifies connectivity. This ambiguity directly impacts health check reliability (REQ-CMS-008) and is critical for implementation. | 2026-02-20 19:50:27 UTC |
| R4-S5 | Align all referenced NuGet package versions with the specified net10.0 target framework | gemini-2.5 (gemini-2.5-pro) | Package version compatibility with the target framework is critical for build success. If specified versions are incompatible with net10.0, the project won't build. This is a feasibility concern. | 2026-02-20 19:50:27 UTC |
| R4-S9 | Update Traceability Matrix to require behavioral validation instead of just Structural diff | gemini-2.5 (gemini-2.5-pro) | Structural diff alone cannot verify functional correctness of cart store selection logic or cart operations. Behavioral validation through tests is necessary to confirm the code works as specified, not just looks correct. | 2026-02-20 19:50:27 UTC |
| R4-S10 | Strengthen validation method for gRPC Health Check to verify correct ServingStatus based on Ping() result | gemini-2.5 (gemini-2.5-pro) | The current validation method (grep for HealthBase and Ping() integration) only confirms presence, not correctness. The health check's core behavior—returning correct status based on Ping()—requires behavioral verification. | 2026-02-20 19:50:27 UTC |
| R1-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Traceability matrix references undefined Feature IDs, creating ambiguity. This was noted in R1-S9 but not fully resolved. | 2026-02-20 19:55:11 UTC |
| R1-F2 | Specify HTTP/2 handler configuration requirements for test client |  | gRPC over TestHost requires specific HttpHandler configuration with HTTP/2; without this, tests will fail with protocol errors. | 2026-02-20 19:55:11 UTC |
| R1-F3 | Add Ping() operation specifics to REQ-CMS-005, 006, 007 |  | R2-S2 was applied but requirements still lack concrete Ping() behaviors. Meaningful health checks require actual connectivity verification. | 2026-02-20 19:55:11 UTC |
| R1-F5 | Specify AlloyDBCartStore startup failure behavior when credentials unavailable |  | Constructor failure behavior during DI affects operational reliability. Fast-fail on startup for missing credentials is important for deployment validation. | 2026-02-20 19:55:11 UTC |
| R3-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Duplicate of R1-F1; traceability requires explicit feature definitions in requirements. | 2026-02-20 19:55:11 UTC |
| R3-F2 | Specify HTTP/2 handler configuration for TestServer in REQ-CMS-012 |  | Duplicate of R1-F2 with 2 endorsements; critical for gRPC test execution. | 2026-02-20 19:55:11 UTC |
| R3-F3 | Specify concrete Ping() operations for each cart store implementation |  | Duplicate of R1-F3; health checks must perform meaningful connectivity verification. | 2026-02-20 19:55:11 UTC |
| R3-F4 | Clarify UserId handling when GetCartAsync returns empty cart for non-existent user |  | Behavioral consistency between AddItemAsync and GetCartAsync for UserId handling prevents subtle bugs. | 2026-02-20 19:55:11 UTC |
| R3-F5 | Document AlloyDB SQL injection as known reference limitation in requirements |  | Duplicate of R3-S4; security acknowledgment should be in requirements document not just plan. | 2026-02-20 19:55:11 UTC |
| R3-F6 | Specify AlloyDBCartStore constructor failure behavior for Secret Manager errors |  | Duplicate of R1-F5/R3-S5; operational reliability requires explicit fail-fast specification. | 2026-02-20 19:55:11 UTC |
| R3-F8 | Specify whether tests require external dependencies or use in-memory fallback |  | Duplicate of R3-S6; CI reproducibility requires explicit test configuration. | 2026-02-20 19:55:11 UTC |
| R5-S1 | Add explicit consistency requirement between ICartStore interface and all implementation classes | claude-4 (claude-opus-4-5) | Critical for ensuring compile-time contract satisfaction across RedisCartStore, SpannerCartStore, and AlloyDBCartStore - interface conformance is fundamental to the design | 2026-02-20 19:59:48 UTC |
| R5-S2 | Standardize error handling pattern with explicit RpcException status codes across all cart store implementations | claude-4 (claude-opus-4-5) | REQ-CMS-007 lacks explicit StatusCode specification while REQ-CMS-005/006 specify FailedPrecondition - this inconsistency affects client error handling | 2026-02-20 19:59:48 UTC |
| R6-S1 | Standardize gRPC exception status code and message format across all ICartStore implementations | gemini-2.5 (gemini-2.5-pro) | Duplicate of R5-S2 with endorsement - REQ-CMS-007 uses inconsistent error messaging compared to REQ-CMS-005/006, which affects client-side error handling consistency | 2026-02-20 19:59:48 UTC |
| R1-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | The traceability matrix references these IDs without definitions, breaking bidirectional traceability. This is a fundamental documentation completeness issue. | 2026-02-20 20:04:37 UTC |
| R1-F2 | Specify HTTP/2 handler configuration requirements for test client |  | R1-S5 was applied but acceptance criteria still lack the HttpHandler configuration needed for gRPC over TestServer. Tests will fail without proper HTTP/2 setup. | 2026-02-20 20:04:37 UTC |
| R1-F3 | Add Ping() operation specifics to cart store requirements |  | This was endorsed multiple times (R2-S2, R4-S1, R5-F3) and requirements still don't specify what operation each Ping() performs. Critical for meaningful health checks. | 2026-02-20 20:04:37 UTC |
| R1-F5 | Specify AlloyDBCartStore startup failure behavior when credentials unavailable |  | Fail-fast behavior is a critical operational characteristic. R2-S3 was applied but the explicit fail-fast behavior for constructor exceptions needs documentation. | 2026-02-20 20:04:37 UTC |
| R3-F4 | Clarify UserId handling when GetCartAsync returns empty cart for non-existent user |  | Behavioral consistency between GetCartAsync and AddItemAsync regarding UserId setting is important for correct implementation. This is a legitimate ambiguity. | 2026-02-20 20:04:37 UTC |
| R3-F5 | Document AlloyDB SQL injection as known reference limitation in requirements |  | Explicitly acknowledging security limitations prevents confusion during code review and demonstrates intentional design decision rather than oversight. Endorsed by R5-F2. | 2026-02-20 20:04:37 UTC |
| R3-F8 | Specify whether tests require external dependencies or use in-memory fallback |  | Test execution environment requirements should be explicit for CI reproducibility. Endorsed by R6-S7 as well. | 2026-02-20 20:04:37 UTC |
| R7-S1 | Add memory/resource constraints validation for trimmed deployment | claude-4 (claude-opus-4-5) | Aggressive trimming with TrimMode=full poses real risk of runtime failures for reflection-dependent libraries like gRPC and Protobuf. This validation requirement addresses a critical feasibility gap. | 2026-02-20 20:08:29 UTC |
| R7-S2 | Specify SecretManagerServiceClient authentication mechanism | claude-4 (claude-opus-4-5) | The requirement for GCP authentication is implicit but critical - the chiseled non-root container makes credential mounting non-trivial. Explicit authentication specification is necessary for implementation feasibility. | 2026-02-20 20:08:29 UTC |
| R7-S3 | Address proto compilation toolchain requirements | claude-4 (claude-opus-4-5) | REQ-CMS-010 references proto compilation but lacks Grpc.Tools in package references. This is a genuine gap that will cause build failures. | 2026-02-20 20:08:29 UTC |
| R8-S1 | Specify expected GCP authentication mechanism instead of implicit ADC | gemini-2.5 (gemini-2.5-pro) | Similar to R7-S2, this addresses a critical hidden dependency. Explicit authentication requirements are essential for implementation in diverse environments. | 2026-02-20 20:08:29 UTC |
| R8-S2 | Add runtime validation requirement for trimmed binary | gemini-2.5 (gemini-2.5-pro) | Aligns with R7-S1. Aggressive trimming requires explicit validation to catch reflection-based failures that aren't detectable at compile time. | 2026-02-20 20:08:29 UTC |
| R8-S4 | Add validation for chiseled image runtime compatibility | gemini-2.5 (gemini-2.5-pro) | Chiseled images lack many runtime dependencies. Validating that the application starts and passes health checks in the final container is a reasonable acceptance criterion. | 2026-02-20 20:08:29 UTC |
| R1-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | The traceability matrix references these IDs without definitions, breaking bidirectional traceability. Self-contained requirements are essential for proper documentation. | 2026-02-20 20:13:14 UTC |
| R1-F2 | Specify HTTP/2 handler configuration requirements for test client |  | gRPC over TestServer requires specific HttpHandler configuration with HTTP/2; without this, tests will fail with protocol errors. R1-S5 was applied but acceptance criteria are still incomplete. | 2026-02-20 20:13:14 UTC |
| R1-F3 | Add Ping() operation specifics to REQ-CMS-005, 006, 007 |  | R2-S2 was applied but requirements still don't specify what each Ping() actually does. This is essential for meaningful health checks and has 2 endorsements (R2-F2). | 2026-02-20 20:13:14 UTC |
| R1-F5 | Specify AlloyDBCartStore startup failure behavior when credentials unavailable |  | Fast-fail behavior on constructor failure is architecturally significant and should be explicitly documented for operational clarity. | 2026-02-20 20:13:14 UTC |
| R3-F4 | Clarify UserId handling when GetCartAsync returns empty cart for non-existent user |  | Behavioral consistency between AddItemAsync and GetCartAsync for UserId handling is important for API contract clarity and testability. | 2026-02-20 20:13:14 UTC |
| R3-F5 | Document AlloyDB SQL injection as known reference limitation in requirements |  | Explicit security acknowledgment prevents reviewers from flagging intentional reference-matching behavior as defects, reducing review friction. | 2026-02-20 20:13:14 UTC |
| R3-F8 | Specify whether tests require external dependencies or use in-memory fallback |  | CI reproducibility requires explicit specification that tests use in-memory fallback without external dependencies. | 2026-02-20 20:13:14 UTC |
| R5-F2 | Add explicit security acknowledgment for AlloyDB string interpolation pattern |  | Same as R3-F5 - explicit security note with production guidance is valuable. Has endorsement. | 2026-02-20 20:13:14 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S1 | Add explicit namespace import requirements for each .cs file | claude-4 (claude-opus-4-5) | The requirements document is intended to specify functional behavior and structure, not implementation details like using statements. Standard C# development practice assumes developers will add necessary imports. Adding this level of detail would bloat the document without adding meaningful value - compilation errors will naturally surface missing imports. | 2026-02-20 19:21:06 UTC |
| R1-S3 | Standardize exception handling message format across cart stores | claude-4 (claude-opus-4-5) | The requirements explicitly state the reference implementation is ground truth. REQ-CMS-007 intentionally documents a different error message ('Unable to access cart storage due to an internal error') which likely matches the reference. The document already captures this distinction accurately. | 2026-02-20 19:21:06 UTC |
| R1-S7 | Specify launchSettings.json for local development | claude-4 (claude-opus-4-5) | The Out of Scope section establishes boundaries, and launchSettings.json is a developer convenience file not present in the reference implementation. Adding it would expand scope beyond the reference-matching goal. If needed, it can be explicitly added to Out of Scope for clarity. | 2026-02-20 19:21:06 UTC |
| R1-S10 | Align Dockerfile WORKDIR between stages | claude-4 (claude-opus-4-5) | The requirements explicitly state reference implementation is ground truth. The /app vs /cartservice pattern is documented accurately and the COPY command works correctly. Adding comments about intentional patterns is documentation preference, not a requirements deficiency. | 2026-02-20 19:21:06 UTC |
| R2-S1 | Mandate parameterized queries in AlloyDBCartStore | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-007 explicitly states 'All use inline SQL (string interpolation, not parameterized — matches reference)'. The requirements document correctly captures the reference implementation behavior. Changing this would deviate from the stated goal of matching the reference. Security improvements should be handled through a separate change request to the reference implementation. | 2026-02-20 19:21:06 UTC |
| R2-S4 | Require ILogger instead of Console.WriteLine | gemini-2.5 (gemini-2.5-pro) | The requirements explicitly specify Console.WriteLine to match the reference implementation. The document's purpose is replication fidelity, not best practices improvement. Changing logging approach would deviate from the reference. | 2026-02-20 19:21:06 UTC |
| R2-S5 | Change ICartStore.Ping() to async Task<bool> PingAsync() | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-004 explicitly defines 'bool Ping()' as the interface method signature, matching the reference implementation. Changing the signature would break compatibility with the reference and all implementing classes. | 2026-02-20 19:21:06 UTC |
| R2-S8 | Specify behavior of AddItemAsync when quantity is zero or negative | gemini-2.5 (gemini-2.5-pro) | The requirements document aims to match reference implementation behavior. Edge case handling should be verified against the reference rather than newly specified. If the reference doesn't handle these cases, neither should the requirements. | 2026-02-20 19:21:06 UTC |
| R2-S9 | Make hardcoded values in SpannerCartStore and AlloyDBCartStore configurable | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-006 and REQ-CMS-007 explicitly document hardcoded values (DefaultInstanceName, alloyDBUser='postgres') to match the reference implementation. Making these configurable would deviate from reference matching goal. | 2026-02-20 19:21:06 UTC |
| R2-S10 | Specify configuration sources and priority order | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-001 specifies using Host.CreateDefaultBuilder which establishes standard ASP.NET Core configuration hierarchy. This is implicit framework behavior that doesn't need explicit documentation. Developers familiar with ASP.NET Core will understand the convention. | 2026-02-20 19:21:06 UTC |
| R1-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Feature IDs are defined in the implementation plan document being reviewed, not the requirements document - the traceability matrix provides the mapping | 2026-02-20 19:24:20 UTC |
| R1-F4 | Document IDistributedMemoryCache to RedisCartStore DI relationship in REQ-CMS-002 |  | This is standard ASP.NET Core DI behavior - IDistributedCache abstraction is well-documented in Microsoft docs and doesn't need restatement | 2026-02-20 19:24:20 UTC |
| R1-F6 | Add test scope clarification to REQ-CMS-012 |  | The plan explicitly states this is a structural equivalence exercise matching the reference implementation - test scope matches reference | 2026-02-20 19:24:20 UTC |
| R3-S1 | Specify exact exception message format for RpcException across all cart store implementations | claude-4 (claude-opus-4-5) | Similar to previously rejected R2-S4, this level of error message standardization is overly prescriptive. The existing requirements already specify the error patterns, and minor variations in message templates don't impact functional correctness. | 2026-02-20 19:50:27 UTC |
| R3-S3 | Harmonize async/await patterns across CartService methods with explicit rationale | claude-4 (claude-opus-4-5) | The async patterns are already clearly specified in REQ-CMS-003. Adding explanatory notes about why patterns differ adds documentation overhead without improving implementation clarity. The specification is already explicit about the difference. | 2026-02-20 19:50:27 UTC |
| R3-S4 | Standardize logging approach specification to explicitly state ILogger is not used | claude-4 (claude-opus-4-5) | The requirements already specify Console.WriteLine usage consistently. Explicitly stating what is NOT used is unnecessary negative specification. Implementations should follow what IS specified. | 2026-02-20 19:50:27 UTC |
| R3-S5 | Align HealthCheckService field declaration style with specification intent | claude-4 (claude-opus-4-5) | REQ-CMS-008 already provides the exact declaration syntax `private ICartStore _cartStore { get; }` with the clarification '(property, not field)'. The suggestion adds no new information beyond what's already specified. | 2026-02-20 19:50:27 UTC |
| R3-S7 | Address potential race condition in RedisCartStore.AddItemAsync | claude-4 (claude-opus-4-5) | The requirement explicitly states 'matches reference' behavior. Adding notes about known limitations or race conditions is out of scope when the goal is structural equivalence with the reference implementation. | 2026-02-20 19:50:27 UTC |
| R3-S10 | Specify which requirements map to which output files in the plan | claude-4 (claude-opus-4-5) | Requirements already reference file paths explicitly (e.g., 'services/CartService.cs'). Adding a separate mapping table creates maintenance burden and potential for inconsistency. The current approach is sufficiently clear. | 2026-02-20 19:50:27 UTC |
| R4-S2 | Clarify the fallback cart store implementation pattern using RedisCartStore with AddDistributedMemoryCache | gemini-2.5 (gemini-2.5-pro) | The requirement accurately describes the reference implementation's design pattern. While conceptually unusual, changing this would diverge from the reference. The pattern is clearly specified even if architecturally questionable. | 2026-02-20 19:50:27 UTC |
| R4-S3 | Mandate the use of standard ILogger<T> instead of Console.WriteLine for all logging | gemini-2.5 (gemini-2.5-pro) | This contradicts the document's explicit scope: replicating the reference implementation. Console.WriteLine is specified because that's what the reference uses. Improvements like ILogger are explicitly out of scope. | 2026-02-20 19:50:27 UTC |
| R4-S4 | Define a consistent error message policy for RpcException across ICartStore implementations | gemini-2.5 (gemini-2.5-pro) | Similar to R3-S1, this is overly prescriptive standardization. The requirements already specify error patterns that match the reference. Security concerns about information disclosure are out of scope per the document. | 2026-02-20 19:50:27 UTC |
| R4-S6 | Replace string-interpolated SQL in AlloyDBCartStore with parameterized queries | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-007 explicitly states 'inline SQL (string interpolation, not parameterized — matches reference)'. Security hardening beyond the reference is explicitly listed as out of scope. The requirement accurately reflects reference behavior. | 2026-02-20 19:50:27 UTC |
| R4-S7 | Add requirement to log warning when multiple cart store configuration variables are detected | gemini-2.5 (gemini-2.5-pro) | This is an improvement/enhancement over the reference implementation. The scope explicitly states code should match the reference, and adding new warning logic would diverge from that goal. | 2026-02-20 19:50:27 UTC |
| R4-S8 | Specify in REQ-CMS-012 that each test method must be fully isolated with no shared state | gemini-2.5 (gemini-2.5-pro) | xUnit naturally provides test isolation via new class instances. The current test specifications in REQ-CMS-012 follow standard xUnit patterns. Adding explicit isolation requirements is unnecessary for this scope. | 2026-02-20 19:50:27 UTC |
| R1-F4 | Document IDistributedMemoryCache → RedisCartStore DI relationship in REQ-CMS-002 |  | The fallback case is already documented in the plan's Startup.cs implementation contract. DI relationships are standard ASP.NET Core patterns that don't require explicit documentation. | 2026-02-20 19:55:11 UTC |
| R1-F6 | Add test scope clarification to REQ-CMS-012 |  | R2-S6 was already rejected. The test scope matches reference implementation intentionally; adding meta-commentary about scope is unnecessary. | 2026-02-20 19:55:11 UTC |
| R3-F7 | Strengthen REQ-CMS-008 validation beyond grep to include behavioral test |  | Adding behavioral tests beyond grep validation expands scope beyond structural equivalence verification. | 2026-02-20 19:55:11 UTC |
| R3-F9 | Clarify protobuf Empty message source - Hipstershop.Empty vs Google.Protobuf.WellKnownTypes.Empty |  | Cart.proto already defines Empty message in hipstershop package. Implementation contract shows Hipstershop.Empty usage. | 2026-02-20 19:55:11 UTC |
| R3-F10 | Add validation requirement for package version compatibility with net10.0 |  | The Risks table already acknowledges .NET 10 SDK availability. Package resolution is validated by dotnet restore during build. | 2026-02-20 19:55:11 UTC |
| R5-S3 | Define consistent logging format pattern across all cart store implementations | claude-4 (claude-opus-4-5) | The document explicitly states the goal is structural equivalence with the reference implementation, not standardization of logging patterns beyond what exists in the reference | 2026-02-20 19:59:48 UTC |
| R5-S4 | Specify .NET 10.0 SDK availability and compatibility verification | claude-4 (claude-opus-4-5) | The document already specifies exact package versions; verifying future framework availability is an operational concern outside the requirements scope, and dotnet restore validation is already implicitly part of build verification | 2026-02-20 19:59:48 UTC |
| R5-S5 | Add feature-to-requirement reverse mapping table | claude-4 (claude-opus-4-5) | The existing traceability matrix already provides requirement-to-feature mapping; a reverse mapping adds documentation overhead without improving generation validation significantly | 2026-02-20 19:59:48 UTC |
| R5-S6 | Specify Secret Manager API authentication requirements for AlloyDBCartStore | claude-4 (claude-opus-4-5) | Authentication handling in GCP environments is an operational/deployment concern; the reference implementation assumes ADC and the requirement correctly reflects this behavior | 2026-02-20 19:59:48 UTC |
| R5-S7 | Link configuration keys to their consuming requirements | claude-4 (claude-opus-4-5) | Configuration keys are already documented within their respective requirements (REQ-CMS-002, REQ-CMS-006, REQ-CMS-007); a consolidated inventory adds maintenance burden without significant validation benefit | 2026-02-20 19:59:48 UTC |
| R5-S8 | Reconcile Protobuf namespace casing between proto definition and C# code references | claude-4 (claude-opus-4-5) | The PascalCase transformation from protoc is standard well-known behavior; documenting this transformation rule is unnecessary as it's implicit in the toolchain | 2026-02-20 19:59:48 UTC |
| R5-S9 | Clarify SpannerConnection retry semantics and transaction isolation | claude-4 (claude-opus-4-5) | The requirement references RunWithRetriableTransactionAsync which uses library defaults; specifying internal library behavior would over-constrain the implementation beyond the reference | 2026-02-20 19:59:48 UTC |
| R5-S10 | Add validation method cross-references to each requirement's acceptance criteria | claude-4 (claude-opus-4-5) | The traceability matrix already links requirements to validation methods; duplicating this information in each requirement creates maintenance overhead and potential inconsistency | 2026-02-20 19:59:48 UTC |
| R6-S2 | Mandate use of ILogger<T> instead of Console.WriteLine for all logging | gemini-2.5 (gemini-2.5-pro) | The document explicitly states structural equivalence with reference is the goal; the reference implementation uses Console.WriteLine and this is intentionally preserved | 2026-02-20 19:59:48 UTC |
| R6-S3 | Unify EmptyCartAsync to perform hard delete across all backends | gemini-2.5 (gemini-2.5-pro) | The document explicitly states matching reference implementation behavior; REQ-CMS-005 correctly documents that RedisCartStore overwrites with empty cart (matching reference), not deletes | 2026-02-20 19:59:48 UTC |
| R6-S4 | Change TrimMode=full to TrimMode=link in Dockerfile | gemini-2.5 (gemini-2.5-pro) | The requirement explicitly matches the reference implementation's Dockerfile; changing trim mode deviates from the stated goal of structural comparability with reference | 2026-02-20 19:59:48 UTC |
| R6-S5 | Use floating patch versions instead of pinned exact versions in package references | gemini-2.5 (gemini-2.5-pro) | The document specifies exact versions to ensure reproducible builds matching the reference; floating versions introduce non-determinism | 2026-02-20 19:59:48 UTC |
| R6-S6 | Register SecretManagerServiceClient as singleton in DI | gemini-2.5 (gemini-2.5-pro) | The reference implementation creates the client in the constructor; changing this pattern deviates from structural equivalence with the reference | 2026-02-20 19:59:48 UTC |
| R6-S7 | Add unit tests for cart store selection logic in Startup.ConfigureServices | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-012 already defines the test scope matching the reference; adding behavioral tests beyond reference scope exceeds the structural equivalence goal | 2026-02-20 19:59:48 UTC |
| R6-S8 | Add unit test for HealthCheckService verifying ServingStatus reflects Ping result | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-012 defines test scope matching the reference implementation; adding tests beyond reference scope exceeds structural equivalence requirements | 2026-02-20 19:59:48 UTC |
| R6-S9 | Strengthen validation for REQ-CMS-009a to check compiled assembly references | gemini-2.5 (gemini-2.5-pro) | Grep for absence of imports is sufficient for generation validation; assembly-level checks are build verification concerns beyond requirements scope | 2026-02-20 19:59:48 UTC |
| R6-S10 | Mandate parameterized queries in AlloyDBCartStore to prevent SQL injection | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-007 explicitly states 'matches reference' and documents inline SQL; security improvements beyond reference are explicitly out of scope per the Out of Scope section | 2026-02-20 19:59:48 UTC |
| R1-F4 | Document IDistributedMemoryCache → RedisCartStore DI relationship in REQ-CMS-002 |  | This is standard ASP.NET Core DI pattern well-documented elsewhere. Adding this would over-specify implementation details that experienced developers understand. | 2026-02-20 20:04:37 UTC |
| R1-F6 | Add test scope clarification to REQ-CMS-012 |  | The test scope is adequately defined by listing the 3 specific test methods. Adding commentary about intentional minimalism is unnecessary documentation. | 2026-02-20 20:04:37 UTC |
| R3-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Duplicate of R1-F1 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R3-F2 | Specify HTTP/2 handler configuration for TestServer in REQ-CMS-012 |  | Duplicate of R1-F2 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R3-F3 | Specify concrete Ping() operations for each cart store implementation |  | Duplicate of R1-F3 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R3-F6 | Specify AlloyDBCartStore constructor failure behavior for Secret Manager errors |  | Duplicate of R1-F5 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R3-F7 | Strengthen REQ-CMS-008 validation beyond grep to include behavioral test |  | R4-S10 was previously rejected. The current validation approach is sufficient for this validation exercise focused on structural equivalence. | 2026-02-20 20:04:37 UTC |
| R3-F9 | Clarify protobuf Empty message source - Hipstershop.Empty vs Google.Protobuf.WellKnownTypes.Empty |  | The proto definition in F-002 clearly shows Hipstershop.Empty is defined in Cart.proto. The implementation contract explicitly shows usage. | 2026-02-20 20:04:37 UTC |
| R3-F10 | Add validation requirement for package version compatibility with net10.0 |  | R4-S5 was previously rejected. The plan already notes .NET 10 compilation as advisory validation only. | 2026-02-20 20:04:37 UTC |
| R5-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Duplicate of R1-F1 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R5-F2 | Add explicit security acknowledgment for AlloyDB string interpolation pattern |  | Duplicate of R3-F5 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R5-F3 | Specify concrete Ping() operations for each cart store in requirements |  | Duplicate of R1-F3 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R5-F4 | Clarify protos/ directory location relative to csproj file |  | The plan clearly shows the full path in F-002 and the csproj Include path in F-005. Standard .NET developers understand relative paths. | 2026-02-20 20:04:37 UTC |
| R5-F5 | Specify GrpcChannelOptions.HttpHandler configuration for HTTP/2 TestServer support |  | Duplicate of R1-F2 which was already accepted. | 2026-02-20 20:04:37 UTC |
| R7-S4 | Add requirement-to-test-method traceability | claude-4 (claude-opus-4-5) | The existing traceability matrix provides sufficient coverage mapping. Adding per-test-method traceability is overly granular for a document focused on structural equivalence to reference implementation. | 2026-02-20 20:08:29 UTC |
| R7-S5 | Add bidirectional feature-to-requirement traceability | claude-4 (claude-opus-4-5) | The current unidirectional traceability is sufficient for this requirements document. Adding reverse mapping creates maintenance burden without proportional value for a reference-based validation approach. | 2026-02-20 20:08:29 UTC |
| R7-S6 | Link validation requirements to functional requirements in matrix | claude-4 (claude-opus-4-5) | Validation requirements (V01, V02) are cross-cutting by nature and apply to all code-generating requirements. Adding them to the matrix would create redundant entries without improving clarity. | 2026-02-20 20:08:29 UTC |
| R7-S7 | Specify Redis connection failure behavior at startup | claude-4 (claude-opus-4-5) | This documents existing reference behavior rather than identifying a gap. The lazy initialization pattern is a design choice already present in the reference implementation. | 2026-02-20 20:08:29 UTC |
| R7-S8 | Clarify Spanner retry semantics under RunWithRetriableTransactionAsync | claude-4 (claude-opus-4-5) | The requirement already specifies using Spanner's built-in retry mechanism. Default Spanner semantics are well-documented by Google and don't need replication here. | 2026-02-20 20:08:29 UTC |
| R7-S9 | Add dependency traceability between requirements | claude-4 (claude-opus-4-5) | R8-S9 covers the same concern. The interface dependencies are implicit in C# code structure and adding explicit dependency columns adds maintenance burden for minimal value. | 2026-02-20 20:08:29 UTC |
| R7-S10 | Specify behavior when multiple cart store configs are set | claude-4 (claude-opus-4-5) | REQ-CMS-002 already clearly specifies priority order. Silent selection of highest-priority store matches reference behavior and is the expected pattern. | 2026-02-20 20:08:29 UTC |
| R8-S3 | Require parameterized queries in AlloyDBCartStore | gemini-2.5 (gemini-2.5-pro) | REQ-CMS-007 explicitly states 'matches reference' for inline SQL. The requirements document aims for structural equivalence to reference, not security improvements. This is explicitly out of scope. | 2026-02-20 20:08:29 UTC |
| R8-S5 | Reclassify tests as integration tests or refactor to true unit tests | gemini-2.5 (gemini-2.5-pro) | The test approach matches the reference implementation. The document's goal is structural equivalence, not improvement of test architecture. | 2026-02-20 20:08:29 UTC |
| R8-S6 | Define Feature IDs used in traceability matrix | gemini-2.5 (gemini-2.5-pro) | Feature IDs (F-001 through F-007) serve as grouping identifiers in the existing matrix structure. The requirements themselves provide sufficient context without a separate feature definition section. | 2026-02-20 20:08:29 UTC |
| R8-S7 | Add ground truth file paths to traceability matrix | gemini-2.5 (gemini-2.5-pro) | The document already states the reference implementation serves as ground truth. Adding specific file paths creates maintenance burden when reference repo changes. | 2026-02-20 20:08:29 UTC |
| R8-S8 | Add configuration variable data dictionary | gemini-2.5 (gemini-2.5-pro) | Configuration keys are already documented within their respective requirements (REQ-CMS-002, REQ-CMS-006, REQ-CMS-007). A separate appendix would duplicate this information. | 2026-02-20 20:08:29 UTC |
| R8-S9 | Add inter-requirement dependency column to matrix | gemini-2.5 (gemini-2.5-pro) | Dependencies are inherent in C# code structure (interfaces, implementations). Adding explicit dependency tracking creates maintenance overhead without improving implementation guidance. | 2026-02-20 20:08:29 UTC |
| R8-S10 | Standardize error handling across ICartStore implementations | gemini-2.5 (gemini-2.5-pro) | The varying error handling patterns match the reference implementation. The requirements document aims for structural equivalence, not consistency improvements. | 2026-02-20 20:08:29 UTC |
| R1-F4 | Document IDistributedMemoryCache → RedisCartStore DI relationship in REQ-CMS-002 |  | The DI relationship is standard ASP.NET Core behavior and the code pattern is clear in the implementation contract. Over-documentation of framework conventions adds noise. | 2026-02-20 20:13:14 UTC |
| R1-F6 | Add test scope clarification to REQ-CMS-012 |  | The test scope is already defined by the 3 listed tests. Adding a note explaining why it's minimal is meta-documentation that doesn't improve implementability. | 2026-02-20 20:13:14 UTC |
| R3-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Duplicate of R1-F1 which was already accepted. | 2026-02-20 20:13:14 UTC |
| R3-F2 | Specify HTTP/2 handler configuration for TestServer in REQ-CMS-012 |  | Duplicate of R1-F2 which was already accepted. | 2026-02-20 20:13:14 UTC |
| R3-F3 | Specify concrete Ping() operations for each cart store implementation |  | Duplicate of R1-F3 which was already accepted. | 2026-02-20 20:13:14 UTC |
| R3-F6 | Specify AlloyDBCartStore constructor failure behavior for Secret Manager errors |  | Duplicate of R1-F5 which was already accepted. | 2026-02-20 20:13:14 UTC |
| R3-F7 | Strengthen REQ-CMS-008 validation beyond grep to include behavioral test |  | R4-S10 was already rejected. The validation approach using grep is appropriate for structural verification; behavioral testing is covered by integration tests. | 2026-02-20 20:13:14 UTC |
| R3-F9 | Clarify protobuf Empty message source - Hipstershop.Empty vs Google.Protobuf.WellKnownTypes.Empty |  | The Cart.proto explicitly defines Empty message in hipstershop package, and the implementation contract clearly uses Hipstershop.Empty. This is already unambiguous. | 2026-02-20 20:13:14 UTC |
| R3-F10 | Add validation requirement for package version compatibility with net10.0 |  | The Risks section already acknowledges .NET 10 SDK requirement with advisory validation. Adding another validation requirement is redundant. | 2026-02-20 20:13:14 UTC |
| R5-F1 | Define Feature IDs F-001 through F-007 explicitly in requirements document |  | Duplicate of R1-F1 which was already accepted. | 2026-02-20 20:13:14 UTC |
| R5-F3 | Specify concrete Ping() operations for each cart store in requirements |  | Duplicate of R1-F3 which was already accepted. | 2026-02-20 20:13:14 UTC |
| R5-F4 | Clarify protos/ directory location relative to csproj file |  | The path is already specified in both REQ-CMS-015 and the .csproj implementation contract. The directory structure is standard and build verification will catch path issues. | 2026-02-20 20:13:14 UTC |
| R5-F5 | Specify GrpcChannelOptions.HttpHandler configuration for HTTP/2 TestServer support |  | Duplicate of R1-F2 which was already accepted. | 2026-02-20 20:13:14 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

(empty — awaiting first review round)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 19:18:59 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | completeness | critical | Add explicit namespace import requirements for each .cs file | REQ-CMS-001 specifies `using` statements but other requirements (REQ-CMS-003 through REQ-CMS-008) do not specify required imports (e.g., `using Grpc.Core`, `using Google.Cloud.Spanner.Data`, `using Npgsql`). This creates ambiguity about which namespaces are required for compilation. | Add "Required imports:" subsection to each .cs file requirement | Verify generated files compile without missing using directives |
| R1-S2 | ambiguity | high | Clarify the `protos/` directory location relative to project structure | REQ-CMS-015 defines `protos/Cart.proto` and REQ-CMS-010 references `protos\Cart.proto` in the Protobuf item, but it's unclear whether this is `src/protos/` or a root-level `protos/` directory. This affects both .csproj path and Dockerfile COPY behavior. | Add explicit file path clarification to REQ-CMS-015 or create a directory structure section | Cross-reference with companion plan-csharp.md output structure |
| R1-S3 | consistency | high | Standardize exception handling message format across cart stores | REQ-CMS-005/006 use `"Can't access cart storage. {ex}"` while REQ-CMS-007 uses `"Unable to access cart storage due to an internal error. {ex}"`. If this matches reference, document it; otherwise, standardize. | Verify against reference and either document intentional difference or standardize in each REQ | Grep for RpcException message strings in generated code |
| R1-S4 | testability | high | Define expected behavior when Spanner/AlloyDB configuration is incomplete | REQ-CMS-002 defines fallback priority but doesn't specify behavior when partial configuration exists (e.g., `SPANNER_PROJECT` set but `SPANNER_INSTANCE` missing). Should it throw, log warning, or fall through to next backend? | Add error handling clarification to REQ-CMS-002 ConfigureServices section | Unit test with partial configuration scenarios |
| R1-S5 | completeness | medium | Specify gRPC channel options for test client in REQ-CMS-012 | Test methods use `GrpcChannel.ForAddress` but don't specify `GrpcChannelOptions` with `HttpHandler`. The TestServer requires specific handler configuration for HTTP/2 over non-TLS. | Add explicit channel configuration to REQ-CMS-012 test setup | Verify tests execute successfully against TestServer |
| R1-S6 | feasibility | medium | Verify SecretManager API availability in test/local environments | REQ-CMS-007 requires `SecretManagerServiceClient.Create()` which needs GCP credentials. No fallback or mock strategy is defined for local development or CI testing without GCP access. | Add note about credential requirements or mock strategy to REQ-CMS-007 | Attempt build/test in credential-less environment |
| R1-S7 | completeness | medium | Specify launchSettings.json for local development | No requirement exists for `Properties/launchSettings.json` which defines local development profiles (HTTP/HTTPS ports, environment variables). This is standard for ASP.NET Core projects. | Add REQ-CMS-016 for launchSettings.json or explicitly add to Out of Scope | Compare with reference implementation for presence/absence |
| R1-S8 | ambiguity | medium | Clarify `IDistributedCache` injection path for fallback RedisCartStore | REQ-CMS-002 case 4 adds both `AddDistributedMemoryCache()` and `AddSingleton<ICartStore, RedisCartStore>()`, but RedisCartStore constructor expects `IDistributedCache`. Clarify that `IDistributedCache` is satisfied by `AddDistributedMemoryCache()`. | Add clarifying note to REQ-CMS-002 acceptance criteria case 4 | Code review of DI registration sequence |
| R1-S9 | traceability | low | Add Feature ID definitions to document | Traceability Matrix references F-001 through F-007 but these Feature IDs are never defined in the document. Readers cannot understand what each feature represents. | Add Feature Definitions section after Scope or add to companion plan reference | Verify all F-XXX codes have definitions |
| R1-S10 | consistency | low | Align Dockerfile WORKDIR between stages | REQ-CMS-014 uses `/app` for stage 2 WORKDIR but publish output goes to `/cartservice`. The COPY uses `--from=builder /cartservice .` which works but creates subtle inconsistency with standard `/app` output conventions. | Verify this matches reference exactly; if so, add comment explaining intentional pattern | Dockerfile build verification |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none - this is R1, no prior suggestions exist)

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:19:30 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | feasibility | critical | Mandate the use of parameterized queries in `AlloyDBCartStore`. | REQ-CMS-007 currently requires string interpolation for SQL queries, which creates a critical SQL injection vulnerability. Requirements should enforce security best practices, not prohibit them, even if matching a reference implementation. | REQ-CMS-007 | Static analysis or code review to confirm `NpgsqlParameter` is used for all external inputs in SQL commands. |
| R2-S2 | completeness | high | Specify the concrete operation performed within the `Ping()` method's `try` block for each `ICartStore` implementation. | REQ-CMS-005, 006, and 007 are untestable as written, stating only that a `try` block should return true. A meaningful health check must perform a lightweight, non-mutating operation against the data store (e.g., `SELECT 1`, check connection status). | REQ-CMS-005, REQ-CMS-006, REQ-CMS-007 | Review each `Ping()` implementation to verify it executes a specific, fast, and reliable check against its backing data store. |
| R2-S3 | completeness | high | Define the application's behavior if the `AlloyDBCartStore` constructor fails to retrieve credentials from Secret Manager. | The secret retrieval process in REQ-CMS-007 is complex and can fail due to network or permission issues. The requirement should specify the outcome, such as a fast-fail crash on startup, to ensure predictable behavior. | REQ-CMS-007 | A unit test that mocks the `SecretManagerServiceClient` to throw an exception and asserts that the constructor propagates an exception, leading to a startup failure. |
| R2-S4 | consistency | medium | Require the use of `Microsoft.Extensions.Logging.ILogger<T>` for all logging instead of `Console.WriteLine`. | The requirements mandate `Console.WriteLine`, which is inconsistent with ASP.NET Core best practices. Structured logging via `ILogger` is essential for observability, filtering, and routing logs in production environments. | REQ-CMS-002, REQ-CMS-005, REQ-CMS-006, REQ-CMS-007, REQ-CMS-008 | Code review to ensure `ILogger<T>` is injected via DI and used for all logging statements, and that no `Console.WriteLine` calls remain in application logic. |
| R2-S5 | consistency | medium | Change the `ICartStore.Ping()` method signature to be asynchronous: `Task<bool> PingAsync()`. | All other data access methods on `ICartStore` are asynchronous. The synchronous `bool Ping()` is inconsistent and can lead to blocking threads. An async signature allows for non-blocking I/O during health checks. | REQ-CMS-004 | Review `ICartStore.cs` and all implementing classes to ensure the method signature is `Task<bool> PingAsync()` and is implemented with `async`/`await`. |
| R2-S6 | testability | medium | Clarify the required scope of test coverage, including negative test cases and edge cases. | REQ-CMS-012 specifies only three "happy path" tests. This is insufficient for ensuring robustness. The requirements should define the expectation for testing failure modes, such as the cart store throwing an exception. | REQ-CMS-012 | Review the test suite to confirm the existence of tests that assert correct behavior when services or dependencies fail (e.g., by mocking `ICartStore` to throw an `RpcException`). |
| R2-S7 | ambiguity | medium | Correct the fallback log message in `Startup.cs` to accurately reflect the implementation. | REQ-CMS-002 specifies a fallback log message "using in memory store" while the implementation uses `RedisCartStore` backed by `IDistributedMemoryCache`. This is misleading and hinders debugging. The log should be precise. | REQ-CMS-002 | Review the generated `Startup.cs` to ensure the fallback log message accurately states that `RedisCartStore` is being used with an in-memory cache. |
| R2-S8 | completeness | low | Specify the expected behavior of `AddItemAsync` when the requested quantity is zero or negative. | The requirements for adding an item do not cover non-positive quantities. The behavior should be explicitly defined (e.g., throw `RpcException` with `InvalidArgument`, ignore the request, remove the item if quantity becomes <= 0). | REQ-CMS-003, REQ-CMS-005 | Add unit tests for `AddItemAsync` with quantities of 0 and -1, and assert that the system behaves as specified. |
| R2-S9 | feasibility | low | Make hardcoded values in `SpannerCartStore` and `AlloyDBCartStore` configurable via `IConfiguration`. | REQ-CMS-006 hardcodes table/instance/database names, and REQ-CMS-007 hardcodes the database user. This reduces flexibility across environments. These values should be read from configuration with sensible defaults. | REQ-CMS-006, REQ-CMS-007 | Review the constructors of the cart store implementations to verify that values like table name and username are read from `IConfiguration`. |
| R2-S10 | ambiguity | low | Specify the expected configuration sources and their priority order. | The requirements list configuration keys but do not state their source (e.g., environment variables, `appsettings.json`). Explicitly defining the standard ASP.NET Core convention (Env > JSON) removes ambiguity for developers and operators. | REQ-CMS-002 (or as a new cross-cutting requirement) | Review `Program.cs` to confirm that the `Host.CreateDefaultBuilder` is used, as it sets up the standard configuration source priorities by default. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 19:22:07 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | clarity | high | Define Feature IDs F-001 through F-007 explicitly in requirements document | R1-S9 was applied noting Feature IDs are undefined, but the requirements document still lacks a "Feature Definitions" section. The traceability matrix references these IDs without definition. | Add new section "Feature Definitions" after Scope | Verify all F-XXX codes in traceability matrix have definitions |
| R1-F2 | completeness | high | Specify HTTP/2 handler configuration requirements for test client | R1-S5 was applied noting TestServer needs specific handler config, but REQ-CMS-012 acceptance criteria still only mention `GrpcChannelOptions { HttpClient = httpClient }` without the required `HttpHandler` with `ResponseVersion = HttpVersion.Version20`. | REQ-CMS-012 acceptance criteria | Tests execute successfully against TestHost |
| R1-F3 | completeness | medium | Add Ping() operation specifics to REQ-CMS-005, 006, 007 | R2-S2 was applied, but the requirements don't specify what operation each Ping() should perform. The document should state: RedisCartStore attempts cache access, SpannerCartStore opens connection, AlloyDBCartStore executes `SELECT 1`. | REQ-CMS-005, REQ-CMS-006, REQ-CMS-007 Ping() acceptance criteria | Code review verifying meaningful health check operation |
| R1-F4 | clarity | medium | Document IDistributedMemoryCache → RedisCartStore DI relationship in REQ-CMS-002 | R1-S8 was applied but REQ-CMS-002 case 4 could be clearer that `AddDistributedMemoryCache()` satisfies `IDistributedCache` which `RedisCartStore` constructor requires. This implicit DI relationship causes confusion. | REQ-CMS-002 ConfigureServices case 4 acceptance criteria | DI container verification that IDistributedCache resolves |
| R1-F5 | completeness | medium | Specify AlloyDBCartStore startup failure behavior when credentials unavailable | R2-S3 was applied, but REQ-CMS-007 doesn't explicitly state the constructor should allow exceptions to propagate (fast-fail). Should state: "If Secret Manager access fails, constructor throws exception causing application startup to fail." | REQ-CMS-007 Constructor acceptance criteria | Test with invalid/missing credentials to verify fast-fail |
| R1-F6 | testability | low | Add test scope clarification to REQ-CMS-012 | R2-S6 was applied noting test scope needs clarification, but REQ-CMS-012 still only lists 3 happy-path tests without stating this is intentionally minimal to match reference implementation. | REQ-CMS-012 Description or note | Review reference implementation test coverage |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:23:09 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Requirement |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | clarity | medium | Clarify which specific SQL statements in `AlloyDBCartStore` use string interpolation. | REQ-CMS-007 states "All use inline SQL (string interpolation...)" but this is ambiguous. The reference likely uses it for `DELETE` but might use parameters for `INSERT`/`UPDATE`. The requirement should be precise for each command to ensure accurate replication. | REQ-CMS-007 |
| R2-F2 | traceability | medium | Explicitly state that multi-architecture container builds are a requirement. | REQ-CMS-014's Dockerfile uses `TARGETARCH`, implying multi-arch support (e.g., `amd64`, `arm64`) is a goal. This is a significant feature that should be stated explicitly as a requirement rather than only being implied by the implementation detail. | REQ-CMS-014 |
| R2-F3 | testability | low | Make the test assertion in REQ-CMS-012 more explicit for empty carts. | The assertion `Assert.Equal(new Cart(), cart)` relies on the auto-generated `Equals` method of the Protobuf class. A more robust and explicit test would be to assert specific properties, e.g., `Assert.Equal(userId, cart.UserId)` and `Assert.Empty(cart.Items)`. | REQ-CMS-012 |
| R2-F4 | clarity | low | Clarify if the version mismatch in Dockerfile base images is intentional. | REQ-CMS-014 specifies `sdk:10.0.100` and `runtime-deps:10.0.0`. This patch version mismatch between the build and runtime environments could be a source of subtle issues. The requirement should confirm if this exact combination is intentional to match the reference. | REQ-CMS-014 |

#### Review Round R3

**Reviewer**: claude-4 (claude-opus-4-5)
**Date**: 2026-02-20 19:47:58 UTC
**Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | ambiguity | high | Specify the exact exception message format for RpcException across all cart store implementations | REQ-CMS-005, REQ-CMS-006, and REQ-CMS-007 each mention throwing RpcException but use slightly different error message patterns. REQ-CMS-007 explicitly states `"Unable to access cart storage due to an internal error. {ex}"` while others say `"Can't access cart storage. {ex}"`. Without explicit message templates for each store, implementations may diverge from reference behavior, affecting error handling in client services. | Add explicit error message templates to each cart store requirement (REQ-CMS-005, REQ-CMS-006, REQ-CMS-007) | String comparison of exception messages in generated code against reference implementation |
| R3-S2 | ambiguity | high | Clarify whether `Hipstershop.Cart.UserId` must be set in all cart store return values | REQ-CMS-005 states "creates new `Hipstershop.Cart()`, sets `UserId`" for AddItemAsync, but GetCartAsync only says "returns `new Hipstershop.Cart()` (empty cart, no error)" for null case. It's ambiguous whether UserId should be set on the empty cart returned when no data exists. Same ambiguity exists in REQ-CMS-006 and REQ-CMS-007. | Add explicit criterion to each cart store requirement specifying UserId handling in empty cart returns | Unit test verifying UserId property on returned Cart objects matches input userId |
| R3-S3 | consistency | high | Harmonize async/await patterns across CartService methods | REQ-CMS-003 specifies AddItem and EmptyCart use `async override Task<Empty>` with await, but GetCart uses `override Task<Cart>` returning Task directly without await. This inconsistency should be explicitly called out as intentional (matching reference) rather than appearing as oversight, and the rationale (performance optimization for passthrough) should be documented. | Add note to REQ-CMS-003 explaining the intentional async pattern difference and its rationale | Code review checklist item to verify async patterns match specification |
| R3-S4 | consistency | medium | Standardize logging approach specification across all requirements | REQ-CMS-002 specifies `Console.WriteLine` for fallback logging, REQ-CMS-005/006/007 specify `Console.WriteLine` for cart operations, but there's no explicit statement that ILogger is NOT used. This could lead to implementations adding ILogger injection, diverging from the reference's simple Console.WriteLine approach. | Add cross-cutting requirement or note in REQ-CMS-002 explicitly stating all logging uses Console.WriteLine, not ILogger | Grep for ILogger absence in generated code |
| R3-S5 | consistency | medium | Align HealthCheckService field declaration style with specification intent | REQ-CMS-008 specifies `private ICartStore _cartStore { get; }` as "(property, not field)" but uses underscore naming convention typical of fields. This mixed terminology could cause implementations to diverge. Clarify whether this is an auto-property with private setter or a get-only property initialized in constructor. | Amend REQ-CMS-008 to show exact declaration syntax: `private ICartStore _cartStore { get; }` with explicit note this is a get-only auto-property | Structural comparison of generated property declaration |
| R3-S6 | feasibility | high | Specify behavior when Secret Manager access fails in AlloyDBCartStore constructor | REQ-CMS-007 specifies fetching password via SecretManagerServiceClient but doesn't specify exception handling if the secret access fails (network error, permission denied, secret not found). Constructor failures during DI would crash the entire service at startup. | Add error handling specification to REQ-CMS-007 constructor: whether to throw, log and use default, or fail fast | Integration test with mocked SecretManager returning errors |
| R3-S7 | feasibility | medium | Address potential race condition in RedisCartStore.AddItemAsync | REQ-CMS-005 specifies get-modify-set pattern for AddItemAsync without transaction or optimistic concurrency. Two concurrent AddItem calls for the same user could result in lost updates. While this matches reference, it should be explicitly documented as a known limitation or specify if the reference uses any Redis transaction primitives. | Add note to REQ-CMS-005 acknowledging the non-atomic read-modify-write pattern matches reference behavior | Review reference implementation for MULTI/EXEC or Lua scripts; document finding |
| R3-S8 | testability | medium | Define expected test behavior when Redis is unavailable in in-memory fallback mode | REQ-CMS-012 test methods use the default host setup but don't specify which cart store backend the tests run against. If tests run in CI without Redis, they'll use in-memory fallback per REQ-CMS-002. Explicitly state that tests are designed to run with in-memory cache fallback. | Add note to REQ-CMS-012 specifying tests use in-memory distributed cache (no external dependencies required) | CI pipeline verification that tests pass without Redis |
| R3-S9 | traceability | high | Add Feature IDs to the Feature list or define features referenced in traceability matrix | The traceability matrix references F-001 through F-007, but these feature IDs are never defined in the document. This makes bidirectional traceability impossible—you cannot trace from a feature to its requirements. | Add a Features section defining F-001 (ASP.NET Core Hosting), F-002 (gRPC Services), F-003 (Cart Store Interface), F-004 (Database Backends), F-005 (Project Configuration), F-006 (Testing), F-007 (Containerization) | Verify all Feature IDs in requirements map to defined features |
| R3-S10 | traceability | medium | Specify which requirements map to which output files in the plan | Requirements reference file paths (e.g., `services/CartService.cs`, `cartstore/ICartStore.cs`) but there's no explicit mapping showing which requirements govern which output files. A single requirement might span multiple files or multiple requirements might govern one file. | Add output file to requirement mapping table, or annotate each requirement with its target output file(s) | Cross-reference plan's output file list with requirements coverage |

#### Review Round R4
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:48:35 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | ambiguity | critical | Define the concrete implementation of the `Ping()` method for each `ICartStore` implementation (Redis, Spanner, AlloyDB). | REQ-CMS-004 defines `bool Ping()` but REQ-CMS-005, 006, and 007 only state "try block returns true, catch returns false" without specifying what operation is attempted. This is too ambiguous to implement or test correctly and impacts the reliability of the health check (REQ-CMS-008). | Add implementation details to the acceptance criteria of REQ-CMS-005, REQ-CMS-006, and REQ-CMS-007. | For each cart store, write a unit test that mocks the underlying dependency to succeed and fail, and assert that `Ping()` returns `true` and `false` respectively. |
| R4-S2 | ambiguity | high | Clarify the fallback cart store implementation in REQ-CMS-002. The log message says "in memory store" but the implementation uses `AddDistributedMemoryCache` with `RedisCartStore`. | This is conceptually confusing. `RedisCartStore` implies a Redis backend. Using it as a wrapper for an in-memory cache is an ambiguous pattern that will confuse future maintainers. The requirement should either specify a dedicated `InMemoryCartStore` class or explicitly state that `RedisCartStore` is being used as a generic `IDistributedCache` consumer. | Modify the fourth bullet point in the `ConfigureServices` acceptance criteria of REQ-CMS-002. | A unit test should confirm that when no other configuration is provided, an `ICartStore` is registered that uses an in-memory cache, regardless of the implementation's class name. |
| R4-S3 | consistency | high | Mandate the use of the standard `ILogger<T>` for all logging instead of `Console.WriteLine`. | Multiple requirements (REQ-CMS-002, REQ-CMS-005, REQ-CMS-006) specify logging via `Console.WriteLine`. This is inconsistent with the standard ASP.NET Core logging framework configured in REQ-CMS-009, bypassing structured logging, log levels, and configurable outputs. | Update REQ-CMS-002, REQ-CMS-005, and REQ-CMS-006 to require constructor injection of `ILogger<T>` and calls to `_logger.LogInformation` or similar methods. | Static code analysis (grep) to ensure no `Console.WriteLine` calls exist in the specified classes and that an `ILogger` is used instead. |
| R4-S4 | consistency | medium | Define a consistent error message policy for `RpcException` thrown by `ICartStore` implementations. | The error messages are inconsistent. REQ-CMS-005 and REQ-CMS-006 leak the full internal exception details (`... {ex}`), a potential information disclosure risk. REQ-CMS-007 uses a different template. A single, safe-by-default policy should be applied to all implementations. | Add a new cross-cutting requirement for error handling, or update the exception handling criteria in REQ-CMS-005, REQ-CMS-006, and REQ-CMS-007. | Unit tests for each cart store's method that trigger an exception and assert the resulting `RpcException`'s status detail message conforms to the specified policy. |
| R4-S5 | consistency | high | Align all referenced NuGet package versions with the specified `net10.0` target framework. | REQ-CMS-010 and REQ-CMS-013 specify a `net10.0` TFM but list versions for testing libraries (`xunit`, `Microsoft.NET.Test.Sdk`) that are current for older frameworks. This is inconsistent and will likely lead to dependency conflicts or build failures. | Update package versions in REQ-CMS-010 and REQ-CMS-013 to versions that are plausible for a .NET 10 project. | Create a temporary project file with the specified TFM and package references and run `dotnet restore` to ensure the package graph is resolvable. |
| R4-S6 | feasibility | critical | Replace the requirement for string-interpolated SQL in `AlloyDBCartStore` (REQ-CMS-007) with a requirement for parameterized queries. | The current requirement (`DELETE FROM {tableName} WHERE userID = '{userId}'`) mandates a SQL injection vulnerability. Requiring the implementation to match a flawed reference on a critical security issue is not a feasible or responsible approach. Security must take precedence over exact replication of unsafe patterns. | Update the data access method criteria in REQ-CMS-007 (specifically for `EmptyCartAsync`). | Code review and static analysis to confirm that all SQL commands in `AlloyDBCartStore` use `NpgsqlParameter` or an equivalent parameterization mechanism. |
| R4-S7 | feasibility | high | In the `Startup.cs` cart store selection logic (REQ-CMS-002), add a requirement to log a warning if configuration variables for multiple cart stores are detected. | The current priority-based selection logic fails silently. If an environment is misconfigured with both `REDIS_ADDR` and `SPANNER_PROJECT` set, the service will pick Redis without any indication that the configuration is ambiguous. This can lead to data being stored in an unexpected backend, a high-severity operational risk. | Add a new acceptance criterion to the `ConfigureServices` section of REQ-CMS-002. | A unit test that configures the `IConfiguration` mock with multiple backend variables set and asserts that a warning message is logged. |
| R4-S8 | testability | medium | Specify in REQ-CMS-012 that each test method (`[Fact]`) must be fully isolated, with no shared state (e.g., `TestServer`, `ICartStore` instance) between them. | The current description of tests doesn't explicitly forbid sharing state. While xUnit creates new test class instances, a shared `TestServer` could persist state across tests, leading to flaky or order-dependent test runs. Explicitly requiring isolation improves test reliability. | Add a new acceptance criterion to REQ-CMS-012, e.g., "Tests must be independent and must not share state that would affect the outcome of other tests." | Code review of the test suite's fixture usage to ensure state is not shared across test methods in a way that would violate isolation. |
| R4-S9 | traceability | high | Update the Traceability Matrix to require behavioral validation (e.g., unit/integration tests) for functional requirements instead of just "Structural diff". | The matrix currently relies on static comparisons ("Structural diff", "Grep"), which verify the shape of the code but not its correctness. For requirements like REQ-CMS-002 (cart store selection logic) or REQ-CMS-005 (Redis cart logic), this is insufficient. The validation method must confirm the code behaves as expected. | Update the "Validation Method" column in the Traceability Matrix for REQ-CMS-002, REQ-CMS-003, REQ-CMS-005, REQ-CMS-006, REQ-CMS-007. | Review the project's test plan to confirm that test cases exist that directly validate the behavior specified in the requirements, not just the code structure. |
| R4-S10 | traceability | high | Strengthen the validation method for the gRPC Health Check (REQ-CMS-008) in the Traceability Matrix. | The current validation, "Grep for `HealthBase` and `Ping()` integration," is a weak check. It does not confirm that the health check returns the correct status (`SERVING` or `NOT_SERVING`) based on the `Ping()` result. This is a critical behavioral aspect of the health check. | Update the "Validation Method" for REQ-CMS-008 in the Traceability Matrix to: "Unit test that mocks `ICartStore.Ping()` and asserts the correct `ServingStatus`." | Implement a unit test for `HealthCheckService` that mocks `ICartStore.Ping()` to return `true` and `false` and asserts that the `Check` method returns a `HealthCheckResponse` with the corresponding `ServingStatus`. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 19:51:25 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Requirement |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | clarity | high | Define Feature IDs F-001 through F-007 in the requirements document | The Traceability Matrix references F-001 through F-007 but these are only defined in the plan, not the requirements. For proper traceability, feature definitions belong in requirements so implementations can be traced back to defined capabilities. | Add Feature Definitions section after Scope |
| R5-F2 | security | critical | Add explicit security exception for AlloyDB SQL injection pattern | REQ-CMS-007 states "matches reference" for string interpolation SQL but doesn't explicitly acknowledge this as a security exception. Future audits may flag this. Add note: "Security Note: String interpolation is used intentionally to match reference implementation. Production forks should use parameterized queries." | REQ-CMS-007 acceptance criteria |
| R5-F3 | testability | medium | Specify concrete Ping() implementation for each cart store in requirements | Applied suggestions R2-S2 and R4-S1 both identify that Ping() lacks implementation specification, but neither is reflected in the requirements document yet. Each ICartStore implementation needs: RedisCartStore checks cache, SpannerCartStore opens connection, AlloyDBCartStore executes `SELECT 1`. | REQ-CMS-005, REQ-CMS-006, REQ-CMS-007 |
| R5-F4 | clarity | medium | Clarify protos/ directory location relative to src/ directory | REQ-CMS-015 says `protos/Cart.proto` and REQ-CMS-010 says `protos\Cart.proto` in Protobuf Include. The plan shows `src/cartservice/src/protos/Cart.proto`. Clarify this is relative to the .csproj file location (inside src/). | REQ-CMS-015 and REQ-CMS-010 |
| R5-F5 | completeness | medium | Specify GrpcChannelOptions.HttpHandler for test client HTTP/2 support | REQ-CMS-012 doesn't specify the HttpHandler configuration needed for HTTP/2 over TestServer. Without `HttpVersionPolicy = HttpVersionPolicy.RequestVersionExact` and proper handler setup, gRPC tests fail. | REQ-CMS-012 acceptance criteria |

#### Review Round R4

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:53:32 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Impacted Requirement(s) |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | security | critical | The requirement to log full exception details in `RpcException` must be removed. | The current requirement mandates a CWE-209 (Information Disclosure) vulnerability. Security best practices must override the goal of exactly matching a reference implementation's flawed behavior. The requirement should specify returning a generic error message to the client. | REQ-CMS-005, REQ-CMS-006 |
| R4-F2 | testability | high | The requirement for `AlloyDBCartStore` should promote a testable design via Dependency Injection. | By specifying a constructor that directly instantiates `SecretManagerServiceClient`, the requirement makes the component inherently difficult to unit test. The requirement should be updated to specify that the client is received via constructor injection. | REQ-CMS-007 |
| R4-F3 | completeness | medium | The requirement for `RedisCartStore.AddItemAsync` is incomplete as it omits the non-functional characteristic of being non-atomic. | The specified get-modify-set pattern has a race condition that leads to data loss. This is a critical behavioral detail. The requirement should be updated to include a note explicitly stating that this operation is not atomic and is subject to data loss under concurrent requests. | REQ-CMS-005 |
| R4-F4 | architecture | medium | The requirement for the fallback cart store promotes a confusing and tightly-coupled design. | REQ-CMS-002, case 4, requires using `RedisCartStore` as an in-memory store. This conflates two distinct responsibilities. The requirement should be changed to specify a dedicated `InMemoryCartStore` implementation for the fallback case to improve architectural clarity. | REQ-CMS-002 |
| R4-F5 | completeness | high | The `AlloyDBCartStore` requirement is missing the authentication prerequisite. | REQ-CMS-007 requires using `SecretManagerServiceClient` but fails to specify how the service authenticates to it. The requirement should be updated to explicitly state the prerequisite of having Application Default Credentials configured in the execution environment. | REQ-CMS-007 |

#### Review Round R5

**Reviewer**: claude-4 (claude-opus-4-5)
**Date**: 2026-02-20 19:57:46 UTC
**Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | consistency | high | Add explicit consistency requirement between ICartStore interface method signatures and all implementation classes (RedisCartStore, SpannerCartStore, AlloyDBCartStore) | REQ-CMS-004 defines the interface but REQ-CMS-005/006/007 don't explicitly mandate matching signatures. For example, REQ-CMS-005 describes `AddItemAsync` behavior but doesn't confirm the exact return type `Task` vs `Task<bool>`. This could lead to subtle interface contract violations during generation. | Add to REQ-CMS-004 or create new cross-cutting requirement linking interface to implementations | Compile-time verification that all implementations satisfy interface contract; automated interface conformance check |
| R5-S2 | consistency | high | Standardize error handling pattern across all cart store implementations with explicit RpcException status codes | REQ-CMS-005 and REQ-CMS-006 specify `StatusCode.FailedPrecondition`, but REQ-CMS-007 uses a different error message pattern ("Unable to access cart storage due to an internal error") without explicitly specifying the status code. This inconsistency could cause different client-side handling for identical failure scenarios. | Add explicit `StatusCode.FailedPrecondition` requirement to REQ-CMS-007's error handling section | Grep for StatusCode usage in all cart store files; verify consistent RpcException construction |
| R5-S3 | consistency | medium | Define consistent logging format pattern across all cart store implementations | REQ-CMS-005 shows `Console.WriteLine($"AddItemAsync called with userId={userId}, productId={productId}, quantity={quantity}")` but other requirements don't specify the exact log message format for equivalent operations in SpannerCartStore and AlloyDBCartStore. This creates inconsistent observability. | Add logging format specification to REQ-CMS-006 and REQ-CMS-007 acceptance criteria | Log output comparison across all three cart store implementations during integration testing |
| R5-S4 | feasibility | high | Specify .NET 10.0 SDK availability and compatibility verification for all NuGet package versions | REQ-CMS-010 specifies `net10.0` target framework and specific package versions (e.g., `Microsoft.Extensions.Caching.StackExchangeRedis` 10.0.2), but .NET 10.0 is future-dated (expected Nov 2025). The document needs explicit verification that all specified package versions exist and are compatible with this TFM. | Add package version compatibility validation to REQ-CMS-V01 or create dedicated REQ-CMS-V03 for dependency resolution | Execute `dotnet restore` in CI to verify all packages resolve successfully against net10.0 |
| R5-S5 | traceability | high | Add feature-to-requirement reverse mapping table | The Traceability Matrix maps requirements to features but lacks reverse mapping (features to requirements). For generation validation, knowing "what requirements must be satisfied for F-003 (Cart Store Interface & Redis Implementation)" is essential for partial feature validation. | Add new "Feature Coverage Matrix" section after existing Traceability Matrix | Automated bidirectional traceability check verifying all features have complete requirement coverage |
| R5-S6 | feasibility | medium | Specify Secret Manager API authentication requirements for AlloyDBCartStore | REQ-CMS-007 uses `SecretManagerServiceClient.Create()` which requires Application Default Credentials (ADC) in GCP environments. The requirement doesn't specify how authentication should be handled in local development or testing scenarios, making the implementation infeasible without GCP credentials. | Add authentication context clarification to REQ-CMS-007 or cross-cutting requirements section | Unit test mock verification; document ADC fallback behavior for non-GCP environments |
| R5-S7 | traceability | medium | Link configuration keys to their consuming requirements | The document references configuration keys (`REDIS_ADDR`, `SPANNER_PROJECT`, `ALLOYDB_PRIMARY_IP`, etc.) across multiple requirements (REQ-CMS-002, REQ-CMS-006, REQ-CMS-007) but lacks a consolidated configuration key inventory with requirement traceability. | Add "Configuration Key Traceability" table listing each env var, its type, default value, and consuming requirements | Automated extraction of configuration key usage from generated code compared against inventory |
| R5-S8 | consistency | medium | Reconcile Protobuf namespace casing between proto definition and C# code references | REQ-CMS-015 defines `package hipstershop` (lowercase) but REQ-CMS-003 and others reference `Hipstershop.CartService.CartServiceBase` (PascalCase). While protoc generates PascalCase by default, the document should explicitly state this transformation rule to ensure consistent expectations. | Add namespace transformation note to REQ-CMS-015 acceptance criteria | Verify generated proto stubs use `Hipstershop` namespace; grep for consistent casing across all .cs files |
| R5-S9 | feasibility | medium | Clarify SpannerConnection retry semantics and transaction isolation | REQ-CMS-006 specifies `RunWithRetriableTransactionAsync` for AddItemAsync but doesn't define expected retry behavior (max attempts, backoff strategy) or transaction isolation level. This affects deterministic behavior validation. | Add transaction configuration details to REQ-CMS-006 or explicitly state "use library defaults" | Integration test with simulated transient failures; verify retry count matches expected behavior |
| R5-S10 | traceability | medium | Add validation method cross-references to each requirement's acceptance criteria | The Traceability Matrix specifies validation methods but these aren't linked back to the requirements themselves. Each REQ-CMS-XXX should reference its validation method to enable self-contained requirement verification. | Add "Validation: See Traceability Matrix" or inline validation reference to each requirement's header | Document linting to verify bidirectional references between requirements and validation methods |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R4-S5: The consistency requirement for cart store implementations accepting IConfiguration uniformly is directly related to my R5-S1 finding about interface-implementation consistency and strengthens the overall type contract coherence.

#### Review Round R6
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:58:25 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | consistency | medium | Standardize gRPC exception status code and message format across all `ICartStore` implementations. | REQ-CMS-005/006 use `StatusCode.FailedPrecondition` and the message "Can't access cart storage...", while REQ-CMS-007 uses a different message ("Unable to access..."). This inconsistency complicates client-side error handling and diagnostics. | Modify acceptance criteria for REQ-CMS-005, REQ-CMS-006, and REQ-CMS-007 to specify a single, shared exception handling pattern. | Code review of exception handling blocks in all `ICartStore` implementations to ensure they throw `RpcException` with a consistent `Status`. |
| R6-S2 | consistency | high | Mandate the use of injected `ILogger<T>` for all application logging instead of `Console.WriteLine`. | `Console.WriteLine` bypasses the configured ASP.NET Core logging infrastructure (levels, formatters, providers). Using `ILogger` is standard practice, ensuring logs are structured, filterable, and routed correctly in production environments. | Modify REQ-CMS-002, REQ-CMS-005, REQ-CMS-006, REQ-CMS-008 to replace `Console.WriteLine` with `_logger.LogInformation` or similar, and require `ILogger<T>` injection in constructors. | Static analysis or code review to ensure no `Console.WriteLine` calls remain for application logging purposes. |
| R6-S3 | consistency | critical | Unify the behavior of `EmptyCartAsync` across all storage backends to perform a hard delete of the cart record. | REQ-CMS-005 specifies overwriting the Redis key with an empty cart (a soft delete), while REQ-CMS-006 and REQ-CMS-007 specify a hard `DELETE` operation. This is a major behavioral inconsistency that affects data persistence, storage usage, and user expectations. | Modify acceptance criteria for REQ-CMS-005 (`RedisCartStore`) to require calling `_cache.RemoveAsync(userId)` instead of `_cache.SetAsync` with an empty cart. | A unit test for `RedisCartStore.EmptyCartAsync` must assert that `IDistributedCache.RemoveAsync` is called. |
| R6-S4 | feasibility | high | Change `TrimMode=full` in REQ-CMS-014 to `TrimMode=link` or add a requirement for trim analysis and rooting. | `TrimMode=full` is highly aggressive and can break applications that rely on reflection (e.g., Protobuf serialization, DI) without careful configuration. This poses a significant risk of producing a non-functional binary that is difficult to debug. `TrimMode=link` is a safer default. | Modify the `RUN dotnet publish` command in the acceptance criteria for REQ-CMS-014. | Inspect the `RUN dotnet publish` command in the final Dockerfile to ensure the trim mode is updated. |
| R6-S5 | feasibility | medium | Specify major/minor package versions in REQ-CMS-010 (e.g., `10.0.*`) instead of pinning exact patch versions. | Pinning exact patch versions for a future .NET release is brittle. It prevents automatic adoption of security patches and bug fixes, and risks specifying a version that may be buggy or incompatible upon release. A floating patch version is more resilient and secure. | Modify the package reference versions in the acceptance criteria for REQ-CMS-010. | Review the generated `cartservice.csproj` file to confirm it uses floating patch versions for its package references. |
| R6-S6 | feasibility | high | Specify that `SecretManagerServiceClient` in REQ-CMS-007 must be registered as a singleton in DI and injected into `AlloyDBCartStore`. | Creating a new client in the constructor is an anti-pattern for expensive, thread-safe objects. It's inefficient and can lead to performance degradation or resource exhaustion under load. The idiomatic and feasible approach is to use a singleton instance managed by the DI container. | Add a service registration requirement to `ConfigureServices` in REQ-CMS-002; modify the `AlloyDBCartStore` constructor in REQ-CMS-007 to accept the client via DI. | Review DI configuration in `Startup.cs` and the constructor signature of `AlloyDBCartStore.cs`. |
| R6-S7 | traceability | high | Add a requirement for unit tests that validate the cart store selection logic in REQ-CMS-002. | The current validation method ("Structural diff") is insufficient as it only verifies code shape, not behavior. Tests are needed to set different configuration variables and assert that the correct `ICartStore` implementation is resolved by the DI container, proving the fallback logic works. | Add a new sub-bullet to REQ-CMS-012; update `Validation Method` in the Traceability Matrix for REQ-CMS-002. | Review the test suite for tests specifically covering the `Startup.ConfigureServices` DI logic under various configuration scenarios. |
| R6-S8 | traceability | medium | Enhance validation for REQ-CMS-008 to require a unit test for `HealthCheckService` that verifies the `ServingStatus` reflects the mocked `ICartStore.Ping()` result. | The current validation ("Grep for... integration") only checks structure, not the functional correctness of the health check. A test is needed to prove the service correctly reports `Serving` and `NotServing` based on its dependency's status. | Add a new test method requirement to REQ-CMS-012; update `Validation Method` in the Traceability Matrix for REQ-CMS-008. | Review `CartServiceTests.cs` (or a new test file) for a health check test that mocks `ICartStore.Ping()` and asserts the gRPC response. |
| R6-S9 | traceability | medium | Strengthen validation for REQ-CMS-009a (No OTel) to include a check of final compiled assembly references. | "Grep for absence of... imports" is a weak validation that can be bypassed (e.g., if code is added without `using` statements). Verifying the actual project dependencies in `project.assets.json` or the final output is a more robust way to enforce this negative requirement. | Update `Validation Method` in the Traceability Matrix for REQ-CMS-009a. | Implement a post-build script or manual check that inspects the build output's dependency graph for any `OpenTelemetry.*` assemblies. |
| R6-S10 | consistency | critical | Mandate the use of parameterized queries in REQ-CMS-007 (`AlloyDBCartStore`) to prevent SQL injection. | REQ-CMS-007 explicitly allows string-interpolated SQL, which is a critical security vulnerability. This is also inconsistent with REQ-CMS-006 (`SpannerCartStore`), which uses parameters. The "matches reference" argument is insufficient justification for propagating a known vulnerability. | Modify acceptance criteria for REQ-CMS-007's `AddItemAsync`, `GetCartAsync`, and `EmptyCartAsync` methods to forbid string interpolation and require parameterized queries (e.g., using `NpgsqlParameter`). | Code review of `AlloyDBCartStore.cs` to ensure all SQL commands use parameter objects and are not built with string concatenation/interpolation of user input. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:00:52 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Requirement |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | clarity | high | Define Feature IDs F-001 through F-007 in the requirements document | The Traceability Matrix references F-001 through F-007 but these are only defined implicitly via the plan's feature sections. For bidirectional traceability, the requirements document should define: F-001 (ASP.NET Core Hosting), F-002 (gRPC Services), F-003 (Cart Store Interface), F-004 (Database Backends), F-005 (Project Configuration), F-006 (Testing), F-007 (Containerization). | Add "Feature Definitions" section between Scope and Functional Requirements |
| R5-F2 | clarity | high | Specify HTTP/2 handler configuration requirements for gRPC test client | REQ-CMS-012 mentions GrpcChannel but doesn't specify the required HttpHandler configuration for HTTP/2 over TestServer. Without `Version = HttpVersion.Version20` and appropriate policy, tests will fail with protocol errors. | Add to REQ-CMS-012: "GrpcChannelOptions must configure HttpHandler with HTTP/2 version policy" |
| R5-F3 | testability | medium | Specify concrete Ping() operation for each ICartStore implementation | REQ-CMS-005/006/007 only state "try block returns true, catch returns false" without specifying what operation verifies connectivity. RedisCartStore should attempt cache access, SpannerCartStore should verify connection, AlloyDBCartStore should execute lightweight query. | Add to each cart store requirement: specific Ping() operation (e.g., "Ping() executes SELECT 1 via NpgsqlDataSource") |
| R5-F4 | architecture | medium | Clarify that ICartStore implementations receive IConfiguration uniformly | REQ-CMS-006 and REQ-CMS-007 show constructor injection of IConfiguration, but REQ-CMS-005 shows IDistributedCache injection. This asymmetry in constructor signatures should be explicitly documented as intentional (Redis uses DI-provided cache; others build connections from config). | Add note to REQ-CMS-004 or cross-cutting section explaining constructor parameter asymmetry across implementations |
| R5-F5 | maintainability | medium | Document the protos/ directory location relative to src/ directory | REQ-CMS-015 says `protos/Cart.proto` and REQ-CMS-010 says `protos\Cart.proto` but neither clarifies this is relative to the .csproj file (i.e., `src/cartservice/src/protos/Cart.proto`). This affects both project reference and Dockerfile COPY paths. | Add explicit path clarification to REQ-CMS-015: "Located at src/cartservice/src/protos/Cart.proto relative to repository root" |

#### Review Round R6

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:02:46 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Impacted Requirement(s) |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | clarity | high | Explicitly document the behavioral inconsistency of `EmptyCartAsync` in `RedisCartStore`. | REQ-CMS-005 specifies that `EmptyCartAsync` overwrites the cart with an empty one (a soft-delete), while REQ-CMS-006 and REQ-CMS-007 specify a hard `DELETE`. This is a critical behavioral difference. The requirement should explicitly call this out as an intentional pattern matching the reference to avoid it being mistaken for a bug. | REQ-CMS-005 |
| R6-F2 | architecture | medium | Reconcile the "minimal hosting pattern" terminology in REQ-CMS-001 with the specified implementation. | REQ-CMS-001 states it uses the "minimal hosting pattern" but then describes the older .NET 5 `UseStartup<Startup>` pattern. True minimal hosting (since .NET 6) uses `WebApplication.CreateBuilder` and a top-level route map. The requirement is architecturally inconsistent, which will confuse implementers. It should either use the correct terminology for the pattern or specify the modern pattern. | REQ-CMS-001 |
| R6-F3 | architecture | high | Specify resilience policies (retries, timeouts) for the `AlloyDBCartStore` constructor logic. | REQ-CMS-007 describes a constructor that performs multiple I/O operations (reading config, calling Secret Manager). A transient failure in any of these steps during application startup would be fatal. The requirement should specify if this critical initialization path should include resilience patterns like retries with backoff. | REQ-CMS-007 |
| R6-F4 | testability | high | The requirements should mandate behavioral tests for `ICartStore` implementations. | Multiple applied suggestions (e.g., R4-S9) call for stronger behavioral validation, but the test requirements (REQ-CMS-012) remain focused only on end-to-end gRPC tests. The requirements document should include a new section for data-layer-specific tests to verify the logic of each `ICartStore` implementation directly. | REQ-CMS-012, REQ-CMS-013 |

---

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:05:47 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | feasibility | high | Add explicit memory/resource constraints for the trimmed single-file deployment to validate runtime viability | REQ-CMS-014 specifies `PublishTrimmed=true` and `TrimMode=full` but doesn't address the feasibility risk that aggressive trimming may remove reflection-dependent code paths used by gRPC, Protobuf deserialization, or DI container. The chiseled base image with trimming needs validated compatibility with `Grpc.AspNetCore` and `Google.Cloud.*` packages. | Add new REQ-CMS-V03 under Validation Requirements specifying trimming compatibility validation | Run trimmed binary in container with all 4 cart store backends; verify no `MissingMethodException` or trimming-related runtime failures |
| R7-S2 | feasibility | high | Specify SecretManagerServiceClient authentication mechanism for AlloyDB password retrieval | REQ-CMS-007 uses `SecretManagerServiceClient.Create()` but doesn't specify how GCP credentials are provided in the container runtime. The chiseled image (REQ-CMS-014) runs as non-root user 1000 without shell access, making credential mounting non-trivial. | Add acceptance criterion to REQ-CMS-007 specifying expected authentication: Application Default Credentials via `GOOGLE_APPLICATION_CREDENTIALS` env var or Workload Identity | Verify AlloyDBCartStore initialization succeeds with mounted service account JSON or workload identity in GKE |
| R7-S3 | feasibility | medium | Address proto compilation toolchain requirements for `Cart.proto` in build pipeline | REQ-CMS-015 defines proto and REQ-CMS-010 references `<Protobuf Include="protos\Cart.proto">` but doesn't specify whether `Grpc.Tools` package is required for proto compilation or if pre-generated stubs are expected. The csproj lacks `Grpc.Tools` in package references. | Add `Grpc.Tools` version `2.76.0` to REQ-CMS-010 package references OR add acceptance criterion that proto stubs are pre-generated | Build project from clean state; verify proto compilation succeeds without manual intervention |
| R7-S4 | traceability | high | Add requirement-to-test-method traceability linking REQ-CMS-003 through REQ-CMS-008 to specific test coverage | REQ-CMS-012 defines 3 test methods but the Traceability Matrix only maps tests to F-006. There's no visibility into which functional requirements (AddItem, GetCart, EmptyCart, Ping) are covered by which tests. | Extend Traceability Matrix with Test Coverage column showing: `GetItem_NoAddItemBefore_EmptyCartReturned` → REQ-CMS-003 (GetCart), `AddItem_ItemExists_Updated` → REQ-CMS-003 (AddItem, GetCart), REQ-CMS-005 | Review test method implementations against requirement acceptance criteria |
| R7-S5 | traceability | high | Add bidirectional traceability from Features (F-001 through F-007) back to requirements | Traceability Matrix maps requirements→features but not features→requirements. This makes impact analysis difficult when a feature changes. F-003 (ICartStore) maps to REQ-CMS-004/005 but there's no reverse lookup in the document. | Add Feature-to-Requirement reverse mapping section after Traceability Matrix: F-001→REQ-CMS-001,002; F-002→REQ-CMS-003,008,015; F-003→REQ-CMS-004,005; F-004→REQ-CMS-006,007; F-005→REQ-CMS-009,009a,010,011; F-006→REQ-CMS-012,013; F-007→REQ-CMS-014 | Verify all features have at least one requirement; verify all requirements map to exactly one feature |
| R7-S6 | traceability | medium | Link validation requirements (REQ-CMS-V01, V02) to the functional requirements they validate | REQ-CMS-V01 and V02 are listed in Validation Requirements but not in the Traceability Matrix, breaking traceability chain. V01 (Syntax Validity) should trace to all code-generating requirements; V02 (Structural Comparability) should trace to specific structural requirements. | Add rows to Traceability Matrix: REQ-CMS-V01 traces to REQ-CMS-001 through REQ-CMS-015; REQ-CMS-V02 traces to REQ-CMS-001 through REQ-CMS-008, REQ-CMS-012 | Verify validation requirements appear in matrix with explicit coverage scope |
| R7-S7 | feasibility | medium | Specify Redis connection failure behavior during Startup for fallback cart store | REQ-CMS-002 specifies cart store selection at startup based on config presence, but if `REDIS_ADDR` is set but Redis is unreachable, the service will fail at first request not at startup. This differs from AlloyDB which fails at `SecretManagerServiceClient.Create()`. Document expected behavior. | Add acceptance criterion to REQ-CMS-002: "Cart store initialization errors are deferred to first request; Startup.ConfigureServices must not throw on unreachable backends" | Configure `REDIS_ADDR` pointing to non-existent host; verify service starts and fails gracefully on first gRPC call |
| R7-S8 | feasibility | medium | Clarify Spanner connection retry semantics under `RunWithRetriableTransactionAsync` | REQ-CMS-006 uses `SpannerConnection.RunWithRetriableTransactionAsync` for AddItem but doesn't specify retry policy. Default Spanner retry can cause duplicate quantity additions if transaction is retried after partial commit visibility. | Add acceptance criterion to REQ-CMS-006 specifying idempotency expectation or noting that default Spanner retry semantics apply | Review generated code for proper use of transaction scope; verify quantity consistency under simulated transient failures |
| R7-S9 | traceability | medium | Add dependency traceability between requirements showing REQ-CMS-008 depends on REQ-CMS-004 | HealthCheckService (REQ-CMS-008) calls `ICartStore.Ping()` (REQ-CMS-004) but this interface dependency isn't captured in the matrix. Changes to ICartStore.Ping signature would break HealthCheckService without clear traceability. | Add Dependencies column to Traceability Matrix or separate Dependency section: REQ-CMS-008 depends on REQ-CMS-004; REQ-CMS-003,005,006,007 depend on REQ-CMS-004; REQ-CMS-002 depends on REQ-CMS-005,006,007 | Parse requirements for interface/class references; verify all cross-requirement dependencies are documented |
| R7-S10 | feasibility | low | Specify expected behavior when multiple cart store environment variables are set simultaneously | REQ-CMS-002 defines priority order (Redis→Spanner→AlloyDB→InMemory) but doesn't specify whether setting both `REDIS_ADDR` and `ALLOYDB_PRIMARY_IP` logs a warning about ignored configuration. Silent ignoring of AlloyDB config when Redis is set could cause deployment confusion. | Add acceptance criterion to REQ-CMS-002: "When multiple cart store configurations are present, only the highest-priority store is used; no warning is logged for lower-priority configurations (matching reference behavior)" | Set all four config options; verify only Redis store is instantiated and no warnings are logged |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None identified in untriaged pool that warrant endorsement based on current document state and priority gaps.

#### Review Round R8
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:06:31 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | feasibility | critical | Specify the expected authentication mechanism for Google Cloud services (Spanner, Secret Manager) instead of relying on implicit Application Default Credentials (ADC). | REQ-CMS-006 and REQ-CMS-007 require connecting to GCP services, which implicitly relies on a correctly configured ADC environment. This makes the requirement infeasible to implement or test in any environment (local, CI, other clouds) where ADC is not available, creating a hidden, critical dependency. | Add a new cross-cutting requirement under "Cross-Cutting Requirements" defining authentication assumptions and strategies (e.g., support for service account keys). | Review the new requirement to ensure it provides explicit guidance on how the service should authenticate to GCP, making the behavior predictable across different environments. |
| R8-S2 | feasibility | high | The `PublishTrimmed=true` and `TrimMode=full` settings in REQ-CMS-014 are high-risk and can cause runtime failures due to reflection-based code being removed by the trimmer. | Aggressive trimming can break libraries like gRPC, DI containers, and database drivers in non-obvious ways that are not caught at compile time. Mandating this without a corresponding requirement for runtime validation makes it infeasible to guarantee a working application. | Add a sub-bullet to REQ-CMS-014 requiring runtime verification tests (e.g., running the unit/integration tests against the trimmed binary) to prove that trimming did not break functionality. | Confirm that REQ-CMS-014's acceptance criteria has been updated to include a validation step that executes tests against the final, trimmed application artifact. |
| R8-S3 | feasibility | critical | The requirement in REQ-CMS-007 to use string interpolation for SQL queries makes it infeasible to meet standard security requirements. | Mandating a practice that is a known vector for SQL injection (OWASP A03:2021) directly conflicts with unstated but universal non-functional requirements for security. A system required to be insecure is not a feasibly buildable system for production use. | Modify REQ-CMS-007 to explicitly require the use of parameterized queries (e.g., via `NpgsqlParameter`) for all database commands in `AlloyDBCartStore`. | Inspect the updated acceptance criteria in REQ-CMS-007 to ensure it mandates parameterized queries and forbids string interpolation for user-provided values in SQL. |
| R8-S4 | feasibility | high | The use of a "chiseled" runtime-deps image in REQ-CMS-014 introduces a risk of runtime failures due to missing native dependencies (e.g., ICU for globalization) that are not present in such minimal images. | It is not feasible to guarantee a working application without validating its behavior in the target minimal environment. The requirement specifies the environment but not the validation needed to prove the application is compatible with it. | Add a sub-bullet to REQ-CMS-014 requiring a validation step where the application is started and its health checked from within the final chiseled container to ensure all runtime dependencies are met. | Review REQ-CMS-014 to verify the presence of a validation step that confirms the application runs successfully within the chiseled container environment. |
| R8-S5 | feasibility | medium | The tests specified in REQ-CMS-012 are integration tests, not unit tests. This makes the validation strategy infeasible for providing the rapid, isolated feedback characteristic of a unit test suite. | By using `TestServer` and a full `IHostBuilder`, the tests are coupled to the entire application stack (DI, configuration, hosting). This slows down execution and makes it hard to pinpoint failures in business logic vs. infrastructure. The requirement misrepresents the validation being performed. | Update REQ-CMS-012 to either re-classify the tests as "Integration Tests" or, preferably, specify true unit tests for `CartService` that mock the `ICartStore` dependency. | Review REQ-CMS-012 to confirm the tests are either correctly labeled or have been refactored to be true unit tests with mocked dependencies. |
| R8-S6 | traceability | high | Feature IDs (e.g., F-001) are used throughout the document but are never defined. | The traceability matrix links requirements to opaque feature IDs. Without a definition for what each feature entails, the matrix is not useful for understanding scope or performing impact analysis. It's a traceability dead-end. | Add a new section before the "Functional Requirements" that lists and briefly describes each Feature ID (F-001 through F-007). | Verify that a new "Features" or "Feature Definitions" section exists and that it defines all F-xxx IDs used in the traceability matrix. |
| R8-S7 | traceability | high | The document's claim that the "reference implementation serves as the ground truth" is not supported by the traceability matrix. | The matrix's "Validation Method" column describes an action (e.g., "Structural diff") but does not provide a direct, static link to the source of truth (e.g., the specific file path in the reference repo). This makes it difficult to verify or maintain the requirements as the reference code evolves. | Add a new column to the Traceability Matrix, "Ground Truth Reference", that contains the specific file path(s) in the reference implementation corresponding to each requirement. | Inspect the Traceability Matrix to confirm the existence of the new column and that it is populated with relevant file paths from the reference implementation. |
| R8-S8 | traceability | medium | External configuration keys (e.g., `REDIS_ADDR`, `SPANNER_PROJECT`) are magic strings. Their origin, format, and purpose are not traced. | The requirements specify that the application consumes these variables, but not where they are defined or what contract they must adhere to. This leads to configuration brittleness and makes it difficult for operators to correctly deploy the service. | Add an appendix or a new cross-cutting requirement that lists all external configuration variables, their purpose, whether they are optional, and their expected format. | Verify the existence of a new section or appendix that serves as a data dictionary for all environment variables and configuration keys used by the service. |
| R8-S9 | traceability | medium | The document does not trace dependencies between requirements. | Many requirements have implicit dependencies (e.g., REQ-CMS-003 depends on REQ-CMS-004). Without making these dependencies explicit, it is difficult to perform impact analysis; a change to one requirement may have untracked consequences for others. | Add a "Depends On" column to the Traceability Matrix to explicitly list the IDs of any other requirements that are prerequisites. | Inspect the Traceability Matrix for the new "Depends On" column and check that logical dependencies (e.g., between a service implementation and its interface) are captured. |
| R8-S10 | consistency | high | The error handling and logging strategies are inconsistent across the different `ICartStore` implementations. | REQ-CMS-005, 006, and 007 specify different logging details and exception message formats. Critically, REQ-CMS-007 does not specify that an `RpcException` should be thrown, which will cause the gRPC service to return a generic `Unknown` error to the client, violating the expected error contract. | Update REQ-CMS-005, REQ-CMS-006, and REQ-CMS-007 to mandate a single, consistent approach: all data access exceptions must be caught and re-thrown as an `RpcException` with a consistent status code (e.g., `FailedPrecondition`), and logging should follow a uniform pattern. | Review the acceptance criteria for all `ICartStore` implementations to confirm they specify a uniform exception type (`RpcException`) and logging strategy. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:09:43 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Requirement |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | clarity | high | REQ-CMS-010 is missing Grpc.Tools package reference required for proto compilation | The csproj specifies `<Protobuf Include="protos\Cart.proto">` which requires Grpc.Tools to compile. Without it, the project won't build from clean state. R7-S3 was applied noting this gap but REQ-CMS-010 package list still omits Grpc.Tools. | Add `Grpc.Tools` version `2.76.0` to REQ-CMS-010 package references |
| R7-F2 | architecture | high | REQ-CMS-002 doesn't specify the DI container lifetime semantics for ICartStore registration | All four registration paths use AddSingleton but the implications differ: Redis wraps IDistributedCache (also singleton), Spanner/AlloyDB hold configuration strings. The requirement should explicitly state Singleton lifetime and rationale. | Add acceptance criterion to REQ-CMS-002: "All ICartStore implementations registered as Singleton; constructor parameters are configuration values or DI-managed services" |
| R7-F3 | maintainability | medium | REQ-CMS-005/006/007 Ping() methods lack specification of what connectivity check to perform | Applied suggestions R2-S2, R4-S1 noted this gap but requirements still say only "try block returns true, catch returns false". Each backend needs specific operation: Redis=cache access attempt, Spanner=connection open, AlloyDB=SELECT 1. | Add to each requirement: RedisCartStore.Ping() calls `_cache.GetAsync("ping")`, SpannerCartStore.Ping() opens SpannerConnection, AlloyDBCartStore.Ping() executes `SELECT 1` via NpgsqlDataSource |
| R7-F4 | testability | high | REQ-CMS-012 test setup lacks HTTP/2 handler configuration required for gRPC over TestServer | R1-S5 was applied but acceptance criteria still show only `GrpcChannelOptions { HttpClient = httpClient }`. TestServer requires ResponseVersion and HttpVersionPolicy configuration for HTTP/2 protocol. | Add to REQ-CMS-012: `GrpcChannelOptions` must include `HttpHandler` configured with `new SocketsHttpHandler { HttpVersionPolicy = HttpVersionPolicy.RequestVersionExact }` or equivalent TestServer-compatible handler |
| R7-F5 | architecture | medium | REQ-CMS-001 uses "minimal hosting pattern" terminology incorrectly | REQ-CMS-001 says "uses top-level statements (C# 9+ minimal hosting pattern)" but then specifies `CreateHostBuilder`/`UseStartup<Startup>` which is the Generic Host pattern, not the .NET 6+ Minimal Hosting pattern using `WebApplication.CreateBuilder`. | Correct REQ-CMS-001 to say "uses top-level statements (C# 9+) with Generic Host pattern" or specify actual Minimal Hosting APIs |
| R7-F6 | scalability | medium | REQ-CMS-006/007 don't specify connection pooling or resource management expectations | Database connection management significantly impacts scalability. Requirements should specify whether per-operation connection creation (current reference behavior) is intentional or if connection pooling configuration is expected. | Add note to REQ-CMS-006/007: "Connection created per operation; no explicit connection pooling configuration (matches reference implementation)" |

#### Review Round R8

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:11:55 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Impacted Requirement(s) |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | architecture | critical | REQ-CMS-007 should not mandate an anti-pattern for database connections. | The requirement to create `NpgsqlDataSource` on every call is fundamentally broken from a scalability and performance perspective. The acceptance criteria should be changed to specify that a single, shared `NpgsqlDataSource` instance is used for all operations within the `AlloyDBCartStore`. | REQ-CMS-007 |
| R8-F2 | clarity | high | REQ-CMS-001 uses incorrect terminology for the hosting model. | The requirement incorrectly labels the `.NET 5`-style `UseStartup<Startup>()` pattern as the "C# 9+ minimal hosting pattern". This is architecturally misleading. The requirement should be rephrased to correctly identify the pattern as "generic host with a `Startup` class". | REQ-CMS-001 |
| R8-F3 | testability | high | REQ-CMS-007 makes `AlloyDBCartStore` untestable by requiring direct client instantiation. | Requiring `SecretManagerServiceClient.Create()` inside the constructor prevents dependency injection and makes unit testing impossible without live credentials. Re-proposing against the rejection of R6-S6: the requirement itself must be changed to mandate constructor injection of the client to be considered verifiable and testable. | REQ-CMS-007 |
| R8-F4 | scalability | medium | REQ-CMS-005 should explicitly acknowledge the race condition in `AddItemAsync`. | The get-modify-set logic specified for Redis is a known race condition. The requirement should be updated to include a note that this behavior matches the reference but is not atomic and has known scalability limitations under concurrent access. | REQ-CMS-005 |
| R8-F5 | clarity | medium | REQ-CMS-012 should be more precise about the nature of the tests. | The requirement calls the tests "Unit Tests", but the use of `TestServer` and a full `IHostBuilder` makes them integration tests. The requirement should be relabeled to "Integration Tests (xUnit)" to accurately reflect the test scope and methodology. | REQ-CMS-012 |

