"""F5 Distributed Cloud API client."""

import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from urllib.parse import urljoin

import requests
import structlog
from prometheus_client import Gauge
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config

logger = structlog.get_logger()


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = 0      # Normal operation
    OPEN = 1        # Failing, reject all requests
    HALF_OPEN = 2   # Testing recovery


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.

    Tracks failures per endpoint and opens circuit when threshold is exceeded.
    After timeout, allows limited requests to test recovery (HALF_OPEN state).

    Thread-safe: All state modifications are protected by an internal lock.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        success_threshold: int = 2
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            timeout_seconds: Seconds to wait before attempting recovery
            success_threshold: Number of successes in HALF_OPEN before closing circuit
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold

        # Track state per endpoint
        self._states: dict[str, CircuitBreakerState] = {}
        self._failure_counts: dict[str, int] = {}
        self._success_counts: dict[str, int] = {}
        self._last_failure_times: dict[str, float] = {}

        # Thread safety lock
        self._lock = threading.Lock()

    def _get_state(self, endpoint: str) -> CircuitBreakerState:
        """Get current state for endpoint."""
        return self._states.get(endpoint, CircuitBreakerState.CLOSED)

    def _set_state(self, endpoint: str, state: CircuitBreakerState) -> None:
        """Set state for endpoint."""
        old_state = self._get_state(endpoint)
        self._states[endpoint] = state

        if old_state != state:
            logger.info(
                "Circuit breaker state changed",
                endpoint=endpoint,
                old_state=old_state.name,
                new_state=state.name
            )

    def is_call_allowed(self, endpoint: str) -> bool:
        """Check if call is allowed for endpoint.

        Thread-safe: Uses internal lock to prevent race conditions during
        state transitions from OPEN to HALF_OPEN.

        Returns:
            True if call should proceed, False if circuit is open
        """
        with self._lock:
            state = self._get_state(endpoint)

            if state == CircuitBreakerState.CLOSED:
                return True

            if state == CircuitBreakerState.OPEN:
                # Check if timeout has elapsed
                last_failure = self._last_failure_times.get(endpoint, 0)
                if time.time() - last_failure >= self.timeout_seconds:
                    # Transition to HALF_OPEN to test recovery
                    self._set_state(endpoint, CircuitBreakerState.HALF_OPEN)
                    self._success_counts[endpoint] = 0
                    logger.info(
                        "Circuit breaker entering HALF_OPEN state",
                        endpoint=endpoint,
                        timeout_seconds=self.timeout_seconds
                    )
                    return True
                else:
                    logger.debug(
                        "Circuit breaker rejecting call",
                        endpoint=endpoint,
                        state="OPEN",
                        seconds_until_retry=int(self.timeout_seconds - (time.time() - last_failure))
                    )
                    return False

            if state == CircuitBreakerState.HALF_OPEN:
                # Allow call in HALF_OPEN state
                return True

            return True

    def record_success(self, endpoint: str) -> None:
        """Record successful call for endpoint.

        Thread-safe: Uses internal lock to prevent race conditions.
        """
        with self._lock:
            state = self._get_state(endpoint)

            if state == CircuitBreakerState.HALF_OPEN:
                # Increment success count in HALF_OPEN state
                self._success_counts[endpoint] = self._success_counts.get(endpoint, 0) + 1

                if self._success_counts[endpoint] >= self.success_threshold:
                    # Enough successes, close the circuit
                    # Log before resetting the count
                    success_count = self._success_counts[endpoint]
                    self._set_state(endpoint, CircuitBreakerState.CLOSED)
                    self._failure_counts[endpoint] = 0
                    self._success_counts[endpoint] = 0
                    logger.info(
                        "Circuit breaker closed after successful recovery",
                        endpoint=endpoint,
                        success_count=success_count
                    )
            else:
                # Reset failure count on success in CLOSED state
                if endpoint in self._failure_counts:
                    self._failure_counts[endpoint] = 0

    def record_failure(self, endpoint: str) -> None:
        """Record failed call for endpoint.

        Thread-safe: Uses internal lock to prevent race conditions.
        """
        with self._lock:
            state = self._get_state(endpoint)

            # Increment failure count
            self._failure_counts[endpoint] = self._failure_counts.get(endpoint, 0) + 1
            self._last_failure_times[endpoint] = time.time()

            if state == CircuitBreakerState.HALF_OPEN:
                # Failure in HALF_OPEN state, reopen circuit
                self._set_state(endpoint, CircuitBreakerState.OPEN)
                logger.warning(
                    "Circuit breaker reopened after failure in HALF_OPEN",
                    endpoint=endpoint
                )
            elif state == CircuitBreakerState.CLOSED:
                # Check if threshold exceeded
                if self._failure_counts[endpoint] >= self.failure_threshold:
                    self._set_state(endpoint, CircuitBreakerState.OPEN)
                    logger.warning(
                        "Circuit breaker opened due to failures",
                        endpoint=endpoint,
                        failure_count=self._failure_counts[endpoint],
                        threshold=self.failure_threshold
                    )

    def get_failure_count(self, endpoint: str) -> int:
        """Get current failure count for endpoint.

        Thread-safe: Uses internal lock to prevent reading inconsistent state.
        """
        with self._lock:
            return self._failure_counts.get(endpoint, 0)

    def get_state_value(self, endpoint: str) -> int:
        """Get numeric state value for metrics.

        Thread-safe: Uses internal lock to prevent reading inconsistent state.
        """
        with self._lock:
            return self._get_state(endpoint).value

    def get_all_endpoints(self) -> list[str]:
        """Get all tracked endpoints.

        Thread-safe: Uses internal lock to prevent reading inconsistent state.
        """
        with self._lock:
            # Collect endpoints from all tracking dictionaries
            all_endpoints: set[str] = set()
            all_endpoints.update(self._states.keys())
            all_endpoints.update(self._failure_counts.keys())
            all_endpoints.update(self._success_counts.keys())
            all_endpoints.update(self._last_failure_times.keys())
            return list(all_endpoints)


