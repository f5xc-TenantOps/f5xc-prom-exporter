"""Synthetic monitoring metrics collector for F5XC.

Collects synthetic monitor summary metrics from the F5 XC API.
Uses 2 API calls per namespace:
1. GET /global-summary?monitorType=http - HTTP monitor counts
2. GET /global-summary?monitorType=dns - DNS monitor counts
"""

import time
from typing import Any

import structlog
from prometheus_client import Gauge

from ..client import F5XCAPIError, F5XCClient

logger = structlog.get_logger()


class SyntheticMonitoringCollector:
    """Collector for F5XC synthetic monitoring metrics.

    Uses exactly 2 API calls per namespace for scalability:
    - Call 1: global-summary?monitorType=http
    - Call 2: global-summary?monitorType=dns
    """

    def __init__(self, client: F5XCClient):
        """Initialize synthetic monitoring collector."""
        self.client = client

        # Namespace labels for all metrics
        ns_labels = ["namespace"]

        # HTTP monitor metrics
        self.http_monitors_total = Gauge(
            "f5xc_synthetic_http_monitors_total",
            "Total number of HTTP synthetic monitors",
            ns_labels
        )
        self.http_monitors_healthy = Gauge(
            "f5xc_synthetic_http_monitors_healthy",
            "Number of healthy HTTP synthetic monitors",
            ns_labels
        )
        self.http_monitors_critical = Gauge(
            "f5xc_synthetic_http_monitors_critical",
            "Number of critical HTTP synthetic monitors",
            ns_labels
        )

        # DNS monitor metrics
        self.dns_monitors_total = Gauge(
            "f5xc_synthetic_dns_monitors_total",
            "Total number of DNS synthetic monitors",
            ns_labels
        )
        self.dns_monitors_healthy = Gauge(
            "f5xc_synthetic_dns_monitors_healthy",
            "Number of healthy DNS synthetic monitors",
            ns_labels
        )
        self.dns_monitors_critical = Gauge(
            "f5xc_synthetic_dns_monitors_critical",
            "Number of critical DNS synthetic monitors",
            ns_labels
        )

        # Collection status metrics (no labels - global)
        self.collection_success = Gauge(
            "f5xc_synthetic_collection_success",
            "Whether synthetic monitoring collection succeeded (1=success, 0=failure)"
        )
        self.collection_duration = Gauge(
            "f5xc_synthetic_collection_duration_seconds",
            "Time taken to collect synthetic monitoring metrics"
        )

    def collect_metrics(self) -> None:
        """Collect synthetic monitoring metrics from all namespaces."""
        start_time = time.time()

        try:
            logger.info("Collecting synthetic monitoring metrics")
            namespaces = self.client.list_namespaces()

            for namespace in namespaces:
                self._collect_http_summary(namespace)
                self._collect_dns_summary(namespace)

            duration = time.time() - start_time
            self.collection_success.set(1)
            self.collection_duration.set(duration)

            logger.info(
                "Synthetic monitoring metrics collection successful",
                duration=duration,
                namespace_count=len(namespaces)
            )

        except Exception as e:
            logger.error(
                "Synthetic monitoring metrics collection failed",
                error=str(e),
                exc_info=True
            )
            self.collection_success.set(0)
            self.collection_duration.set(time.time() - start_time)

    def _collect_http_summary(self, namespace: str) -> None:
        """Collect HTTP monitor summary for a namespace."""
        try:
            data = self.client.get_synthetic_summary(namespace, "http")
            self._process_summary(data, namespace, "http")
        except F5XCAPIError as e:
            # 404 means no monitors in this namespace - not an error
            if "404" in str(e):
                logger.debug(
                    "No HTTP monitors in namespace",
                    namespace=namespace
                )
            else:
                logger.warning(
                    "Failed to get HTTP monitor summary",
                    namespace=namespace,
                    error=str(e)
                )

    def _collect_dns_summary(self, namespace: str) -> None:
        """Collect DNS monitor summary for a namespace."""
        try:
            data = self.client.get_synthetic_summary(namespace, "dns")
            self._process_summary(data, namespace, "dns")
        except F5XCAPIError as e:
            # 404 means no monitors in this namespace - not an error
            if "404" in str(e):
                logger.debug(
                    "No DNS monitors in namespace",
                    namespace=namespace
                )
            else:
                logger.warning(
                    "Failed to get DNS monitor summary",
                    namespace=namespace,
                    error=str(e)
                )

    def _process_summary(
        self,
        data: dict[str, Any],
        namespace: str,
        monitor_type: str
    ) -> None:
        """Process global-summary response and update metrics.

        Response format:
        {
            "critical_monitor_count": 0,
            "number_of_monitors": 2,
            "healthy_monitor_count": 2
        }
        """
        total = data.get("number_of_monitors", 0)
        healthy = data.get("healthy_monitor_count", 0)
        critical = data.get("critical_monitor_count", 0)

        if monitor_type == "http":
            self.http_monitors_total.labels(namespace=namespace).set(total)
            self.http_monitors_healthy.labels(namespace=namespace).set(healthy)
            self.http_monitors_critical.labels(namespace=namespace).set(critical)
        elif monitor_type == "dns":
            self.dns_monitors_total.labels(namespace=namespace).set(total)
            self.dns_monitors_healthy.labels(namespace=namespace).set(healthy)
            self.dns_monitors_critical.labels(namespace=namespace).set(critical)

        logger.debug(
            "Processed synthetic monitor summary",
            namespace=namespace,
            monitor_type=monitor_type,
            total=total,
            healthy=healthy,
            critical=critical
        )
