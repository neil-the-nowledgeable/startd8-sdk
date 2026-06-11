"""Tests for structural pattern extraction (Layer 2: Cross-Language Structural Transfer)."""

import pytest
from startd8.exemplars.models import (
    ConfigFingerprint,
    ExemplarEntry,
    ExemplarScores,
    StructuralPattern,
)
from startd8.exemplars.structural_extractor import extract_structural_pattern
from startd8.exemplars.registry import ExemplarRegistry


# --- Structural extraction tests ---


class TestExtractStructuralPattern:
    def test_grpc_server_go(self):
        code = '''
func main() {
    lis, err := net.Listen("tcp", ":50051")
    grpcServer := grpc.NewServer(
        grpc.UnaryInterceptor(logging_interceptor),
        grpc.UnaryInterceptor(auth_interceptor),
    )
    pb.RegisterCurrencyServiceServer(grpcServer, &server{})
    grpc_health.RegisterHealthServer(grpcServer)
    log.Printf("Serving on port 50051")
    go func() {
        sigCh := make(chan os.Signal, 1)
        signal.Notify(sigCh, syscall.SIGTERM)
        <-sigCh
        grpcServer.GracefulStop()
    }()
    grpcServer.Serve(lis)
}
'''
        pattern = extract_structural_pattern(
            code, "grpc_server", "go", "go:source:grpc:grpc_server"
        )
        assert pattern is not None
        assert "create" in pattern.lifecycle_phases
        assert "serve" in pattern.lifecycle_phases
        assert "shutdown" in pattern.lifecycle_phases
        assert "logging" in pattern.middleware_points
        assert "auth" in pattern.middleware_points
        assert pattern.error_strategy == "graceful_shutdown"
        assert pattern.source_language == "go"

    def test_insufficient_signal(self):
        """Code with fewer than 2 lifecycle phases returns None."""
        code = "x = 1\ny = 2\n"
        pattern = extract_structural_pattern(
            code, "source_module", "python", "python:source:none:source_module"
        )
        assert pattern is None

    def test_empty_code(self):
        assert extract_structural_pattern("", "x", "go", "go:source:none:x") is None
        assert extract_structural_pattern(None, "x", "go", "go:source:none:x") is None

    def test_http_server(self):
        code = '''
func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/healthz", healthHandler)
    server := &http.Server{Addr: ":8080"}
    log.Println("listening on port 8080")
    go func() {
        sigCh := make(chan os.Signal, 1)
        signal.Notify(sigCh, os.Interrupt)
        <-sigCh
        server.Shutdown(context.Background())
    }()
    server.ListenAndServe()
}
'''
        pattern = extract_structural_pattern(
            code, "http_server", "go", "go:source:http:http_server"
        )
        assert pattern is not None
        assert "health" in pattern.lifecycle_phases
        assert "serve" in pattern.lifecycle_phases
        assert "shutdown" in pattern.lifecycle_phases
        assert "port" in pattern.config_keys

    def test_config_keys_dedup(self):
        code = "port = 8080\nhttp_port = 9090\nport = 3000\nServe()\nShutdown()"
        pattern = extract_structural_pattern(
            code, "http_server", "go", "go:source:http:http_server"
        )
        assert pattern is not None
        # "port" should appear only once
        assert pattern.config_keys.count("port") == 1

    def test_middleware_detection(self):
        code = '''
grpc.NewServer()
server.Serve(lis)
grpc.UnaryInterceptor(otel.TracingInterceptor())
prometheus.NewHistogramVec()
recovery.UnaryServerInterceptor()
'''
        pattern = extract_structural_pattern(
            code, "grpc_server", "go", "go:source:grpc:grpc_server"
        )
        assert pattern is not None
        assert "tracing" in pattern.middleware_points
        assert "metrics" in pattern.middleware_points
        assert "recovery" in pattern.middleware_points

    def test_frozen_dataclass(self):
        """StructuralPattern should be immutable."""
        pattern = StructuralPattern(
            archetype="grpc_server",
            lifecycle_phases=("create", "serve"),
            middleware_points=(),
            config_keys=(),
            error_strategy="unknown",
            source_language="go",
            source_fingerprint="go:source:grpc:grpc_server",
        )
        with pytest.raises(AttributeError):
            pattern.archetype = "http_server"  # type: ignore[misc]
