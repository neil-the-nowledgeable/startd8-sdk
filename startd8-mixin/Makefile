# startd8-mixin Makefile
#
# Usage:
#   make generate    Generate dashboards and alerts
#   make test        Run golden file tests
#   make lint        Check Jsonnet formatting
#   make fmt         Format Jsonnet files
#   make install     Install jsonnet-bundler dependencies
#   make clean       Remove generated artifacts

JSONNET ?= jsonnet
JSONNETFMT ?= jsonnetfmt
JB ?= jb

GENERATED_DIR := generated
DASHBOARD_DIR := $(GENERATED_DIR)/dashboards
ALERTS_DIR := $(GENERATED_DIR)/alerts

.PHONY: generate test lint fmt install clean help

generate: ## Generate all artifacts from Jsonnet
	@mkdir -p $(DASHBOARD_DIR) $(ALERTS_DIR)
	@echo "Generating dashboards..."
	@$(JSONNET) -J vendor -e '(import "mixin.libsonnet").grafanaDashboards' | \
		python3 -c "import sys,json; data=json.load(sys.stdin); [open('$(DASHBOARD_DIR)/'+k,'w').write(json.dumps(v,indent=2)+'\n') for k,v in data.items()]"
	@echo "Generating alerts..."
	@$(JSONNET) -S -J vendor -e 'std.manifestYamlDoc((import "mixin.libsonnet").prometheusAlerts)' > $(ALERTS_DIR)/alerts.yaml
	@echo "Done. Output in $(GENERATED_DIR)/"

test: ## Run smoke test
	@echo "Running smoke test..."
	@$(JSONNET) -J vendor tests/smoke_test.jsonnet > /dev/null && echo "OK: All outputs compile" || (echo "FAIL: Compilation error" && exit 1)

lint: ## Check Jsonnet formatting
	@echo "Checking formatting..."
	@find . -name '*.libsonnet' -o -name '*.jsonnet' | grep -v vendor | xargs $(JSONNETFMT) --test && echo "OK: All files formatted" || (echo "FAIL: Run 'make fmt' to fix" && exit 1)

fmt: ## Format Jsonnet files
	@find . -name '*.libsonnet' -o -name '*.jsonnet' | grep -v vendor | xargs $(JSONNETFMT) -i
	@echo "Formatted."

install: ## Install jsonnet-bundler dependencies
	$(JB) install

clean: ## Remove generated artifacts
	rm -rf $(GENERATED_DIR)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
