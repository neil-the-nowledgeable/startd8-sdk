# PROTOTYPE Dockerfile — recommendationservice (Python) for the Round 3 compose FLEET substrate.
#
# Mirrors install_plan("python"): grpcio + protobuf runtime + the co-located demo_pb2 stubs (the
# Python OB convention — demo_pb2 / demo_pb2_grpc next to server.py, not a package). The BUILD pulls
# the base image + pip deps over the network — fine for the PROTOTYPE (offline vendored closure, like
# node_runtime/, is the scoped containerization next step).
#
# Build context layout (assembled by prepare_build_context.sh):
#   ./server.py            the recommendation_reference server (dials productcatalog)
#   ./demo_pb2.py          gRPC message stubs   (copied from behavioral/)
#   ./demo_pb2_grpc.py     gRPC service stubs   (copied from behavioral/)

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "grpcio>=1.60" "protobuf>=4.25"
COPY server.py demo_pb2.py demo_pb2_grpc.py /app/
ENV PORT=8080
# OB convention: read PORT + PRODUCT_CATALOG_SERVICE_ADDR from env; serve gRPC on 0.0.0.0:$PORT.
CMD ["python3", "server.py"]
