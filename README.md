# F5 Distributed Cloud Prometheus Exporter

A Prometheus exporter for collecting metrics from F5 Distributed Cloud (F5xc) tenants. This exporter provides observability into your F5xc infrastructure by exposing key metrics that can be scraped by Prometheus.

## Features

- **Multi-Collector Architecture**: Quota, Security, DNS, Load Balancer, and Synthetic Monitoring collectors
- **Circuit Breaker Pattern**: Automatic API failure protection and recovery
- **Cardinality Management**: Prevents metric explosion with configurable resource limits
- **Health & Readiness Probes**: Kubernetes-ready health check endpoints
- **Grafana Dashboards**: 5 production-ready dashboards for visualization
- **Prometheus Alerts**: Comprehensive alerting rules for all metrics
- **Flexible Deployment**: Run with Python, Docker, or Kubernetes
- **Secure Configuration**: Environment variable-based credential management

## Quick Start

### Prerequisites

- F5 Distributed Cloud tenant access
- Valid F5xc API access token

### Running with Docker

```bash
docker run -p 8080:8080 \
  -e F5XC_TENANT_URL="https://your-tenant.console.ves.volterra.io" \
  -e F5XC_ACCESS_TOKEN="your-token" \
  ghcr.io/f5xc-tenantops/f5xc-prom-exporter:latest
```

### Running with Python

```bash
# Install and run
pip install -r requirements.txt
export F5XC_TENANT_URL="https://your-tenant.console.ves.volterra.io"
export F5XC_ACCESS_TOKEN="your-token"
python -m f5xc_exporter
```

### Kubernetes Deployment

See [config/kubernetes/](config/kubernetes/) for deployment manifests and Helm charts.

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `F5XC_TENANT_URL` | F5 Distributed Cloud tenant URL (e.g., `https://tenant.console.ves.volterra.io`) |
| `F5XC_ACCESS_TOKEN` | F5xc API access token for authentication |

### Optional Environment Variables

#### Server Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `F5XC_EXP_HTTP_PORT` | 8080 | Port for metrics HTTP server |
| `F5XC_EXP_LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

#### Collector Intervals
Set to `0` to disable a collector entirely.

| Variable | Default | Description |
|----------|---------|-------------|
| `F5XC_QUOTA_INTERVAL` | 600 | Quota/usage collection interval (seconds) |
| `F5XC_SECURITY_INTERVAL` | 120 | Security events collection interval (seconds) |
| `F5XC_SYNTHETIC_INTERVAL` | 120 | Synthetic monitoring collection interval (seconds) |
| `F5XC_HTTP_LB_INTERVAL` | 120 | HTTP load balancer stats interval (seconds) |
| `F5XC_TCP_LB_INTERVAL` | 120 | TCP load balancer stats interval (seconds) |
| `F5XC_UDP_LB_INTERVAL` | 120 | UDP load balancer stats interval (seconds) |
| `F5XC_DNS_INTERVAL` | 120 | DNS zone and LB metrics interval (seconds) |

#### API Client Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `F5XC_MAX_CONCURRENT_REQUESTS` | 5 | Maximum concurrent API requests |
| `F5XC_REQUEST_TIMEOUT` | 30 | API request timeout (seconds) |

#### Circuit Breaker Configuration
See [docs/CIRCUIT_BREAKER.md](docs/CIRCUIT_BREAKER.md) for detailed documentation.

| Variable | Default | Description |
|----------|---------|-------------|
| `F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 | Failures before opening circuit |
| `F5XC_CIRCUIT_BREAKER_TIMEOUT` | 60 | Seconds before testing recovery |
| `F5XC_CIRCUIT_BREAKER_SUCCESS_THRESHOLD` | 2 | Successes needed to close circuit |
| `F5XC_CIRCUIT_BREAKER_ENDPOINT_TTL_HOURS` | 24 | Hours before endpoint cleanup |
| `F5XC_CIRCUIT_BREAKER_CLEANUP_INTERVAL` | 21600 | Seconds between cleanup runs (0=disabled) |

#### Cardinality Management
See [docs/CARDINALITY.md](docs/CARDINALITY.md) for detailed documentation.

| Variable | Default | Description |
|----------|---------|-------------|
| `F5XC_MAX_NAMESPACES` | 100 | Maximum namespaces to track (0 = unlimited) |
| `F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE` | 50 | Maximum load balancers per namespace (0 = unlimited) |
| `F5XC_MAX_DNS_ZONES` | 100 | Maximum DNS zones to track (0 = unlimited) |
| `F5XC_WARN_CARDINALITY_THRESHOLD` | 10000 | Log warning when cardinality exceeds value (0 = disabled) |

### Example Configurations

**Minimal (defaults)**:
```bash
export F5XC_TENANT_URL="https://your-tenant.console.ves.volterra.io"
export F5XC_ACCESS_TOKEN="your-token"
```

