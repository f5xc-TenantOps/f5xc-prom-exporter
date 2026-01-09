# F5 Distributed Cloud Prometheus Exporter - Metrics Reference

This document catalogs all Prometheus metrics exposed by the F5XC exporter, including labels, API call costs per collector, and example PromQL queries.

## Table of Contents

- [API Call Summary](#api-call-summary)
- [Quota Metrics](#quota-metrics)
- [Security Metrics](#security-metrics)
- [Synthetic Monitoring Metrics](#synthetic-monitoring-metrics)
- [Load Balancer Metrics](#load-balancer-metrics)
- [DNS Metrics](#dns-metrics)
- [Example PromQL Queries](#example-promql-queries)

---

## API Call Summary

| Collector | API Calls per Cycle | Notes |
|-----------|---------------------|-------|
| Quota | 1 per namespace | Collects quota usage for each namespace |
| Security | 2 per namespace | 1 for firewall metrics, 1 for event aggregation |
| Synthetic | 2 per namespace | 1 for HTTP monitors, 1 for DNS monitors |
| Load Balancer | 1 total | Single unified call collects HTTP/TCP/UDP across all namespaces |
| DNS | 3 total | Zone metrics + LB health + pool member health (all system namespace) |

**Total API Calls per Collection Cycle**: `1 + N*(1 + 2 + 2) + 1 + 3 = 5 + 5N` where N = number of namespaces

---

## Quota Metrics

Metrics for F5XC resource quota usage per namespace.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_quota_limit` | Gauge | tenant, namespace, resource_type, resource_name | Resource quota limit |
| `f5xc_quota_current` | Gauge | tenant, namespace, resource_type, resource_name | Current resource usage |
| `f5xc_quota_utilization` | Gauge | tenant, namespace, resource_type, resource_name | Utilization percentage (0-100) |
| `f5xc_quota_collection_success` | Gauge | tenant, namespace | Collection success (1=success, 0=failure) |
| `f5xc_quota_collection_duration_seconds` | Gauge | tenant, namespace | Collection duration |

### Labels

- **tenant**: F5XC tenant name
- **namespace**: F5XC namespace
- **resource_type**: "quota" or "resources"
- **resource_name**: Resource identifier (e.g., "load_balancer", "origin_pool")

---

## Security Metrics

Security metrics from WAF, bot defense, and security events.

### Per-Load Balancer Metrics (from app_firewall/metrics API)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_security_total_requests` | Gauge | tenant, namespace, load_balancer | Total requests to the LB |
| `f5xc_security_attacked_requests` | Gauge | tenant, namespace, load_balancer | Requests flagged as attacks |
| `f5xc_security_bot_detections` | Gauge | tenant, namespace, load_balancer | Bot detection count |

### Namespace Event Counts (from events/aggregation API)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_security_waf_events` | Gauge | tenant, namespace | WAF security events |
| `f5xc_security_bot_defense_events` | Gauge | tenant, namespace | Bot defense events |
| `f5xc_security_api_events` | Gauge | tenant, namespace | API security events |
| `f5xc_security_service_policy_events` | Gauge | tenant, namespace | Service policy events |
| `f5xc_security_malicious_user_events` | Gauge | tenant, namespace | Malicious user events |
| `f5xc_security_dos_events` | Gauge | tenant, namespace | DoS attack events |

### Collection Status

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_security_collection_success` | Gauge | tenant | Collection success (1/0) |
| `f5xc_security_collection_duration_seconds` | Gauge | tenant | Collection duration |

---

## Synthetic Monitoring Metrics

Metrics for HTTP and DNS synthetic monitors per namespace.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_synthetic_http_monitors_total` | Gauge | tenant, namespace | Total HTTP monitors |
| `f5xc_synthetic_http_monitors_healthy` | Gauge | tenant, namespace | Healthy HTTP monitors |
| `f5xc_synthetic_http_monitors_critical` | Gauge | tenant, namespace | Critical HTTP monitors |
| `f5xc_synthetic_dns_monitors_total` | Gauge | tenant, namespace | Total DNS monitors |
| `f5xc_synthetic_dns_monitors_healthy` | Gauge | tenant, namespace | Healthy DNS monitors |
| `f5xc_synthetic_dns_monitors_critical` | Gauge | tenant, namespace | Critical DNS monitors |
| `f5xc_synthetic_collection_success` | Gauge | tenant | Collection success (1/0) |
| `f5xc_synthetic_collection_duration_seconds` | Gauge | tenant | Collection duration |

---

## Load Balancer Metrics

Unified metrics for HTTP, TCP, and UDP load balancers with upstream/downstream direction.

### HTTP Load Balancer Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_http_lb_request_rate` | Gauge | tenant, namespace, load_balancer, site, direction | HTTP requests/second |
| `f5xc_http_lb_request_to_origin_rate` | Gauge | tenant, namespace, load_balancer, site, direction | Requests to origin/second |
| `f5xc_http_lb_error_rate` | Gauge | tenant, namespace, load_balancer, site, direction | HTTP errors/second |
| `f5xc_http_lb_error_rate_4xx` | Gauge | tenant, namespace, load_balancer, site, direction | 4xx errors/second |
| `f5xc_http_lb_error_rate_5xx` | Gauge | tenant, namespace, load_balancer, site, direction | 5xx errors/second |
| `f5xc_http_lb_latency_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Average response latency |
| `f5xc_http_lb_latency_p50_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | P50 latency |
| `f5xc_http_lb_latency_p90_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | P90 latency |
| `f5xc_http_lb_latency_p99_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | P99 latency |
| `f5xc_http_lb_app_latency_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Application latency |
| `f5xc_http_lb_server_data_transfer_time_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Server data transfer time |
| `f5xc_http_lb_request_throughput_bps` | Gauge | tenant, namespace, load_balancer, site, direction | Request throughput (bits/sec) |
| `f5xc_http_lb_response_throughput_bps` | Gauge | tenant, namespace, load_balancer, site, direction | Response throughput (bits/sec) |
| `f5xc_http_lb_client_rtt_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Client RTT |
| `f5xc_http_lb_server_rtt_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Server RTT |

### TCP Load Balancer Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_tcp_lb_connection_rate` | Gauge | tenant, namespace, load_balancer, site, direction | TCP connections/second |
| `f5xc_tcp_lb_connection_duration_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Average connection duration |
| `f5xc_tcp_lb_error_rate` | Gauge | tenant, namespace, load_balancer, site, direction | TCP errors/second |
| `f5xc_tcp_lb_error_rate_client` | Gauge | tenant, namespace, load_balancer, site, direction | Client-side errors/second |
| `f5xc_tcp_lb_error_rate_upstream` | Gauge | tenant, namespace, load_balancer, site, direction | Upstream errors/second |
| `f5xc_tcp_lb_request_throughput_bps` | Gauge | tenant, namespace, load_balancer, site, direction | Request throughput (bits/sec) |
| `f5xc_tcp_lb_response_throughput_bps` | Gauge | tenant, namespace, load_balancer, site, direction | Response throughput (bits/sec) |
| `f5xc_tcp_lb_client_rtt_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Client RTT |
| `f5xc_tcp_lb_server_rtt_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Server RTT |

### UDP Load Balancer Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_udp_lb_request_throughput_bps` | Gauge | tenant, namespace, load_balancer, site, direction | Request throughput (bits/sec) |
| `f5xc_udp_lb_response_throughput_bps` | Gauge | tenant, namespace, load_balancer, site, direction | Response throughput (bits/sec) |
| `f5xc_udp_lb_client_rtt_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Client RTT |
| `f5xc_udp_lb_server_rtt_seconds` | Gauge | tenant, namespace, load_balancer, site, direction | Server RTT |

### Load Balancer Collection Status

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_lb_collection_success` | Gauge | tenant | Collection success (1/0) |
| `f5xc_lb_collection_duration_seconds` | Gauge | tenant | Collection duration |
| `f5xc_http_lb_count` | Gauge | tenant | Number of HTTP LBs discovered |
| `f5xc_tcp_lb_count` | Gauge | tenant | Number of TCP LBs discovered |
| `f5xc_udp_lb_count` | Gauge | tenant | Number of UDP LBs discovered |

### Labels

- **direction**: "downstream" (client to LB) or "upstream" (LB to origin)

---

## DNS Metrics

DNS zone query metrics and DNS Load Balancer health status.

**Note**: DNS is not namespaced in F5XC - all DNS resources are in the system namespace.

### Zone Traffic Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_dns_zone_query_count` | Gauge | tenant, zone | Total DNS queries per zone |

### DNS Load Balancer Health Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_dns_lb_health_status` | Gauge | tenant, dns_lb | LB health (1=healthy, 0=unhealthy) |
| `f5xc_dns_lb_pool_member_health` | Gauge | tenant, dns_lb, pool, member | Pool member health (1=healthy, 0=unhealthy) |

### DNS Collection Status

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `f5xc_dns_collection_success` | Gauge | tenant | Collection success (1/0) |
| `f5xc_dns_collection_duration_seconds` | Gauge | tenant | Collection duration |
| `f5xc_dns_zone_count` | Gauge | tenant | Number of DNS zones discovered |
| `f5xc_dns_lb_count` | Gauge | tenant | Number of DNS LBs discovered |

---

## Example PromQL Queries

### Quota Monitoring

```promql
# Top 10 resources by utilization
topk(10, f5xc_quota_utilization)

# Resources over 80% utilization
f5xc_quota_utilization > 80

# Load balancer quota usage trend
f5xc_quota_current{resource_name="load_balancer"}
```

### Security Alerts

```promql
# Total WAF events across all namespaces
sum(f5xc_security_waf_events) by (tenant)

# Attack rate per load balancer
f5xc_security_attacked_requests / f5xc_security_total_requests * 100

# Bot detection rate
rate(f5xc_security_bot_detections[5m])
```

### Load Balancer Performance

```promql
# P99 latency by load balancer
f5xc_http_lb_latency_p99_seconds{direction="downstream"}

# Error rate percentage
f5xc_http_lb_error_rate / f5xc_http_lb_request_rate * 100

# Total request throughput
sum(f5xc_http_lb_request_throughput_bps) by (tenant)
```

### Synthetic Monitoring

```promql
# Critical monitors (needs attention)
f5xc_synthetic_http_monitors_critical > 0
or
f5xc_synthetic_dns_monitors_critical > 0

# Monitor health percentage
f5xc_synthetic_http_monitors_healthy / f5xc_synthetic_http_monitors_total * 100
```

### DNS Monitoring

```promql
# Top 5 DNS zones by query count
topk(5, f5xc_dns_zone_query_count)

# Unhealthy DNS load balancers
f5xc_dns_lb_health_status == 0

# Unhealthy DNS pool members
f5xc_dns_lb_pool_member_health == 0
```

### Collection Health

```promql
# Failed collections (any collector)
{__name__=~"f5xc_.*_collection_success"} == 0

# Collection duration (potential performance issue)
{__name__=~"f5xc_.*_collection_duration_seconds"} > 30
```

---

## Collection Intervals

Configure collection intervals via environment variables:

| Variable | Default | Collector |
|----------|---------|-----------|
| `F5XC_QUOTA_INTERVAL` | 600s | Quota metrics |
| `F5XC_SECURITY_INTERVAL` | 300s | Security metrics |
| `F5XC_SYNTHETIC_INTERVAL` | 120s | Synthetic monitoring |
| `F5XC_HTTP_LB_INTERVAL` | 120s | Load balancer metrics (uses min of HTTP/TCP/UDP) |
| `F5XC_TCP_LB_INTERVAL` | 120s | Load balancer metrics |
| `F5XC_UDP_LB_INTERVAL` | 120s | Load balancer metrics |
| `F5XC_DNS_INTERVAL` | 120s | DNS metrics |

**Disabling collectors**: Set any interval to `0` to disable that collector. For example, `F5XC_QUOTA_INTERVAL=0` disables quota collection. The load balancer collector is only disabled when all three intervals (HTTP, TCP, UDP) are set to 0.

**Recommendation**: Set Prometheus scrape interval to match or be slightly longer than the shortest collection interval.
