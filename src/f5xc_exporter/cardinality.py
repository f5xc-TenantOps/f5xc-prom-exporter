"""Cardinality management for F5XC Prometheus Exporter.

Tracks and manages metric cardinality to prevent metric explosion
and Prometheus performance degradation.
"""

from collections import defaultdict
from typing import Any

import structlog
from prometheus_client import Gauge

logger = structlog.get_logger()


class CardinalityTracker:
    """Tracks metric cardinality and enforces limits."""

    def __init__(
        self,
        max_namespaces: int = 100,
        max_load_balancers_per_namespace: int = 50,
        max_dns_zones: int = 100,
        warn_cardinality_threshold: int = 10000,
    ):
        """Initialize cardinality tracker.

        Args:
            max_namespaces: Maximum number of namespaces to track (0 = unlimited)
            max_load_balancers_per_namespace: Maximum LBs per namespace (0 = unlimited)
            max_dns_zones: Maximum number of DNS zones to track (0 = unlimited)
            warn_cardinality_threshold: Warn when total cardinality exceeds this (0 = no warning)

        Raises:
            ValueError: If any limit is negative
        """
        # Validate that limits are non-negative
        if max_namespaces < 0:
            raise ValueError("max_namespaces must be >= 0 (0 = unlimited)")
        if max_load_balancers_per_namespace < 0:
            raise ValueError("max_load_balancers_per_namespace must be >= 0 (0 = unlimited)")
        if max_dns_zones < 0:
            raise ValueError("max_dns_zones must be >= 0 (0 = unlimited)")
        if warn_cardinality_threshold < 0:
            raise ValueError("warn_cardinality_threshold must be >= 0 (0 = disabled)")

        self.max_namespaces = max_namespaces
        self.max_load_balancers_per_namespace = max_load_balancers_per_namespace
        self.max_dns_zones = max_dns_zones
        self.warn_cardinality_threshold = warn_cardinality_threshold

        # Track unique label combinations per collector
        self.tracked_namespaces: set[str] = set()
        self.tracked_load_balancers: dict[str, set[str]] = defaultdict(set)
        self.tracked_dns_zones: set[str] = set()

        # Track cardinality per collector and metric
        self.cardinality_per_collector: dict[str, int] = defaultdict(int)
        self.cardinality_per_metric: dict[str, int] = defaultdict(int)

        # Track limit exceeded events
        self.limits_exceeded: dict[str, int] = defaultdict(int)

        # Initialize metrics
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize Prometheus metrics for cardinality tracking."""
        self.metric_cardinality = Gauge(
            "f5xc_metric_cardinality",
            "Number of unique label combinations for a metric",
            ["collector", "metric_name"],
        )

        self.cardinality_limit_exceeded = Gauge(
            "f5xc_cardinality_limit_exceeded",
            "Number of times cardinality limit was exceeded",
            ["collector", "limit_type"],
        )

        self.total_tracked_namespaces = Gauge(
            "f5xc_tracked_namespaces_total",
            "Total number of tracked namespaces",
        )

        self.total_tracked_load_balancers = Gauge(
            "f5xc_tracked_load_balancers_total",
            "Total number of tracked load balancers",
        )

        self.total_tracked_dns_zones = Gauge(
            "f5xc_tracked_dns_zones_total",
            "Total number of tracked DNS zones",
        )

    def check_namespace_limit(self, namespace: str, collector: str) -> bool:
        """Check if namespace can be tracked within limits.

        Args:
            namespace: Namespace to check
            collector: Collector name for logging

        Returns:
            True if namespace should be tracked, False if limit exceeded
        """
        if namespace in self.tracked_namespaces:
            return True

        # 0 means unlimited
        if self.max_namespaces > 0 and len(self.tracked_namespaces) >= self.max_namespaces:
            self.limits_exceeded[f"{collector}_namespace"] += 1
            self.cardinality_limit_exceeded.labels(collector=collector, limit_type="namespace").set(
                self.limits_exceeded[f"{collector}_namespace"]
            )

            logger.warning(
                "Namespace cardinality limit exceeded, skipping namespace",
                collector=collector,
                namespace=namespace,
                current_count=len(self.tracked_namespaces),
                max_namespaces=self.max_namespaces,
            )
            return False

        self.tracked_namespaces.add(namespace)
        self.total_tracked_namespaces.set(len(self.tracked_namespaces))
        return True

    def check_load_balancer_limit(self, namespace: str, load_balancer: str, collector: str) -> bool:
        """Check if load balancer can be tracked within limits.

        Args:
            namespace: Namespace containing the load balancer
            load_balancer: Load balancer name to check
            collector: Collector name for logging

        Returns:
            True if load balancer should be tracked, False if limit exceeded
        """
        if load_balancer in self.tracked_load_balancers[namespace]:
            return True

        # 0 means unlimited
        if (
            self.max_load_balancers_per_namespace > 0
            and len(self.tracked_load_balancers[namespace]) >= self.max_load_balancers_per_namespace
        ):
            self.limits_exceeded[f"{collector}_load_balancer"] += 1
            self.cardinality_limit_exceeded.labels(collector=collector, limit_type="load_balancer").set(
                self.limits_exceeded[f"{collector}_load_balancer"]
            )

            logger.warning(
                "Load balancer cardinality limit exceeded for namespace, skipping load balancer",
                collector=collector,
                namespace=namespace,
                load_balancer=load_balancer,
                current_count=len(self.tracked_load_balancers[namespace]),
                max_per_namespace=self.max_load_balancers_per_namespace,
            )
            return False

        self.tracked_load_balancers[namespace].add(load_balancer)
        # Update total count across all namespaces
        total_lbs = sum(len(lbs) for lbs in self.tracked_load_balancers.values())
        self.total_tracked_load_balancers.set(total_lbs)
        return True

    def check_dns_zone_limit(self, zone: str, collector: str) -> bool:
        """Check if DNS zone can be tracked within limits.

        Args:
            zone: DNS zone to check
            collector: Collector name for logging

        Returns:
            True if DNS zone should be tracked, False if limit exceeded
        """
        if zone in self.tracked_dns_zones:
            return True

        # 0 means unlimited
        if self.max_dns_zones > 0 and len(self.tracked_dns_zones) >= self.max_dns_zones:
            self.limits_exceeded[f"{collector}_dns_zone"] += 1
            self.cardinality_limit_exceeded.labels(collector=collector, limit_type="dns_zone").set(
                self.limits_exceeded[f"{collector}_dns_zone"]
            )

            logger.warning(
                "DNS zone cardinality limit exceeded, skipping zone",
                collector=collector,
                zone=zone,
                current_count=len(self.tracked_dns_zones),
                max_dns_zones=self.max_dns_zones,
            )
            return False

        self.tracked_dns_zones.add(zone)
        self.total_tracked_dns_zones.set(len(self.tracked_dns_zones))
        return True

    def update_metric_cardinality(self, collector: str, metric_name: str, cardinality: int) -> None:
        """Update cardinality tracking for a specific metric.

        Args:
            collector: Collector name
            metric_name: Metric name
            cardinality: Current cardinality count
        """
        key = f"{collector}:{metric_name}"
        self.cardinality_per_metric[key] = cardinality
        self.metric_cardinality.labels(collector=collector, metric_name=metric_name).set(cardinality)

        # Update collector total
        collector_total = sum(
            count for metric_key, count in self.cardinality_per_metric.items() if metric_key.startswith(f"{collector}:")
        )
        self.cardinality_per_collector[collector] = collector_total

        # Check warning threshold (0 means no warning)
        if self.warn_cardinality_threshold > 0 and cardinality > self.warn_cardinality_threshold:
            logger.warning(
                "Metric cardinality exceeds warning threshold",
                collector=collector,
                metric_name=metric_name,
                cardinality=cardinality,
                threshold=self.warn_cardinality_threshold,
            )

    def get_collector_cardinality(self, collector: str) -> int:
        """Get total cardinality for a collector.

        Args:
            collector: Collector name

        Returns:
            Total cardinality across all metrics for this collector
        """
        return self.cardinality_per_collector.get(collector, 0)

    def get_total_cardinality(self) -> int:
        """Get total cardinality across all collectors.

        Returns:
            Total cardinality
        """
        return sum(self.cardinality_per_collector.values())

    def reset_tracking(self) -> None:
        """Reset all tracking data.

        Used for testing or when limits need to be recalculated.
        """
        self.tracked_namespaces.clear()
        self.tracked_load_balancers.clear()
        self.tracked_dns_zones.clear()
        self.cardinality_per_collector.clear()
        self.cardinality_per_metric.clear()
        self.limits_exceeded.clear()

        # Reset metrics
        self.total_tracked_namespaces.set(0)
        self.total_tracked_load_balancers.set(0)
        self.total_tracked_dns_zones.set(0)

    def get_stats(self) -> dict[str, Any]:
        """Get current cardinality statistics.

        Returns:
            Dictionary with current tracking stats
        """
        return {
            "namespaces_tracked": len(self.tracked_namespaces),
            "max_namespaces": self.max_namespaces,
            "load_balancers_tracked": sum(len(lbs) for lbs in self.tracked_load_balancers.values()),
            "max_load_balancers_per_namespace": self.max_load_balancers_per_namespace,
            "dns_zones_tracked": len(self.tracked_dns_zones),
            "max_dns_zones": self.max_dns_zones,
            "total_cardinality": self.get_total_cardinality(),
            "warn_threshold": self.warn_cardinality_threshold,
            "limits_exceeded": dict(self.limits_exceeded),
        }
