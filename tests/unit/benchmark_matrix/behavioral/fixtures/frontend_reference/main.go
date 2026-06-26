// reference_frontend — a CORRECT journey-facing HTTP frontend (Go HTTP→gRPC), the known-good oracle
// for the frontend health/contract gate + Adapter A, and the M4 frontend-bonus lane's reference.
//
// It serves the journey-critical routes of FRONTEND_OPENAPI_CONTRACT §1 (GET / , GET /product/{id},
// POST /setCurrency, POST /cart, GET /cart, POST /cart/checkout) + GET /_healthz, threads the
// shop_session-id / shop_currency cookies, and fans out each route to the backend gRPC services via
// the *_SERVICE_ADDR env convention (§3). It is "just another Go service": $PORT, vendored hipstershop
// stubs, distroless runtime.
//
// Lessons folded in (craft/Lessons_Learned/sdk/lessons/01-benchmarking.md):
//   - #31: bind 0.0.0.0 (NOT localhost) so the published port is reachable; GET /_healthz is the
//     readiness probe the gate's BOOT stage polls.
//   - Leg 16 #21: POST /setCurrency + POST /cart do a REAL http.Redirect (302), not a header — a plain
//     browser form POST ignores HX-Redirect-style headers.
//   - The DECISIVE gate signal (#5/#28): POST /cart/checkout renders an order-confirmation page with
//     the REAL order id from Checkout.PlaceOrder — a subtly-broken frontend that omits it fails the gate.
package main

import (
	"context"
	"fmt"
	"html"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/hipstershop"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const (
	sessionCookie  = "shop_session-id"
	currencyCookie = "shop_currency"
	defaultCurr    = "USD"
)

// the §2 10-field checkout form — the single source for both the form RENDER (checkoutForm) and the
// server-side REQUIRED-field validation (placeOrder), so they can't drift apart.
var checkoutFields = []string{"email", "street_address", "zip_code", "city", "state", "country",
	"credit_card_number", "credit_card_expiration_month", "credit_card_expiration_year", "credit_card_cvv"}

type frontend struct {
	catalog  pb.ProductCatalogServiceClient
	currency pb.CurrencyServiceClient
	cart     pb.CartServiceClient
	shipping pb.ShippingServiceClient
	checkout pb.CheckoutServiceClient
	rec      pb.RecommendationServiceClient // best-effort (graceful-degrade)
}

func dial(addr string) *grpc.ClientConn {
	c, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("dial %s: %v", addr, err)
	}
	return c
}

func mustEnv(k string) string {
	v := os.Getenv(k)
	if v == "" {
		log.Fatalf("missing required dependency address env %s", k)
	}
	return v
}

// --- cookies (the session threads the cart user_id; currency localizes prices) -------------------

func (f *frontend) session(w http.ResponseWriter, r *http.Request) string {
	if c, err := r.Cookie(sessionCookie); err == nil && c.Value != "" {
		return c.Value
	}
	id := fmt.Sprintf("session-%d", time.Now().UnixNano())
	http.SetCookie(w, &http.Cookie{Name: sessionCookie, Value: id, Path: "/", MaxAge: 3600})
	return id
}

func currencyOf(r *http.Request) string {
	if c, err := r.Cookie(currencyCookie); err == nil && c.Value != "" {
		return c.Value
	}
	return defaultCurr
}

func ctx() (context.Context, context.CancelFunc) { return context.WithTimeout(context.Background(), 8*time.Second) }

func money(m *pb.Money) string {
	if m == nil {
		return "—"
	}
	return fmt.Sprintf("%d.%02d %s", m.GetUnits(), m.GetNanos()/10_000_000, m.GetCurrencyCode())
}

func (f *frontend) convert(c context.Context, from *pb.Money, to string) *pb.Money {
	if from == nil {
		return nil
	}
	out, err := f.currency.Convert(c, &pb.CurrencyConversionRequest{From: from, ToCode: to})
	if err != nil {
		return from // degrade to USD display rather than fail the page
	}
	return out
}

