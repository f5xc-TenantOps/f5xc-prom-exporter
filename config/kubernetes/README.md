# Kubernetes Deployment

This directory contains Kubernetes manifests to deploy the F5XC Prometheus Exporter.

## Quick Start

### 1. Configure Credentials

Edit `secret.yaml` and replace the placeholder values:

```yaml
stringData:
  F5XC_TENANT_URL: "https://your-tenant.console.ves.volterra.io"
  F5XC_ACCESS_TOKEN: "your-access-token-here"
```

### 2. Deploy with kubectl

```bash
# Apply all manifests
kubectl apply -f config/kubernetes/

# Or apply in order
kubectl apply -f config/kubernetes/namespace.yaml
kubectl apply -f config/kubernetes/rbac.yaml
kubectl apply -f config/kubernetes/secret.yaml
kubectl apply -f config/kubernetes/configmap.yaml
kubectl apply -f config/kubernetes/deployment.yaml
kubectl apply -f config/kubernetes/service.yaml
kubectl apply -f config/kubernetes/servicemonitor.yaml  # If using Prometheus Operator
```

### 3. Deploy with Kustomize

```bash
kubectl apply -k config/kubernetes/
```

## Files Overview

| File | Description |
|------|-------------|
| `namespace.yaml` | Creates `f5xc-monitoring` namespace |
| `rbac.yaml` | ServiceAccount and RBAC permissions |
| `secret.yaml` | F5XC credentials (edit with your values) |
| `configmap.yaml` | Configuration settings and intervals |
| `deployment.yaml` | Main exporter deployment |
| `service.yaml` | Service to expose the exporter |
| `servicemonitor.yaml` | Prometheus Operator ServiceMonitor |
| `kustomization.yaml` | Kustomize configuration |

## Configuration

### Environment Variables

Configure collection intervals in `configmap.yaml`:

```yaml
data:
  F5XC_QUOTA_INTERVAL: "600"        # 10 minutes
  F5XC_HTTP_LB_INTERVAL: "120"      # 2 minutes
  F5XC_SECURITY_INTERVAL: "180"     # 3 minutes
```

### Resource Limits

Adjust resource requests/limits in `deployment.yaml`:

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "200m"
```

## Security

### Secrets Management

For production deployments, consider using:

1. **External Secrets Operator** (example included in `secret.yaml`)
2. **Sealed Secrets**
3. **Cloud provider secret managers** (AWS Secrets Manager, Azure Key Vault, etc.)

### Security Context

The deployment runs with:
- Non-root user (UID 1000)
- Read-only root filesystem
- Dropped capabilities
- Security context constraints

## Monitoring

### Prometheus Integration

The exporter is automatically discovered by Prometheus using:

1. **Service annotations** in `service.yaml`:
   ```yaml
   annotations:
     prometheus.io/scrape: "true"
     prometheus.io/path: "/metrics"
     prometheus.io/port: "8080"
   ```

2. **ServiceMonitor** for Prometheus Operator (optional)

### Health Checks

The deployment includes:
- **Liveness probe**: `/health` endpoint
- **Readiness probe**: `/health` endpoint

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n f5xc-monitoring
kubectl logs -n f5xc-monitoring deployment/f5xc-prom-exporter
```

### Verify Configuration

```bash
# Check config
kubectl describe configmap f5xc-exporter-config -n f5xc-monitoring

# Check secrets (values will be redacted)
kubectl describe secret f5xc-credentials -n f5xc-monitoring
```

### Test Metrics Endpoint

```bash
# Port forward to test locally
kubectl port-forward -n f5xc-monitoring svc/f5xc-prom-exporter 8080:8080

# Test endpoints
curl http://localhost:8080/health
curl http://localhost:8080/metrics
```

### Common Issues

1. **Authentication errors**: Verify F5XC credentials in secret
2. **High memory usage**: Adjust collection intervals or resource limits
3. **Network issues**: Check F5XC tenant URL accessibility from cluster

## Scaling

### Multiple Replicas

While the exporter can run multiple replicas, it's recommended to use a single replica to avoid:
- Duplicate metrics collection
- F5XC API rate limiting issues

### High Availability

For HA deployments, consider:
- Anti-affinity rules across nodes
- Pod disruption budgets
- Monitoring the exporter itself

## Updates

### Rolling Updates

Update the image tag in `deployment.yaml` or `kustomization.yaml`:

```yaml
images:
- name: ghcr.io/tenantops/f5xc-prom-exporter
  newTag: v1.0.0
```

Then apply:
```bash
kubectl apply -k config/kubernetes/
```

### Configuration Changes

Restart deployment after config changes:
```bash
kubectl rollout restart deployment/f5xc-prom-exporter -n f5xc-monitoring
```