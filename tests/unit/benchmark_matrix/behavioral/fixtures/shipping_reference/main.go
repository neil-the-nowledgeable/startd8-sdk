// reference_shipping — a CORRECT ShippingService (Go), the known-good oracle for the shipping
// behavioral suite and the R3 fleet's shipping backend. There was no shipping fixture before; this is
// the minimal grpc server the M1 full-fleet (checkout's 6-dep fan-out) needs.
//
// Mirrors catalog_reference: reads $PORT, binds 0.0.0.0 (reachable when published/over service-DNS),
// uses the vendored hipstershop stubs (build_service_image stages them via setup_go_stubs). Implements
// the two ShippingService RPCs:
//   - GetQuote  → a DETERMINISTIC, non-negative, USD quote (the invariants run_shipping_suite asserts:
//                 non-negative cost, valid 3-letter ISO code, same cart → same quote). The amount is a
//                 simple count-based formula so it varies by cart yet is stable.
//   - ShipOrder → a deterministic, non-empty tracking id (checkout's fan-out calls it; no suite pins
//                 its value, so it's derived from the request to stay stable).
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"

	pb "github.com/GoogleCloudPlatform/microservices-demo/hipstershop"
	"google.golang.org/grpc"
)

type server struct {
	pb.UnimplementedShippingServiceServer
}

// itemCount sums the quantities in a cart (the quote/tracking inputs).
func itemCount(items []*pb.CartItem) int64 {
	var n int64
	for _, it := range items {
		n += int64(it.GetQuantity())
	}
	return n
}

// GetQuote returns a deterministic USD quote: a $8.99 base + $0.50 per item. Non-negative and stable
// for a given cart (the suite asserts exactly those invariants; the proto pins no formula).
func (s *server) GetQuote(ctx context.Context, req *pb.GetQuoteRequest) (*pb.GetQuoteResponse, error) {
	cents := 899 + itemCount(req.GetItems())*50
	return &pb.GetQuoteResponse{
		CostUsd: &pb.Money{
			CurrencyCode: "USD",
			Units:        cents / 100,
			Nanos:        int32(cents%100) * 10_000_000,
		},
	}, nil
}

// ShipOrder returns a deterministic, non-empty tracking id derived from the destination + cart size,
// so a re-run is stable (checkout only needs a non-empty id; no suite pins the value).
func (s *server) ShipOrder(ctx context.Context, req *pb.ShipOrderRequest) (*pb.ShipOrderResponse, error) {
	return &pb.ShipOrderResponse{
		TrackingId: fmt.Sprintf("TRK-%d-%d", req.GetAddress().GetZipCode(), itemCount(req.GetItems())),
	}, nil
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	lis, err := net.Listen("tcp", "0.0.0.0:"+port)
	if err != nil {
		log.Fatalf("listen: %v", err)
	}
	grpcServer := grpc.NewServer()
	pb.RegisterShippingServiceServer(grpcServer, &server{})
	log.Printf("shippingservice listening on %s", port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
