// reference_checkout — a CORRECT 6-way CheckoutService orchestrator (FR-CO-12, the known-good oracle).
//
// It reads the six *_SERVICE_ADDR env vars (the Online Boutique convention the harness injects),
// dials all six dependency stubs, and implements PlaceOrder as: GetCart -> GetProduct per item ->
// Convert each line cost to the user currency -> GetQuote (shipping) -> Convert shipping -> Charge
// the total -> ShipOrder -> SendOrderConfirmation -> return the assembled OrderResult.
//
// Scored against the SDK stub harness it must yield coverage 1.00 (all six steps). Anything less is
// a HARNESS defect, not a model defect. The broken variant (../checkout_broken) intentionally skips
// the payment Charge to prove per-step attribution.
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/hipstershop"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// SKIP_PAYMENT, when "1", omits the Charge call (used by the broken-variant build via -ldflags or a
// copy that flips the constant). The reference build leaves it empty.
var skipPayment = os.Getenv("SKIP_PAYMENT") == "1"

func dial(addr string) (*grpc.ClientConn, error) {
	return grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

func convert(ctx context.Context, cur pb.CurrencyServiceClient, from *pb.Money, to string) (*pb.Money, error) {
	if to == "" || to == from.GetCurrencyCode() {
		// Still dial currency to honor the orchestration contract (step 3 requires it).
	}
	return cur.Convert(ctx, &pb.CurrencyConversionRequest{From: from, ToCode: to})
}

func addMoney(a, b *pb.Money) *pb.Money {
	total := (a.GetUnits()*1_000_000_000 + int64(a.GetNanos())) + (b.GetUnits()*1_000_000_000 + int64(b.GetNanos()))
	return &pb.Money{CurrencyCode: a.GetCurrencyCode(), Units: total / 1_000_000_000, Nanos: int32(total % 1_000_000_000)}
}

func mulMoney(m *pb.Money, q int32) *pb.Money {
	total := (m.GetUnits()*1_000_000_000 + int64(m.GetNanos())) * int64(q)
	return &pb.Money{CurrencyCode: m.GetCurrencyCode(), Units: total / 1_000_000_000, Nanos: int32(total % 1_000_000_000)}
}

type server struct {
	pb.UnimplementedCheckoutServiceServer
	catalog  pb.ProductCatalogServiceClient
	cart     pb.CartServiceClient
	currency pb.CurrencyServiceClient
	shipping pb.ShippingServiceClient
	payment  pb.PaymentServiceClient
	email    pb.EmailServiceClient
}

func (s *server) PlaceOrder(ctx context.Context, req *pb.PlaceOrderRequest) (*pb.PlaceOrderResponse, error) {
	userCurrency := req.GetUserCurrency()

	// 1+2) Cart -> per-item catalog price.
	cart, err := s.cart.GetCart(ctx, &pb.GetCartRequest{UserId: req.GetUserId()})
	if err != nil {
		return nil, fmt.Errorf("getcart: %w", err)
	}

	var orderItems []*pb.OrderItem
	total := &pb.Money{CurrencyCode: userCurrency}
	for _, ci := range cart.GetItems() {
		prod, err := s.catalog.GetProduct(ctx, &pb.GetProductRequest{Id: ci.GetProductId()})
		if err != nil {
			return nil, fmt.Errorf("getproduct: %w", err)
		}
		// 3) currency-convert the per-line cost (priceUSD * qty -> userCurrency).
		lineUSD := mulMoney(prod.GetPriceUsd(), ci.GetQuantity())
		lineConv, err := convert(ctx, s.currency, lineUSD, userCurrency)
		if err != nil {
			return nil, fmt.Errorf("convert line: %w", err)
		}
		orderItems = append(orderItems, &pb.OrderItem{Item: ci, Cost: lineConv})
		total = addMoney(total, lineConv)
	}

	// 4) shipping quote (USD) -> convert -> add.
	quote, err := s.shipping.GetQuote(ctx, &pb.GetQuoteRequest{Address: req.GetAddress(), Items: cart.GetItems()})
	if err != nil {
		return nil, fmt.Errorf("getquote: %w", err)
	}
	shipConv, err := convert(ctx, s.currency, quote.GetCostUsd(), userCurrency)
	if err != nil {
		return nil, fmt.Errorf("convert shipping: %w", err)
	}
	total = addMoney(total, shipConv)

	// 5) charge.
	if !skipPayment {
		if _, err := s.payment.Charge(ctx, &pb.ChargeRequest{Amount: total, CreditCard: req.GetCreditCard()}); err != nil {
			return nil, fmt.Errorf("charge: %w", err)
		}
	}

	// ship -> tracking id.
	ship, err := s.shipping.ShipOrder(ctx, &pb.ShipOrderRequest{Address: req.GetAddress(), Items: cart.GetItems()})
	if err != nil {
		return nil, fmt.Errorf("shiporder: %w", err)
	}

	order := &pb.OrderResult{
		OrderId:            "ground-truth-order-0001",
		ShippingTrackingId: ship.GetTrackingId(),
		ShippingCost:       shipConv,
		ShippingAddress:    req.GetAddress(),
		Items:              orderItems,
	}

	// 6) email confirmation.
	if _, err := s.email.SendOrderConfirmation(ctx, &pb.SendOrderConfirmationRequest{Email: req.GetEmail(), Order: order}); err != nil {
		return nil, fmt.Errorf("email: %w", err)
	}

	return &pb.PlaceOrderResponse{Order: order}, nil
}

func mustEnv(k string) string {
	v := os.Getenv(k)
	if v == "" {
		log.Fatalf("missing required dependency address env %s", k)
	}
	return v
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	conns := map[string]*grpc.ClientConn{}
	for _, k := range []string{
		"PRODUCT_CATALOG_SERVICE_ADDR", "CART_SERVICE_ADDR", "CURRENCY_SERVICE_ADDR",
		"SHIPPING_SERVICE_ADDR", "PAYMENT_SERVICE_ADDR", "EMAIL_SERVICE_ADDR",
	} {
		c, err := dial(mustEnv(k))
		if err != nil {
			log.Fatalf("dial %s: %v", k, err)
		}
		conns[k] = c
	}

	s := &server{
		catalog:  pb.NewProductCatalogServiceClient(conns["PRODUCT_CATALOG_SERVICE_ADDR"]),
		cart:     pb.NewCartServiceClient(conns["CART_SERVICE_ADDR"]),
		currency: pb.NewCurrencyServiceClient(conns["CURRENCY_SERVICE_ADDR"]),
		shipping: pb.NewShippingServiceClient(conns["SHIPPING_SERVICE_ADDR"]),
		payment:  pb.NewPaymentServiceClient(conns["PAYMENT_SERVICE_ADDR"]),
		email:    pb.NewEmailServiceClient(conns["EMAIL_SERVICE_ADDR"]),
	}

	lis, err := net.Listen("tcp", "0.0.0.0:"+port)
	if err != nil {
		log.Fatalf("listen: %v", err)
	}
	grpcServer := grpc.NewServer()
	pb.RegisterCheckoutServiceServer(grpcServer, s)
	log.Printf("checkoutservice listening on %s (deps wired) at %s", port, time.Now().Format(time.RFC3339))
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