class F5XCAPIError(Exception):
    """Base exception for F5XC API errors."""

    pass


class F5XCAuthenticationError(F5XCAPIError):
    """Authentication error."""

    pass


class F5XCRateLimitError(F5XCAPIError):
    """Rate limit error."""

    pass


class F5XCCircuitBreakerOpenError(F5XCAPIError):
    """Circuit breaker is open, call rejected."""
    pass


class F5XCClient:
    """F5 Distributed Cloud API client."""

    def __init__(self, config: Config):
        """Initialize F5XC API client."""
        self.config = config
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=config.f5xc_retry_max_attempts,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set headers
        self.session.headers.update(
            {
                "Authorization": f"APIToken {config.f5xc_access_token}",
                "Content-Type": "application/json",
                "User-Agent": "f5xc-prom-exporter/0.1.0",
            }
        )

        # Store timeout for requests
        self.timeout = config.f5xc_request_timeout

        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.f5xc_circuit_breaker_failure_threshold,
            timeout_seconds=config.f5xc_circuit_breaker_timeout,
            success_threshold=config.f5xc_circuit_breaker_success_threshold
        )

        # Circuit breaker metrics
        self.circuit_breaker_state_metric = Gauge(
            'f5xc_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=open, 2=half_open)',
            ['endpoint']
        )
        self.circuit_breaker_failures_metric = Gauge(
            'f5xc_circuit_breaker_failures',
            'Circuit breaker failure count',
            ['endpoint']
        )

    def _update_circuit_breaker_metrics(self, endpoint: str) -> None:
        """Update circuit breaker metrics for an endpoint."""
        state_value = self.circuit_breaker.get_state_value(endpoint)
        failure_count = self.circuit_breaker.get_failure_count(endpoint)

        self.circuit_breaker_state_metric.labels(endpoint=endpoint).set(state_value)
        self.circuit_breaker_failures_metric.labels(endpoint=endpoint).set(failure_count)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Make HTTP request to F5XC API with circuit breaker protection."""
        # Check circuit breaker before making request
        if not self.circuit_breaker.is_call_allowed(endpoint):
            logger.warning(
                "Circuit breaker rejecting request",
                endpoint=endpoint,
                state="OPEN"
            )
            raise F5XCCircuitBreakerOpenError(
                f"Circuit breaker is open for endpoint: {endpoint}"
            )
        url = urljoin(self.config.tenant_url_str, endpoint)

        logger.info(
            "Making F5XC API request",
            method=method,
            url=url,
            endpoint=endpoint,
        )

        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(
                    "Rate limited by F5XC API",
                    retry_after=retry_after,
                    endpoint=endpoint,
                )
                # Record failure for circuit breaker
                self.circuit_breaker.record_failure(endpoint)
                self._update_circuit_breaker_metrics(endpoint)
                raise F5XCRateLimitError(f"Rate limited. Retry after {retry_after} seconds")

            # Handle authentication errors
            if response.status_code == 401:
                logger.error("Authentication failed", endpoint=endpoint)
                # Don't record auth failures - likely config issue, not API issue
                raise F5XCAuthenticationError("Invalid F5XC access token")

            # Handle other HTTP errors
            response.raise_for_status()

            # Parse JSON response
            data = response.json()

            logger.info(
                "F5XC API request successful",
                endpoint=endpoint,
                status_code=response.status_code,
                response_size=len(response.content),
            )

            # Record success for circuit breaker
            self.circuit_breaker.record_success(endpoint)
            self._update_circuit_breaker_metrics(endpoint)

            return dict(data)

        except F5XCRateLimitError:
            # Re-raise rate limit errors (already recorded failure and updated metrics)
            raise
        except F5XCAuthenticationError:
            # Re-raise auth errors (not recorded as circuit breaker failure)
            raise
        except requests.exceptions.RequestException as e:
            logger.error(
                "F5XC API request failed",
                endpoint=endpoint,
                error=str(e),
                exc_info=True,
            )
            # Record failure for circuit breaker
            self.circuit_breaker.record_failure(endpoint)
            self._update_circuit_breaker_metrics(endpoint)
            raise F5XCAPIError(f"API request failed: {e}") from e

    def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make GET request."""
        return self._make_request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make POST request."""
        return self._make_request("POST", endpoint, **kwargs)

    def list_namespaces(self) -> list[str]:
        """List all namespaces in the tenant.

        Returns:
            List of namespace names (excluding internal ves-io- namespaces)
        """
        endpoint = "/api/web/namespaces"
        response = self.get(endpoint)
        items = response.get("items", [])

        # Filter out internal namespaces:
        # - ves-io-* are F5 internal namespaces
        # - system namespace returns aggregated data for all namespaces (causes duplicates)
        return [
            item.get("name", "")
            for item in items
            if item.get("name") and not item.get("name", "").startswith("ves-io-") and item.get("name") != "system"
        ]

    def get_quota_usage(self, namespace: str = "system") -> dict[str, Any]:
        """Get quota usage for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/quota/usage"
        return self.get(endpoint)

    def get_service_graph_data(self, namespace: str = "system") -> dict[str, Any]:
        """Get service graph data for namespace."""
        endpoint = f"/api/data/namespaces/{namespace}/graph/service"

        # Service graph API requires POST with query parameters
        payload = {
            "agg_type": "avg",
            "namespace": namespace,
            "tenant": self.config.tenant_name,
            "metrics": ["overallHealth"],
            "step": "1m",
            "time": {
                "end": int(time.time()),
                "start": int(time.time() - 3600),  # Last hour
            },
        }

        return self.post(endpoint, json=payload)

    def get_app_firewall_metrics_for_namespace(self, namespace: str, step_seconds: int = 300) -> dict[str, Any]:
        """Get app firewall metrics for a namespace.

        Uses the F5XC API endpoint: /api/data/namespaces/{namespace}/app_firewall/metrics
        Returns metrics grouped by virtual host (load balancer).

        Args:
            namespace: The namespace to query
            step_seconds: Time step for metrics aggregation (default: 300s / 5min)

        Returns:
            Response containing TOTAL_REQUESTS, ATTACKED_REQUESTS, BOT_DETECTION
            grouped by VIRTUAL_HOST
        """
        endpoint = f"/api/data/namespaces/{namespace}/app_firewall/metrics"
        end_time = int(time.time())
        start_time = end_time - step_seconds

        payload = {
            "namespace": namespace,
            "field_selector": ["TOTAL_REQUESTS", "ATTACKED_REQUESTS", "BOT_DETECTION"],
            "group_by": ["VIRTUAL_HOST"],
            "filter": f'NAMESPACE="{namespace}"',
            "start_time": str(start_time),
            "end_time": str(end_time),
            "step": f"{step_seconds}s",
        }

        return self.post(endpoint, json=payload)

    def get_security_event_counts_for_namespace(
        self, namespace: str, event_types: list[str], step_seconds: int = 300
    ) -> dict[str, Any]:
        """Get security event counts at namespace level.

        Uses the F5XC API endpoint: /api/data/namespaces/{namespace}/app_security/events/aggregation
        to get counts of security events by type for the entire namespace.

        Note: Nested sub_aggs (VH_NAME -> SEC_EVENT_TYPE) don't work in this API,
        so we aggregate at namespace level only. Per-LB security totals come from
        the app_firewall/metrics API instead.

        Args:
            namespace: The namespace to query
            event_types: List of sec_event_type values to query
                         (e.g., ["waf_sec_event", "bot_defense_sec_event"])
            step_seconds: Time window for event aggregation (default: 300s / 5min)

        Returns:
            Response containing event counts aggregated by SEC_EVENT_TYPE
        """
        endpoint = f"/api/data/namespaces/{namespace}/app_security/events/aggregation"

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(seconds=step_seconds)

        # Build query filter for event types
        event_filter = "|".join(event_types)

        payload = {
            "namespace": namespace,
            "query": f'{{sec_event_type=~"{event_filter}"}}',
            "aggs": {"by_event_type": {"field_aggregation": {"field": "SEC_EVENT_TYPE", "topk": 100}}},
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }

        return self.post(endpoint, json=payload)

    def get_firewall_logs(self, namespace: str = "system") -> dict[str, Any]:
        """Get firewall logs (security events) for namespace.

        Uses the correct F5XC API endpoint: /api/data/namespaces/{namespace}/firewall_logs
        """
        endpoint = f"/api/data/namespaces/{namespace}/firewall_logs"

        # Firewall logs requires POST with query parameters
        payload = {
            "namespace": namespace,
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time()),
            "agg": {"type": "cardinality", "field": "req_id"},
        }

        return self.post(endpoint, json=payload)

    def get_access_logs_aggregation(self, namespace: str = "system") -> dict[str, Any]:
        """Get aggregated access logs for namespace.

        Uses the correct F5XC API endpoint: /api/data/namespaces/{namespace}/access_logs/aggregation
        """
        endpoint = f"/api/data/namespaces/{namespace}/access_logs/aggregation"

        # Access logs aggregation requires POST with query parameters
        payload = {
            "namespace": namespace,
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time()),
            "aggs": {"response_codes": {"field": "rsp_code_class", "topk": 10}},
        }

        return self.post(endpoint, json=payload)

    def get_synthetic_summary(self, namespace: str, monitor_type: str) -> dict[str, Any]:
        """Get synthetic monitor summary for a namespace.

        Uses F5XC API endpoint:
        GET /api/observability/synthetic_monitor/namespaces/{namespace}/global-summary

        Args:
            namespace: The namespace to query
            monitor_type: Either 'http' or 'dns'

        Returns:
            Response containing:
            - critical_monitor_count: Number of critical monitors
            - number_of_monitors: Total number of monitors
            - healthy_monitor_count: Number of healthy monitors
        """
        endpoint = f"/api/observability/synthetic_monitor/namespaces/{namespace}/global-summary"
        params = {"monitorType": monitor_type}
        return self.get(endpoint, params=params)

    def get_http_lb_metrics(self, step_seconds: int = 120) -> dict[str, Any]:
        """Get HTTP load balancer metrics across all namespaces.

        Uses QueryAllNamespaces API: /api/data/namespaces/system/graph/all_ns_service
        Returns metrics for all HTTP load balancers across all namespaces in a single call.

        Args:
            step_seconds: Time step for metrics aggregation (default: 120s)

        Returns:
            Response containing nodes with HTTP LB metrics grouped by namespace, vhost, and site
        """
        endpoint = "/api/data/namespaces/system/graph/all_ns_service"

        end_time = int(time.time())
        start_time = end_time - step_seconds

        payload = {
            "field_selector": {
                "node": {
                    "metric": {
                        "downstream": [
                            "HTTP_REQUEST_RATE",
                            "HTTP_ERROR_RATE",
                            "HTTP_ERROR_RATE_4XX",
                            "HTTP_ERROR_RATE_5XX",
                            "HTTP_RESPONSE_LATENCY",
                            "HTTP_RESPONSE_LATENCY_PERCENTILE_50",
                            "HTTP_RESPONSE_LATENCY_PERCENTILE_90",
                            "HTTP_RESPONSE_LATENCY_PERCENTILE_99",
                            "HTTP_APP_LATENCY",
                            "HTTP_SERVER_DATA_TRANSFER_TIME",
                            "REQUEST_THROUGHPUT",
                            "RESPONSE_THROUGHPUT",
                            "CLIENT_RTT",
                            "SERVER_RTT",
                            "REQUEST_TO_ORIGIN_RATE",
                        ]
                    }
                }
            },
            "step": f"{step_seconds}s",
            "start_time": str(start_time),
            "end_time": str(end_time),
            "label_filter": [{"label": "LABEL_VHOST_TYPE", "op": "EQ", "value": "HTTP_LOAD_BALANCER"}],
            "group_by": ["NAMESPACE", "VHOST", "SITE"],
        }

        return self.post(endpoint, json=payload)

    def get_tcp_lb_metrics(self, step_seconds: int = 120) -> dict[str, Any]:
        """Get TCP load balancer metrics across all namespaces.

        Uses QueryAllNamespaces API: /api/data/namespaces/system/graph/all_ns_service
        Returns metrics for all TCP load balancers across all namespaces in a single call.

        Args:
            step_seconds: Time step for metrics aggregation (default: 120s)

        Returns:
            Response containing nodes with TCP LB metrics grouped by namespace, vhost, and site
        """
        endpoint = "/api/data/namespaces/system/graph/all_ns_service"

        end_time = int(time.time())
        start_time = end_time - step_seconds

        payload = {
            "field_selector": {
                "node": {
                    "metric": {
                        "downstream": [
                            "TCP_CONNECTION_RATE",
                            "TCP_ERROR_RATE",
                            "TCP_ERROR_RATE_CLIENT",
                            "TCP_ERROR_RATE_UPSTREAM",
                            "TCP_CONNECTION_DURATION",
                            "REQUEST_THROUGHPUT",
                            "RESPONSE_THROUGHPUT",
                            "CLIENT_RTT",
                            "SERVER_RTT",
                        ]
                    }
                }
            },
            "step": f"{step_seconds}s",
            "start_time": str(start_time),
            "end_time": str(end_time),
            "label_filter": [{"label": "LABEL_VHOST_TYPE", "op": "EQ", "value": "TCP_LOAD_BALANCER"}],
            "group_by": ["NAMESPACE", "VHOST", "SITE"],
        }

        return self.post(endpoint, json=payload)

    def get_udp_lb_metrics(self, step_seconds: int = 120) -> dict[str, Any]:
        """Get UDP load balancer metrics across all namespaces.

        Uses QueryAllNamespaces API: /api/data/namespaces/system/graph/all_ns_service
        Returns metrics for all UDP load balancers across all namespaces in a single call.

        Args:
            step_seconds: Time step for metrics aggregation (default: 120s)

        Returns:
            Response containing nodes with UDP LB metrics grouped by namespace, vhost, and site
        """
        endpoint = "/api/data/namespaces/system/graph/all_ns_service"

        end_time = int(time.time())
        start_time = end_time - step_seconds

        payload = {
            "field_selector": {
                "node": {
                    "metric": {"downstream": ["REQUEST_THROUGHPUT", "RESPONSE_THROUGHPUT", "CLIENT_RTT", "SERVER_RTT"]}
                }
            },
            "step": f"{step_seconds}s",
            "start_time": str(start_time),
            "end_time": str(end_time),
            "label_filter": [{"label": "LABEL_VHOST_TYPE", "op": "EQ", "value": "UDP_LOAD_BALANCER"}],
            "group_by": ["NAMESPACE", "VHOST", "SITE"],
        }

        return self.post(endpoint, json=payload)

    def get_all_lb_metrics_for_namespace(self, namespace: str, step_seconds: int = 120) -> dict[str, Any]:
        """Get ALL load balancer metrics (HTTP, TCP, UDP) for a namespace in one call.

        Uses the per-namespace service graph API without LABEL_VHOST_TYPE filter
        to retrieve metrics for all load balancer types. The virtual_host_type
        field in each node's ID indicates the LB type.

        Args:
            namespace: The namespace to query
            step_seconds: Time step for metrics aggregation (default: 120s)

        Returns:
            Service graph response with nodes containing metrics for all LB types
        """
        endpoint = f"/api/data/namespaces/{namespace}/graph/service"

        end_time = int(time.time())
        start_time = end_time - step_seconds

        # Request ALL metrics from all LB types
        all_metrics = [
            # HTTP metrics
            "HTTP_REQUEST_RATE",
            "HTTP_ERROR_RATE",
            "HTTP_ERROR_RATE_4XX",
            "HTTP_ERROR_RATE_5XX",
            "HTTP_RESPONSE_LATENCY",
            "HTTP_RESPONSE_LATENCY_PERCENTILE_50",
            "HTTP_RESPONSE_LATENCY_PERCENTILE_90",
            "HTTP_RESPONSE_LATENCY_PERCENTILE_99",
            "HTTP_APP_LATENCY",
            "HTTP_SERVER_DATA_TRANSFER_TIME",
            # TCP metrics
            "TCP_CONNECTION_RATE",
            "TCP_ERROR_RATE",
            "TCP_ERROR_RATE_CLIENT",
            "TCP_ERROR_RATE_UPSTREAM",
            "TCP_CONNECTION_DURATION",
            # Common metrics (apply to all LB types)
            "REQUEST_THROUGHPUT",
            "RESPONSE_THROUGHPUT",
            "CLIENT_RTT",
            "SERVER_RTT",
            "REQUEST_TO_ORIGIN_RATE",
        ]

        # Health score types to collect for both directions
        healthscore_types = [
            "HEALTHSCORE_OVERALL",
            "HEALTHSCORE_CONNECTIVITY",
            "HEALTHSCORE_PERFORMANCE",
            "HEALTHSCORE_SECURITY",
            "HEALTHSCORE_RELIABILITY",
        ]

        payload = {
            "field_selector": {
                "node": {
                    "metric": {"downstream": all_metrics, "upstream": all_metrics},
                    "healthscore": {"downstream": healthscore_types, "upstream": healthscore_types},
                }
            },
            "step": f"{step_seconds}s",
            "start_time": str(start_time),
            "end_time": str(end_time),
            # NO label_filter - get all LB types
            "group_by": ["VHOST", "SITE", "VIRTUAL_HOST_TYPE"],
        }

        return self.post(endpoint, json=payload)

    def get_all_lb_metrics(self, step_seconds: int = 120) -> dict[str, Any]:
        """Get all LB metrics across all namespaces.

        Iterates through all namespaces and collects LB metrics for each,
        aggregating the results into a single response structure.

        Args:
            step_seconds: Time step for metrics aggregation (default: 120s)

        Returns:
            Aggregated response with nodes from all namespaces, each node
            containing namespace in its ID
        """
        namespaces = self.list_namespaces()
        all_nodes = []

        logger.info("Collecting LB metrics from all namespaces", namespace_count=len(namespaces))

        for namespace in namespaces:
            try:
                response = self.get_all_lb_metrics_for_namespace(namespace, step_seconds)
                nodes = response.get("data", {}).get("nodes", [])

                for node in nodes:
                    # Add namespace to node ID since per-namespace endpoint doesn't include it
                    if "id" in node:
                        node["id"]["namespace"] = namespace
                    all_nodes.append(node)

                logger.debug("Collected LB metrics for namespace", namespace=namespace, node_count=len(nodes))

            except F5XCAPIError as e:
                logger.warning("Failed to get LB metrics for namespace", namespace=namespace, error=str(e))
                continue

        logger.info("LB metrics collection complete", total_nodes=len(all_nodes))

        return {"data": {"nodes": all_nodes, "edges": []}}

    def get_dns_zone_metrics(self, group_by: Optional[list[str]] = None, step_seconds: int = 300) -> dict[str, Any]:
        """Get DNS zone metrics from system namespace.

        Uses F5XC API endpoint: POST /api/data/namespaces/system/dns_zones/metrics
        DNS zones are not namespaced - all data is in the system namespace.

        Args:
            group_by: List of grouping fields. Options:
                      DNS_ZONE_NAME, COUNTRY_CODE, DOMAIN, QUERY_TYPE,
                      RESPONSE_CODE, CLIENT_SUBNET
                      Default: ["DNS_ZONE_NAME"]
            step_seconds: Time step for metrics aggregation (default: 300s / 5min)

        Returns:
            Response containing DNS zone metrics grouped by the specified fields
        """
        endpoint = "/api/data/namespaces/system/dns_zones/metrics"

        if group_by is None:
            group_by = ["DNS_ZONE_NAME"]

        end_time = int(time.time())
        start_time = end_time - step_seconds

        payload = {
            "namespace": "system",
            "group_by": group_by,
            "filter": "",
            "start_time": str(start_time),
            "end_time": str(end_time),
            "step": f"{step_seconds}s",
        }

        return self.post(endpoint, json=payload)

    def get_dns_lb_health_status(self) -> dict[str, Any]:
        """Get DNS Load Balancer health status from system namespace.

        Uses F5XC API endpoint:
        GET /api/data/namespaces/system/dns_load_balancers/health_status

        DNS LBs are not namespaced - all data is in the system namespace.

        Returns:
            Response containing health status for all DNS load balancers
        """
        endpoint = "/api/data/namespaces/system/dns_load_balancers/health_status"
        return self.get(endpoint)

    def get_dns_lb_pool_member_health(self) -> dict[str, Any]:
        """Get DNS Load Balancer pool member health status from system namespace.

        Uses F5XC API endpoint:
        GET /api/data/namespaces/system/dns_load_balancers/pool_members_health_status

        DNS LBs are not namespaced - all data is in the system namespace.

        Returns:
            Response containing health status for all DNS LB pool members
        """
        endpoint = "/api/data/namespaces/system/dns_load_balancers/pool_members_health_status"
        return self.get(endpoint)

    def close(self) -> None:
        """Close the session."""
        self.session.close()
