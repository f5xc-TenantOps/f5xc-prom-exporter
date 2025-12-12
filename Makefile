# F5XC Prometheus Exporter Makefile

# Variables
PYTHON := python
PIP := pip
PYTEST := pytest
BLACK := black
RUFF := ruff
MYPY := mypy

# Virtual environment
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
VENV_PYTEST := $(VENV)/bin/pytest

# Source directories
SRC_DIR := src
TEST_DIR := tests

.PHONY: help install install-dev venv clean test test-cov lint format type-check check-all run docker-build docker-run

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

venv: ## Create virtual environment
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip

install: venv ## Install dependencies
	$(VENV_PIP) install -e .

install-dev: venv ## Install development dependencies
	$(VENV_PIP) install -e ".[dev]"

clean: ## Clean up generated files
	rm -rf $(VENV)
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/

test: install-dev ## Run tests
	$(VENV_PYTEST) $(TEST_DIR) -v

test-cov: install-dev ## Run tests with coverage
	$(VENV_PYTEST) $(TEST_DIR) -v --cov=$(SRC_DIR)/f5xc_exporter --cov-report=html --cov-report=term-missing

test-quick: ## Run tests without installing (assumes deps already installed)
	$(VENV_PYTEST) $(TEST_DIR) -v -x

lint: install-dev ## Run linting
	$(VENV)/bin/ruff check $(SRC_DIR) $(TEST_DIR)

format: install-dev ## Format code
	$(VENV)/bin/black $(SRC_DIR) $(TEST_DIR)
	$(VENV)/bin/ruff check --fix $(SRC_DIR) $(TEST_DIR)

type-check: install-dev ## Run type checking
	$(VENV)/bin/mypy $(SRC_DIR)/f5xc_exporter

check-all: install-dev format lint type-check test-cov ## Run all checks

run: install ## Run the exporter (requires F5XC_TENANT_URL and F5XC_ACCESS_TOKEN env vars)
	$(VENV_PYTHON) -m f5xc_exporter.main

docker-build: ## Build Docker image
	docker build -t f5xc-prom-exporter .

docker-run: ## Run Docker container (requires env vars)
	docker run -p 8080:8080 \
		-e F5XC_TENANT_URL=$(F5XC_TENANT_URL) \
		-e F5XC_ACCESS_TOKEN=$(F5XC_ACCESS_TOKEN) \
		f5xc-prom-exporter

docker-test: docker-build ## Build and test Docker image
	@echo "Building and testing Docker image..."
	@echo "Testing health endpoint..."
	@docker run -d --name f5xc-test -p 8081:8080 \
		-e F5XC_TENANT_URL=https://test.example.com \
		-e F5XC_ACCESS_TOKEN=test-token \
		f5xc-prom-exporter || true
	@sleep 3
	@curl -f http://localhost:8081/health && echo "✅ Health check passed" || echo "❌ Health check failed"
	@docker stop f5xc-test && docker rm f5xc-test || true

# Development shortcuts
dev-setup: install-dev ## Complete development setup
	@echo "✅ Development environment ready!"
	@echo "Run 'make test' to run tests"
	@echo "Run 'make run' to start the exporter"

ci-test: ## Run tests in CI environment
	$(PYTEST) $(TEST_DIR) -v --cov=$(SRC_DIR)/f5xc_exporter --cov-report=xml

# Quick test with real F5XC (requires credentials)
integration-test: install ## Test against real F5XC tenant
	@if [ -z "$(F5XC_TENANT_URL)" ] || [ -z "$(F5XC_ACCESS_TOKEN)" ]; then \
		echo "❌ Please set F5XC_TENANT_URL and F5XC_ACCESS_TOKEN environment variables"; \
		exit 1; \
	fi
	@echo "🧪 Testing configuration..."
	$(VENV_PYTHON) -c "from f5xc_exporter.config import get_config; print('✅ Config loaded:', get_config().tenant_url_str)"
	@echo "🧪 Testing API connectivity..."
	$(VENV_PYTHON) -c "from f5xc_exporter.config import get_config; from f5xc_exporter.client import F5XCClient; client = F5XCClient(get_config()); data = client.get_quota_usage(); print('✅ API accessible, quota items:', len(data.get('quota_usage', {})))"