# F5 Distributed Cloud Grafana Dashboards

This directory contains production-ready Grafana dashboards for visualizing F5XC metrics exposed by the f5xc-prom-exporter.

## Dashboard Files

- **overview.json** - Overall tenant health, collector status, quota utilization, and resource counts
- **loadbalancer.json** - HTTP/TCP/UDP load balancer performance, latency, health scores, and throughput
- **security.json** - WAF events, bot defense, attack rates, and security event trends
- **dns.json** - DNS zone queries, load balancer health, and pool member status
- **synthetic.json** - Synthetic monitoring availability, monitor health, and alerting

## Dashboard Features

### Common Features Across All Dashboards
- **Template Variables**: Filter by tenant, namespace, and/or specific resources
- **Auto-refresh**: 30-second refresh interval (configurable)
- **Alert Annotations**: Visual indicators for critical thresholds
- **Time Range**: Default 6-hour window (adjustable)
- **Interactive Legends**: Click to show/hide series, hover for details

### Dashboard-Specific Highlights

#### Overview Dashboard (f5xc-overview)
- **Collector Health**: Status indicators for all metric collectors
- **Quota Utilization**: Top 10 resources by usage percentage with thresholds
- **Resource Counts**: HTTP/TCP/UDP load balancers, DNS zones, and LBs
- **Collection Duration**: Performance metrics for each collector
- **Security Overview**: WAF events by namespace

#### Load Balancer Performance Dashboard (f5xc-loadbalancer)
- **Request Metrics**: Request rate, error rate percentage
- **Latency Percentiles**: P50, P90, P99 latency graphs
- **Health Scores**: Overall, connectivity, performance, and security gauges
- **Throughput**: Request/response bandwidth in bits per second
- **RTT Metrics**: Client and server round-trip time
- **Alert Threshold Annotations**: Visual markers when error rate exceeds 5%

#### Security Dashboard (f5xc-security)
- **Event Totals**: WAF, bot defense, DoS, and malicious user events
- **Event Rates**: Rate of change for security events
- **Attack Rates**: Per-load balancer attack percentage
- **Bot Detection**: Detection rates per load balancer
- **Event Type Breakdown**: Stacked view of all security event types
- **Alert Annotations**: Visual markers for security event spikes

#### DNS Monitoring Dashboard (f5xc-dns)
- **Zone Metrics**: Query rates and total queries for top zones
- **Health Status Tables**: DNS LB and pool member health with color coding
- **Health Trends**: Historical health status over time
- **Query Distribution**: Top 10 zones by query volume
- **Alert Annotations**: Indicators for DNS LB failures

#### Synthetic Monitoring Dashboard (f5xc-synthetic)
- **Availability Gauges**: HTTP and DNS monitor availability percentages
- **Monitor Counts**: Total, healthy, and critical monitor statistics
- **Health Trends**: Time-series view of monitor health states
- **Namespace Availability**: Per-namespace availability tracking
- **Alert Annotations**: Critical monitor state indicators

## Installation

### Prerequisites
- Grafana 8.0 or later
- Prometheus data source configured in Grafana
- F5XC Prometheus exporter running and scraped by Prometheus

### Option 1: Import via Grafana UI

1. **Navigate to Dashboards**:
   - Open Grafana in your browser
   - Click "Dashboards" → "Import" (or navigate to `/dashboard/import`)

2. **Upload JSON**:
   - Click "Upload JSON file"
   - Select one of the dashboard files (e.g., `overview.json`)
   - Or copy/paste the JSON content directly

3. **Configure Data Source**:
   - Select your Prometheus data source from the dropdown
   - Click "Import"

4. **Repeat** for each dashboard file

### Option 2: Provisioning (Recommended for Production)

Create a provisioning configuration for automatic dashboard deployment:

**1. Create provisioning directory structure:**
```bash
mkdir -p /etc/grafana/provisioning/dashboards
```

**2. Create dashboard provider configuration:**

`/etc/grafana/provisioning/dashboards/f5xc.yaml`:
```yaml
apiVersion: 1

providers:
  - name: 'F5 Distributed Cloud'
    orgId: 1
    folder: 'F5XC'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards/f5xc
      foldersFromFilesStructure: false
```

**3. Copy dashboard files:**
```bash
sudo mkdir -p /var/lib/grafana/dashboards/f5xc
sudo cp config/grafana/*.json /var/lib/grafana/dashboards/f5xc/
sudo chown -R grafana:grafana /var/lib/grafana/dashboards/f5xc
```

**4. Restart Grafana:**
```bash
sudo systemctl restart grafana-server
```

Dashboards will appear in the "F5XC" folder automatically.

### Option 3: Kubernetes ConfigMap

