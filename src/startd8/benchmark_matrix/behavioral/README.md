# Track 2 behavioral harness — protos & stubs

The behavioral suites are SDK-authored gRPC clients that talk to a model-generated server over the
wire. Each suite imports committed, pre-generated Python stubs (`*_pb2.py` / `*_pb2_grpc.py`) — there
is no build step at runtime, so the stubs are checked in.

## Protos

| Proto | Package | Services | Used by |
|-------|---------|----------|---------|
| `demo.proto` | `hipstershop` | all 9 Online Boutique services | charge / currency / shipping / ad suites |
| `pricing.proto` | `startd8.bench.pricing.v1` | `PricingService` (hardened tier, Liferay-derived) | pricing suite |

`execute.py:_PROTO_BY_SERVICE` maps a service to the proto its generated server is provisioned with
(default `demo.proto`; FR-14). OB cells are byte-identical to before this mapping existed.

## Regenerating stubs

Pin the toolchain to match the existing stubs (generated with **Protobuf Python 6.33.x**) so the
`runtime_version.ValidateProtobufRuntimeVersion` guard in the generated code stays satisfied:

```bash
cd src/startd8/benchmark_matrix/behavioral
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. pricing.proto
```

After generating `pricing_pb2_grpc.py`, restore the package-relative import fallback (grpc-tools
emits a bare top-level `import pricing_pb2`, which breaks when imported as part of the package):

```python
try:
    from . import pricing_pb2 as pricing__pb2
except ImportError:  # standalone subprocess (server fixture): stubs co-located in cwd
    import pricing_pb2 as pricing__pb2
```

(`demo_pb2_grpc.py` carries the same patch.) Validate with
`tests/unit/benchmark_matrix/behavioral/test_pricing_suite.py`.
