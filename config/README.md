# Deployment Configuration

This directory contains deployment configurations for the F5XC Prometheus Exporter.

## Available Deployments

### 🐳 Docker Compose
- **File**: `docker-compose.yml` (in project root)
- **Use case**: Local development and testing

### ☸️ Kubernetes (Plain Manifests)
- **Directory**: `kubernetes/`
- **Use case**: Direct kubectl deployment
- **Features**:
  - Namespace isolation
  - Security contexts
  - Resource limits
  - Health checks
  - Prometheus integration
  - ServiceMonitor for Prometheus Operator

### 📦 Helm Chart
- **Directory**: `helm/f5xc-prom-exporter/`
- **Use case**: Templated Kubernetes deployments
- **Features**:
  - Configurable values
  - External secrets support
  - Ingress configuration
  - Autoscaling options

### 📄 Environment Configuration
- **File**: `example.env`
- **Use case**: Environment variable reference

## Quick Start

### Docker Compose
```bash
# Copy and edit environment file
cp config/example.env .env
# Edit .env with your F5XC credentials
docker-compose up
```

### Kubernetes
```bash
# Edit credentials in secret.yaml
vi config/kubernetes/secret.yaml

# Deploy
kubectl apply -f config/kubernetes/
```

### Helm
```bash
# Install with custom values
helm install f5xc-exporter config/helm/f5xc-prom-exporter/ \
  --set f5xc.tenantUrl="https://your-tenant.console.ves.volterra.io" \
  --set f5xc.accessToken="your-token"
```

## Configuration Options

### Core Settings
- **F5XC_TENANT_URL**: Your F5 Distributed Cloud tenant URL
- **F5XC_ACCESS_TOKEN**: Your F5XC API access token

### Collection Intervals (seconds)
- **F5XC_QUOTA_INTERVAL**: 600 (10 minutes) - Resource quota metrics
- **F5XC_SECURITY_INTERVAL**: 120 (2 minutes) - Security event metrics
- **F5XC_SYNTHETIC_INTERVAL**: 120 (2 minutes) - Synthetic monitoring
- **F5XC_HTTP_LB_INTERVAL**: 120 (2 minutes) - HTTP load balancer metrics
- **F5XC_TCP_LB_INTERVAL**: 120 (2 minutes) - TCP load balancer metrics
- **F5XC_UDP_LB_INTERVAL**: 120 (2 minutes) - UDP load balancer metrics
- **F5XC_DNS_INTERVAL**: 120 (2 minutes) - DNS zone and LB metrics

### Server Settings
- **F5XC_EXP_HTTP_PORT**: 8080 - Metrics server port
- **F5XC_EXP_LOG_LEVEL**: INFO - Logging level

## Security Considerations

### Credentials Management
1. **Never commit credentials** to version control
2. Use **Kubernetes secrets** for production deployments
3. Consider **external secret management** (Vault, AWS Secrets Manager, etc.)

### Network Security
- Deploy in isolated namespace
- Use network policies if available
- Restrict egress to F5XC API endpoints only

### Container Security
- Runs as non-root user
- Read-only root filesystem
- Dropped capabilities
- Resource limits enforced

## Monitoring Integration

### Prometheus
The exporter is automatically discovered by Prometheus using:
- Service annotations
- ServiceMonitor (for Prometheus Operator)

### Grafana
5 production-ready dashboards available in `grafana/`:
- Overview - Collector health, quota utilization, resource counts
- Load Balancer - Request rates, latency, health scores
- Security - WAF events, bot defense, attack rates
- DNS - Zone queries, load balancer health
- Synthetic - Monitor availability and health

See [grafana/README.md](grafana/README.md) for installation instructions.

### Prometheus Alerts
Comprehensive alerting rules available in `prometheus/alerts/`:
- Quota utilization thresholds (critical >80%, warning >60%)
- Security events and attack detection
- Load balancer performance and health
- DNS zone query anomalies
- Synthetic monitoring failures

See [prometheus/alerts/README.md](prometheus/alerts/README.md) for installation and configuration.

## Troubleshooting

### Common Issues
1. **Authentication errors**: Verify F5XC credentials
2. **Network connectivity**: Ensure cluster can reach F5XC tenant
3. **Resource limits**: Adjust memory/CPU based on collection frequency
4. **Rate limiting**: Increase intervals if hitting F5XC API limits

### Debug Commands
```bash
# Check pod logs
kubectl logs -l app.kubernetes.io/name=f5xc-prom-exporter

# Test metrics endpoint
kubectl port-forward svc/f5xc-prom-exporter 8080:8080
curl http://localhost:8080/metrics

# Verify configuration
kubectl get configmap f5xc-exporter-config -o yaml
```

## Production Considerations

### Scaling
- Single replica recommended to avoid duplicate metrics
- Use anti-affinity for high availability
- Monitor exporter resource usage

### Updates
- Use rolling updates for zero downtime
- Test configuration changes in staging first
- Monitor metrics continuity during updates

### Backup
- Export Prometheus data regularly
- Backup F5XC exporter configuration
- Document custom alerting rules