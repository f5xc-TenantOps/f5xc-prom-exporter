# F5 Distributed Cloud Prometheus Alerting Rules

This directory contains production-ready Prometheus alerting rules for monitoring F5XC metrics exposed by the f5xc-prom-exporter.

## Alert Rule Files

- **f5xc_quota.yml** - Quota and resource utilization alerts
- **f5xc_security.yml** - Security events, WAF, bot defense, and attack detection alerts
- **f5xc_loadbalancer.yml** - HTTP/TCP/UDP load balancer performance and health alerts
- **f5xc_dns.yml** - DNS zone query and load balancer health alerts
- **f5xc_synthetic.yml** - Synthetic monitoring availability and health alerts

## Alert Severity Levels

### Critical (severity: critical)
Alerts requiring immediate attention that indicate service disruption or imminent failure:
- Quota utilization > 80%
- Error rates > 5%
- Load balancer or DNS health failures
- Security event spikes > 3x baseline
- Synthetic monitor availability < 95%

### Warning (severity: warning)
Alerts indicating degraded performance or potential future issues:
- Quota utilization > 60%
- Elevated latency > 2x baseline
- Degraded health scores < 80
- Elevated bot detections
- Individual monitor failures

### Info (severity: info)
Informational alerts for configuration changes or notable events:
- DNS zone count changes
- Configuration updates

## Installation

### Option 1: Kubernetes ConfigMap

Create a ConfigMap with the alert rules:

```bash
kubectl create configmap prometheus-f5xc-alerts \
  --from-file=config/prometheus/alerts/ \
  --namespace=monitoring
```