func page(w http.ResponseWriter, status int, title, body string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(status)
	fmt.Fprintf(w, "<!doctype html><html><head><title>%s</title></head><body>%s</body></html>", html.EscapeString(title), body)
}

// --- handlers ------------------------------------------------------------------------------------

func (f *frontend) healthz(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

func (f *frontend) home(w http.ResponseWriter, r *http.Request) {
	f.session(w, r)
	cur := currencyOf(r)
	c, cancel := ctx()
	defer cancel()
	_, _ = f.currency.GetSupportedCurrencies(c, &pb.Empty{})
	resp, err := f.catalog.ListProducts(c, &pb.Empty{})
	if err != nil {
		page(w, http.StatusInternalServerError, "error", "catalog unavailable")
		return
	}
	var b strings.Builder
	b.WriteString("<h1>Online Boutique</h1><ul id=\"product-grid\">")
	for _, p := range resp.GetProducts() {
		price := f.convert(c, p.GetPriceUsd(), cur)
		fmt.Fprintf(&b, "<li class=\"product\"><a href=\"/product/%s\">%s</a> — %s</li>",
			html.EscapeString(p.GetId()), html.EscapeString(p.GetName()), html.EscapeString(money(price)))
	}
	b.WriteString("</ul>")
	page(w, http.StatusOK, "home", b.String())
}

func (f *frontend) product(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/product/")
	if id == "" {
		page(w, http.StatusBadRequest, "bad request", "missing product id")
		return
	}
	f.session(w, r)
	cur := currencyOf(r)
	c, cancel := ctx()
	defer cancel()
	prod, err := f.catalog.GetProduct(c, &pb.GetProductRequest{Id: id})
	if err != nil {
		page(w, http.StatusNotFound, "not found", "no such product")
		return
	}
	_, _ = f.currency.GetSupportedCurrencies(c, &pb.Empty{})
	price := f.convert(c, prod.GetPriceUsd(), cur)
	// best-effort recommendations (graceful-degrade — not journey-critical)
	if f.rec != nil {
		_, _ = f.rec.ListRecommendations(c, &pb.ListRecommendationsRequest{UserId: "", ProductIds: []string{id}})
	}
	body := fmt.Sprintf("<h1 id=\"product-name\">%s</h1><p id=\"price\">%s</p><p>%s</p>"+
		"<form method=\"post\" action=\"/cart\"><input type=\"hidden\" name=\"product_id\" value=\"%s\">"+
		"<input name=\"quantity\" value=\"1\"><button type=\"submit\">Add to Cart</button></form>",
		html.EscapeString(prod.GetName()), html.EscapeString(money(price)),
		html.EscapeString(prod.GetDescription()), html.EscapeString(id))
	page(w, http.StatusOK, "product", body)
}

func (f *frontend) setCurrency(w http.ResponseWriter, r *http.Request) {
	code := r.FormValue("currency_code")
	if code != "" {
		http.SetCookie(w, &http.Cookie{Name: currencyCookie, Value: code, Path: "/", MaxAge: 48 * 3600})
	}
	target := r.Header.Get("Referer")
	if target == "" {
		target = "/"
	}
	http.Redirect(w, r, target, http.StatusFound) // 302 (real redirect, not a header — Leg 16 #21)
}

func (f *frontend) addToCart(w http.ResponseWriter, r *http.Request) {
	pid := r.FormValue("product_id")
	qty, err := strconv.Atoi(r.FormValue("quantity"))
	if pid == "" || err != nil || qty < 1 || qty > 10 {
		page(w, http.StatusUnprocessableEntity, "invalid", "bad add-to-cart payload")
		return
	}
	sid := f.session(w, r)
	c, cancel := ctx()
	defer cancel()
	if _, err := f.catalog.GetProduct(c, &pb.GetProductRequest{Id: pid}); err != nil {
		page(w, http.StatusUnprocessableEntity, "invalid", "no such product")
		return
	}
	if _, err := f.cart.AddItem(c, &pb.AddItemRequest{
		UserId: sid, Item: &pb.CartItem{ProductId: pid, Quantity: int32(qty)},
	}); err != nil {
		page(w, http.StatusInternalServerError, "error", "cart unavailable")
		return
	}
	http.Redirect(w, r, "/cart", http.StatusFound) // 302 → /cart
}

func (f *frontend) viewCart(w http.ResponseWriter, r *http.Request) {
	sid := f.session(w, r)
	cur := currencyOf(r)
	c, cancel := ctx()
	defer cancel()
	_, _ = f.currency.GetSupportedCurrencies(c, &pb.Empty{})
	cart, err := f.cart.GetCart(c, &pb.GetCartRequest{UserId: sid})
	if err != nil {
		page(w, http.StatusInternalServerError, "error", "cart unavailable")
		return
	}
	total := &pb.Money{CurrencyCode: cur}
	var b strings.Builder
	b.WriteString("<h1>Your Cart</h1><ul id=\"cart-items\">")
	for _, it := range cart.GetItems() {
		prod, perr := f.catalog.GetProduct(c, &pb.GetProductRequest{Id: it.GetProductId()})
		line := "—"
		if perr == nil {
			conv := f.convert(c, mul(prod.GetPriceUsd(), it.GetQuantity()), cur)
			line = money(conv)
			total = add(total, conv)
		}
		fmt.Fprintf(&b, "<li class=\"cart-item\">%s ×%d — %s</li>",
			html.EscapeString(it.GetProductId()), it.GetQuantity(), html.EscapeString(line))
	}
	b.WriteString("</ul>")
	// shipping quote (USD → active currency) added to the total
	quote, qerr := f.shipping.GetQuote(c, &pb.GetQuoteRequest{Items: cart.GetItems()})
	if qerr == nil {
		ship := f.convert(c, quote.GetCostUsd(), cur)
		total = add(total, ship)
		fmt.Fprintf(&b, "<p id=\"shipping\">Shipping: %s</p>", html.EscapeString(money(ship)))
	}
	fmt.Fprintf(&b, "<p id=\"total\">Total: %s</p>", html.EscapeString(money(total)))
	b.WriteString(checkoutForm())
	page(w, http.StatusOK, "cart", b.String())
}

func (f *frontend) placeOrder(w http.ResponseWriter, r *http.Request) {
	for _, k := range checkoutFields {
		if r.FormValue(k) == "" {
			page(w, http.StatusUnprocessableEntity, "invalid", "missing checkout field: "+k)
			return
		}
	}
	zip, e1 := strconv.Atoi(r.FormValue("zip_code"))
	cvv, e2 := strconv.Atoi(r.FormValue("credit_card_cvv"))
	month, e3 := strconv.Atoi(r.FormValue("credit_card_expiration_month"))
	year, e4 := strconv.Atoi(r.FormValue("credit_card_expiration_year"))
	if e1 != nil || e2 != nil || e3 != nil || e4 != nil {
		page(w, http.StatusUnprocessableEntity, "invalid", "non-numeric checkout field")
		return
	}
	sid := f.session(w, r)
	cur := currencyOf(r)
	c, cancel := ctx()
	defer cancel()
	resp, err := f.checkout.PlaceOrder(c, &pb.PlaceOrderRequest{
		UserId: sid, UserCurrency: cur,
		Address: &pb.Address{
			StreetAddress: r.FormValue("street_address"), City: r.FormValue("city"),
			State: r.FormValue("state"), Country: r.FormValue("country"), ZipCode: int32(zip),
		},
		Email: r.FormValue("email"),
		CreditCard: &pb.CreditCardInfo{
			CreditCardNumber: r.FormValue("credit_card_number"), CreditCardCvv: int32(cvv),
			CreditCardExpirationYear: int32(year), CreditCardExpirationMonth: int32(month),
		},
	})
	if err != nil {
		page(w, http.StatusInternalServerError, "error", "checkout failed: "+err.Error())
		return
	}
	// THE decisive gate signal: render the REAL order id from PlaceOrder. The broken variant
	// (FRONTEND_BREAK_ORDER_ID=1) renders a confirmation page WITHOUT the order id — a subtly-broken
	// frontend that passes route-presence but must FAIL the gate's stateful-journey stage.
	if os.Getenv("FRONTEND_BREAK_ORDER_ID") == "1" {
		page(w, http.StatusOK, "order confirmation", "<h1>Order Confirmed</h1><p>Thank you for shopping!</p>")
		return
	}
	oid := resp.GetOrder().GetOrderId()
	body := fmt.Sprintf("<h1>Order Confirmed</h1><p id=\"order-id\">Order ID: %s</p>"+
		"<p id=\"tracking-id\">Tracking: %s</p>",
		html.EscapeString(oid), html.EscapeString(resp.GetOrder().GetShippingTrackingId()))
	page(w, http.StatusOK, "order confirmation", body)
}

// --- Money helpers + the checkout form ----------------------------------------------------------

func mul(m *pb.Money, q int32) *pb.Money {
	t := (m.GetUnits()*1_000_000_000 + int64(m.GetNanos())) * int64(q)
	return &pb.Money{CurrencyCode: m.GetCurrencyCode(), Units: t / 1_000_000_000, Nanos: int32(t % 1_000_000_000)}
}

func add(a, b *pb.Money) *pb.Money {
	t := (a.GetUnits()*1_000_000_000 + int64(a.GetNanos())) + (b.GetUnits()*1_000_000_000 + int64(b.GetNanos()))
	return &pb.Money{CurrencyCode: a.GetCurrencyCode(), Units: t / 1_000_000_000, Nanos: int32(t % 1_000_000_000)}
}

func checkoutForm() string {
	var b strings.Builder
	b.WriteString("<form method=\"post\" action=\"/cart/checkout\" id=\"checkout-form\">")
	for _, k := range checkoutFields {
		fmt.Fprintf(&b, "<input name=\"%s\">", k)
	}
	b.WriteString("<button type=\"submit\">Place Order</button></form>")
	return b.String()
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	f := &frontend{
		catalog:  pb.NewProductCatalogServiceClient(dial(mustEnv("PRODUCT_CATALOG_SERVICE_ADDR"))),
		currency: pb.NewCurrencyServiceClient(dial(mustEnv("CURRENCY_SERVICE_ADDR"))),
		cart:     pb.NewCartServiceClient(dial(mustEnv("CART_SERVICE_ADDR"))),
		shipping: pb.NewShippingServiceClient(dial(mustEnv("SHIPPING_SERVICE_ADDR"))),
		checkout: pb.NewCheckoutServiceClient(dial(mustEnv("CHECKOUT_SERVICE_ADDR"))),
	}
	if addr := os.Getenv("RECOMMENDATION_SERVICE_ADDR"); addr != "" {
		f.rec = pb.NewRecommendationServiceClient(dial(addr)) // best-effort
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /_healthz", f.healthz)
	mux.HandleFunc("GET /{$}", f.home)
	mux.HandleFunc("GET /product/", f.product) // subtree → extract id (empty → 400)
	mux.HandleFunc("POST /setCurrency", f.setCurrency)
	mux.HandleFunc("POST /cart/checkout", f.placeOrder)
	mux.HandleFunc("POST /cart", f.addToCart)
	mux.HandleFunc("GET /cart", f.viewCart)

	// Bind 0.0.0.0 so the published container port is reachable (#31).
	log.Printf("frontend listening on 0.0.0.0:%s (deps wired)", port)
	if err := http.ListenAndServe("0.0.0.0:"+port, mux); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
