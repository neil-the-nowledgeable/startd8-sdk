// SPIKE FIXTURE — a stand-in for the Online Boutique `checkoutservice`.
//
// The real checkoutservice is a Go gRPC service instrumented with OpenTelemetry
// gRPC-server auto-instrumentation. Its RED metrics come from the OTel semantic
// conventions (`rpc_server_duration` + histogram family), NOT from a span-metrics
// connector (`calls_total`). This fixture reproduces that shape so the static
// fidelity check can catch the profile mismatch against the generated alerts,
// which assume the span-metrics-connector convention.
package main

import (
	"context"
	"net"

	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/metric"
	"google.golang.org/grpc"
)

func main() {
	// gRPC server auto-instrumentation → emits rpc_server_duration (semconv-grpc).
	srv := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
	)

	// One explicit business counter, created via the OTel Go meter API.
	meter := otel.Meter("checkoutservice")
	ordersPlaced, _ := meter.Int64Counter("app_orders_placed_total")
	_ = ordersPlaced

	// A prometheus/client_golang direct registration, promauto style.
	// (Name pulled from the Opts struct literal.)
	checkoutLatency := promauto.NewHistogram(prometheus.HistogramOpts{
		Name: "checkout_pipeline_seconds",
	})
	_ = checkoutLatency

	lis, _ := net.Listen("tcp", ":5050")
	_ = context.Background()
	_ = metric.Meter(nil)
	srv.Serve(lis)
}
