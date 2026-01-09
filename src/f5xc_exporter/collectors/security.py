"""Security metrics collector for F5XC.

Collects security metrics from two F5 XC APIs per namespace:
1. App Firewall Metrics API - per-LB counters (total requests, attacked requests, bot detections)
2. Security Events Aggregation API - namespace-level event counts by type
"""

import time
from typing import Any, Optional

import structlog
from prometheus_client import Gauge

from ..cardinality import CardinalityTracker
from ..client import F5XCAPIError, F5XCClient

logger = structlog.get_logger()


class SecurityCollector:
    """Collector for F5XC security metrics.

    Uses exactly 2 API calls per namespace for scalability:
    - Call 1: app_firewall/metrics - per-LB aggregate counters
    - Call 2: events/aggregation - all event type counts in single query
    """

    # All security event types to collect in a single aggregation query
    ALL_EVENT_TYPES = [
        "waf_sec_event",
        "bot_defense_sec_event",
        "api_sec_event",
        "svc_policy_sec_event",
        "malicious_user_sec_event",
        "ddos_sec_event",
        "dos_sec_event",
    ]

    def __init__(
        self,
        client: F5XCClient,
        tenant: str,
        cardinality_tracker: Optional[CardinalityTracker] = None,
    ):
        """Initialize security collector.

        Args:
            client: F5XC API client
            tenant: Tenant name
            cardinality_tracker: Optional cardinality tracker for limit enforcement
        """
        self.client = client
        self.tenant = tenant
        self.cardinality_tracker = cardinality_tracker

        # --- Per-LB Metrics (from app_firewall/metrics API) ---
        lb_labels = ["tenant", "namespace", "load_balancer"]
        self.total_requests = Gauge(
            "f5xc_security_total_requests", "Total requests processed by app firewall", lb_labels
        )
        self.attacked_requests = Gauge("f5xc_security_attacked_requests", "WAF blocked/attacked requests", lb_labels)
        self.bot_detections = Gauge(
            "f5xc_security_bot_detections", "Total bot detections (all classifications)", lb_labels
        )

        # --- Namespace-level Event Counts (from events/aggregation API) ---
        # Single aggregation query returns all event type counts
        ns_labels = ["tenant", "namespace"]
        self.waf_events = Gauge("f5xc_security_waf_events", "WAF security event count (namespace total)", ns_labels)
        self.bot_defense_events = Gauge(
            "f5xc_security_bot_defense_events", "Bot defense security event count (namespace total)", ns_labels
        )
        self.api_events = Gauge("f5xc_security_api_events", "API security event count (namespace total)", ns_labels)
        self.service_policy_events = Gauge(
            "f5xc_security_service_policy_events", "Service policy security event count (namespace total)", ns_labels
        )
        self.malicious_user_events = Gauge(
            "f5xc_security_malicious_user_events", "Malicious user event count (namespace total)", ns_labels
        )
        self.dos_events = Gauge("f5xc_security_dos_events", "DDoS/DoS event count (namespace total)", ns_labels)

        # --- Collection Status Metrics ---
        self.collection_success = Gauge(
            "f5xc_security_collection_success",
            "Whether security metrics collection succeeded (1=success, 0=failure)",
            ["tenant"],
        )
        self.collection_duration = Gauge(
            "f5xc_security_collection_duration_seconds", "Time taken to collect security metrics", ["tenant"]
        )

    def collect_metrics(self) -> None:
        """Collect all security metrics from all namespaces."""
        start_time = time.time()

        try:
            logger.info("Collecting security metrics")

            namespaces = self.client.list_namespaces()
            logger.debug("Found namespaces for security collection", count=len(namespaces))

            namespaces_processed = 0
            for namespace in namespaces:
                # Check cardinality limits if tracker is enabled
                if self.cardinality_tracker:
                    if not self.cardinality_tracker.check_namespace_limit(namespace, "security"):
                        continue

                try:
                    # Call 1: Per-LB metrics from app_firewall/metrics
                    self._collect_app_firewall_metrics(namespace)
                    # Call 2: All event counts from events/aggregation
                    self._collect_event_counts(namespace)
                    namespaces_processed += 1
                except F5XCAPIError as e:
                    logger.warning(
                        "Failed to collect security metrics for namespace", namespace=namespace, error=str(e)
                    )
                    continue

            self.collection_success.labels(tenant=self.tenant).set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.labels(tenant=self.tenant).set(collection_duration)

            logger.info(
                "Security metrics collection successful",
                duration=collection_duration,
                namespace_count=len(namespaces),
                namespaces_processed=namespaces_processed,
            )

            # Update cardinality tracking if enabled
            if self.cardinality_tracker:
                self.cardinality_tracker.update_metric_cardinality("security", "security_metrics", namespaces_processed)

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect security metrics",
                error=str(e),
                exc_info=True,
            )
            self.collection_success.labels(tenant=self.tenant).set(0)
            raise

    def _collect_app_firewall_metrics(self, namespace: str) -> None:
        """Collect metrics from app_firewall/metrics API (Call 1)."""
        try:
            response = self.client.get_app_firewall_metrics_for_namespace(namespace)
            self._process_app_firewall_response(response, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to get app firewall metrics", namespace=namespace, error=str(e))

    def _collect_event_counts(self, namespace: str) -> None:
        """Collect all event counts in single API call (Call 2)."""
        try:
            response = self.client.get_security_event_counts_for_namespace(namespace, self.ALL_EVENT_TYPES)
            self._process_event_aggregation(response, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to get security event counts", namespace=namespace, error=str(e))

    def _process_app_firewall_response(self, data: dict[str, Any], namespace: str) -> None:
        """Process app firewall metrics response.

        Response structure:
        {
            "data": [
                {
                    "type": "ATTACKED_REQUESTS",
                    "data": [
                        {
                            "key": {"VIRTUAL_HOST": "ves-io-http-loadbalancer-..."},
                            "value": [{"timestamp": ..., "value": "0"}]
                        }
                    ],
                    "unit": "UNIT_COUNT"
                }
            ],
            "step": "5m"
        }
        """
        for metric_group in data.get("data", []):
            metric_type = metric_group.get("type", "")
            gauge = self._get_gauge_for_app_firewall_type(metric_type)

            if not gauge:
                continue

            for item in metric_group.get("data", []):
                key = item.get("key", {})
                load_balancer = key.get("VIRTUAL_HOST", "unknown")

                # Get latest value from the value array
                values = item.get("value", [])
                if not values:
                    continue

                latest = values[-1] if values else {}
                value_str = latest.get("value", "0")

                try:
                    value = float(value_str)
                    gauge.labels(tenant=self.tenant, namespace=namespace, load_balancer=load_balancer).set(value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Failed to parse app firewall metric value",
                        metric_type=metric_type,
                        value=value_str,
                        error=str(e),
                    )

    def _process_event_aggregation(self, data: dict[str, Any], namespace: str) -> None:
        """Process security events aggregation response.

        Response structure (single-level aggregation by event type):
        {
            "aggs": {
                "by_event_type": {
                    "field_aggregation": {
                        "buckets": [
                            {"key": "waf_sec_event", "count": "20"},
                            {"key": "bot_defense_sec_event", "count": "15"},
                            {"key": "malicious_user_sec_event", "count": "5"},
                            {"key": "ddos_sec_event", "count": "3"}
                        ]
                    }
                }
            }
        }
        """
        aggs = data.get("aggs", {})
        event_type_agg = aggs.get("by_event_type", {})
        field_agg = event_type_agg.get("field_aggregation", {})
        buckets = field_agg.get("buckets", [])

        # Track DoS events separately to sum ddos + dos
        dos_total: float = 0.0

        for bucket in buckets:
            event_type = bucket.get("key", "")
            count_str = bucket.get("count", "0")

            try:
                count = float(count_str)
            except (ValueError, TypeError):
                continue

            # Handle DoS events specially (sum ddos + dos)
            if event_type in ("ddos_sec_event", "dos_sec_event"):
                dos_total += count
                continue

            gauge = self._get_gauge_for_event_type(event_type)
            if gauge:
                gauge.labels(tenant=self.tenant, namespace=namespace).set(count)

        # Set combined DoS count
        self.dos_events.labels(tenant=self.tenant, namespace=namespace).set(dos_total)

    def _get_gauge_for_app_firewall_type(self, metric_type: str) -> Optional[Gauge]:
        """Get the appropriate gauge for an app firewall metric type."""
        mapping = {
            "TOTAL_REQUESTS": self.total_requests,
            "ATTACKED_REQUESTS": self.attacked_requests,
            "BOT_DETECTION": self.bot_detections,
        }
        return mapping.get(metric_type)

    def _get_gauge_for_event_type(self, event_type: str) -> Optional[Gauge]:
        """Get the appropriate gauge for a security event type."""
        mapping = {
            "waf_sec_event": self.waf_events,
            "bot_defense_sec_event": self.bot_defense_events,
            "api_sec_event": self.api_events,
            "svc_policy_sec_event": self.service_policy_events,
            "malicious_user_sec_event": self.malicious_user_events,
        }
        return mapping.get(event_type)
