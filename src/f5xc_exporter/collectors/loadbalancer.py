"""Unified Load Balancer metrics collector for F5XC.

Collects HTTP, TCP, and UDP load balancer metrics in a single API call
per namespace, filtering by virtual_host_type.
"""

import time
from typing import Any, Optional

import structlog
from prometheus_client import Gauge

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

    def __init__(self, client: F5XCClient):
        """Initialize unified load balancer collector."""
        self.client = client

        # Common labels for all metrics
        labels = ["namespace", "load_balancer", "site", "direction"]

        # --- HTTP LB Metrics ---
        self.http_request_rate = Gauge(
            "f5xc_http_lb_request_rate",
            "HTTP requests per second",
            labels
        )
        self.http_request_to_origin_rate = Gauge(
            "f5xc_http_lb_request_to_origin_rate",
            "Requests to origin per second",
            labels
        )
        self.http_error_rate = Gauge(
            "f5xc_http_lb_error_rate",
            "HTTP errors per second",
            labels
        )
        self.http_error_rate_4xx = Gauge(
            "f5xc_http_lb_error_rate_4xx",
            "HTTP 4xx client errors per second",
            labels
        )
        self.http_error_rate_5xx = Gauge(
            "f5xc_http_lb_error_rate_5xx",
            "HTTP 5xx server errors per second",
            labels
        )
        self.http_latency = Gauge(
            "f5xc_http_lb_latency_seconds",
            "Average HTTP response latency in seconds",
            labels
        )
        self.http_latency_p50 = Gauge(
            "f5xc_http_lb_latency_p50_seconds",
            "HTTP response latency 50th percentile in seconds",
            labels
        )
        self.http_latency_p90 = Gauge(
            "f5xc_http_lb_latency_p90_seconds",
            "HTTP response latency 90th percentile in seconds",
            labels
        )
        self.http_latency_p99 = Gauge(
            "f5xc_http_lb_latency_p99_seconds",
            "HTTP response latency 99th percentile in seconds",
            labels
        )
        self.http_app_latency = Gauge(
            "f5xc_http_lb_app_latency_seconds",
            "Application processing latency in seconds",
            labels
        )
        self.http_server_data_transfer_time = Gauge(
            "f5xc_http_lb_server_data_transfer_time_seconds",
            "Server data transfer time in seconds",
            labels
        )
        self.http_request_throughput = Gauge(
            "f5xc_http_lb_request_throughput_bps",
            "HTTP request throughput in bits per second",
            labels
        )
        self.http_response_throughput = Gauge(
            "f5xc_http_lb_response_throughput_bps",
            "HTTP response throughput in bits per second",
            labels
        )
        self.http_client_rtt = Gauge(
            "f5xc_http_lb_client_rtt_seconds",
            "HTTP client round-trip time in seconds",
            labels
        )
        self.http_server_rtt = Gauge(
            "f5xc_http_lb_server_rtt_seconds",
            "HTTP server round-trip time in seconds",
            labels
        )

        # --- TCP LB Metrics ---
        self.tcp_connection_rate = Gauge(
            "f5xc_tcp_lb_connection_rate",
            "TCP connections per second",
            labels
        )
        self.tcp_connection_duration = Gauge(
            "f5xc_tcp_lb_connection_duration_seconds",
            "Average TCP connection duration in seconds",
            labels
        )
        self.tcp_error_rate = Gauge(
            "f5xc_tcp_lb_error_rate",
            "TCP errors per second",
            labels
        )
        self.tcp_error_rate_client = Gauge(
            "f5xc_tcp_lb_error_rate_client",
            "TCP client-side errors per second",
            labels
        )
        self.tcp_error_rate_upstream = Gauge(
            "f5xc_tcp_lb_error_rate_upstream",
            "TCP upstream errors per second",
            labels
        )
        self.tcp_request_throughput = Gauge(
            "f5xc_tcp_lb_request_throughput_bps",
            "TCP request throughput in bits per second",
            labels
        )
        self.tcp_response_throughput = Gauge(
            "f5xc_tcp_lb_response_throughput_bps",
            "TCP response throughput in bits per second",
            labels
        )
        self.tcp_client_rtt = Gauge(
            "f5xc_tcp_lb_client_rtt_seconds",
            "TCP client round-trip time in seconds",
            labels
        )
        self.tcp_server_rtt = Gauge(
            "f5xc_tcp_lb_server_rtt_seconds",
            "TCP server round-trip time in seconds",
            labels
        )

        # --- UDP LB Metrics ---
        self.udp_request_throughput = Gauge(
            "f5xc_udp_lb_request_throughput_bps",
            "UDP request throughput in bits per second",
            labels
        )
        self.udp_response_throughput = Gauge(
            "f5xc_udp_lb_response_throughput_bps",
            "UDP response throughput in bits per second",
            labels
        )
        self.udp_client_rtt = Gauge(
            "f5xc_udp_lb_client_rtt_seconds",
            "UDP client round-trip time in seconds",
            labels
        )
        self.udp_server_rtt = Gauge(
            "f5xc_udp_lb_server_rtt_seconds",
            "UDP server round-trip time in seconds",
            labels
        )

        # --- Unified Collection Status Metrics ---
        self.collection_success = Gauge(
            "f5xc_lb_collection_success",
            "Whether LB metrics collection succeeded (1=success, 0=failure)",
            []
        )
        self.collection_duration = Gauge(
            "f5xc_lb_collection_duration_seconds",
            "Time taken to collect all LB metrics",
            []
        )

        # Count metrics by type
        self.http_lb_count = Gauge(
            "f5xc_http_lb_count",
            "Number of HTTP load balancers discovered",
            []
        )
        self.tcp_lb_count = Gauge(
            "f5xc_tcp_lb_count",
            "Number of TCP load balancers discovered",
            []
        )
        self.udp_lb_count = Gauge(
            "f5xc_udp_lb_count",
            "Number of UDP load balancers discovered",
            []
        )

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
            self.http_lb_count.set(counts.get("HTTP_LOAD_BALANCER", 0))
            self.tcp_lb_count.set(counts.get("TCP_LOAD_BALANCER", 0))
            self.udp_lb_count.set(counts.get("UDP_LOAD_BALANCER", 0))

            # Mark collection as successful
            self.collection_success.set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.set(collection_duration)

            logger.info(
                "LB metrics collection successful",
                duration=collection_duration,
                http_lb_count=counts.get("HTTP_LOAD_BALANCER", 0),
                tcp_lb_count=counts.get("TCP_LOAD_BALANCER", 0),
                udp_lb_count=counts.get("UDP_LOAD_BALANCER", 0),
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect LB metrics",
                error=str(e),
                exc_info=True,
            )
            self.collection_success.set(0)
            raise

    def _process_response(self, data: dict[str, Any]) -> dict[str, int]:
        """Process the API response and update Prometheus metrics.

        Returns:
            Dict with counts of each LB type processed
        """
        graph_data = data.get("data", {})
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
        node_id = node.get("id", {})
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

        # Extract metrics from node data
        node_data = node.get("data", {})
        metric_data = node_data.get("metric", {})

        # Process downstream metrics (client -> LB)
        downstream_metrics = metric_data.get("downstream", [])
        for metric in downstream_metrics:
            self._process_metric(metric, namespace, vhost, site, virtual_host_type, "downstream")

        # Process upstream metrics (LB -> origin)
        upstream_metrics = metric_data.get("upstream", [])
        for metric in upstream_metrics:
            self._process_metric(metric, namespace, vhost, site, virtual_host_type, "upstream")

        return virtual_host_type

    def _process_metric(
        self,
        metric: dict[str, Any],
        namespace: str,
        load_balancer: str,
        site: str,
        lb_type: str,
        direction: str
    ) -> None:
        """Process a single metric and update the corresponding Prometheus gauge."""
        metric_type = metric.get("type", "")
        value_data = metric.get("value", {})

        # Get the latest raw value
        raw_values = value_data.get("raw", [])
        if not raw_values:
            return

        # Use the most recent value
        latest = raw_values[-1] if raw_values else {}
        value = latest.get("value")

        if value is None:
            return

        try:
            value = float(value)
        except (ValueError, TypeError):
            logger.warning(
                "Failed to parse metric value",
                metric_type=metric_type,
                value=latest.get("value")
            )
            return

        # Get the gauge for this metric based on LB type
        gauge = self._get_gauge_for_metric(metric_type, lb_type)
        if gauge:
            gauge.labels(
                namespace=namespace,
                load_balancer=load_balancer,
                site=site,
                direction=direction
            ).set(value)

    def _get_gauge_for_metric(self, metric_type: str, lb_type: str) -> Optional[Gauge]:
        """Get the appropriate Prometheus gauge for a metric type and LB type."""
        # HTTP-specific metrics
        if lb_type == "HTTP_LOAD_BALANCER":
            if metric_type in self.HTTP_METRIC_MAP:
                return getattr(self, self.HTTP_METRIC_MAP[metric_type], None)
            # Common metrics for HTTP
            if metric_type == "REQUEST_THROUGHPUT":
                return self.http_request_throughput
            if metric_type == "RESPONSE_THROUGHPUT":
                return self.http_response_throughput
            if metric_type == "CLIENT_RTT":
                return self.http_client_rtt
            if metric_type == "SERVER_RTT":
                return self.http_server_rtt
            if metric_type == "REQUEST_TO_ORIGIN_RATE":
                return self.http_request_to_origin_rate

        # TCP-specific metrics
        elif lb_type == "TCP_LOAD_BALANCER":
            if metric_type in self.TCP_METRIC_MAP:
                return getattr(self, self.TCP_METRIC_MAP[metric_type], None)
            # Common metrics for TCP
            if metric_type == "REQUEST_THROUGHPUT":
                return self.tcp_request_throughput
            if metric_type == "RESPONSE_THROUGHPUT":
                return self.tcp_response_throughput
            if metric_type == "CLIENT_RTT":
                return self.tcp_client_rtt
            if metric_type == "SERVER_RTT":
                return self.tcp_server_rtt

        # UDP-specific metrics
        elif lb_type == "UDP_LOAD_BALANCER":
            # Common metrics for UDP
            if metric_type == "REQUEST_THROUGHPUT":
                return self.udp_request_throughput
            if metric_type == "RESPONSE_THROUGHPUT":
                return self.udp_response_throughput
            if metric_type == "CLIENT_RTT":
                return self.udp_client_rtt
            if metric_type == "SERVER_RTT":
                return self.udp_server_rtt

        return None
