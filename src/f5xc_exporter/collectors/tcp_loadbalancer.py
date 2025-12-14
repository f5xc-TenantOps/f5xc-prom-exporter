"""TCP Load Balancer metrics collector for F5XC."""

import time
from typing import Any, Dict

import structlog
from prometheus_client import Gauge

from ..client import F5XCClient, F5XCAPIError

logger = structlog.get_logger()


class TcpLoadBalancerCollector:
    """Collector for F5XC TCP Load Balancer metrics.

    Uses the per-namespace service graph API to collect metrics for all TCP LBs
    across all namespaces. Filters nodes by virtual_host_type to only process
    TCP load balancers.
    """

    # Mapping from F5XC metric types to Prometheus metric attributes
    METRIC_MAP = {
        "TCP_CONNECTION_RATE": "connection_rate",
        "TCP_ERROR_RATE": "error_rate",
        "TCP_ERROR_RATE_CLIENT": "error_rate_client",
        "TCP_ERROR_RATE_UPSTREAM": "error_rate_upstream",
        "TCP_CONNECTION_DURATION": "connection_duration",
        "REQUEST_THROUGHPUT": "request_throughput",
        "RESPONSE_THROUGHPUT": "response_throughput",
        "CLIENT_RTT": "client_rtt",
        "SERVER_RTT": "server_rtt",
    }

    def __init__(self, client: F5XCClient):
        """Initialize TCP load balancer collector."""
        self.client = client

        # Common labels for all metrics
        labels = ["namespace", "load_balancer", "site"]

        # Connection metrics
        self.connection_rate = Gauge(
            "f5xc_tcp_lb_connection_rate",
            "TCP connections per second",
            labels
        )

        self.connection_duration = Gauge(
            "f5xc_tcp_lb_connection_duration_seconds",
            "Average TCP connection duration in seconds",
            labels
        )

        # Error metrics
        self.error_rate = Gauge(
            "f5xc_tcp_lb_error_rate",
            "TCP errors per second",
            labels
        )

        self.error_rate_client = Gauge(
            "f5xc_tcp_lb_error_rate_client",
            "TCP client-side errors per second",
            labels
        )

        self.error_rate_upstream = Gauge(
            "f5xc_tcp_lb_error_rate_upstream",
            "TCP upstream errors per second",
            labels
        )

        # Throughput metrics (bps)
        self.request_throughput = Gauge(
            "f5xc_tcp_lb_request_throughput_bps",
            "Request throughput in bits per second",
            labels
        )

        self.response_throughput = Gauge(
            "f5xc_tcp_lb_response_throughput_bps",
            "Response throughput in bits per second",
            labels
        )

        # RTT metrics (seconds)
        self.client_rtt = Gauge(
            "f5xc_tcp_lb_client_rtt_seconds",
            "Client round-trip time in seconds",
            labels
        )

        self.server_rtt = Gauge(
            "f5xc_tcp_lb_server_rtt_seconds",
            "Server round-trip time in seconds",
            labels
        )

        # Collection status metrics
        self.collection_success = Gauge(
            "f5xc_tcp_lb_collection_success",
            "Whether TCP LB metrics collection succeeded (1=success, 0=failure)",
            []
        )

        self.collection_duration = Gauge(
            "f5xc_tcp_lb_collection_duration_seconds",
            "Time taken to collect TCP LB metrics",
            []
        )

    def collect_metrics(self) -> None:
        """Collect TCP load balancer metrics for all namespaces."""
        start_time = time.time()

        try:
            logger.info("Collecting TCP load balancer metrics")

            # Get all LB metrics from all namespaces (HTTP, TCP, UDP combined)
            data = self.client.get_all_lb_metrics()

            # Process the response
            self._process_response(data)

            # Mark collection as successful
            self.collection_success.set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.set(collection_duration)

            logger.info(
                "TCP LB metrics collection successful",
                duration=collection_duration,
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect TCP LB metrics",
                error=str(e),
                exc_info=True,
            )
            self.collection_success.set(0)
            raise

    def _process_response(self, data: Dict[str, Any]) -> None:
        """Process the API response and update Prometheus metrics."""
        # Response structure: { "data": { "nodes": [...], "edges": [...] } }
        graph_data = data.get("data", {})
        nodes = graph_data.get("nodes", [])

        logger.debug("Processing TCP LB nodes", node_count=len(nodes))

        for node in nodes:
            self._process_node(node)

    def _process_node(self, node: Dict[str, Any]) -> None:
        """Process a single node from the response."""
        # Extract node identity
        node_id = node.get("id", {})

        # Skip nodes that aren't TCP load balancers
        virtual_host_type = node_id.get("virtual_host_type", "")
        if virtual_host_type != "TCP_LOAD_BALANCER":
            return

        namespace = node_id.get("namespace", "unknown")
        vhost = node_id.get("vhost", "unknown")
        site = node_id.get("site", "unknown")

        # Skip nodes without proper identification
        if vhost == "unknown":
            return

        # Extract metrics from node data
        node_data = node.get("data", {})
        metric_data = node_data.get("metric", {})

        # Process downstream metrics (traffic from clients to this LB)
        downstream_metrics = metric_data.get("downstream", [])
        for metric in downstream_metrics:
            self._process_metric(metric, namespace, vhost, site)

    def _process_metric(
        self,
        metric: Dict[str, Any],
        namespace: str,
        load_balancer: str,
        site: str
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

        # Map metric type to Prometheus gauge
        gauge_name = self.METRIC_MAP.get(metric_type)
        if not gauge_name:
            logger.debug("Unhandled metric type", metric_type=metric_type)
            return

        # Get the corresponding gauge and set the value
        gauge = getattr(self, gauge_name, None)
        if gauge:
            gauge.labels(
                namespace=namespace,
                load_balancer=load_balancer,
                site=site
            ).set(value)