**1. Create ConfigMap with dashboards:**
```bash
kubectl create configmap grafana-f5xc-dashboards \
  --from-file=config/grafana/ \
  --namespace=monitoring
```

**2. Create dashboard provider ConfigMap:**

`grafana-dashboard-provider.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-provider
  namespace: monitoring
data:
  f5xc.yaml: |
    apiVersion: 1
    providers:
      - name: 'F5 Distributed Cloud'
        orgId: 1
        folder: 'F5XC'
        type: file
        disableDeletion: false
        updateIntervalSeconds: 30
        allowUiUpdates: true
        options:
          path: /var/lib/grafana/dashboards/f5xc
          foldersFromFilesStructure: false
```

**3. Mount in Grafana deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: monitoring
spec:
  template:
    spec:
      containers:
        - name: grafana
          volumeMounts:
            - name: dashboard-provider
              mountPath: /etc/grafana/provisioning/dashboards
            - name: dashboards
              mountPath: /var/lib/grafana/dashboards/f5xc
      volumes:
        - name: dashboard-provider
          configMap:
            name: grafana-dashboard-provider
        - name: dashboards
          configMap:
            name: grafana-f5xc-dashboards
```

### Option 4: Docker Compose

Mount dashboard files and provisioning config in your Grafana container:

`docker-compose.yml`:
```yaml
version: '3.8'
services:
  grafana:
    image: grafana/grafana:latest
    ports:
      - 3000:3000
    volumes:
      - ./config/grafana:/var/lib/grafana/dashboards/f5xc:ro
      - ./grafana-provisioning:/etc/grafana/provisioning:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

Create provisioning file at `grafana-provisioning/dashboards/f5xc.yaml` with content from Option 2.

## Configuration

### Data Source Configuration

Dashboards use a variable `${DS_PROMETHEUS}` for the data source. Configure it by:

1. **During Import**: Select your Prometheus data source
2. **After Import**: Dashboard Settings → Variables → Edit datasource variable

### Template Variables

Each dashboard includes template variables for filtering:

| Dashboard | Variables | Description |
|-----------|-----------|-------------|
| Overview | `$tenant` | F5XC tenant to display |
| Load Balancer | `$tenant`, `$namespace`, `$load_balancer` | Filter by tenant, namespace, and LB |
| Security | `$tenant`, `$namespace` | Filter by tenant and namespace |
| DNS | `$tenant` | Filter by tenant (DNS is not namespaced) |
| Synthetic | `$tenant`, `$namespace` | Filter by tenant and namespace |

**Multi-select**: Most variables support selecting multiple values (use "All" for everything)

### Time Range and Refresh

Default settings:
- **Time Range**: Last 6 hours
- **Refresh**: 30 seconds

Adjust via dashboard settings:
- Click time range picker in top-right to change window
- Click refresh dropdown to change auto-refresh interval
- Click calendar icon to set custom time range

## Customization

### Adjusting Alert Thresholds

Alert annotations are configured in each dashboard's annotation settings. To modify:

1. **Dashboard Settings** → **Annotations**
2. Select the annotation to edit (e.g., "High Error Rate")
3. Modify the PromQL expression
4. Update threshold values

Example - Changing error rate threshold from 5% to 3%:
```promql
# Original
(f5xc_http_lb_error_rate / f5xc_http_lb_request_rate) > 0.05

# Modified
(f5xc_http_lb_error_rate / f5xc_http_lb_request_rate) > 0.03
```

### Modifying Thresholds in Visualizations

Gauge and graph thresholds can be adjusted per panel:

1. **Edit Panel** (click panel title → Edit)
2. Navigate to **Field** → **Thresholds**
3. Add, remove, or modify threshold values and colors
4. Click **Apply** to save

Example threshold configurations:
- **Quota Utilization**: Green (0-60%), Yellow (60-80%), Red (80-100%)
- **Health Scores**: Red (0-50), Orange (50-70), Yellow (70-80), Green (80-100)
- **Availability**: Red (0-90%), Orange (90-95%), Yellow (95-98%), Green (98-100%)

### Adding New Panels

To add custom panels:

1. **Add Panel** → **Add a new panel**
2. Configure query using PromQL (see [METRICS.md](../../METRICS.md) for available metrics)
3. Select visualization type (Time series, Gauge, Stat, Table, etc.)
4. Configure display options, thresholds, and legends
5. Click **Apply** to add to dashboard

### Cloning Dashboards

To create customized versions without modifying originals:

1. Dashboard Settings → **Save As**
2. Enter new dashboard name
3. Modify as needed
4. Original remains unchanged

## Troubleshooting

### Dashboard Shows "No Data"

**Symptoms**: Panels display "No data" or "N/A"

**Causes & Solutions**:

