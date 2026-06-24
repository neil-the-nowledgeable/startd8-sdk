module productcatalogservice

go 1.21

require (
	github.com/GoogleCloudPlatform/microservices-demo/hipstershop v0.0.0
	google.golang.org/grpc v1.81.1
)

// PROTOTYPE: mirror provision.setup_go_stubs — the upstream hipstershop module restructured and no
// longer ships the `hipstershop` package, so we vendor the protoc-generated stubs locally and
// `replace` the import path to them. The build context COPYs the vendored stubs to ./_stubs (see
// Dockerfile + prepare_build_context.sh, which copy from src/.../behavioral/go_stubs/hipstershop).
replace github.com/GoogleCloudPlatform/microservices-demo/hipstershop => ./_stubs
