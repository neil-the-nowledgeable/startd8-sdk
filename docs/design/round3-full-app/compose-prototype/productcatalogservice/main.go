// PROTOTYPE — productcatalogservice for the Round 3 docker-compose FLEET substrate prototype.
//
// This is the catalog_reference fixture (tests/.../fixtures/catalog_reference/main.go) with ONE
// addition: a per-RPC access log line on ListProducts. In the in-process behavioral harness the
// "catalog was dialed" observable comes from RecommendationDepHarness._CallCounter; in a REAL fleet
// the productcatalog is a separate container, so the counter must come from the container itself.
// The driver greps these "DIAL ListProducts" lines out of `docker compose logs` to reconstruct the
// same call-counter signal the recommendation suite asserts (catalog_dialed > 0) — faithfully, from
// the real inter-service gRPC call rather than an in-process mock.
//
// Reads ./products.json (the harness-owned ground-truth catalog, baked into the image), implements
// ListProducts / GetProduct / SearchProducts, returns NOT_FOUND for an absent id. Listens on $PORT.
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
	// The faithful inter-service call-counter: every ListProducts dial (from recommendationservice
	// over service-DNS) prints a greppable line the fleet driver counts. This replaces the in-process
	// _CallCounter when productcatalog is a real container.
	log.Printf("DIAL ListProducts")
	return &pb.ListProductsResponse{Products: s.products}, nil
}

func (s *server) GetProduct(ctx context.Context, req *pb.GetProductRequest) (*pb.Product, error) {
	for _, p := range s.products {
		if p.GetId() == req.GetId() {
			return p, nil
		}
	}
	return nil, status.Errorf(codes.NotFound, "no product with id %q", req.GetId())
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
