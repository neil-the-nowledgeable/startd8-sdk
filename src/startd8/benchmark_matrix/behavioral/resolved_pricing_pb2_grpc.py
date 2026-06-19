# Handwritten gRPC bindings matching resolved_pricing.proto.
"""Client and server classes for the canonical ResolvedPriceService."""

import grpc

try:
    from . import resolved_pricing_pb2 as resolved__pricing__pb2
except ImportError:  # standalone fixture: stubs co-located in cwd
    import resolved_pricing_pb2 as resolved__pricing__pb2


class ResolvedPriceServiceStub:
    """Client stub for benchmark.pricing.v1.ResolvedPriceService."""

    def __init__(self, channel):
        self.AssessLines = channel.unary_unary(
            "/benchmark.pricing.v1.ResolvedPriceService/AssessLines",
            request_serializer=resolved__pricing__pb2.AssessLinesRequest.SerializeToString,
            response_deserializer=resolved__pricing__pb2.AssessLinesResponse.FromString,
            _registered_method=True,
        )


class ResolvedPriceServiceServicer:
    """Server base class for benchmark.pricing.v1.ResolvedPriceService."""

    def AssessLines(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_ResolvedPriceServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "AssessLines": grpc.unary_unary_rpc_method_handler(
            servicer.AssessLines,
            request_deserializer=resolved__pricing__pb2.AssessLinesRequest.FromString,
            response_serializer=resolved__pricing__pb2.AssessLinesResponse.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "benchmark.pricing.v1.ResolvedPriceService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers(
        "benchmark.pricing.v1.ResolvedPriceService", rpc_method_handlers
    )


class ResolvedPriceService:
    """Experimental static client API."""

    @staticmethod
    def AssessLines(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/benchmark.pricing.v1.ResolvedPriceService/AssessLines",
            resolved__pricing__pb2.AssessLinesRequest.SerializeToString,
            resolved__pricing__pb2.AssessLinesResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True,
        )
