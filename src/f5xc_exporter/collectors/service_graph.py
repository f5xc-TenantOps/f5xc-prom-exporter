"""Service graph metrics collector for F5XC."""

from typing import Any, Dict, List, Optional
import json
import time

import structlog
from prometheus_client import Gauge

from ..client import F5XCClient, F5XCAPIError

logger = structlog.get_logger()


class ServiceGraphCollector:
    """Collector for F5XC service graph metrics."""

    def __init__(self, client: F5XCClient):
        """Initialize service graph collector."""
        self.client = client

        # Prometheus metrics for HTTP load balancers
        self.http_requests_total = Gauge(
            "f5xc_http_requests_total",
            "Total HTTP requests",
            ["namespace", "load_balancer", "backend", "response_class"]
        )

        self.http_request_duration = Gauge(
            "f5xc_http_request_duration_seconds",
            "HTTP request duration",
            ["namespace", "load_balancer", "backend", "percentile"]
        )

        self.http_request_size_bytes = Gauge(
            "f5xc_http_request_size_bytes",
            "HTTP request size",
            ["namespace", "load_balancer", "backend", "percentile"]
        )

        self.http_response_size_bytes = Gauge(
            "f5xc_http_response_size_bytes",
            "HTTP response size",
            ["namespace", "load_balancer", "backend", "percentile"]
        )

        self.http_connections_active = Gauge(
            "f5xc_http_connections_active",
            "Active HTTP connections",
            ["namespace", "load_balancer", "backend"]
        )

        # Prometheus metrics for TCP load balancers
        self.tcp_connections_total = Gauge(
            "f5xc_tcp_connections_total",
            "Total TCP connections",
            ["namespace", "load_balancer", "backend"]
        )

        self.tcp_connections_active = Gauge(
            "f5xc_tcp_connections_active",
            "Active TCP connections",
            ["namespace", "load_balancer", "backend"]
        )

        self.tcp_bytes_transmitted = Gauge(
            "f5xc_tcp_bytes_transmitted_total",
            "Total TCP bytes transmitted",
            ["namespace", "load_balancer", "backend", "direction"]
        )

        # Collection metrics
        self.service_graph_collection_success = Gauge(
            "f5xc_service_graph_collection_success",
            "Whether service graph collection succeeded",
            ["namespace"]
        )

        self.service_graph_collection_duration = Gauge(
            "f5xc_service_graph_collection_duration_seconds",
            "Time taken to collect service graph metrics",
            ["namespace"]
        )

    def collect_metrics(self, namespace: str = "system") -> None:
        """Collect service graph metrics for the specified namespace."""
        start_time = time.time()

        try:
            logger.info("Collecting service graph metrics", namespace=namespace)

            # Get service graph data
            service_graph_data = self.client.get_service_graph_data(namespace)

            # Process service graph data
            self._process_service_graph_data(service_graph_data, namespace)

            # Mark collection as successful
            self.service_graph_collection_success.labels(namespace=namespace).set(1)

            collection_duration = time.time() - start_time
            self.service_graph_collection_duration.labels(namespace=namespace).set(collection_duration)

            logger.info(
                "Service graph metrics collection successful",
                namespace=namespace,
                duration=collection_duration,
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect service graph metrics",
                namespace=namespace,
                error=str(e),
                exc_info=True,
            )
            self.service_graph_collection_success.labels(namespace=namespace).set(0)
            raise

    def _process_service_graph_data(self, data: Dict[str, Any], namespace: str) -> None:
        """Process service graph data and update metrics."""
        logger.debug("Processing service graph data", namespace=namespace)

        # Process nodes (load balancers and backends)
        nodes = data.get("nodes", [])
        for node in nodes:
            self._process_node(node, namespace)

        # Process edges (connections between services)
        edges = data.get("edges", [])
        for edge in edges:
            self._process_edge(edge, namespace)

    def _process_node(self, node: Dict[str, Any], namespace: str) -> None:
        """Process individual service node."""
        node_type = node.get("type", "unknown")
        node_name = node.get("name", "unknown")
        stats = node.get("stats", {})

        logger.debug(
            "Processing service node",
            namespace=namespace,
            node_type=node_type,
            node_name=node_name,
        )

        if node_type == "load_balancer":
            self._process_load_balancer_stats(stats, namespace, node_name)
        elif node_type == "origin_pool":
            self._process_origin_pool_stats(stats, namespace, node_name)

    def _process_load_balancer_stats(self, stats: Dict[str, Any], namespace: str, lb_name: str) -> None:
        """Process load balancer statistics."""
        # HTTP metrics
        http_stats = stats.get("http", {})
        if http_stats:
            self._process_http_stats(http_stats, namespace, lb_name, "frontend")

        # TCP metrics
        tcp_stats = stats.get("tcp", {})
        if tcp_stats:
            self._process_tcp_stats(tcp_stats, namespace, lb_name, "frontend")

    def _process_origin_pool_stats(self, stats: Dict[str, Any], namespace: str, pool_name: str) -> None:
        """Process origin pool (backend) statistics."""
        # HTTP metrics
        http_stats = stats.get("http", {})
        if http_stats:
            self._process_http_stats(http_stats, namespace, "backend", pool_name)

        # TCP metrics
        tcp_stats = stats.get("tcp", {})
        if tcp_stats:
            self._process_tcp_stats(tcp_stats, namespace, "backend", pool_name)

    def _process_http_stats(self, http_stats: Dict[str, Any], namespace: str, lb_name: str, backend: str) -> None:
        """Process HTTP statistics."""
        # Request counts by response class
        response_classes = http_stats.get("response_classes", {})
        for response_class, count in response_classes.items():
            try:
                self.http_requests_total.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend,
                    response_class=response_class
                ).set(float(count))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse HTTP request count",
                    response_class=response_class,
                    count=count,
                    error=str(e)
                )

        # Request duration percentiles
        duration_percentiles = http_stats.get("request_duration_percentiles", {})
        for percentile, duration in duration_percentiles.items():
            try:
                self.http_request_duration.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend,
                    percentile=percentile
                ).set(float(duration) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse HTTP duration",
                    percentile=percentile,
                    duration=duration,
                    error=str(e)
                )

        # Request size percentiles
        request_size_percentiles = http_stats.get("request_size_percentiles", {})
        for percentile, size in request_size_percentiles.items():
            try:
                self.http_request_size_bytes.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend,
                    percentile=percentile
                ).set(float(size))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse HTTP request size",
                    percentile=percentile,
                    size=size,
                    error=str(e)
                )

        # Response size percentiles
        response_size_percentiles = http_stats.get("response_size_percentiles", {})
        for percentile, size in response_size_percentiles.items():
            try:
                self.http_response_size_bytes.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend,
                    percentile=percentile
                ).set(float(size))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse HTTP response size",
                    percentile=percentile,
                    size=size,
                    error=str(e)
                )

        # Active connections
        active_connections = http_stats.get("active_connections")
        if active_connections is not None:
            try:
                self.http_connections_active.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend
                ).set(float(active_connections))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse HTTP active connections",
                    active_connections=active_connections,
                    error=str(e)
                )

    def _process_tcp_stats(self, tcp_stats: Dict[str, Any], namespace: str, lb_name: str, backend: str) -> None:
        """Process TCP statistics."""
        # Total connections
        total_connections = tcp_stats.get("total_connections")
        if total_connections is not None:
            try:
                self.tcp_connections_total.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend
                ).set(float(total_connections))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse TCP total connections",
                    total_connections=total_connections,
                    error=str(e)
                )

        # Active connections
        active_connections = tcp_stats.get("active_connections")
        if active_connections is not None:
            try:
                self.tcp_connections_active.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend
                ).set(float(active_connections))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse TCP active connections",
                    active_connections=active_connections,
                    error=str(e)
                )

        # Bytes transmitted
        bytes_tx = tcp_stats.get("bytes_transmitted")
        if bytes_tx is not None:
            try:
                self.tcp_bytes_transmitted.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend,
                    direction="tx"
                ).set(float(bytes_tx))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse TCP bytes transmitted",
                    bytes_tx=bytes_tx,
                    error=str(e)
                )

        # Bytes received
        bytes_rx = tcp_stats.get("bytes_received")
        if bytes_rx is not None:
            try:
                self.tcp_bytes_transmitted.labels(
                    namespace=namespace,
                    load_balancer=lb_name,
                    backend=backend,
                    direction="rx"
                ).set(float(bytes_rx))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse TCP bytes received",
                    bytes_rx=bytes_rx,
                    error=str(e)
                )

    def _process_edge(self, edge: Dict[str, Any], namespace: str) -> None:
        """Process service graph edge (connection between services)."""
        # Edges typically contain traffic flow information
        # This could be expanded based on actual F5XC edge data structure
        logger.debug("Processing service graph edge", namespace=namespace, edge_keys=list(edge.keys()))