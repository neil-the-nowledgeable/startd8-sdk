# StartD8 SDK root Makefile
#
# Jsonnet dashboard generation targets (delegate to startd8-mixin/)

.PHONY: jsonnet-generate jsonnet-test jsonnet-lint jsonnet-fmt jsonnet-install tier0-attest help

jsonnet-generate: ## Generate dashboards and alerts from Jsonnet, copy to dashboards/
	$(MAKE) -C startd8-mixin generate
	@cp startd8-mixin/generated/dashboards/*.json dashboards/
	@echo "Copied generated dashboards to dashboards/"

jsonnet-test: ## Run Jsonnet smoke tests
	$(MAKE) -C startd8-mixin test

jsonnet-lint: ## Check Jsonnet formatting
	$(MAKE) -C startd8-mixin lint

jsonnet-fmt: ## Format Jsonnet files
	$(MAKE) -C startd8-mixin fmt

jsonnet-install: ## Install Jsonnet dependencies (grafonnet)
	$(MAKE) -C startd8-mixin install

tier0-attest: ## Run Tier 0 probe + attestation + verify + startup capture (live demo required)
	bash scripts/otel_demo/tier0_attest.sh

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
