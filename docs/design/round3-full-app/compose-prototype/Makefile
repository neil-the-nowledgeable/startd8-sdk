# PROTOTYPE entrypoints for the Round 3 compose FLEET substrate prototype.
.PHONY: prepare up down drive clean

prepare:        ## Assemble build contexts (vendored stubs + ground-truth products.json) from SDK sources
	bash prepare_build_context.sh

up: prepare     ## Build + start the 2-service fleet (detached)
	REC_HOST_PORT=$${REC_HOST_PORT:-18080} docker compose up --build -d

down:           ## Stop + remove the fleet
	docker compose down -v --remove-orphans

drive:          ## Full substrate proof: prepare -> up -> score (coverage 1.0) -> egress-deny -> teardown
	python3 drive_fleet.py

clean: down     ## Teardown + drop generated build-context artifacts
	rm -rf productcatalogservice/_stubs productcatalogservice/products.json productcatalogservice/go.sum \
	       recommendationservice/demo_pb2.py recommendationservice/demo_pb2_grpc.py
