// reference_catalog — a CORRECT ProductCatalogService over the harness-seeded products.json
// (the known-good oracle). Reads ./products.json (the cwd the serve command sets), implements
// ListProducts / GetProduct / SearchProducts, and returns NOT_FOUND for an absent product id.
//
// Scored against the SDK catalog suite over loopback it must yield coverage 1.00. Anything less is a
// HARNESS defect, not a model defect. The broken variant (../catalog_broken) returns a zero-value
// Product instead of NOT_FOUND, to prove per-RPC attribution.
package main

import (
	"context"
	"encoding/json"
	"log"
	"net"
	"os"
	"strings"

	pb "github.com/GoogleCloudPlatform/microservices-demo/hipstershop"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// notFoundOnAbsent, when "0", makes GetProduct return a zero Product instead of NOT_FOUND (the
// broken-variant copy flips this). The reference build leaves it default (true).
var notFoundOnAbsent = os.Getenv("CATALOG_NOT_FOUND_ON_ABSENT") != "0"

func loadProducts() []*pb.Product {
	raw, err := os.ReadFile("products.json")
	if err != nil {
		log.Fatalf("read products.json: %v", err)
	}
	var doc struct {
		Products []struct {
			ID          string `json:"id"`
			Name        string `json:"name"`
			Description string `json:"description"`
			Picture     string `json:"picture"`
			PriceUsd    struct {
				CurrencyCode string `json:"currencyCode"`
				Units        int64  `json:"units"`
				Nanos        int32  `json:"nanos"`
			} `json:"priceUsd"`
			Categories []string `json:"categories"`
		} `json:"products"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		log.Fatalf("parse products.json: %v", err)
	}
	out := make([]*pb.Product, 0, len(doc.Products))
	for _, p := range doc.Products {
		out = append(out, &pb.Product{
			Id:          p.ID,
			Name:        p.Name,
			Description: p.Description,
			Picture:     p.Picture,
			PriceUsd: &pb.Money{
				CurrencyCode: p.PriceUsd.CurrencyCode,
				Units:        p.PriceUsd.Units,
				Nanos:        p.PriceUsd.Nanos,
			},
			Categories: p.Categories,
		})
	}
	return out
}

type server struct {
	pb.UnimplementedProductCatalogServiceServer
	products []*pb.Product
}

func (s *server) ListProducts(ctx context.Context, _ *pb.Empty) (*pb.ListProductsResponse, error) {
	return &pb.ListProductsResponse{Products: s.products}, nil
}

func (s *server) GetProduct(ctx context.Context, req *pb.GetProductRequest) (*pb.Product, error) {
	for _, p := range s.products {
		if p.GetId() == req.GetId() {
			return p, nil
		}
	}
	if notFoundOnAbsent {
		return nil, status.Errorf(codes.NotFound, "no product with id %q", req.GetId())
	}
	return &pb.Product{}, nil
}

func (s *server) SearchProducts(ctx context.Context, req *pb.SearchProductsRequest) (*pb.SearchProductsResponse, error) {
	q := strings.ToLower(strings.TrimSpace(req.GetQuery()))
	var results []*pb.Product
	for _, p := range s.products {
		if q != "" && (strings.Contains(strings.ToLower(p.GetName()), q) ||
			strings.Contains(strings.ToLower(p.GetDescription()), q)) {
			results = append(results, p)
		}
	}
	return &pb.SearchProductsResponse{Results: results}, nil
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
	pb.RegisterProductCatalogServiceServer(grpcServer, &server{products: loadProducts()})
	log.Printf("productcatalogservice listening on %s", port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
