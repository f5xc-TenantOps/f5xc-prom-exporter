"""Security metrics collector for F5XC."""

from typing import Any, Dict, List, Optional
import time

import structlog
from prometheus_client import Gauge, Counter

from ..client import F5XCClient, F5XCAPIError

logger = structlog.get_logger()


class SecurityCollector:
    """Collector for F5XC security metrics."""

    def __init__(self, client: F5XCClient):
        """Initialize security collector."""
        self.client = client

        # WAF metrics
        self.waf_requests_total = Counter(
            "f5xc_waf_requests_total",
            "Total WAF requests",
            ["namespace", "app", "action", "rule_type"]
        )

        self.waf_blocked_requests_total = Counter(
            "f5xc_waf_blocked_requests_total",
            "Total WAF blocked requests",
            ["namespace", "app", "attack_type"]
        )

        self.waf_rule_hits_total = Counter(
            "f5xc_waf_rule_hits_total",
            "Total WAF rule hits",
            ["namespace", "app", "rule_id", "rule_type"]
        )

        # Bot Defense metrics
        self.bot_requests_total = Counter(
            "f5xc_bot_requests_total",
            "Total bot defense requests",
            ["namespace", "app", "action", "bot_type"]
        )

        self.bot_blocked_requests_total = Counter(
            "f5xc_bot_blocked_requests_total",
            "Total bot defense blocked requests",
            ["namespace", "app", "bot_type"]
        )

        self.bot_score = Gauge(
            "f5xc_bot_score",
            "Bot score (0-100, higher is more likely bot)",
            ["namespace", "app", "client_ip"]
        )

        # API Discovery metrics
        self.api_endpoints_discovered = Gauge(
            "f5xc_api_endpoints_discovered_total",
            "Total API endpoints discovered",
            ["namespace", "app"]
        )

        self.api_schema_violations_total = Counter(
            "f5xc_api_schema_violations_total",
            "Total API schema violations",
            ["namespace", "app", "endpoint", "violation_type"]
        )

        # DDoS metrics
        self.ddos_attacks_total = Counter(
            "f5xc_ddos_attacks_total",
            "Total DDoS attacks detected",
            ["namespace", "app", "attack_type"]
        )

        self.ddos_mitigation_active = Gauge(
            "f5xc_ddos_mitigation_active",
            "Whether DDoS mitigation is active",
            ["namespace", "app"]
        )

        # Security Events
        self.security_events_total = Counter(
            "f5xc_security_events_total",
            "Total security events",
            ["namespace", "app", "event_type", "severity"]
        )

        self.security_alerts_total = Counter(
            "f5xc_security_alerts_total",
            "Total security alerts",
            ["namespace", "alert_type", "severity"]
        )

        # Collection metrics
        self.security_collection_success = Gauge(
            "f5xc_security_collection_success",
            "Whether security collection succeeded",
            ["namespace"]
        )

        self.security_collection_duration = Gauge(
            "f5xc_security_collection_duration_seconds",
            "Time taken to collect security metrics",
            ["namespace"]
        )

    def collect_metrics(self, namespace: str = "system") -> None:
        """Collect security metrics for the specified namespace."""
        start_time = time.time()

        try:
            logger.info("Collecting security metrics", namespace=namespace)

            # Collect different security metrics
            self._collect_waf_metrics(namespace)
            self._collect_bot_defense_metrics(namespace)
            self._collect_api_security_metrics(namespace)
            self._collect_ddos_metrics(namespace)
            self._collect_security_events(namespace)

            # Mark collection as successful
            self.security_collection_success.labels(namespace=namespace).set(1)

            collection_duration = time.time() - start_time
            self.security_collection_duration.labels(namespace=namespace).set(collection_duration)

            logger.info(
                "Security metrics collection successful",
                namespace=namespace,
                duration=collection_duration,
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect security metrics",
                namespace=namespace,
                error=str(e),
                exc_info=True,
            )
            self.security_collection_success.labels(namespace=namespace).set(0)
            raise

    def _collect_waf_metrics(self, namespace: str) -> None:
        """Collect WAF metrics."""
        try:
            waf_data = self.client.get_waf_metrics(namespace)
            self._process_waf_data(waf_data, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to collect WAF metrics", namespace=namespace, error=str(e))

    def _collect_bot_defense_metrics(self, namespace: str) -> None:
        """Collect Bot Defense metrics."""
        try:
            bot_data = self.client.get_bot_defense_metrics(namespace)
            self._process_bot_defense_data(bot_data, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to collect bot defense metrics", namespace=namespace, error=str(e))

    def _collect_api_security_metrics(self, namespace: str) -> None:
        """Collect API Security metrics."""
        try:
            api_data = self.client.get_api_security_metrics(namespace)
            self._process_api_security_data(api_data, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to collect API security metrics", namespace=namespace, error=str(e))

    def _collect_ddos_metrics(self, namespace: str) -> None:
        """Collect DDoS metrics."""
        try:
            ddos_data = self.client.get_ddos_metrics(namespace)
            self._process_ddos_data(ddos_data, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to collect DDoS metrics", namespace=namespace, error=str(e))

    def _collect_security_events(self, namespace: str) -> None:
        """Collect security events."""
        try:
            events_data = self.client.get_security_events(namespace)
            self._process_security_events_data(events_data, namespace)
        except F5XCAPIError as e:
            logger.warning("Failed to collect security events", namespace=namespace, error=str(e))

    def _process_waf_data(self, waf_data: Dict[str, Any], namespace: str) -> None:
        """Process WAF data and update metrics."""
        logger.debug("Processing WAF data", namespace=namespace)

        # Process WAF requests by action and rule type
        requests = waf_data.get("requests", [])
        for request in requests:
            app = request.get("app", "unknown")
            action = request.get("action", "unknown")  # allow, block, log
            rule_type = request.get("rule_type", "unknown")
            count = request.get("count", 0)

            try:
                self.waf_requests_total.labels(
                    namespace=namespace,
                    app=app,
                    action=action,
                    rule_type=rule_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse WAF request count", error=str(e))

        # Process blocked requests by attack type
        blocked_requests = waf_data.get("blocked_requests", [])
        for blocked in blocked_requests:
            app = blocked.get("app", "unknown")
            attack_type = blocked.get("attack_type", "unknown")
            count = blocked.get("count", 0)

            try:
                self.waf_blocked_requests_total.labels(
                    namespace=namespace,
                    app=app,
                    attack_type=attack_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse WAF blocked request count", error=str(e))

        # Process rule hits
        rule_hits = waf_data.get("rule_hits", [])
        for hit in rule_hits:
            app = hit.get("app", "unknown")
            rule_id = hit.get("rule_id", "unknown")
            rule_type = hit.get("rule_type", "unknown")
            count = hit.get("count", 0)

            try:
                self.waf_rule_hits_total.labels(
                    namespace=namespace,
                    app=app,
                    rule_id=rule_id,
                    rule_type=rule_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse WAF rule hit count", error=str(e))

    def _process_bot_defense_data(self, bot_data: Dict[str, Any], namespace: str) -> None:
        """Process bot defense data and update metrics."""
        logger.debug("Processing bot defense data", namespace=namespace)

        # Process bot requests
        bot_requests = bot_data.get("requests", [])
        for request in bot_requests:
            app = request.get("app", "unknown")
            action = request.get("action", "unknown")  # allow, block, challenge
            bot_type = request.get("bot_type", "unknown")  # malicious, suspicious, good
            count = request.get("count", 0)

            try:
                self.bot_requests_total.labels(
                    namespace=namespace,
                    app=app,
                    action=action,
                    bot_type=bot_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse bot request count", error=str(e))

        # Process blocked bot requests
        blocked_requests = bot_data.get("blocked_requests", [])
        for blocked in blocked_requests:
            app = blocked.get("app", "unknown")
            bot_type = blocked.get("bot_type", "unknown")
            count = blocked.get("count", 0)

            try:
                self.bot_blocked_requests_total.labels(
                    namespace=namespace,
                    app=app,
                    bot_type=bot_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse bot blocked request count", error=str(e))

        # Process bot scores
        bot_scores = bot_data.get("bot_scores", [])
        for score_data in bot_scores:
            app = score_data.get("app", "unknown")
            client_ip = score_data.get("client_ip", "unknown")
            score = score_data.get("score", 0)

            try:
                self.bot_score.labels(
                    namespace=namespace,
                    app=app,
                    client_ip=client_ip
                ).set(float(score))
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse bot score", error=str(e))

    def _process_api_security_data(self, api_data: Dict[str, Any], namespace: str) -> None:
        """Process API security data and update metrics."""
        logger.debug("Processing API security data", namespace=namespace)

        # Process discovered endpoints
        discovered_endpoints = api_data.get("discovered_endpoints", [])
        for endpoint_data in discovered_endpoints:
            app = endpoint_data.get("app", "unknown")
            count = endpoint_data.get("count", 0)

            try:
                self.api_endpoints_discovered.labels(
                    namespace=namespace,
                    app=app
                ).set(float(count))
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse API endpoint count", error=str(e))

        # Process schema violations
        schema_violations = api_data.get("schema_violations", [])
        for violation in schema_violations:
            app = violation.get("app", "unknown")
            endpoint = violation.get("endpoint", "unknown")
            violation_type = violation.get("violation_type", "unknown")
            count = violation.get("count", 0)

            try:
                self.api_schema_violations_total.labels(
                    namespace=namespace,
                    app=app,
                    endpoint=endpoint,
                    violation_type=violation_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse API schema violation count", error=str(e))

    def _process_ddos_data(self, ddos_data: Dict[str, Any], namespace: str) -> None:
        """Process DDoS data and update metrics."""
        logger.debug("Processing DDoS data", namespace=namespace)

        # Process DDoS attacks
        attacks = ddos_data.get("attacks", [])
        for attack in attacks:
            app = attack.get("app", "unknown")
            attack_type = attack.get("attack_type", "unknown")
            count = attack.get("count", 0)

            try:
                self.ddos_attacks_total.labels(
                    namespace=namespace,
                    app=app,
                    attack_type=attack_type
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse DDoS attack count", error=str(e))

        # Process mitigation status
        mitigation_status = ddos_data.get("mitigation_status", [])
        for status in mitigation_status:
            app = status.get("app", "unknown")
            active = status.get("active", False)

            self.ddos_mitigation_active.labels(
                namespace=namespace,
                app=app
            ).set(1 if active else 0)

    def _process_security_events_data(self, events_data: Dict[str, Any], namespace: str) -> None:
        """Process security events data and update metrics."""
        logger.debug("Processing security events data", namespace=namespace)

        # Process security events
        events = events_data.get("events", [])
        for event in events:
            app = event.get("app", "unknown")
            event_type = event.get("event_type", "unknown")
            severity = event.get("severity", "unknown")
            count = event.get("count", 0)

            try:
                self.security_events_total.labels(
                    namespace=namespace,
                    app=app,
                    event_type=event_type,
                    severity=severity
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse security event count", error=str(e))

        # Process security alerts
        alerts = events_data.get("alerts", [])
        for alert in alerts:
            alert_type = alert.get("alert_type", "unknown")
            severity = alert.get("severity", "unknown")
            count = alert.get("count", 0)

            try:
                self.security_alerts_total.labels(
                    namespace=namespace,
                    alert_type=alert_type,
                    severity=severity
                )._value._value += float(count)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse security alert count", error=str(e))