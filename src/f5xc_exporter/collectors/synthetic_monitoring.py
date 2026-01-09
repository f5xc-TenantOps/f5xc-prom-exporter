"""Synthetic monitoring metrics collector for F5XC.

Collects synthetic monitor summary metrics from the F5 XC API.
Uses 2 API calls per namespace:
1. GET /global-summary?monitorType=http - HTTP monitor counts
2. GET /global-summary?monitorType=dns - DNS monitor counts
"""

import time
from typing import Any, Optional

import structlog
from prometheus_client import Gauge

from ..cardinality import CardinalityTracker
from ..client import F5XCAPIError, F5XCClient

logger = structlog.get_logger()


class SyntheticMonitoringCollector:
    """Collector for F5XC synthetic monitoring metrics.

    Uses exactly 2 API calls per namespace for scalability:
    - Call 1: global-summary?monitorType=http
    - Call 2: global-summary?monitorType=dns
    """

    def __init__(
        self,
        client: F5XCClient,
        tenant: str,
        cardinality_tracker: Optional[CardinalityTracker] = None,
    ):
        """Initialize synthetic monitoring collector.

        Args:
            client: F5XC API client
            tenant: Tenant name
            cardinality_tracker: Optional cardinality tracker for limit enforcement
        """
        self.client = client
        self.tenant = tenant
        self.cardinality_tracker = cardinality_tracker

        # Namespace labels for all metrics
        ns_labels = ["tenant", "namespace"]

        # HTTP monitor metrics
        self.http_monitors_total = Gauge(
            "f5xc_synthetic_http_monitors_total", "Total number of HTTP synthetic monitors", ns_labels
        )
        self.http_monitors_healthy = Gauge(
            "f5xc_synthetic_http_monitors_healthy", "Number of healthy HTTP synthetic monitors", ns_labels
        )
        self.http_monitors_critical = Gauge(
            "f5xc_synthetic_http_monitors_critical", "Number of critical HTTP synthetic monitors", ns_labels
        )

        # DNS monitor metrics
        self.dns_monitors_total = Gauge(
            "f5xc_synthetic_dns_monitors_total", "Total number of DNS synthetic monitors", ns_labels
        )
        self.dns_monitors_healthy = Gauge(
            "f5xc_synthetic_dns_monitors_healthy", "Number of healthy DNS synthetic monitors", ns_labels
        )
        self.dns_monitors_critical = Gauge(
            "f5xc_synthetic_dns_monitors_critical", "Number of critical DNS synthetic monitors", ns_labels
        )

        # Collection status metrics
        self.collection_success = Gauge(
            "f5xc_synthetic_collection_success",
            "Whether synthetic monitoring collection succeeded (1=success, 0=failure)",
            ["tenant"],
        )
        self.collection_duration = Gauge(
            "f5xc_synthetic_collection_duration_seconds",
            "Time taken to collect synthetic monitoring metrics",
            ["tenant"],
        )

    def collect_metrics(self) -> None:
        """Collect synthetic monitoring metrics from all namespaces."""
        start_time = time.time()

        try:
            logger.info("Collecting synthetic monitoring metrics")
            namespaces = self.client.list_namespaces()

            namespaces_processed = 0
            for namespace in namespaces:
                # Check cardinality limits if tracker is enabled
                if self.cardinality_tracker:
                    if not self.cardinality_tracker.check_namespace_limit(namespace, "synthetic"):
                        continue

                self._collect_http_summary(namespace)
                self._collect_dns_summary(namespace)
                namespaces_processed += 1

            duration = time.time() - start_time
            self.collection_success.labels(tenant=self.tenant).set(1)
            self.collection_duration.labels(tenant=self.tenant).set(duration)

            logger.info(
                "Synthetic monitoring metrics collection successful",
                duration=duration,
                namespace_count=len(namespaces),
                namespaces_processed=namespaces_processed,
            )

            # Update cardinality tracking if enabled
            if self.cardinality_tracker:
                self.cardinality_tracker.update_metric_cardinality(
                    "synthetic", "synthetic_metrics", namespaces_processed
                )

        except Exception as e:
            logger.error("Synthetic monitoring metrics collection failed", error=str(e), exc_info=True)
            self.collection_success.labels(tenant=self.tenant).set(0)
            self.collection_duration.labels(tenant=self.tenant).set(time.time() - start_time)

    def _collect_http_summary(self, namespace: str) -> None:
        """Collect HTTP monitor summary for a namespace."""
        try:
            data = self.client.get_synthetic_summary(namespace, "http")
            self._process_summary(data, namespace, "http")
        except F5XCAPIError as e:
            # 404 means no monitors in this namespace - not an error
            if "404" in str(e):
                logger.debug("No HTTP monitors in namespace", namespace=namespace)
            else:
                logger.warning("Failed to get HTTP monitor summary", namespace=namespace, error=str(e))

    def _collect_dns_summary(self, namespace: str) -> None:
        """Collect DNS monitor summary for a namespace."""
        try:
            data = self.client.get_synthetic_summary(namespace, "dns")
            self._process_summary(data, namespace, "dns")
        except F5XCAPIError as e:
            # 404 means no monitors in this namespace - not an error
            if "404" in str(e):
                logger.debug("No DNS monitors in namespace", namespace=namespace)
            else:
                logger.warning("Failed to get DNS monitor summary", namespace=namespace, error=str(e))

    def _process_summary(self, data: dict[str, Any], namespace: str, monitor_type: str) -> None:
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
            self.http_monitors_total.labels(tenant=self.tenant, namespace=namespace).set(total)
            self.http_monitors_healthy.labels(tenant=self.tenant, namespace=namespace).set(healthy)
            self.http_monitors_critical.labels(tenant=self.tenant, namespace=namespace).set(critical)
        elif monitor_type == "dns":
            self.dns_monitors_total.labels(tenant=self.tenant, namespace=namespace).set(total)
            self.dns_monitors_healthy.labels(tenant=self.tenant, namespace=namespace).set(healthy)
            self.dns_monitors_critical.labels(tenant=self.tenant, namespace=namespace).set(critical)

        logger.debug(
            "Processed synthetic monitor summary",
            namespace=namespace,
            monitor_type=monitor_type,
            total=total,
            healthy=healthy,
            critical=critical,
        )
