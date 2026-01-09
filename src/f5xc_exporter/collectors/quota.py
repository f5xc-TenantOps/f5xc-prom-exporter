"""Quota metrics collector for F5XC."""

from typing import Any, Optional

import structlog
from prometheus_client import Gauge

from ..cardinality import CardinalityTracker
from ..client import F5XCAPIError, F5XCClient

logger = structlog.get_logger()


class QuotaCollector:
    """Collector for F5XC quota metrics."""

    def __init__(
        self,
        client: F5XCClient,
        tenant: str,
        cardinality_tracker: Optional[CardinalityTracker] = None,
    ):
        """Initialize quota collector.

        Args:
            client: F5XC API client
            tenant: Tenant name
            cardinality_tracker: Optional cardinality tracker for limit enforcement
        """
        self.client = client
        self.tenant = tenant
        self.cardinality_tracker = cardinality_tracker
        self.quota_metric_count = 0

        # Prometheus metrics
        self.quota_limit = Gauge(
            "f5xc_quota_limit", "F5XC quota limit", ["tenant", "namespace", "resource_type", "resource_name"]
        )

        self.quota_current = Gauge(
            "f5xc_quota_current", "F5XC quota current usage", ["tenant", "namespace", "resource_type", "resource_name"]
        )

        self.quota_utilization = Gauge(
            "f5xc_quota_utilization_percentage",
            "F5XC quota utilization percentage",
            ["tenant", "namespace", "resource_type", "resource_name"],
        )

        self.quota_collection_success = Gauge(
            "f5xc_quota_collection_success", "Whether quota collection succeeded", ["tenant", "namespace"]
        )

        self.quota_collection_duration = Gauge(
            "f5xc_quota_collection_duration_seconds", "Time taken to collect quota metrics", ["tenant", "namespace"]
        )

    def collect_metrics(self, namespace: str = "system") -> None:
        """Collect quota metrics for the specified namespace."""
        import time

        start_time = time.time()

        try:
            # Check cardinality limits if tracker is enabled
            if self.cardinality_tracker:
                if not self.cardinality_tracker.check_namespace_limit(namespace, "quota"):
                    logger.warning(
                        "Skipping quota collection due to namespace limit",
                        namespace=namespace,
                    )
                    return

            logger.info("Collecting quota metrics", namespace=namespace)

            # Reset metric count for this collection
            self.quota_metric_count = 0

            # Get quota usage data
            quota_data = self.client.get_quota_usage(namespace)

            # Process quota data
            self._process_quota_data(quota_data, namespace)

            # Mark collection as successful
            self.quota_collection_success.labels(tenant=self.tenant, namespace=namespace).set(1)

            collection_duration = time.time() - start_time
            self.quota_collection_duration.labels(tenant=self.tenant, namespace=namespace).set(collection_duration)

            logger.info(
                "Quota metrics collection successful",
                namespace=namespace,
                duration=collection_duration,
                quota_metric_count=self.quota_metric_count,
            )

            # Update cardinality tracking if enabled
            if self.cardinality_tracker:
                self.cardinality_tracker.update_metric_cardinality("quota", "quota_metrics", self.quota_metric_count)

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect quota metrics",
                namespace=namespace,
                error=str(e),
                exc_info=True,
            )
            self.quota_collection_success.labels(tenant=self.tenant, namespace=namespace).set(0)
            raise

    def _process_quota_data(self, quota_data: dict[str, Any], namespace: str) -> None:
        """Process quota usage data and update metrics."""
        logger.debug("Processing quota data", namespace=namespace, data_keys=list(quota_data.keys()))

        # Handle F5XC quota response structure
        if "quota_usage" in quota_data:
            logger.debug("Processing quota_usage section", count=len(quota_data["quota_usage"]))
            self._process_f5xc_quota_section(quota_data["quota_usage"], namespace, "quota")

        if "resources" in quota_data:
            logger.debug("Processing resources section", count=len(quota_data["resources"]))
            self._process_f5xc_quota_section(quota_data["resources"], namespace, "resource")

        if "objects" in quota_data:
            logger.debug("Processing objects section", count=len(quota_data["objects"]))
            self._process_f5xc_quota_section(quota_data["objects"], namespace, "object")

    def _process_f5xc_quota_section(self, quota_section: dict[str, Any], namespace: str, resource_type: str) -> None:
        """Process F5XC quota section (quota_usage, resources, objects)."""
        for resource_name, quota_info in quota_section.items():
            if isinstance(quota_info, dict):
                # Extract limit and usage from F5XC structure
                limit = None
                current = None

                if "limit" in quota_info and isinstance(quota_info["limit"], dict):
                    limit = quota_info["limit"].get("maximum")

                if "usage" in quota_info and isinstance(quota_info["usage"], dict):
                    current = quota_info["usage"].get("current")

                if limit is not None and current is not None:
                    try:
                        limit_val = float(limit)
                        current_val = float(current)

                        # Set Prometheus metrics
                        self.quota_limit.labels(
                            tenant=self.tenant,
                            namespace=namespace,
                            resource_type=resource_type,
                            resource_name=resource_name,
                        ).set(limit_val)

                        self.quota_current.labels(
                            tenant=self.tenant,
                            namespace=namespace,
                            resource_type=resource_type,
                            resource_name=resource_name,
                        ).set(current_val)

                        # Calculate utilization percentage
                        # Skip if limit <= 0 (unlimited) or current < 0 (no data)
                        utilization = (current_val / limit_val * 100) if limit_val > 0 and current_val >= 0 else 0
                        self.quota_utilization.labels(
                            tenant=self.tenant,
                            namespace=namespace,
                            resource_type=resource_type,
                            resource_name=resource_name,
                        ).set(utilization)

                        logger.debug(
                            "Processed F5XC quota metric",
                            namespace=namespace,
                            resource_type=resource_type,
                            resource_name=resource_name,
                            limit=limit_val,
                            current=current_val,
                            utilization=utilization,
                        )

                        # Track metric count
                        self.quota_metric_count += 1
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Failed to parse quota values",
                            resource_name=resource_name,
                            limit=limit,
                            current=current,
                            error=str(e),
                        )

    def _process_quotas_list(self, quotas: list[dict[str, Any]], namespace: str) -> None:
        """Process quota data in list format."""
        for quota in quotas:
            self._process_single_quota(quota, namespace)

    def _process_usage_data(self, usage_data: dict[str, Any], namespace: str) -> None:
        """Process quota data in usage format."""
        for resource_type, resource_data in usage_data.items():
            if isinstance(resource_data, dict):
                for resource_name, quota_info in resource_data.items():
                    self._process_quota_info(quota_info, namespace, resource_type, resource_name)

    def _process_direct_quota_data(self, quota_data: dict[str, Any], namespace: str) -> None:
        """Process direct quota data format."""
        for key, value in quota_data.items():
            if isinstance(value, dict) and ("limit" in value or "current" in value or "used" in value):
                self._process_quota_info(value, namespace, "resource", key)

    def _process_single_quota(self, quota: dict[str, Any], namespace: str) -> None:
        """Process a single quota entry."""
        resource_type = quota.get("type", "unknown")
        resource_name = quota.get("name", quota.get("resource", "unknown"))

        self._process_quota_info(quota, namespace, resource_type, resource_name)

    def _process_quota_info(
        self, quota_info: dict[str, Any], namespace: str, resource_type: str, resource_name: str
    ) -> None:
        """Process individual quota information."""
        # Get limit and current usage
        limit = self._extract_numeric_value(quota_info, ["limit", "max", "quota"])
        current = self._extract_numeric_value(quota_info, ["current", "used", "usage"])

        if limit is not None and current is not None:
            # Set Prometheus metrics
            self.quota_limit.labels(
                tenant=self.tenant, namespace=namespace, resource_type=resource_type, resource_name=resource_name
            ).set(limit)

            self.quota_current.labels(
                tenant=self.tenant, namespace=namespace, resource_type=resource_type, resource_name=resource_name
            ).set(current)

            # Calculate utilization percentage
            utilization = (current / limit * 100) if limit > 0 else 0
            self.quota_utilization.labels(
                tenant=self.tenant, namespace=namespace, resource_type=resource_type, resource_name=resource_name
            ).set(utilization)

            logger.debug(
                "Processed quota metric",
                namespace=namespace,
                resource_type=resource_type,
                resource_name=resource_name,
                limit=limit,
                current=current,
                utilization=utilization,
            )

    def _extract_numeric_value(self, data: dict[str, Any], possible_keys: list[str]) -> Optional[float]:
        """Extract numeric value from data using possible keys."""
        for key in possible_keys:
            if key in data:
                value = data[key]
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        return None
