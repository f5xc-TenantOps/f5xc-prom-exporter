"""Unified Load Balancer metrics collector for F5XC.

Collects HTTP, TCP, and UDP load balancer metrics in a single API call
per namespace, filtering by virtual_host_type.
"""

import time
from typing import Any, Callable, Optional

import structlog
from prometheus_client import Gauge

from ..cardinality import CardinalityTracker
from ..client import F5XCAPIError, F5XCClient

logger = structlog.get_logger()


class LoadBalancerCollector:
    """Unified collector for F5XC Load Balancer metrics (HTTP, TCP, UDP).

    Uses the per-namespace service graph API to collect metrics for all LB types
    across all namespaces in a single collection cycle.
    """

    # Mapping from F5XC metric types to Prometheus metric attributes
    # HTTP metrics
    HTTP_METRIC_MAP = {
        "HTTP_REQUEST_RATE": "http_request_rate",
        "HTTP_ERROR_RATE": "http_error_rate",
        "HTTP_ERROR_RATE_4XX": "http_error_rate_4xx",
        "HTTP_ERROR_RATE_5XX": "http_error_rate_5xx",
        "HTTP_RESPONSE_LATENCY": "http_latency",
        "HTTP_RESPONSE_LATENCY_PERCENTILE_50": "http_latency_p50",
        "HTTP_RESPONSE_LATENCY_PERCENTILE_90": "http_latency_p90",
        "HTTP_RESPONSE_LATENCY_PERCENTILE_99": "http_latency_p99",
        "HTTP_APP_LATENCY": "http_app_latency",
        "HTTP_SERVER_DATA_TRANSFER_TIME": "http_server_data_transfer_time",
    }

    # TCP metrics
    TCP_METRIC_MAP = {
        "TCP_CONNECTION_RATE": "tcp_connection_rate",
        "TCP_ERROR_RATE": "tcp_error_rate",
        "TCP_ERROR_RATE_CLIENT": "tcp_error_rate_client",
        "TCP_ERROR_RATE_UPSTREAM": "tcp_error_rate_upstream",
        "TCP_CONNECTION_DURATION": "tcp_connection_duration",
    }

    # Common metrics (apply to all LB types)
    COMMON_METRIC_MAP = {
        "REQUEST_THROUGHPUT": "request_throughput",
        "RESPONSE_THROUGHPUT": "response_throughput",
        "CLIENT_RTT": "client_rtt",
        "SERVER_RTT": "server_rtt",
        "REQUEST_TO_ORIGIN_RATE": "request_to_origin_rate",
    }

    # Healthscore mapping (apply to all LB types)
    HEALTHSCORE_MAP = {
        "HEALTHSCORE_OVERALL": "healthscore_overall",
        "HEALTHSCORE_CONNECTIVITY": "healthscore_connectivity",
        "HEALTHSCORE_PERFORMANCE": "healthscore_performance",
        "HEALTHSCORE_SECURITY": "healthscore_security",
        "HEALTHSCORE_RELIABILITY": "healthscore_reliability",
    }

    def __init__(
        self,
        client: F5XCClient,
        tenant: str,
        cardinality_tracker: Optional[CardinalityTracker] = None,
    ):
        """Initialize unified load balancer collector.

        Args:
            client: F5XC API client
            tenant: Tenant name
            cardinality_tracker: Optional cardinality tracker for limit enforcement
        """
        self.client = client
        self.tenant = tenant
        self.cardinality_tracker = cardinality_tracker

        # Common labels for all metrics
        labels = ["tenant", "namespace", "load_balancer", "site", "direction"]

        # Define metric specifications: (attr_suffix, metric_suffix, description)
        # HTTP-specific metrics
        http_metrics = [
            ("request_rate", "request_rate", "requests per second"),
            ("request_to_origin_rate", "request_to_origin_rate", "requests to origin per second"),
            ("error_rate", "error_rate", "errors per second"),
            ("error_rate_4xx", "error_rate_4xx", "4xx client errors per second"),
            ("error_rate_5xx", "error_rate_5xx", "5xx server errors per second"),
            ("latency", "latency_seconds", "average response latency in seconds"),
            ("latency_p50", "latency_p50_seconds", "response latency 50th percentile in seconds"),
            ("latency_p90", "latency_p90_seconds", "response latency 90th percentile in seconds"),
            ("latency_p99", "latency_p99_seconds", "response latency 99th percentile in seconds"),
            ("app_latency", "app_latency_seconds", "application processing latency in seconds"),
            ("server_data_transfer_time", "server_data_transfer_time_seconds", "server data transfer time in seconds"),
        ]

        # TCP-specific metrics
        tcp_metrics = [
            ("connection_rate", "connection_rate", "connections per second"),
            ("connection_duration", "connection_duration_seconds", "average connection duration in seconds"),
            ("error_rate", "error_rate", "errors per second"),
            ("error_rate_client", "error_rate_client", "client-side errors per second"),
            ("error_rate_upstream", "error_rate_upstream", "upstream errors per second"),
        ]

        # Common metrics for all LB types
        common_metrics = [
            ("request_throughput", "request_throughput_bps", "request throughput in bits per second"),
            ("response_throughput", "response_throughput_bps", "response throughput in bits per second"),
            ("client_rtt", "client_rtt_seconds", "client round-trip time in seconds"),
            ("server_rtt", "server_rtt_seconds", "server round-trip time in seconds"),
        ]

        # Healthscore metrics (common to all LB types)
        healthscore_metrics = [
            ("healthscore_overall", "healthscore_overall", "overall health score (0-100)"),
            ("healthscore_connectivity", "healthscore_connectivity", "connectivity health score (0-100)"),
            ("healthscore_performance", "healthscore_performance", "performance health score (0-100)"),
            ("healthscore_security", "healthscore_security", "security health score (0-100)"),
            ("healthscore_reliability", "healthscore_reliability", "reliability health score (0-100)"),
        ]

        # Generate HTTP LB metrics
        for attr_suffix, metric_suffix, desc in http_metrics + common_metrics + healthscore_metrics:
            setattr(self, f"http_{attr_suffix}", Gauge(f"f5xc_http_lb_{metric_suffix}", f"HTTP LB {desc}", labels))

        # Generate TCP LB metrics
        for attr_suffix, metric_suffix, desc in tcp_metrics + common_metrics + healthscore_metrics:
            setattr(self, f"tcp_{attr_suffix}", Gauge(f"f5xc_tcp_lb_{metric_suffix}", f"TCP LB {desc}", labels))

        # Generate UDP LB metrics (only common + healthscore)
        for attr_suffix, metric_suffix, desc in common_metrics + healthscore_metrics:
            setattr(self, f"udp_{attr_suffix}", Gauge(f"f5xc_udp_lb_{metric_suffix}", f"UDP LB {desc}", labels))

        # --- Unified Collection Status Metrics ---
        self.collection_success = Gauge(
            "f5xc_lb_collection_success", "Whether LB metrics collection succeeded (1=success, 0=failure)", ["tenant"]
        )
        self.collection_duration = Gauge(
            "f5xc_lb_collection_duration_seconds", "Time taken to collect all LB metrics", ["tenant"]
        )

        # Count metrics by type
        self.http_lb_count = Gauge("f5xc_http_lb_count", "Number of HTTP load balancers discovered", ["tenant"])
        self.tcp_lb_count = Gauge("f5xc_tcp_lb_count", "Number of TCP load balancers discovered", ["tenant"])
        self.udp_lb_count = Gauge("f5xc_udp_lb_count", "Number of UDP load balancers discovered", ["tenant"])

    def collect_metrics(self) -> None:
        """Collect all load balancer metrics in a single pass."""
        start_time = time.time()

        try:
            logger.info("Collecting load balancer metrics (HTTP, TCP, UDP)")

            # Get all LB metrics from all namespaces in one call
            data = self.client.get_all_lb_metrics()

            # Process the response
            counts = self._process_response(data)

            # Update count metrics
            self.http_lb_count.labels(tenant=self.tenant).set(counts.get("HTTP_LOAD_BALANCER", 0))
            self.tcp_lb_count.labels(tenant=self.tenant).set(counts.get("TCP_LOAD_BALANCER", 0))
            self.udp_lb_count.labels(tenant=self.tenant).set(counts.get("UDP_LOAD_BALANCER", 0))

            # Mark collection as successful
            self.collection_success.labels(tenant=self.tenant).set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.labels(tenant=self.tenant).set(collection_duration)

            logger.info(
                "LB metrics collection successful",
                duration=collection_duration,
                http_lb_count=counts.get("HTTP_LOAD_BALANCER", 0),
                tcp_lb_count=counts.get("TCP_LOAD_BALANCER", 0),
                udp_lb_count=counts.get("UDP_LOAD_BALANCER", 0),
            )

            # Update cardinality tracking if enabled
            if self.cardinality_tracker:
                # Track cardinality for each LB type
                self.cardinality_tracker.update_metric_cardinality(
                    "loadbalancer",
                    "http_lb_metrics",
                    counts.get("HTTP_LOAD_BALANCER", 0),
                )
                self.cardinality_tracker.update_metric_cardinality(
                    "loadbalancer",
                    "tcp_lb_metrics",
                    counts.get("TCP_LOAD_BALANCER", 0),
                )
                self.cardinality_tracker.update_metric_cardinality(
                    "loadbalancer",
                    "udp_lb_metrics",
                    counts.get("UDP_LOAD_BALANCER", 0),
                )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect LB metrics",
                error=str(e),
                exc_info=True,
            )
            self.collection_success.labels(tenant=self.tenant).set(0)
            raise

    def _process_response(self, data: dict[str, Any]) -> dict[str, int]:
        """Process the API response and update Prometheus metrics.

        Returns:
            Dict with counts of each LB type processed
        """
        # Handle null values from API responses
        graph_data = data.get("data") or {}
        nodes = graph_data.get("nodes", [])

        logger.debug("Processing LB nodes", node_count=len(nodes))

        counts: dict[str, int] = {}

        for node in nodes:
            lb_type = self._process_node(node)
            if lb_type:
                counts[lb_type] = counts.get(lb_type, 0) + 1

        return counts

    def _process_node(self, node: dict[str, Any]) -> Optional[str]:
        """Process a single node from the response.

        Returns:
            The virtual_host_type if processed, None if skipped
        """
        # Handle null values from API responses
        node_id = node.get("id") or {}
        virtual_host_type: str = node_id.get("virtual_host_type", "")

        # Skip nodes without a recognized LB type
        if virtual_host_type not in ("HTTP_LOAD_BALANCER", "TCP_LOAD_BALANCER", "UDP_LOAD_BALANCER"):
            return None

        namespace = node_id.get("namespace", "unknown")
        vhost = node_id.get("vhost", "unknown")
        site = node_id.get("site", "unknown")

        # Skip nodes without proper identification
        if vhost == "unknown":
            return None

        # Check cardinality limits if tracker is enabled
        if self.cardinality_tracker:
            # Check namespace limit
            if not self.cardinality_tracker.check_namespace_limit(namespace, "loadbalancer"):
                return None

            # Check load balancer limit per namespace
            if not self.cardinality_tracker.check_load_balancer_limit(namespace, vhost, "loadbalancer"):
                return None

        # Extract metrics from node data
        # Handle null values from API responses - use "or {}" to convert None to empty dict
        node_data = node.get("data") or {}
        metric_data = node_data.get("metric") or {}

        # Process downstream metrics (client -> LB)
        downstream_metrics = metric_data.get("downstream", [])
        for metric in downstream_metrics:
            self._process_metric(metric, namespace, vhost, site, virtual_host_type, "downstream")

        # Process upstream metrics (LB -> origin)
        upstream_metrics = metric_data.get("upstream", [])
        for metric in upstream_metrics:
            self._process_metric(metric, namespace, vhost, site, virtual_host_type, "upstream")

        # Process healthscore data - handle null values from API
        healthscore_data = node_data.get("healthscore") or {}

        # Process downstream healthscores (client -> LB)
        downstream_healthscores = healthscore_data.get("downstream", [])
        for healthscore in downstream_healthscores:
            self._process_healthscore(healthscore, namespace, vhost, site, virtual_host_type, "downstream")

        # Process upstream healthscores (LB -> origin)
        upstream_healthscores = healthscore_data.get("upstream", [])
        for healthscore in upstream_healthscores:
            self._process_healthscore(healthscore, namespace, vhost, site, virtual_host_type, "upstream")

        return virtual_host_type

    def _process_datapoint(
        self,
        data: dict[str, Any],
        namespace: str,
        load_balancer: str,
        site: str,
        lb_type: str,
        direction: str,
        gauge_lookup_fn: Callable[[str, str], Optional[Gauge]],
        data_type_name: str,
    ) -> None:
        """Process a single metric or healthscore datapoint.

        Args:
            data: The metric or healthscore data dict
            namespace: Namespace label value
            load_balancer: Load balancer name label value
            site: Site label value
            lb_type: Load balancer type (HTTP_LOAD_BALANCER, etc.)
            direction: Direction label value (upstream/downstream)
            gauge_lookup_fn: Callable to get the gauge (e.g., self._get_gauge_for_metric)
            data_type_name: Name for logging (e.g., "metric", "healthscore")
        """
        data_type = data.get("type", "")
        # Handle null values from API responses
        value_data = data.get("value") or {}

        raw_values = value_data.get("raw", [])
        if not raw_values:
            return

        latest = raw_values[-1]
        value = latest.get("value")

        if value is None:
            return

        try:
            value = float(value)
        except (ValueError, TypeError):
            logger.warning(
                "Failed to parse datapoint value",
                data_type_name=data_type_name,
                type=data_type,
                value=latest.get("value"),
            )
            return

        gauge = gauge_lookup_fn(data_type, lb_type)
        if gauge:
            gauge.labels(
                tenant=self.tenant, namespace=namespace, load_balancer=load_balancer, site=site, direction=direction
            ).set(value)

    def _process_metric(
        self, metric: dict[str, Any], namespace: str, load_balancer: str, site: str, lb_type: str, direction: str
    ) -> None:
        """Process a single metric and update the corresponding Prometheus gauge."""
        self._process_datapoint(
            metric, namespace, load_balancer, site, lb_type, direction, self._get_gauge_for_metric, "metric"
        )

    def _get_gauge_for_metric(self, metric_type: str, lb_type: str) -> Optional[Gauge]:
        """Get the appropriate Prometheus gauge for a metric type and LB type."""
        # HTTP-specific metrics
        if lb_type == "HTTP_LOAD_BALANCER":
            if metric_type in self.HTTP_METRIC_MAP:
                return getattr(self, self.HTTP_METRIC_MAP[metric_type], None)
            # Common metrics for HTTP
            if metric_type == "REQUEST_THROUGHPUT":
                return self.http_request_throughput  # type: ignore[attr-defined,no-any-return]
            if metric_type == "RESPONSE_THROUGHPUT":
                return self.http_response_throughput  # type: ignore[attr-defined,no-any-return]
            if metric_type == "CLIENT_RTT":
                return self.http_client_rtt  # type: ignore[attr-defined,no-any-return]
            if metric_type == "SERVER_RTT":
                return self.http_server_rtt  # type: ignore[attr-defined,no-any-return]
            if metric_type == "REQUEST_TO_ORIGIN_RATE":
                return self.http_request_to_origin_rate  # type: ignore[attr-defined,no-any-return]

        # TCP-specific metrics
        elif lb_type == "TCP_LOAD_BALANCER":
            if metric_type in self.TCP_METRIC_MAP:
                return getattr(self, self.TCP_METRIC_MAP[metric_type], None)
            # Common metrics for TCP
            if metric_type == "REQUEST_THROUGHPUT":
                return self.tcp_request_throughput  # type: ignore[attr-defined,no-any-return]
            if metric_type == "RESPONSE_THROUGHPUT":
                return self.tcp_response_throughput  # type: ignore[attr-defined,no-any-return]
            if metric_type == "CLIENT_RTT":
                return self.tcp_client_rtt  # type: ignore[attr-defined,no-any-return]
            if metric_type == "SERVER_RTT":
                return self.tcp_server_rtt  # type: ignore[attr-defined,no-any-return]

        # UDP-specific metrics
        elif lb_type == "UDP_LOAD_BALANCER":
            # Common metrics for UDP
            if metric_type == "REQUEST_THROUGHPUT":
                return self.udp_request_throughput  # type: ignore[attr-defined,no-any-return]
            if metric_type == "RESPONSE_THROUGHPUT":
                return self.udp_response_throughput  # type: ignore[attr-defined,no-any-return]
            if metric_type == "CLIENT_RTT":
                return self.udp_client_rtt  # type: ignore[attr-defined,no-any-return]
            if metric_type == "SERVER_RTT":
                return self.udp_server_rtt  # type: ignore[attr-defined,no-any-return]

        return None

    def _process_healthscore(
        self, healthscore: dict[str, Any], namespace: str, load_balancer: str, site: str, lb_type: str, direction: str
    ) -> None:
        """Process a single healthscore and update the corresponding Prometheus gauge."""
        self._process_datapoint(
            healthscore,
            namespace,
            load_balancer,
            site,
            lb_type,
            direction,
            self._get_gauge_for_healthscore,
            "healthscore",
        )

    def _get_gauge_for_healthscore(self, healthscore_type: str, lb_type: str) -> Optional[Gauge]:
        """Get the appropriate Prometheus gauge for a healthscore type and LB type."""
        if healthscore_type not in self.HEALTHSCORE_MAP:
            return None

        healthscore_attr = self.HEALTHSCORE_MAP[healthscore_type]

        # HTTP healthscores
        if lb_type == "HTTP_LOAD_BALANCER":
            return getattr(self, f"http_{healthscore_attr}", None)

        # TCP healthscores
        elif lb_type == "TCP_LOAD_BALANCER":
            return getattr(self, f"tcp_{healthscore_attr}", None)

        # UDP healthscores
        elif lb_type == "UDP_LOAD_BALANCER":
            return getattr(self, f"udp_{healthscore_attr}", None)

        return None
