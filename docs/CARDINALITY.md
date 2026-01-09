# Cardinality Management

To prevent metric explosion and Prometheus performance degradation, the exporter includes automatic cardinality tracking and limits.

## What is Cardinality?

Cardinality is the number of unique time series in Prometheus. High cardinality occurs when metrics have many unique label combinations, which can:

- Degrade Prometheus query performance
- Increase memory and storage requirements
- Cause out-of-memory errors
- Make dashboards and queries slow

## How It Works

The exporter tracks and limits the number of resources it monitors:

- **Namespaces**: Limits total namespaces tracked across all collectors
- **Load Balancers**: Limits load balancers per namespace
- **DNS Zones**: Limits total DNS zones tracked

When limits are exceeded:
- Resources beyond the limit are **skipped**
- Warning messages are logged with context
- `f5xc_cardinality_limit_exceeded` metric is incremented
- Existing tracked resources continue to be updated normally

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `F5XC_MAX_NAMESPACES` | 100 | Maximum number of namespaces to track (0 = unlimited) |
| `F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE` | 50 | Maximum load balancers per namespace (0 = unlimited) |
| `F5XC_MAX_DNS_ZONES` | 100 | Maximum number of DNS zones to track (0 = unlimited) |
| `F5XC_WARN_CARDINALITY_THRESHOLD` | 10000 | Log warning when metric cardinality exceeds this value (0 = disabled) |

**Note**: Setting any limit to `0` disables that limit, allowing unlimited tracking. Use with caution as this can lead to high cardinality and Prometheus performance issues.

## Metrics

The exporter exposes cardinality tracking metrics:

- `f5xc_metric_cardinality{collector, metric_name}` - Number of unique label combinations per metric
- `f5xc_cardinality_limit_exceeded{collector, limit_type}` - Number of times limit was exceeded
- `f5xc_tracked_namespaces_total` - Total number of tracked namespaces
- `f5xc_tracked_load_balancers_total` - Total number of tracked load balancers
- `f5xc_tracked_dns_zones_total` - Total number of tracked DNS zones

## Example Configurations

### Default (Recommended)
Suitable for most F5XC tenants:
```bash
# Uses built-in defaults
docker run -e F5XC_TENANT_URL="..." -e F5XC_ACCESS_TOKEN="..." ghcr.io/f5xc-tenantops/f5xc-prom-exporter:latest
```

### Small Tenant
For tenants with few resources:
```bash
export F5XC_MAX_NAMESPACES=20
export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=10
export F5XC_MAX_DNS_ZONES=20
```

### Large Tenant
For tenants with many resources (requires more Prometheus resources):
```bash
export F5XC_MAX_NAMESPACES=200
export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=100
export F5XC_MAX_DNS_ZONES=200
export F5XC_WARN_CARDINALITY_THRESHOLD=20000
```

### Unlimited Tracking
Disable limits (not recommended for production):
```bash
export F5XC_MAX_NAMESPACES=0
export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=0
export F5XC_MAX_DNS_ZONES=0
```

## Monitoring Cardinality

Query cardinality metrics in Prometheus:

```promql
# Total cardinality across all collectors
sum(f5xc_metric_cardinality)

# Cardinality by collector
sum by (collector) (f5xc_metric_cardinality)

# Check if limits are being hit
f5xc_cardinality_limit_exceeded > 0

# Current number of tracked resources
f5xc_tracked_namespaces_total
f5xc_tracked_load_balancers_total
f5xc_tracked_dns_zones_total
```

### Alerting on High Cardinality

```promql
# Alert when cardinality exceeds threshold
ALERT HighMetricCardinality
  IF sum(f5xc_metric_cardinality) > 10000
  FOR 10m
  ANNOTATIONS {
    summary = "F5XC exporter has high metric cardinality",
    description = "Cardinality is {{ $value }}, which may impact Prometheus performance."
  }

# Alert when limits are frequently exceeded
ALERT CardinalityLimitExceeded
  IF increase(f5xc_cardinality_limit_exceeded[5m]) > 10
  ANNOTATIONS {
    summary = "F5XC exporter hitting cardinality limits",
    description = "{{ $labels.collector }} has exceeded {{ $labels.limit_type }} limit {{ $value }} times in 5 minutes."
  }
```

## Estimating Cardinality

Calculate expected cardinality for your tenant:

### Formula
```
Total Cardinality ≈ (
  Namespaces × Load_Balancers_Per_NS × Metrics_Per_LB +
  DNS_Zones × Metrics_Per_Zone +
  Namespaces × Metrics_Per_NS
)
```

### Example Calculation
For a tenant with:
- 50 namespaces
- 20 load balancers per namespace (avg)
- 100 DNS zones

```
Load Balancer metrics: 50 × 20 × ~40 = 40,000
DNS metrics: 100 × ~15 = 1,500
Other metrics: 50 × ~30 = 1,500
Total: ~43,000 time series
```

This is within reasonable limits for Prometheus.

## Troubleshooting

### Cardinality limit warnings in logs

**Example log**:
```
WARNING Namespace limit reached, skipping namespace: my-namespace
WARNING Load balancer limit reached for namespace 'prod', skipping: my-lb
```

**Cause**: Tenant has more resources than configured limits

**Solutions**:
1. **Increase limits** if Prometheus can handle higher cardinality:
   ```bash
   export F5XC_MAX_NAMESPACES=200
   export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=100
   ```

2. **Filter namespaces** at the F5XC API level (if supported)

3. **Deploy multiple exporters** with different namespace filters

### Prometheus performance degradation

**Symptoms**: Slow queries, high memory usage, OOM errors

**Cause**: Total cardinality too high for Prometheus resources

**Solutions**:
1. **Reduce limits**:
   ```bash
   export F5XC_MAX_NAMESPACES=50
   export F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE=25
   ```

2. **Increase Prometheus resources** (memory and CPU)

3. **Reduce retention period** in Prometheus

4. **Use recording rules** to pre-aggregate data

### Important resources not tracked

**Cause**: Resources were added after limits were reached

**Solutions**:
1. Review tracked resources: Check `f5xc_tracked_*` metrics
2. Increase limits to accommodate all critical resources
3. Consider priority-based tracking (feature request)

## Best Practices

1. **Monitor cardinality metrics** regularly to understand your tenant's footprint
2. **Set limits based on Prometheus capacity**, not tenant size
3. **Start conservative** and increase limits gradually while monitoring Prometheus performance
4. **Alert on limit violations** to detect when tenant grows beyond configured capacity
5. **Test limit changes in staging** before applying to production
6. **Document your limits** in runbooks for on-call engineers

## Related Configuration

Cardinality management works alongside collection intervals to control resource usage:

- **Lower collection intervals** = More frequent updates but same cardinality
- **Higher limits** = More time series but potentially better coverage
- **Disable collectors** = Reduce cardinality by removing entire metric families

See [README.md](../README.md) for collection interval configuration.
