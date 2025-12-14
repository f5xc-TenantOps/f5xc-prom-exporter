# F5 Distributed Cloud Prometheus Exporter

A Prometheus exporter for collecting metrics from F5 Distributed Cloud (F5xc) tenants. This exporter provides observability into your F5xc infrastructure by exposing key metrics that can be scraped by Prometheus.

## Features

- **Tenant Metrics Collection**: Collects metrics from F5xc tenant APIs
- **Prometheus Integration**: Exposes metrics in Prometheus format at `/metrics` endpoint
- **Configurable Collection**: Adjustable polling intervals to control API load
- **Multiple Deployment Options**: Run directly with Python, Docker, or Kubernetes
- **Secure Configuration**: Environment variable-based configuration for credentials

## Quick Start

### Prerequisites

- F5 Distributed Cloud tenant access
- Valid F5xc API access token

### Configuration

Set the required environment variables:

```bash
export F5XC_TENANT_URL="https://your-tenant.console.ves.volterra.io"
export F5XC_ACCESS_TOKEN="your-access-token"
```

### Running with Docker

```bash
docker run -p 8080:8080 \
  -e F5XC_TENANT_URL="https://your-tenant.console.ves.volterra.io" \
  -e F5XC_ACCESS_TOKEN="your-token" \
  ghcr.io/f5xc-tenantops/f5xc-prom-exporter:latest
```

Or using docker-compose:

```bash
# Set your credentials
export F5XC_TENANT_URL="https://your-tenant.console.ves.volterra.io"
export F5XC_ACCESS_TOKEN="your-token"

# Start the exporter (uses latest stable image)
docker-compose up -d

# Or use staging/development image
export F5XC_IMAGE_TAG=staging
docker-compose up -d
```

### Running with Python

```bash
# Install dependencies
pip install -r requirements.txt

# Run the exporter
python -m f5xc_exporter
```

### Kubernetes Deployment

See the `config/` directory for Kubernetes deployment examples.

## Configuration Options

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `F5XC_TENANT_URL` | Yes | - | F5 Distributed Cloud tenant URL |
| `F5XC_ACCESS_TOKEN` | Yes | - | F5xc API access token |
| `F5XC_COLLECTION_INTERVAL` | No | 60 | Seconds between API calls |
| `F5XC_HTTP_PORT` | No | 8080 | Port for metrics HTTP server |
| `F5XC_LOG_LEVEL` | No | INFO | Logging level |

## Prometheus Configuration

Add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'f5xc-exporter'
    static_configs:
      - targets: ['localhost:8080']
    scrape_interval: 60s
```

## Development

This project follows an issue-based development workflow with feature branches and pull requests.

### Local Development

```bash
# Clone repository
git clone https://github.com/tenantOps/f5xc-prom-exporter.git
cd f5xc-prom-exporter

# Complete development setup
make dev-setup

# Copy and configure environment
cp config/example.env .env
# Edit .env with your F5xc credentials

# Run tests
make test

# Run the exporter
make run
```

### Testing

Comprehensive test suite with unit tests, integration tests, and code quality checks.

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run all quality checks (format, lint, type-check, test)
make check-all
```

Run `make help` to see all available commands and testing options.

### Available Make Commands

- `make help` - Show available commands
- `make test` - Run tests
- `make test-cov` - Run tests with coverage
- `make lint` - Run code linting
- `make format` - Format code
- `make type-check` - Run type checking
- `make check-all` - Run all quality checks
- `make run` - Run the exporter
- `make docker-build` - Build Docker image
- `make docker-test` - Test Docker image

## License

This project is released into the public domain. See [LICENSE](LICENSE) for details.
