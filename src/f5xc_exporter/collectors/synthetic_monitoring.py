"""Synthetic monitoring metrics collector for F5XC."""

from typing import Any, Dict, List, Optional
import time

import structlog
from prometheus_client import Gauge, Counter

from ..client import F5XCClient, F5XCAPIError

logger = structlog.get_logger()


class SyntheticMonitoringCollector:
    """Collector for F5XC synthetic monitoring metrics."""

    def __init__(self, client: F5XCClient):
        """Initialize synthetic monitoring collector."""
        self.client = client

        # HTTP synthetic monitoring metrics
        self.http_check_success = Gauge(
            "f5xc_synthetic_http_check_success",
            "Whether HTTP synthetic check succeeded (1=success, 0=failure)",
            ["namespace", "monitor_name", "location", "target_url"]
        )

        self.http_check_response_time = Gauge(
            "f5xc_synthetic_http_check_response_time_seconds",
            "HTTP synthetic check response time",
            ["namespace", "monitor_name", "location", "target_url"]
        )

        self.http_check_status_code = Gauge(
            "f5xc_synthetic_http_check_status_code",
            "HTTP synthetic check status code",
            ["namespace", "monitor_name", "location", "target_url"]
        )

        self.http_check_connect_time = Gauge(
            "f5xc_synthetic_http_check_connect_time_seconds",
            "HTTP synthetic check connection time",
            ["namespace", "monitor_name", "location", "target_url"]
        )

        self.http_check_ttfb = Gauge(
            "f5xc_synthetic_http_check_ttfb_seconds",
            "HTTP synthetic check time to first byte",
            ["namespace", "monitor_name", "location", "target_url"]
        )

        # DNS synthetic monitoring metrics
        self.dns_check_success = Gauge(
            "f5xc_synthetic_dns_check_success",
            "Whether DNS synthetic check succeeded (1=success, 0=failure)",
            ["namespace", "monitor_name", "location", "target_domain"]
        )

        self.dns_check_response_time = Gauge(
            "f5xc_synthetic_dns_check_response_time_seconds",
            "DNS synthetic check response time",
            ["namespace", "monitor_name", "location", "target_domain"]
        )

        self.dns_check_record_count = Gauge(
            "f5xc_synthetic_dns_check_record_count",
            "Number of DNS records returned",
            ["namespace", "monitor_name", "location", "target_domain", "record_type"]
        )

        # TCP synthetic monitoring metrics
        self.tcp_check_success = Gauge(
            "f5xc_synthetic_tcp_check_success",
            "Whether TCP synthetic check succeeded (1=success, 0=failure)",
            ["namespace", "monitor_name", "location", "target_host", "target_port"]
        )

        self.tcp_check_connect_time = Gauge(
            "f5xc_synthetic_tcp_check_connect_time_seconds",
            "TCP synthetic check connection time",
            ["namespace", "monitor_name", "location", "target_host", "target_port"]
        )

        # Ping synthetic monitoring metrics
        self.ping_check_success = Gauge(
            "f5xc_synthetic_ping_check_success",
            "Whether ping synthetic check succeeded (1=success, 0=failure)",
            ["namespace", "monitor_name", "location", "target_host"]
        )

        self.ping_check_rtt = Gauge(
            "f5xc_synthetic_ping_check_rtt_seconds",
            "Ping synthetic check round trip time",
            ["namespace", "monitor_name", "location", "target_host"]
        )

        self.ping_check_packet_loss = Gauge(
            "f5xc_synthetic_ping_check_packet_loss_percentage",
            "Ping synthetic check packet loss percentage",
            ["namespace", "monitor_name", "location", "target_host"]
        )

        # Aggregate metrics
        self.synthetic_checks_total = Counter(
            "f5xc_synthetic_checks_total",
            "Total number of synthetic checks performed",
            ["namespace", "monitor_type", "location", "status"]
        )

        self.synthetic_uptime_percentage = Gauge(
            "f5xc_synthetic_uptime_percentage",
            "Synthetic monitoring uptime percentage",
            ["namespace", "monitor_name", "location"]
        )

        # Collection metrics
        self.synthetic_collection_success = Gauge(
            "f5xc_synthetic_collection_success",
            "Whether synthetic monitoring collection succeeded",
            ["namespace"]
        )

        self.synthetic_collection_duration = Gauge(
            "f5xc_synthetic_collection_duration_seconds",
            "Time taken to collect synthetic monitoring metrics",
            ["namespace"]
        )

    def collect_metrics(self, namespace: str = "system") -> None:
        """Collect synthetic monitoring metrics for the specified namespace."""
        start_time = time.time()

        try:
            logger.info("Collecting synthetic monitoring metrics", namespace=namespace)

            # Get synthetic monitoring data
            synthetic_data = self.client.get_synthetic_monitoring_metrics(namespace)

            # Process synthetic monitoring data
            self._process_synthetic_monitoring_data(synthetic_data, namespace)

            # Mark collection as successful
            self.synthetic_collection_success.labels(namespace=namespace).set(1)

            collection_duration = time.time() - start_time
            self.synthetic_collection_duration.labels(namespace=namespace).set(collection_duration)

            logger.info(
                "Synthetic monitoring metrics collection successful",
                namespace=namespace,
                duration=collection_duration,
            )

        except F5XCAPIError as e:
            logger.error(
                "Failed to collect synthetic monitoring metrics",
                namespace=namespace,
                error=str(e),
                exc_info=True,
            )
            self.synthetic_collection_success.labels(namespace=namespace).set(0)
            raise

    def _process_synthetic_monitoring_data(self, data: Dict[str, Any], namespace: str) -> None:
        """Process synthetic monitoring data and update metrics."""
        logger.debug("Processing synthetic monitoring data", namespace=namespace)

        # Process HTTP monitors
        http_monitors = data.get("http_monitors", [])
        for monitor in http_monitors:
            self._process_http_monitor(monitor, namespace)

        # Process DNS monitors
        dns_monitors = data.get("dns_monitors", [])
        for monitor in dns_monitors:
            self._process_dns_monitor(monitor, namespace)

        # Process TCP monitors
        tcp_monitors = data.get("tcp_monitors", [])
        for monitor in tcp_monitors:
            self._process_tcp_monitor(monitor, namespace)

        # Process Ping monitors
        ping_monitors = data.get("ping_monitors", [])
        for monitor in ping_monitors:
            self._process_ping_monitor(monitor, namespace)

        # Process aggregate statistics
        aggregate_stats = data.get("aggregate_stats", [])
        for stats in aggregate_stats:
            self._process_aggregate_stats(stats, namespace)

    def _process_http_monitor(self, monitor: Dict[str, Any], namespace: str) -> None:
        """Process HTTP monitor data."""
        monitor_name = monitor.get("name", "unknown")
        target_url = monitor.get("target_url", "unknown")

        results = monitor.get("results", [])
        for result in results:
            location = result.get("location", "unknown")
            success = result.get("success", False)
            response_time = result.get("response_time", 0)
            status_code = result.get("status_code", 0)
            connect_time = result.get("connect_time", 0)
            ttfb = result.get("ttfb", 0)

            # Set success metric
            self.http_check_success.labels(
                namespace=namespace,
                monitor_name=monitor_name,
                location=location,
                target_url=target_url
            ).set(1 if success else 0)

            # Set response time metric
            try:
                self.http_check_response_time.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_url=target_url
                ).set(float(response_time) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError):
                pass

            # Set status code metric
            try:
                self.http_check_status_code.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_url=target_url
                ).set(float(status_code))
            except (ValueError, TypeError):
                pass

            # Set connect time metric
            try:
                self.http_check_connect_time.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_url=target_url
                ).set(float(connect_time) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError):
                pass

            # Set TTFB metric
            try:
                self.http_check_ttfb.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_url=target_url
                ).set(float(ttfb) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError):
                pass

            # Update total checks counter
            status = "success" if success else "failure"
            self.synthetic_checks_total.labels(
                namespace=namespace,
                monitor_type="http",
                location=location,
                status=status
            )._value._value += 1

    def _process_dns_monitor(self, monitor: Dict[str, Any], namespace: str) -> None:
        """Process DNS monitor data."""
        monitor_name = monitor.get("name", "unknown")
        target_domain = monitor.get("target_domain", "unknown")

        results = monitor.get("results", [])
        for result in results:
            location = result.get("location", "unknown")
            success = result.get("success", False)
            response_time = result.get("response_time", 0)
            records = result.get("records", [])

            # Set success metric
            self.dns_check_success.labels(
                namespace=namespace,
                monitor_name=monitor_name,
                location=location,
                target_domain=target_domain
            ).set(1 if success else 0)

            # Set response time metric
            try:
                self.dns_check_response_time.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_domain=target_domain
                ).set(float(response_time) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError):
                pass

            # Process DNS records
            record_counts = {}
            for record in records:
                record_type = record.get("type", "unknown")
                record_counts[record_type] = record_counts.get(record_type, 0) + 1

            for record_type, count in record_counts.items():
                self.dns_check_record_count.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_domain=target_domain,
                    record_type=record_type
                ).set(count)

            # Update total checks counter
            status = "success" if success else "failure"
            self.synthetic_checks_total.labels(
                namespace=namespace,
                monitor_type="dns",
                location=location,
                status=status
            )._value._value += 1

    def _process_tcp_monitor(self, monitor: Dict[str, Any], namespace: str) -> None:
        """Process TCP monitor data."""
        monitor_name = monitor.get("name", "unknown")
        target_host = monitor.get("target_host", "unknown")
        target_port = monitor.get("target_port", "unknown")

        results = monitor.get("results", [])
        for result in results:
            location = result.get("location", "unknown")
            success = result.get("success", False)
            connect_time = result.get("connect_time", 0)

            # Set success metric
            self.tcp_check_success.labels(
                namespace=namespace,
                monitor_name=monitor_name,
                location=location,
                target_host=target_host,
                target_port=str(target_port)
            ).set(1 if success else 0)

            # Set connect time metric
            try:
                self.tcp_check_connect_time.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_host=target_host,
                    target_port=str(target_port)
                ).set(float(connect_time) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError):
                pass

            # Update total checks counter
            status = "success" if success else "failure"
            self.synthetic_checks_total.labels(
                namespace=namespace,
                monitor_type="tcp",
                location=location,
                status=status
            )._value._value += 1

    def _process_ping_monitor(self, monitor: Dict[str, Any], namespace: str) -> None:
        """Process Ping monitor data."""
        monitor_name = monitor.get("name", "unknown")
        target_host = monitor.get("target_host", "unknown")

        results = monitor.get("results", [])
        for result in results:
            location = result.get("location", "unknown")
            success = result.get("success", False)
            rtt = result.get("rtt", 0)
            packet_loss = result.get("packet_loss", 0)

            # Set success metric
            self.ping_check_success.labels(
                namespace=namespace,
                monitor_name=monitor_name,
                location=location,
                target_host=target_host
            ).set(1 if success else 0)

            # Set RTT metric
            try:
                self.ping_check_rtt.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_host=target_host
                ).set(float(rtt) / 1000.0)  # Convert ms to seconds
            except (ValueError, TypeError):
                pass

            # Set packet loss metric
            try:
                self.ping_check_packet_loss.labels(
                    namespace=namespace,
                    monitor_name=monitor_name,
                    location=location,
                    target_host=target_host
                ).set(float(packet_loss))
            except (ValueError, TypeError):
                pass

            # Update total checks counter
            status = "success" if success else "failure"
            self.synthetic_checks_total.labels(
                namespace=namespace,
                monitor_type="ping",
                location=location,
                status=status
            )._value._value += 1

    def _process_aggregate_stats(self, stats: Dict[str, Any], namespace: str) -> None:
        """Process aggregate statistics."""
        monitor_name = stats.get("monitor_name", "unknown")
        location = stats.get("location", "unknown")
        uptime_percentage = stats.get("uptime_percentage", 0)

        try:
            self.synthetic_uptime_percentage.labels(
                namespace=namespace,
                monitor_name=monitor_name,
                location=location
            ).set(float(uptime_percentage))
        except (ValueError, TypeError):
            pass