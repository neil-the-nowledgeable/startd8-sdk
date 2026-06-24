# PROTOTYPE Dockerfile — productcatalogservice (Go) for the Round 3 compose FLEET substrate prototype.
#
# Mirrors provision.setup_go_stubs + install_plan("go"): vendor the protoc-generated hipstershop
# stubs as a local module, `go mod tidy` to derive grpc/protobuf, then `go build` the static server.
# The BUILD uses network (pull base image + go deps) — that is fine for the PROTOTYPE; the substrate
# claim is about RUNTIME networking + egress-deny, not offline build hermeticity (that is the scoped
# containerization next step). Kept minimal + clearly marked prototype.
#
# Build context layout (assembled by prepare_build_context.sh, NOT this dir's raw state):
#   ./main.go          the prototype catalog server (per-RPC DIAL log)
#   ./go.mod           service module with `replace ... => ./_stubs`
#   ./_stubs/*.pb.go   vendored hipstershop stubs (copied from behavioral/go_stubs/hipstershop)
#   ./_stubs/go.mod    synthesized localmod go.mod (mirrors setup_go_stubs)
#   ./products.json    harness-owned ground-truth catalog (from catalog_suite.products_json())

# grpc v1.81.1 requires go >= 1.25; match the toolchain.
FROM golang:1.25-alpine AS build
WORKDIR /src
# Copy the assembled context (sources + vendored stubs + go.mod).
COPY . .
# Derive deps from imports + write go.sum (integrity), then compile a static binary.
RUN go mod tidy && CGO_ENABLED=0 go build -o /out/server .

# Minimal runtime: just the static binary + the ground-truth catalog it reads from cwd.
FROM alpine:3.20
WORKDIR /app
COPY --from=build /out/server /app/server
COPY products.json /app/products.json
ENV PORT=8080
# OB convention: read PORT from env, serve gRPC on 0.0.0.0:$PORT.
CMD ["/app/server"]
