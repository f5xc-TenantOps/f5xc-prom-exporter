"""DNS metrics collector for F5XC.

Collects DNS zone query metrics and DNS Load Balancer health status.
All DNS resources are in the system namespace (not namespaced).
"""

import time
from typing import Any, Optional

import structlog
from prometheus_client import Gauge

from ..cardinality import CardinalityTracker
from ..client import F5XCAPIError, F5XCClient

logger = structlog.get_logger()


class DNSCollector:
    """Collector for F5XC DNS metrics.

    Collects metrics from the system namespace (DNS is not namespaced):
    - DNS Zone query metrics (grouped by zone name)
    - DNS Load Balancer health status
    - DNS LB pool member health status

    Uses 3 API calls per collection cycle.
    """

    def __init__(
        self,
        client: F5XCClient,
        tenant: str,
        cardinality_tracker: Optional[CardinalityTracker] = None,
    ):
        """Initialize DNS collector.

        Args:
            client: F5XC API client
            tenant: Tenant name
            cardinality_tracker: Optional cardinality tracker for limit enforcement
        """
        self.client = client
        self.tenant = tenant
        self.cardinality_tracker = cardinality_tracker

        # --- DNS Zone Metrics ---
        zone_labels = ["tenant", "zone"]
        self.zone_query_count = Gauge("f5xc_dns_zone_query_count", "Total DNS queries per zone", zone_labels)

        # --- DNS Load Balancer Health Metrics ---
        lb_labels = ["tenant", "dns_lb"]
        self.dns_lb_health = Gauge(
            "f5xc_dns_lb_health_status", "DNS Load Balancer health status (1=healthy, 0=unhealthy)", lb_labels
        )

        pool_labels = ["tenant", "dns_lb", "pool", "member"]
        self.dns_lb_pool_member_health = Gauge(
            "f5xc_dns_lb_pool_member_health", "DNS LB pool member health status (1=healthy, 0=unhealthy)", pool_labels
        )

        # --- Collection Status Metrics ---
        self.collection_success = Gauge(
            "f5xc_dns_collection_success", "Whether DNS metrics collection succeeded (1=success, 0=failure)", ["tenant"]
        )
        self.collection_duration = Gauge(
            "f5xc_dns_collection_duration_seconds", "Time taken to collect DNS metrics", ["tenant"]
        )
        self.zone_count = Gauge("f5xc_dns_zone_count", "Number of DNS zones discovered", ["tenant"])
        self.dns_lb_count = Gauge("f5xc_dns_lb_count", "Number of DNS load balancers discovered", ["tenant"])

    def collect_metrics(self) -> None:
        """Collect all DNS metrics."""
        start_time = time.time()

        try:
            logger.info("Collecting DNS metrics")

            # Collect DNS zone metrics
            zone_count = self._collect_zone_metrics()

            # Collect DNS LB health status
            lb_count = self._collect_lb_health()

            # Collect DNS LB pool member health
            self._collect_pool_member_health()

            # Update count metrics
            self.zone_count.labels(tenant=self.tenant).set(zone_count)
            self.dns_lb_count.labels(tenant=self.tenant).set(lb_count)

            # Mark collection as successful
            self.collection_success.labels(tenant=self.tenant).set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.labels(tenant=self.tenant).set(collection_duration)

            logger.info(
                "DNS metrics collection successful",
                duration=collection_duration,
                zone_count=zone_count,
                lb_count=lb_count,
            )

            # Update cardinality tracking if enabled
            if self.cardinality_tracker:
                self.cardinality_tracker.update_metric_cardinality("dns", "dns_zone_metrics", zone_count)
                self.cardinality_tracker.update_metric_cardinality("dns", "dns_lb_metrics", lb_count)

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect DNS metrics",
                error=str(e),
                exc_info=True,
            )
            self.collection_success.labels(tenant=self.tenant).set(0)
            raise

    def _collect_zone_metrics(self) -> int:
        """Collect DNS zone query metrics.

        Returns:
            Number of zones discovered
        """
        try:
            response = self.client.get_dns_zone_metrics(group_by=["DNS_ZONE_NAME"])
            return self._process_zone_metrics(response)
        except F5XCAPIError as e:
            logger.warning("Failed to get DNS zone metrics", error=str(e))
            return 0

    def _collect_lb_health(self) -> int:
        """Collect DNS Load Balancer health status.

        Returns:
            Number of DNS LBs discovered
        """
        try:
            response = self.client.get_dns_lb_health_status()
            return self._process_lb_health(response)
        except F5XCAPIError as e:
            logger.warning("Failed to get DNS LB health status", error=str(e))
            return 0

    def _collect_pool_member_health(self) -> None:
        """Collect DNS LB pool member health status."""
        try:
            response = self.client.get_dns_lb_pool_member_health()
            self._process_pool_member_health(response)
        except F5XCAPIError as e:
            logger.warning("Failed to get DNS LB pool member health", error=str(e))

    def _process_zone_metrics(self, data: dict[str, Any]) -> int:
        """Process DNS zone metrics response.

        Response structure (from HAR analysis):
        {
            "data": [
                {
                    "labels": {"DNS_ZONE_NAME": "example.com"},
                    "value": [{"timestamp": 1765850829, "value": "1049"}]
                }
            ],
            "step": "1440m",
            "total_hits": "10"
        }

        Returns:
            Number of zones processed
        """
        zone_data = data.get("data") or []
        zone_count = 0

        for item in zone_data:
            labels = item.get("labels") or {}
            zone_name = labels.get("DNS_ZONE_NAME", "unknown")

            if zone_name == "unknown":
                continue

            # Check cardinality limits if tracker is enabled
            if self.cardinality_tracker:
                if not self.cardinality_tracker.check_dns_zone_limit(zone_name, "dns"):
                    continue

            # Get the latest value
            values = item.get("value") or []
            if not values:
                continue

            latest = values[-1] if values else {}
            value_str = latest.get("value", "0")

            try:
                value = float(value_str)
                self.zone_query_count.labels(tenant=self.tenant, zone=zone_name).set(value)
                zone_count += 1
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse DNS zone metric value", zone=zone_name, value=value_str, error=str(e))

        return zone_count

    def _process_lb_health(self, data: dict[str, Any]) -> int:
        """Process DNS Load Balancer health status response.

        Response structure (from OAS analysis):
        {
            "dns_lb_pools_status_summary": [...],
            "items": [
                {
                    "name": "dns-lb-name",
                    "namespace": "system",
                    "health_status": "HEALTHY" | "UNHEALTHY" | "DEGRADED"
                }
            ]
        }

        Returns:
            Number of DNS LBs processed
        """
        items = data.get("items") or []
        lb_count = 0

        for item in items:
            lb_name = item.get("name", "unknown")

            if lb_name == "unknown":
                continue

            health_status = item.get("health_status", "UNKNOWN")
            # Convert to numeric: HEALTHY=1, anything else=0
            health_value = 1.0 if health_status == "HEALTHY" else 0.0

            self.dns_lb_health.labels(tenant=self.tenant, dns_lb=lb_name).set(health_value)
            lb_count += 1

            logger.debug("DNS LB health status", dns_lb=lb_name, health_status=health_status)

        return lb_count

    def _process_pool_member_health(self, data: dict[str, Any]) -> None:
        """Process DNS LB pool member health status response.

        Response structure (from OAS analysis):
        {
            "items": [
                {
                    "dns_lb_name": "dns-lb-name",
                    "pool_name": "pool-name",
                    "member_address": "10.0.0.1",
                    "health_status": "HEALTHY" | "UNHEALTHY"
                }
            ]
        }
        """
        items = data.get("items") or []

        for item in items:
            dns_lb = item.get("dns_lb_name", "unknown")
            pool = item.get("pool_name", "unknown")
            member = item.get("member_address", "unknown")

            if dns_lb == "unknown" or pool == "unknown":
                continue

            health_status = item.get("health_status", "UNKNOWN")
            # Convert to numeric: HEALTHY=1, anything else=0
            health_value = 1.0 if health_status == "HEALTHY" else 0.0

            self.dns_lb_pool_member_health.labels(tenant=self.tenant, dns_lb=dns_lb, pool=pool, member=member).set(
                health_value
            )

            logger.debug(
                "DNS LB pool member health", dns_lb=dns_lb, pool=pool, member=member, health_status=health_status
            )
