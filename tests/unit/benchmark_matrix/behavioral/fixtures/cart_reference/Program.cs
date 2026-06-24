// CORRECT reference CartService — the known-good oracle for the cart behavioral suite.
//
// A standalone .NET gRPC server launched by the C# startup contract
// (``cd src/cartservice && exec dotnet ./.bin/server.dll`` with ``$PORT`` / ``ASPNETCORE_URLS`` in
// the env). It implements AddItem / GetCart / EmptyCart over an IN-MEMORY per-user store
// (a ConcurrentDictionary) — NO external Redis. Statefulness is the discriminating signal the suite
// asserts: AddItem then GetCart reflects the item; AddItem twice for the same product ACCUMULATES
// the quantity (upstream OB semantics); EmptyCart clears the user's cart; GetCart for an unknown
// user returns an empty cart (not an error).
//
// The C# gRPC stubs (namespace ``Hipstershop``) are generated from the co-located ``demo.proto`` at
// build time by Grpc.Tools (see cartservice.csproj) — there is no vendored C# stub set.

using System.Collections.Concurrent;
using Grpc.Core;
using Hipstershop;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddGrpc();

// Read the port the harness injected ($PORT, the OB convention shared with the other languages) and
// bind HTTP/2 cleartext (h2c) on loopback so the SDK gRPC client can reach it.
var portEnv = Environment.GetEnvironmentVariable("PORT");
int port = int.TryParse(portEnv, out var p) ? p : 8080;
builder.WebHost.ConfigureKestrel(options =>
    options.ListenLocalhost(port, listen =>
        listen.Protocols = Microsoft.AspNetCore.Server.Kestrel.Core.HttpProtocols.Http2));

var app = builder.Build();
app.MapGrpcService<CartServiceImpl>();
app.Run();

// In-memory per-user cart store (no Redis). Each user maps to a list of CartItem; access to a
// user's list is locked so concurrent AddItem/GetCart stay consistent.
sealed class CartServiceImpl : CartService.CartServiceBase
{
    private static readonly ConcurrentDictionary<string, List<CartItem>> Store = new();

    public override Task<Empty> AddItem(AddItemRequest request, ServerCallContext context)
    {
        var items = Store.GetOrAdd(request.UserId, _ => new List<CartItem>());
        lock (items)
        {
            // Upstream OB semantics: a second AddItem for the same product accumulates the quantity.
            var existing = items.FirstOrDefault(i => i.ProductId == request.Item.ProductId);
            if (existing != null)
                existing.Quantity += request.Item.Quantity;
            else
                items.Add(new CartItem { ProductId = request.Item.ProductId, Quantity = request.Item.Quantity });
        }
        return Task.FromResult(new Empty());
    }

    public override Task<Cart> GetCart(GetCartRequest request, ServerCallContext context)
    {
        var cart = new Cart { UserId = request.UserId };
        // Unknown user → an empty cart (NOT an error): TryGetValue simply misses.
        if (Store.TryGetValue(request.UserId, out var items))
            lock (items)
                cart.Items.AddRange(items.Select(i => new CartItem { ProductId = i.ProductId, Quantity = i.Quantity }));
        return Task.FromResult(cart);
    }

    public override Task<Empty> EmptyCart(EmptyCartRequest request, ServerCallContext context)
    {
        Store.TryRemove(request.UserId, out _);
        return Task.FromResult(new Empty());
    }
}
