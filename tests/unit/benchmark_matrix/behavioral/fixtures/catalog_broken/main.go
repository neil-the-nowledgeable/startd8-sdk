// broken_catalog — a DELIBERATELY-BROKEN ProductCatalogService that ignores NOT_FOUND: GetProduct
// returns a zero-value Product for an absent id instead of a NOT_FOUND error. Every other RPC is
// correct. Used to prove the catalog suite discriminates per-RPC (only get_product_absent_not_found
// must fail; ListProducts / GetProduct(known) / SearchProducts stay green).
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
	return &pb.ListProductsResponse{Products: s.products}, nil
}

// BROKEN: returns a zero-value Product for an absent id instead of NOT_FOUND.
func (s *server) GetProduct(ctx context.Context, req *pb.GetProductRequest) (*pb.Product, error) {
	for _, p := range s.products {
		if p.GetId() == req.GetId() {
			return p, nil
		}
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
	log.Printf("broken productcatalogservice listening on %s", port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