Reference the ConfigMap in your Prometheus configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      evaluation_interval: 1m

    rule_files:
      - /etc/prometheus/rules/*.yml

    alerting:
      alertmanagers:
        - static_configs:
            - targets:
                - alertmanager:9093
```

Mount the ConfigMap in your Prometheus deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  template:
    spec:
      containers:
        - name: prometheus
          volumeMounts:
            - name: alert-rules
              mountPath: /etc/prometheus/rules
              readOnly: true
      volumes:
        - name: alert-rules
          configMap:
            name: prometheus-f5xc-alerts
```

### Option 2: Docker Compose

Mount the alert rules directory in your Prometheus container:

```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./config/prometheus/alerts:/etc/prometheus/rules:ro
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    ports:
      - 9090:9090
```

Update your `prometheus.yml`:

```yaml
global:
  evaluation_interval: 1m

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

### Option 3: Bare Metal / VM Installation

Copy the alert rule files to your Prometheus rules directory:

```bash
# Default Prometheus rules directory (may vary by installation)
sudo cp config/prometheus/alerts/*.yml /etc/prometheus/rules/

# Reload Prometheus configuration
curl -X POST http://localhost:9090/-/reload
# or
sudo systemctl reload prometheus
```

## Validation

Validate the alert rules before applying:

```bash
# Using promtool
promtool check rules config/prometheus/alerts/*.yml

# Using Prometheus API (after loading)
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type=="alerting")'
```

## Alert Annotations

Each alert includes:

- **summary**: Brief description of the alert condition
- **description**: Detailed information including:
  - Affected resources (tenant, namespace, load balancer, etc.)
  - Current metric values
  - Related metrics for context
  - Impact assessment
- **runbook_url**: Link to runbook documentation (placeholder - customize for your environment)

### Customizing Runbook URLs

Update the `runbook_url` annotations to point to your internal documentation:

```yaml
# Example: Update all runbook URLs
sed -i 's|https://github.com/f5xc-TenantOps/f5xc-prom-exporter/wiki/|https://your-company.com/runbooks/|g' config/prometheus/alerts/*.yml
```

## Alert Examples

### Quota Critical Alert
```yaml
- alert: QuotaUtilizationCritical
  expr: f5xc_quota_utilization > 80
  for: 5m
  labels:
    severity: critical
```

**Triggered when**: Any quota resource exceeds 80% utilization for 5 minutes

**Response**: Immediate action required to prevent service disruption - consider resource expansion or usage reduction

### High Error Rate Alert
```yaml
- alert: HTTPLoadBalancerHighErrorRate
  expr: (f5xc_http_lb_error_rate / f5xc_http_lb_request_rate) > 0.05
  for: 5m
  labels:
    severity: critical
```

**Triggered when**: HTTP error rate exceeds 5% for 5 minutes

**Response**: Investigate origin pool health, check for upstream service issues

## Integration with Alertmanager

Example Alertmanager configuration for F5XC alerts:

```yaml
route:
  group_by: ['alertname', 'tenant', 'namespace']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'

  routes:
    # Critical alerts - immediate notification
    - match:
        severity: critical
      receiver: 'pagerduty'
      continue: true

    # Warning alerts - Slack notification
    - match:
        severity: warning
      receiver: 'slack'

    # Info alerts - log only
    - match:
        severity: info
      receiver: 'null'

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://alertmanager-webhook:8080/alerts'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<your-pagerduty-key>'
        description: '{{ .CommonAnnotations.summary }}'

  - name: 'slack'
    slack_configs:
      - api_url: '<your-slack-webhook>'
        channel: '#f5xc-alerts'
        title: '{{ .CommonAnnotations.summary }}'
        text: '{{ .CommonAnnotations.description }}'

  - name: 'null'
```

## Tuning Alerts

### Adjusting Thresholds

Common threshold adjustments:

```yaml
# Increase quota warning threshold from 60% to 70%
f5xc_quota_utilization > 70 and f5xc_quota_utilization <= 80

# Reduce error rate threshold from 5% to 3% for stricter monitoring
(f5xc_http_lb_error_rate / f5xc_http_lb_request_rate) > 0.03

# Extend latency baseline window from 1 hour to 24 hours
f5xc_http_lb_latency_p95_seconds{direction="downstream"} > 2 * avg_over_time(f5xc_http_lb_latency_p95_seconds{direction="downstream"}[24h] offset 24h)
```

### Adjusting Alert Duration

Modify the `for:` clause to change how long a condition must be true before firing:

```yaml
# Faster alerting (1 minute instead of 5)
for: 1m

# Slower alerting to reduce noise (15 minutes instead of 5)
for: 15m
```

## Silencing Alerts

Temporarily silence alerts using Alertmanager:

```bash
# Silence all alerts for a specific namespace during maintenance
amtool silence add namespace="production" --duration=2h --comment="Planned maintenance"

# Silence quota alerts for a specific resource
amtool silence add alertname="QuotaUtilizationWarning" resource_name="load_balancer" --duration=30m
```

## Testing Alerts

### Verify Alert Rules Load
```bash
# Check Prometheus configuration
curl http://localhost:9090/api/v1/status/config | jq '.data.yaml' | grep -A 5 'rule_files'

# List all loaded alerts
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type=="alerting") | .name'
```

### Check Active Alerts
```bash
# View all firing alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'

# View pending alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="pending")'
```

### Manual Alert Testing
```bash
# Query the alert expression to see if it would fire
curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=f5xc_quota_utilization > 80' | jq
```

## Troubleshooting

### Alerts Not Firing

1. **Verify metrics are being scraped**:
   ```bash
   curl http://localhost:9090/api/v1/query?query=f5xc_quota_utilization
   ```

2. **Check alert rule syntax**:
   ```bash
   promtool check rules config/prometheus/alerts/*.yml
   ```

3. **Verify rule file is loaded**:
   ```bash
   curl http://localhost:9090/api/v1/status/config
   ```

### Too Many Alerts (Alert Fatigue)

1. **Increase thresholds** for warning alerts
2. **Extend `for:` duration** to require sustained issues
3. **Add label filters** to exclude test/development environments:
   ```yaml
   expr: f5xc_quota_utilization{namespace!~"dev.*|test.*"} > 80
   ```
4. **Aggregate related alerts** using alert grouping in Alertmanager

## References

- [Prometheus Alerting Documentation](https://prometheus.io/docs/alerting/latest/overview/)
- [F5XC Metrics Reference](../../../METRICS.md)
- [F5XC Metrics Implementation Plan](../../../docs/METRICS_PLAN.md)
- [PromQL Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)

## Contributing

To add new alert rules:

1. Follow the existing structure and naming conventions
2. Include appropriate severity labels (critical/warning/info)
3. Add clear summary and description annotations
4. Set appropriate `for:` duration based on alert criticality
5. Test the alert expression using PromQL
6. Document the alert in this README if it introduces new patterns
