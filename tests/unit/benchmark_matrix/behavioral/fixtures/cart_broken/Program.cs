// DELIBERATELY-BROKEN CartService — proves the cart suite discriminates STATEFUL behavior.
//
// AddItem and EmptyCart succeed (return Empty), but GetCart ALWAYS returns an empty cart — it never
// reflects what was added. So the stateful cases fail (add-then-get sees nothing; accumulate sees
// nothing) while the structurally-trivial unknown-user-is-empty case still "passes" (an empty cart
// for an unknown user is, coincidentally, what a broken always-empty GetCart returns too). This is
// the per-case attribution the e2e asserts.

using Grpc.Core;
using Hipstershop;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddGrpc();

var portEnv = Environment.GetEnvironmentVariable("PORT");
int port = int.TryParse(portEnv, out var p) ? p : 8080;
builder.WebHost.ConfigureKestrel(options =>
    options.ListenLocalhost(port, listen =>
        listen.Protocols = Microsoft.AspNetCore.Server.Kestrel.Core.HttpProtocols.Http2));

var app = builder.Build();
app.MapGrpcService<BrokenCartService>();
app.Run();

sealed class BrokenCartService : CartService.CartServiceBase
{
    public override Task<Empty> AddItem(AddItemRequest request, ServerCallContext context)
        => Task.FromResult(new Empty());  // accepts but never stores

    public override Task<Cart> GetCart(GetCartRequest request, ServerCallContext context)
        => Task.FromResult(new Cart { UserId = request.UserId });  // BUG: always empty

    public override Task<Empty> EmptyCart(EmptyCartRequest request, ServerCallContext context)
        => Task.FromResult(new Empty());
}