1. **Prometheus not scraping exporter**:
   ```bash
   # Check Prometheus targets
   curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="f5xc-exporter")'
   ```

2. **Incorrect data source**:
   - Dashboard Settings → Variables → Verify `DS_PROMETHEUS` points to correct data source

3. **No data from exporter yet**:
   - Check exporter logs: `kubectl logs -n monitoring deployment/f5xc-exporter`
   - Verify collection intervals haven't disabled collectors

4. **Template variable returns empty**:
   - Edit variable → Preview of values should show tenant names
   - Verify metric exists: `curl http://prometheus:9090/api/v1/query?query=f5xc_quota_utilization`

### Queries Timeout or Slow

**Symptoms**: Panels take long to load or timeout

**Causes & Solutions**:

1. **Large cardinality**:
   - Reduce time range (e.g., from 24h to 6h)
   - Add more specific label filters
   - Increase Prometheus query timeout

2. **High metric volume**:
   - Use `topk()` to limit results: `topk(10, metric_name)`
   - Aggregate by fewer labels: `sum by (tenant, namespace) instead of all labels`

3. **Prometheus resource constraints**:
   - Check Prometheus memory/CPU usage
   - Consider increasing retention period limits
   - Optimize PromQL queries (avoid regex where possible)

### Template Variables Not Working

**Symptoms**: Dropdowns empty or "All" returns no data

**Causes & Solutions**:

1. **Metric doesn't exist**:
   ```bash
   # Test variable query directly
   curl -G http://prometheus:9090/api/v1/label/tenant/values
   ```

2. **Variable dependency**:
   - Variables are queried in order
   - Ensure `$tenant` is populated before `$namespace`
   - Check variable query uses correct previous variable

3. **Regex filter too restrictive**:
   - Edit variable → Remove or adjust Regex filter
   - Test with Regex: `.*` (matches all)

### Colors or Thresholds Wrong

**Symptoms**: Panels show incorrect colors, thresholds not triggering

**Solutions**:

1. **Check threshold configuration**:
   - Edit panel → Field → Thresholds
   - Verify threshold values match expected data range
   - Ensure threshold mode is appropriate (Absolute vs Percentage)

2. **Verify units**:
   - Some metrics are in seconds, others in milliseconds
   - Check Field → Standard options → Unit

3. **Mappings may override**:
   - Edit panel → Field → Value mappings
   - Ensure mappings don't conflict with thresholds

## Integration with Alerts

Dashboards include alert threshold annotations that visualize when Prometheus alerts would fire. To see active alerts within dashboards:

1. **Enable Grafana Alerting**:
   ```ini
   # grafana.ini
   [alerting]
   enabled = true
   ```

2. **Configure alert notifications**:
   - Alerting → Notification channels
   - Add Slack, PagerDuty, email, etc.

3. **Create alert rules from panels**:
   - Edit panel → Alert tab → Create Alert
   - Configure thresholds and notification channels

**Recommended**: Use Prometheus Alertmanager for alerting (see `config/prometheus/alerts/README.md`) and Grafana dashboards for visualization.

## Best Practices

### Dashboard Organization
- **Overview first**: Start with the Overview dashboard to assess overall health
- **Drill down**: Use Load Balancer, Security, DNS, or Synthetic dashboards for detailed investigation
- **Folder structure**: Organize in Grafana folders by environment (Production, Staging, Development)

### Performance Optimization
- **Limit time ranges**: Shorter ranges load faster and reduce Prometheus load
- **Use variables**: Filter to specific namespaces/LBs instead of showing all
- **Aggregate**: Use `sum()`, `avg()`, or `topk()` to reduce cardinality
- **Appropriate intervals**: Match dashboard refresh to Prometheus scrape interval

### Collaboration
- **Snapshot sharing**: Create snapshots to share specific views
- **Annotations**: Add manual annotations to mark incidents or changes
- **Playlists**: Create playlists to cycle through dashboards on monitors

## Exporting Dashboards

To export customized dashboards for version control:

1. **Dashboard Settings** → **JSON Model**
2. **Copy JSON** to clipboard
3. Save to file: `custom-dashboard.json`
4. Commit to repository for team sharing

## References

- [F5XC Metrics Reference](../../METRICS.md) - Complete list of available metrics
- [Prometheus Alerting Rules](../prometheus/alerts/README.md) - Alert rule definitions
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/) - Official Grafana docs
- [PromQL Documentation](https://prometheus.io/docs/prometheus/latest/querying/basics/) - Query language reference

## Support

For dashboard issues or feature requests:
- **Issues**: https://github.com/f5xc-TenantOps/f5xc-prom-exporter/issues
- **Documentation**: Project README and METRICS.md
- **Community**: F5 Distributed Cloud community forums