**Disable specific collectors**:
```bash
# Disable security and synthetic monitoring
export F5XC_SECURITY_INTERVAL=0
export F5XC_SYNTHETIC_INTERVAL=0
```

**High-frequency collection**:
```bash
# Collect more frequently (increased API load)
export F5XC_HTTP_LB_INTERVAL=60
export F5XC_DNS_INTERVAL=60
```

**Large tenant**:
```bash
# Increase limits for tenants with many resources
export F5XC_MAX_NAMESPACES=200
export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=100
export F5XC_MAX_DNS_ZONES=200
```

**Unlimited tracking**:
```bash
# Disable cardinality limits (use with caution)
export F5XC_MAX_NAMESPACES=0
export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=0
export F5XC_MAX_DNS_ZONES=0
```

## Prometheus Configuration

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'f5xc-exporter'
    static_configs:
      - targets: ['localhost:8080']
    scrape_interval: 60s
```

## Health Endpoints

### `/health` - Liveness Probe

Returns 200 if exporter is running.

**Example response**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "collectors": {
    "quota": "enabled",
    "security": "enabled",
    "dns": "enabled",
    "loadbalancer": "enabled",
    "synthetic": "enabled"
  }
}
```

**Kubernetes probe**:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
```

### `/ready` - Readiness Probe

Returns 200 if F5XC API is accessible, 503 otherwise. State is cached and updated every 30 seconds.

**Kubernetes probe**:
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
```

## Monitoring & Visualization

### Grafana Dashboards

5 production-ready dashboards are available in [config/grafana/](config/grafana/):

- **Overview** - Collector health, quota utilization, resource counts
- **Load Balancer** - Request rates, latency, health scores
- **Security** - WAF events, bot defense, attack rates
- **DNS** - Zone queries, load balancer health
- **Synthetic** - Monitor availability and health

See [config/grafana/README.md](config/grafana/README.md) for installation instructions.

### Prometheus Alerts

Comprehensive alerting rules are available in [config/prometheus/alerts/](config/prometheus/alerts/):

- Quota utilization (critical >80%, warning >60%)
- Security events and attack detection
- Load balancer performance and health
- DNS zone query anomalies
- Synthetic monitoring failures

See [config/prometheus/alerts/README.md](config/prometheus/alerts/README.md) for installation and tuning.

## Metrics

All exported metrics are documented in [METRICS.md](METRICS.md).

### Metric Categories

- **Quota & Usage**: Resource utilization, costs, subscription status
- **Load Balancer**: Request rates, error rates, latency, throughput, health scores
- **Security**: WAF attacks, bot defense, firewall events
- **DNS**: Zone queries, load balancer health, pool member status
- **Synthetic Monitoring**: HTTP and DNS monitor availability
- **Collector Health**: Collection duration, success/failure rates

## Development

### Local Development

```bash
# Clone and setup
git clone https://github.com/f5xc-tenantops/f5xc-prom-exporter.git
cd f5xc-prom-exporter
make dev-setup

# Configure environment
cp config/example.env .env
# Edit .env with your credentials

# Run tests
make test

# Run exporter
make run
```

### Testing

```bash
# Run all tests with coverage
make test-cov

# Run quality checks (format, lint, type-check, test)
make check-all

# Run only integration tests
pytest tests/integration/
```

Run `make help` to see all available commands.

## Deployment

See [config/README.md](config/README.md) for deployment guides:

- Docker Compose
- Kubernetes (plain manifests)
- Helm Chart
- Production considerations

## Troubleshooting

### Common Issues

**Authentication errors**:
- Verify `F5XC_ACCESS_TOKEN` is valid and not expired
- Check token has appropriate permissions

**No metrics appearing**:
- Check exporter logs for errors
- Verify Prometheus is scraping the exporter
- Ensure collectors are not disabled (interval > 0)

**High memory usage**:
- Reduce cardinality limits (see [docs/CARDINALITY.md](docs/CARDINALITY.md))
- Increase collection intervals
- Disable unused collectors

**Circuit breaker opening frequently**:
- Check F5XC API status
- Increase `F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
- See [docs/CIRCUIT_BREAKER.md](docs/CIRCUIT_BREAKER.md) for tuning

### Debug Commands

```bash
# View exporter logs
kubectl logs -l app.kubernetes.io/name=f5xc-prom-exporter -f

# Test metrics endpoint
curl http://localhost:8080/metrics

# Check health status
curl http://localhost:8080/health
curl http://localhost:8080/ready

# Test Prometheus scrape
curl http://localhost:8080/metrics | grep f5xc_
```

## License

This project is released into the public domain. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please see our development workflow in [CLAUDE.md](CLAUDE.md).

## Support

- **Issues**: https://github.com/f5xc-tenantops/f5xc-prom-exporter/issues
- **Metrics Documentation**: [METRICS.md](METRICS.md)
- **Deployment Guide**: [config/README.md](config/README.md)
