# Circuit Breaker Pattern

The exporter implements a circuit breaker pattern to prevent cascading failures when the F5XC API is experiencing issues.

## How It Works

The circuit breaker monitors API call failures and automatically stops sending requests when the API is unhealthy, allowing it time to recover.

### States

- **CLOSED** (Normal): All requests proceed normally
- **OPEN** (Failed): API is unhealthy, requests are rejected immediately without calling the API
- **HALF_OPEN** (Testing): Testing recovery after timeout, allowing limited requests through

### State Transitions

1. **CLOSED → OPEN**: After failure threshold is exceeded
2. **OPEN → HALF_OPEN**: After timeout period expires
3. **HALF_OPEN → CLOSED**: After success threshold is met
4. **HALF_OPEN → OPEN**: On any failure during testing

## Interaction with Retry Strategy

The circuit breaker works in conjunction with the retry strategy:

1. **Retry Layer (First)**: Retries requests up to 3 times for specific status codes (429, 500, 502, 503, 504)
2. **Circuit Breaker Layer (Second)**: Only counts failures after all retries are exhausted

This means `failure_threshold=5` actually represents 15 failed API attempts (5 × 3 retries).

### Important Notes

- Authentication errors (401) do NOT trigger retries or count as circuit breaker failures
- Rate limit errors (429) trigger retries AND count as circuit breaker failures if all retries are exhausted
- A single circuit breaker failure = 3 failed API retry attempts

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 | Number of retry-exhausted failures before opening circuit |
| `F5XC_CIRCUIT_BREAKER_TIMEOUT` | 60 | Seconds before transitioning from OPEN to HALF_OPEN |
| `F5XC_CIRCUIT_BREAKER_SUCCESS_THRESHOLD` | 2 | Consecutive successes needed in HALF_OPEN to close circuit |
| `F5XC_CIRCUIT_BREAKER_ENDPOINT_TTL_HOURS` | 24 | Hours of inactivity before endpoint cleanup |
| `F5XC_CIRCUIT_BREAKER_CLEANUP_INTERVAL` | 21600 | Seconds between automatic cleanup runs (0 to disable) |

## Endpoint Cleanup

To prevent memory leaks from tracking endpoints indefinitely, the circuit breaker implements automatic cleanup:

- Tracks last access time for each endpoint
- Background thread runs every 6 hours (configurable) to remove stale endpoints
- Removes endpoints not accessed within the TTL period (default: 24 hours)
- Cleanup is thread-safe and logs removed endpoints
- Set `F5XC_CIRCUIT_BREAKER_CLEANUP_INTERVAL=0` to disable automatic cleanup

## Metrics

The circuit breaker exposes Prometheus metrics for monitoring:

- `f5xc_circuit_breaker_state{endpoint}` - Current state per endpoint (0=CLOSED, 1=OPEN, 2=HALF_OPEN)
- `f5xc_circuit_breaker_failures{endpoint}` - Failure count per endpoint
- `f5xc_circuit_breaker_endpoints_cleaned_total` - Total number of endpoints cleaned up (counter)

## Example Configuration

### Default (Recommended)
```bash
# Uses built-in defaults
docker run -e F5XC_TENANT_URL="..." -e F5XC_ACCESS_TOKEN="..." ghcr.io/f5xc-tenantops/f5xc-prom-exporter:latest
```

### Aggressive Circuit Breaking
For APIs with frequent issues:
```bash
export F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3  # Open faster (9 API attempts)
export F5XC_CIRCUIT_BREAKER_TIMEOUT=30           # Test recovery sooner
export F5XC_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3  # Require more successes to close
```

### Lenient Circuit Breaking
For stable APIs:
```bash
export F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10 # Open slower (30 API attempts)
export F5XC_CIRCUIT_BREAKER_TIMEOUT=120          # Wait longer before testing
export F5XC_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=1  # Close faster
```

## Monitoring Circuit Breaker Health

Query circuit breaker state in Prometheus:

```promql
# Check if any endpoints have open circuits
f5xc_circuit_breaker_state == 1

# Count endpoints in each state
count by (state) (f5xc_circuit_breaker_state)

# Alert on open circuits
ALERT CircuitBreakerOpen
  IF f5xc_circuit_breaker_state == 1
  FOR 5m
  ANNOTATIONS {
    summary = "Circuit breaker open for {{ $labels.endpoint }}",
    description = "The circuit breaker has been open for 5 minutes, indicating persistent API issues."
  }
```

## Troubleshooting

### Circuit breaker opens frequently

**Cause**: API is experiencing issues or thresholds are too aggressive

**Solutions**:
1. Check F5XC API status and network connectivity
2. Increase `F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
3. Increase `F5XC_REQUEST_TIMEOUT` if requests are timing out
4. Review exporter logs for specific error patterns

### Circuit breaker never opens despite API errors

**Cause**: Authentication errors (401) don't count as circuit breaker failures

**Solution**: Verify `F5XC_ACCESS_TOKEN` is valid and not expired

### Memory usage grows over time

**Cause**: Endpoint cleanup disabled or TTL too long

**Solutions**:
1. Ensure `F5XC_CIRCUIT_BREAKER_CLEANUP_INTERVAL > 0`
2. Reduce `F5XC_CIRCUIT_BREAKER_ENDPOINT_TTL_HOURS`
3. Monitor `f5xc_circuit_breaker_endpoints_cleaned_total` to verify cleanup is running
