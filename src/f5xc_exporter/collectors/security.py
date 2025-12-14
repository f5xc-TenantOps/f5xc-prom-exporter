"""Security metrics collector for F5XC.

Collects security trend metrics from two F5 XC APIs:
1. App Firewall Metrics API - aggregate counters (total requests, attacked requests, bot detections)
2. Security Events Aggregation API - event counts by type (WAF, bot defense, API sec, etc.)
"""

import time
from typing import Any, Dict, List, Optional

import structlog
from prometheus_client import Gauge

from ..client import F5XCClient, F5XCAPIError

logger = structlog.get_logger()


class SecurityCollector:
    """Collector for F5XC security metrics.

    Uses two APIs to collect security trend metrics:
    - App Firewall Metrics: aggregate counters per load balancer
    - Security Events Aggregation: event counts by type per load balancer
    """

    # Security event types to collect from events/aggregation API
    SECURITY_EVENT_TYPES = [
        "waf_sec_event",
        "bot_defense_sec_event",
        "api_sec_event",
        "svc_policy_sec_event",
    ]

    MALICIOUS_USER_EVENT_TYPES = ["malicious_user_sec_event"]
    DOS_EVENT_TYPES = ["ddos_sec_event", "dos_sec_event"]

    def __init__(self, client: F5XCClient):
        """Initialize security collector."""
        self.client = client

        # Labels for all security metrics
        labels = ["namespace", "load_balancer"]

        # --- App Firewall Metrics (API 1) ---
        self.total_requests = Gauge(
            "f5xc_security_total_requests",
            "Total requests processed by app firewall",
            labels
        )
        self.attacked_requests = Gauge(
            "f5xc_security_attacked_requests",
            "WAF blocked/attacked requests",
            labels
        )
        self.bot_detections = Gauge(
            "f5xc_security_bot_detections",
            "Total bot detections (all classifications)",
            labels
        )
        self.malicious_bot_detections = Gauge(
            "f5xc_security_malicious_bot_detections",
            "Malicious bot detections only",
            labels
        )

        # --- Security Event Counts (API 2) ---
        self.waf_events = Gauge(
            "f5xc_security_waf_events",
            "WAF security event count",
            labels
        )
        self.bot_defense_events = Gauge(
            "f5xc_security_bot_defense_events",
            "Bot defense security event count",
            labels
        )
        self.api_events = Gauge(
            "f5xc_security_api_events",
            "API security event count",
            labels
        )
        self.service_policy_events = Gauge(
            "f5xc_security_service_policy_events",
            "Service policy security event count",
            labels
        )
        self.malicious_user_events = Gauge(
            "f5xc_security_malicious_user_events",
            "Malicious user event count",
            labels
        )
        self.dos_events = Gauge(
            "f5xc_security_dos_events",
            "DDoS/DoS event count",
            labels
        )

        # --- Geographic/Source Metrics ---
        self.events_by_country = Gauge(
            "f5xc_security_events_by_country",
            "Security events by source country",
            ["namespace", "country"]
        )
        self.top_attack_sources = Gauge(
            "f5xc_security_top_attack_sources",
            "Top attack sources by IP and country",
            ["namespace", "country", "src_ip"]
        )

        # --- Collection Status Metrics (no labels) ---
        self.collection_success = Gauge(
            "f5xc_security_collection_success",
            "Whether security metrics collection succeeded (1=success, 0=failure)",
            []
        )
        self.collection_duration = Gauge(
            "f5xc_security_collection_duration_seconds",
            "Time taken to collect security metrics",
            []
        )

    def collect_metrics(self) -> None:
        """Collect all security metrics from all namespaces."""
        start_time = time.time()

        try:
            logger.info("Collecting security metrics")

            namespaces = self.client.list_namespaces()
            logger.debug("Found namespaces for security collection", count=len(namespaces))

            for namespace in namespaces:
                try:
                    self._collect_app_firewall_metrics(namespace)
                    self._collect_security_event_counts(namespace)
                    self._collect_geographic_metrics(namespace)
                except F5XCAPIError as e:
                    logger.warning(
                        "Failed to collect security metrics for namespace",
                        namespace=namespace,
                        error=str(e)
                    )
                    continue

            self.collection_success.set(1)

            collection_duration = time.time() - start_time
            self.collection_duration.set(collection_duration)

            logger.info(
                "Security metrics collection successful",
                duration=collection_duration,
                namespace_count=len(namespaces),
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect security metrics",
                error=str(e),
                exc_info=True,
            )
            self.collection_success.set(0)
            raise

    def _collect_app_firewall_metrics(self, namespace: str) -> None:
        """Collect metrics from app_firewall/metrics API."""
        # Get main metrics (total requests, attacked requests, bot detections)
        try:
            response = self.client.get_app_firewall_metrics_for_namespace(namespace)
            self._process_app_firewall_response(response, namespace)
        except F5XCAPIError as e:
            logger.warning(
                "Failed to get app firewall metrics",
                namespace=namespace,
                error=str(e)
            )

        # Get malicious bot metrics separately (filtered by BOT_CLASSIFICATION)
        try:
            bot_response = self.client.get_malicious_bot_metrics_for_namespace(namespace)
            self._process_malicious_bot_response(bot_response, namespace)
        except F5XCAPIError as e:
            logger.warning(
                "Failed to get malicious bot metrics",
                namespace=namespace,
                error=str(e)
            )

    def _collect_security_event_counts(self, namespace: str) -> None:
        """Collect event counts from app_security/events/aggregation API."""
        # Main security events (WAF, bot defense, API sec, service policy)
        try:
            response = self.client.get_security_event_counts_for_namespace(
                namespace, self.SECURITY_EVENT_TYPES
            )
            self._process_event_aggregation(response, namespace)
        except F5XCAPIError as e:
            logger.warning(
                "Failed to get security event counts",
                namespace=namespace,
                error=str(e)
            )

        # Malicious user events
        try:
            user_response = self.client.get_security_event_counts_for_namespace(
                namespace, self.MALICIOUS_USER_EVENT_TYPES
            )
            self._process_malicious_user_aggregation(user_response, namespace)
        except F5XCAPIError as e:
            logger.warning(
                "Failed to get malicious user events",
                namespace=namespace,
                error=str(e)
            )

        # DoS events
        try:
            dos_response = self.client.get_security_event_counts_for_namespace(
                namespace, self.DOS_EVENT_TYPES
            )
            self._process_dos_aggregation(dos_response, namespace)
        except F5XCAPIError as e:
            logger.warning(
                "Failed to get DoS events",
                namespace=namespace,
                error=str(e)
            )

    def _collect_geographic_metrics(self, namespace: str) -> None:
        """Collect geographic metrics (events by country, top attack sources)."""
        try:
            response = self.client.get_security_events_by_country_for_namespace(
                namespace, self.SECURITY_EVENT_TYPES
            )
            self._process_country_aggregation(response, namespace)
            self._process_attack_sources_aggregation(response, namespace)
        except F5XCAPIError as e:
            logger.warning(
                "Failed to get geographic metrics",
                namespace=namespace,
                error=str(e)
            )

    def _process_app_firewall_response(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
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
                    gauge.labels(
                        namespace=namespace,
                        load_balancer=load_balancer
                    ).set(value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Failed to parse app firewall metric value",
                        metric_type=metric_type,
                        value=value_str,
                        error=str(e)
                    )

    def _process_malicious_bot_response(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
        """Process malicious bot metrics response."""
        for metric_group in data.get("data", []):
            metric_type = metric_group.get("type", "")

            # Only process BOT_DETECTION for malicious bots
            if metric_type != "BOT_DETECTION":
                continue

            for item in metric_group.get("data", []):
                key = item.get("key", {})
                load_balancer = key.get("VIRTUAL_HOST", "unknown")

                values = item.get("value", [])
                if not values:
                    continue

                latest = values[-1] if values else {}
                value_str = latest.get("value", "0")

                try:
                    value = float(value_str)
                    self.malicious_bot_detections.labels(
                        namespace=namespace,
                        load_balancer=load_balancer
                    ).set(value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Failed to parse malicious bot metric value",
                        value=value_str,
                        error=str(e)
                    )

    def _process_event_aggregation(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
        """Process security events aggregation response.

        Response structure:
        {
            "aggs": {
                "by_lb_and_type": {
                    "field_aggregation": {
                        "buckets": [
                            {
                                "key": "ves-io-http-loadbalancer-...",
                                "count": "42",
                                "sub_aggs": {
                                    "by_type": {
                                        "field_aggregation": {
                                            "buckets": [
                                                {"key": "waf_sec_event", "count": "20"},
                                                {"key": "bot_defense_sec_event", "count": "22"}
                                            ]
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        """
        aggs = data.get("aggs", {})
        lb_agg = aggs.get("by_lb_and_type", {})
        field_agg = lb_agg.get("field_aggregation", {})
        buckets = field_agg.get("buckets", [])

        for bucket in buckets:
            load_balancer = bucket.get("key", "unknown")

            # Get sub-aggregation by event type
            sub_aggs = bucket.get("sub_aggs", {})
            type_agg = sub_aggs.get("by_type", {})
            type_field_agg = type_agg.get("field_aggregation", {})
            type_buckets = type_field_agg.get("buckets", [])

            for type_bucket in type_buckets:
                event_type = type_bucket.get("key", "")
                count_str = type_bucket.get("count", "0")

                gauge = self._get_gauge_for_event_type(event_type)
                if not gauge:
                    continue

                try:
                    count = float(count_str)
                    gauge.labels(
                        namespace=namespace,
                        load_balancer=load_balancer
                    ).set(count)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Failed to parse event count",
                        event_type=event_type,
                        count=count_str,
                        error=str(e)
                    )

    def _process_malicious_user_aggregation(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
        """Process malicious user events aggregation response."""
        aggs = data.get("aggs", {})
        lb_agg = aggs.get("by_lb_and_type", {})
        field_agg = lb_agg.get("field_aggregation", {})
        buckets = field_agg.get("buckets", [])

        for bucket in buckets:
            load_balancer = bucket.get("key", "unknown")
            count_str = bucket.get("count", "0")

            try:
                count = float(count_str)
                self.malicious_user_events.labels(
                    namespace=namespace,
                    load_balancer=load_balancer
                ).set(count)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse malicious user count",
                    count=count_str,
                    error=str(e)
                )

    def _process_dos_aggregation(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
        """Process DoS events aggregation response."""
        aggs = data.get("aggs", {})
        lb_agg = aggs.get("by_lb_and_type", {})
        field_agg = lb_agg.get("field_aggregation", {})
        buckets = field_agg.get("buckets", [])

        for bucket in buckets:
            load_balancer = bucket.get("key", "unknown")
            count_str = bucket.get("count", "0")

            try:
                count = float(count_str)
                self.dos_events.labels(
                    namespace=namespace,
                    load_balancer=load_balancer
                ).set(count)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse DoS event count",
                    count=count_str,
                    error=str(e)
                )

    def _process_country_aggregation(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
        """Process events by country aggregation response.

        Response structure:
        {
            "aggs": {
                "by_country": {
                    "field_aggregation": {
                        "buckets": [
                            {"key": "DE", "count": "1517"},
                            {"key": "US", "count": "500"}
                        ]
                    }
                }
            }
        }
        """
        aggs = data.get("aggs", {})
        country_agg = aggs.get("by_country", {})
        field_agg = country_agg.get("field_aggregation", {})
        buckets = field_agg.get("buckets", [])

        for bucket in buckets:
            country = bucket.get("key", "unknown")
            count_str = bucket.get("count", "0")

            try:
                count = float(count_str)
                self.events_by_country.labels(
                    namespace=namespace,
                    country=country
                ).set(count)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse country event count",
                    country=country,
                    count=count_str,
                    error=str(e)
                )

    def _process_attack_sources_aggregation(
        self,
        data: Dict[str, Any],
        namespace: str
    ) -> None:
        """Process top attack sources aggregation response.

        Response structure:
        {
            "aggs": {
                "top_attack_sources": {
                    "multi_field_aggregation": {
                        "buckets": [
                            {
                                "keys": {"country": "DE", "src_ip": "188.68.49.235"},
                                "count": "1517"
                            }
                        ]
                    }
                }
            }
        }
        """
        aggs = data.get("aggs", {})
        sources_agg = aggs.get("top_attack_sources", {})
        multi_field_agg = sources_agg.get("multi_field_aggregation", {})
        buckets = multi_field_agg.get("buckets", [])

        for bucket in buckets:
            keys = bucket.get("keys", {})
            country = keys.get("country", "unknown")
            src_ip = keys.get("src_ip", "unknown")
            count_str = bucket.get("count", "0")

            try:
                count = float(count_str)
                self.top_attack_sources.labels(
                    namespace=namespace,
                    country=country,
                    src_ip=src_ip
                ).set(count)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse attack source count",
                    country=country,
                    src_ip=src_ip,
                    count=count_str,
                    error=str(e)
                )

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
        }
        return mapping.get(event_type)
