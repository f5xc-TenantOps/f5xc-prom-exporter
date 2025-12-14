"""HTTP Load Balancer metrics collector for F5XC."""

import time
from typing import Any, Dict

import structlog
from prometheus_client import Gauge

from ..client import F5XCClient, F5XCAPIError

logger = structlog.get_logger()


class HttpLoadBalancerCollector:
    """Collector for F5XC HTTP Load Balancer metrics.

    Uses the QueryAllNamespaces API to collect metrics for all HTTP LBs
    across all namespaces in a single API call.
    """

    # Mapping from F5XC metric types to Prometheus metric attributes
    METRIC_MAP = {
        "HTTP_REQUEST_RATE": "request_rate",
        "HTTP_ERROR_RATE": "error_rate",
        "HTTP_ERROR_RATE_4XX": "error_rate_4xx",
        "HTTP_ERROR_RATE_5XX": "error_rate_5xx",
        "HTTP_RESPONSE_LATENCY": "latency",
        "HTTP_RESPONSE_LATENCY_PERCENTILE_50": "latency_p50",
        "HTTP_RESPONSE_LATENCY_PERCENTILE_90": "latency_p90",
        "HTTP_RESPONSE_LATENCY_PERCENTILE_99": "latency_p99",
        "HTTP_APP_LATENCY": "app_latency",
        "HTTP_SERVER_DATA_TRANSFER_TIME": "server_data_transfer_time",
        "REQUEST_THROUGHPUT": "request_throughput",
        "RESPONSE_THROUGHPUT": "response_throughput",
        "CLIENT_RTT": "client_rtt",
        "SERVER_RTT": "server_rtt",
        "REQUEST_TO_ORIGIN_RATE": "request_to_origin_rate",
    }

    def __init__(self, client: F5XCClient):
        """Initialize HTTP load balancer collector."""
        self.client = client

        # Common labels for all metrics
        labels = ["namespace", "load_balancer", "site"]

        # Request metrics
        self.request_rate = Gauge(
            "f5xc_http_lb_request_rate",
            "HTTP requests per second",
            labels
        )

        self.request_to_origin_rate = Gauge(
            "f5xc_http_lb_request_to_origin_rate",
            "Requests to origin per second",
            labels
        )

        # Error metrics
        self.error_rate = Gauge(
            "f5xc_http_lb_error_rate",
            "HTTP errors per second",
            labels
        )

        self.error_rate_4xx = Gauge(
            "f5xc_http_lb_error_rate_4xx",
            "HTTP 4xx client errors per second",
            labels
        )

        self.error_rate_5xx = Gauge(
            "f5xc_http_lb_error_rate_5xx",
            "HTTP 5xx server errors per second",
            labels
        )

        # Latency metrics (seconds)
        self.latency = Gauge(
            "f5xc_http_lb_latency_seconds",
            "Average HTTP response latency in seconds",
            labels
        )

        self.latency_p50 = Gauge(
            "f5xc_http_lb_latency_p50_seconds",
            "HTTP response latency 50th percentile in seconds",
            labels
        )

        self.latency_p90 = Gauge(
            "f5xc_http_lb_latency_p90_seconds",
            "HTTP response latency 90th percentile in seconds",
            labels
        )

        self.latency_p99 = Gauge(
            "f5xc_http_lb_latency_p99_seconds",
            "HTTP response latency 99th percentile in seconds",
            labels
        )

        self.app_latency = Gauge(
            "f5xc_http_lb_app_latency_seconds",
            "Application processing latency in seconds",
            labels
        )

        self.server_data_transfer_time = Gauge(
            "f5xc_http_lb_server_data_transfer_time_seconds",
            "Server data transfer time in seconds",
            labels
        )

        # Throughput metrics (bps)
        self.request_throughput = Gauge(
            "f5xc_http_lb_request_throughput_bps",
            "Request throughput in bits per second",
            labels
        )

        self.response_throughput = Gauge(
            "f5xc_http_lb_response_throughput_bps",
            "Response throughput in bits per second",
            labels
        )

        # RTT metrics (seconds)
        self.client_rtt = Gauge(
            "f5xc_http_lb_client_rtt_seconds",
            "Client round-trip time in seconds",
            labels
        )

        self.server_rtt = Gauge(
            "f5xc_http_lb_server_rtt_seconds",
            "Server round-trip time in seconds",
            labels
        )

        # Collection status metrics
        self.collection_success = Gauge(
            "f5xc_http_lb_collection_success",
            "Whether HTTP LB metrics collection succeeded (1=success, 0=failure)",
            []
        )

        self.collection_duration = Gauge(
            "f5xc_http_lb_collection_duration_seconds",
            "Time taken to collect HTTP LB metrics",
            []
        )

    def collect_metrics(self) -> None:
        """Collect HTTP load balancer metrics for all namespaces."""
        start_time = time.time()

        try:
            logger.info("Collecting HTTP load balancer metrics")

            # Get HTTP LB metrics from all namespaces
            data = self.client.get_http_lb_metrics()

            # Process the response
            self._process_response(data)

            # Mark collection as successful
            self.collection_success.set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.set(collection_duration)

            logger.info(
                "HTTP LB metrics collection successful",
                duration=collection_duration,
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect HTTP LB metrics",
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

        logger.debug("Processing HTTP LB nodes", node_count=len(nodes))

        for node in nodes:
            self._process_node(node)

    def _process_node(self, node: Dict[str, Any]) -> None:
        """Process a single node from the response."""
        # Extract node identity
        node_id = node.get("id", {})
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
