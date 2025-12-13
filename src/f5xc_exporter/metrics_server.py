"""Prometheus metrics HTTP server."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, Optional

import structlog
from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest

from .client import F5XCClient
from .collectors import (
    QuotaCollector,
    ServiceGraphCollector,
    SecurityCollector,
    SyntheticMonitoringCollector
)
from .config import Config

logger = structlog.get_logger()


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/metrics":
            self._handle_metrics()
        elif self.path == "/health":
            self._handle_health()
        else:
            self._handle_not_found()

    def _handle_metrics(self) -> None:
        """Handle /metrics endpoint."""
        try:
            registry = getattr(self.server, 'registry', None)
            if registry:
                metrics = generate_latest(registry)
                self.send_response(200)
                self.send_header('Content-Type', CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(metrics)
            else:
                self._send_error_response(500, "Metrics registry not available")
        except Exception as e:
            logger.error("Error generating metrics", error=str(e), exc_info=True)
            self._send_error_response(500, "Internal server error")

    def _handle_health(self) -> None:
        """Handle /health endpoint."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_not_found(self) -> None:
        """Handle 404 responses."""
        self._send_error_response(404, "Not found")

    def _send_error_response(self, status_code: int, message: str) -> None:
        """Send error response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))

    def log_message(self, format_string: str, *args: Any) -> None:
        """Override to use structured logging."""
        logger.info("HTTP request", message=format_string % args)


class MetricsServer:
    """Prometheus metrics server for F5XC exporter."""

    def __init__(self, config: Config):
        """Initialize metrics server."""
        self.config = config
        self.registry = CollectorRegistry()
        self.client = F5XCClient(config)

        # Initialize collectors and register them with the registry
        self.quota_collector = QuotaCollector(self.client)
        self.service_graph_collector = ServiceGraphCollector(self.client)
        self.security_collector = SecurityCollector(self.client)
        self.synthetic_monitoring_collector = SyntheticMonitoringCollector(self.client)

        # Register individual metrics with Prometheus registry
        # Quota metrics
        self.registry.register(self.quota_collector.quota_limit)
        self.registry.register(self.quota_collector.quota_current)
        self.registry.register(self.quota_collector.quota_utilization)
        self.registry.register(self.quota_collector.quota_collection_success)
        self.registry.register(self.quota_collector.quota_collection_duration)

        # Service graph metrics
        self.registry.register(self.service_graph_collector.http_requests_total)
        self.registry.register(self.service_graph_collector.http_request_duration)
        self.registry.register(self.service_graph_collector.http_request_size_bytes)
        self.registry.register(self.service_graph_collector.http_response_size_bytes)
        self.registry.register(self.service_graph_collector.http_connections_active)
        self.registry.register(self.service_graph_collector.tcp_connections_total)
        self.registry.register(self.service_graph_collector.tcp_connections_active)
        self.registry.register(self.service_graph_collector.tcp_bytes_transmitted)
        self.registry.register(self.service_graph_collector.service_graph_collection_success)
        self.registry.register(self.service_graph_collector.service_graph_collection_duration)

        # Security metrics
        self.registry.register(self.security_collector.waf_requests_total)
        self.registry.register(self.security_collector.waf_blocked_requests_total)
        self.registry.register(self.security_collector.waf_rule_hits_total)
        self.registry.register(self.security_collector.bot_requests_total)
        self.registry.register(self.security_collector.bot_blocked_requests_total)
        self.registry.register(self.security_collector.bot_score)
        self.registry.register(self.security_collector.api_endpoints_discovered)
        self.registry.register(self.security_collector.api_schema_violations_total)
        self.registry.register(self.security_collector.ddos_attacks_total)
        self.registry.register(self.security_collector.ddos_mitigation_active)
        self.registry.register(self.security_collector.security_events_total)
        self.registry.register(self.security_collector.security_alerts_total)
        self.registry.register(self.security_collector.security_collection_success)
        self.registry.register(self.security_collector.security_collection_duration)

        # Synthetic monitoring metrics
        self.registry.register(self.synthetic_monitoring_collector.http_check_success)
        self.registry.register(self.synthetic_monitoring_collector.http_check_response_time)
        self.registry.register(self.synthetic_monitoring_collector.http_check_status_code)
        self.registry.register(self.synthetic_monitoring_collector.http_check_connect_time)
        self.registry.register(self.synthetic_monitoring_collector.http_check_ttfb)
        self.registry.register(self.synthetic_monitoring_collector.dns_check_success)
        self.registry.register(self.synthetic_monitoring_collector.dns_check_response_time)
        self.registry.register(self.synthetic_monitoring_collector.dns_check_record_count)
        self.registry.register(self.synthetic_monitoring_collector.tcp_check_success)
        self.registry.register(self.synthetic_monitoring_collector.tcp_check_connect_time)
        self.registry.register(self.synthetic_monitoring_collector.ping_check_success)
        self.registry.register(self.synthetic_monitoring_collector.ping_check_rtt)
        self.registry.register(self.synthetic_monitoring_collector.ping_check_packet_loss)
        self.registry.register(self.synthetic_monitoring_collector.synthetic_checks_total)
        self.registry.register(self.synthetic_monitoring_collector.synthetic_uptime_percentage)
        self.registry.register(self.synthetic_monitoring_collector.synthetic_collection_success)
        self.registry.register(self.synthetic_monitoring_collector.synthetic_collection_duration)

        # Collection threads
        self.collection_threads: Dict[str, threading.Thread] = {}
        self.stop_event = threading.Event()

        # HTTP server
        self.httpd: Optional[HTTPServer] = None

    def start(self) -> None:
        """Start the metrics server and collection threads."""
        logger.info("Starting F5XC Prometheus exporter", port=self.config.f5xc_exp_http_port)

        # Start collection threads
        self._start_collection_threads()

        # Start HTTP server
        self._start_http_server()

    def _start_collection_threads(self) -> None:
        """Start metric collection threads."""
        # Quota metrics collection
        if self.config.f5xc_quota_interval > 0:
            quota_thread = threading.Thread(
                target=self._collect_quota_metrics,
                name="quota-collector",
                daemon=True
            )
            quota_thread.start()
            self.collection_threads["quota"] = quota_thread
            logger.info("Started quota metrics collection", interval=self.config.f5xc_quota_interval)

        # Service graph metrics collection (combining HTTP/TCP/UDP LB intervals)
        service_graph_interval = min(
            self.config.f5xc_http_lb_interval,
            self.config.f5xc_tcp_lb_interval,
            self.config.f5xc_udp_lb_interval
        )
        if service_graph_interval > 0:
            service_graph_thread = threading.Thread(
                target=self._collect_service_graph_metrics,
                name="service-graph-collector",
                daemon=True
            )
            service_graph_thread.start()
            self.collection_threads["service_graph"] = service_graph_thread
            logger.info("Started service graph metrics collection", interval=service_graph_interval)

        # Security metrics collection
        if self.config.f5xc_security_interval > 0:
            security_thread = threading.Thread(
                target=self._collect_security_metrics,
                name="security-collector",
                daemon=True
            )
            security_thread.start()
            self.collection_threads["security"] = security_thread
            logger.info("Started security metrics collection", interval=self.config.f5xc_security_interval)

        # Synthetic monitoring metrics collection
        if self.config.f5xc_synthetic_interval > 0:
            synthetic_thread = threading.Thread(
                target=self._collect_synthetic_metrics,
                name="synthetic-collector",
                daemon=True
            )
            synthetic_thread.start()
            self.collection_threads["synthetic"] = synthetic_thread
            logger.info("Started synthetic monitoring metrics collection", interval=self.config.f5xc_synthetic_interval)

    def _start_http_server(self) -> None:
        """Start HTTP server for metrics endpoint."""
        self.httpd = HTTPServer(("", self.config.f5xc_exp_http_port), MetricsHandler)
        self.httpd.registry = self.registry

        logger.info("Starting HTTP server", port=self.config.f5xc_exp_http_port)

        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down")
            self.stop()

    def _collect_quota_metrics(self) -> None:
        """Collect quota metrics periodically."""
        while not self.stop_event.is_set():
            try:
                self.quota_collector.collect_metrics()
            except Exception as e:
                logger.error(
                    "Error in quota metrics collection",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next collection interval
            if self.stop_event.wait(self.config.f5xc_quota_interval):
                break

    def _collect_service_graph_metrics(self) -> None:
        """Collect service graph metrics periodically."""
        service_graph_interval = min(
            self.config.f5xc_http_lb_interval,
            self.config.f5xc_tcp_lb_interval,
            self.config.f5xc_udp_lb_interval
        )

        while not self.stop_event.is_set():
            try:
                self.service_graph_collector.collect_metrics()
            except Exception as e:
                logger.error(
                    "Error in service graph metrics collection",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next collection interval
            if self.stop_event.wait(service_graph_interval):
                break

    def _collect_security_metrics(self) -> None:
        """Collect security metrics periodically."""
        while not self.stop_event.is_set():
            try:
                self.security_collector.collect_metrics()
            except Exception as e:
                logger.error(
                    "Error in security metrics collection",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next collection interval
            if self.stop_event.wait(self.config.f5xc_security_interval):
                break

    def _collect_synthetic_metrics(self) -> None:
        """Collect synthetic monitoring metrics periodically."""
        while not self.stop_event.is_set():
            try:
                self.synthetic_monitoring_collector.collect_metrics()
            except Exception as e:
                logger.error(
                    "Error in synthetic monitoring metrics collection",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next collection interval
            if self.stop_event.wait(self.config.f5xc_synthetic_interval):
                break

    def stop(self) -> None:
        """Stop the metrics server and collection threads."""
        logger.info("Stopping F5XC Prometheus exporter")

        # Signal threads to stop
        self.stop_event.set()

        # Stop HTTP server
        if self.httpd:
            self.httpd.shutdown()

        # Wait for collection threads to finish
        for thread_name, thread in self.collection_threads.items():
            logger.info(f"Waiting for {thread_name} thread to stop")
            thread.join(timeout=5)

        # Close F5XC client
        self.client.close()

        logger.info("F5XC Prometheus exporter stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get server status information."""
        service_graph_interval = min(
            self.config.f5xc_http_lb_interval,
            self.config.f5xc_tcp_lb_interval,
            self.config.f5xc_udp_lb_interval
        ) if min(self.config.f5xc_http_lb_interval, self.config.f5xc_tcp_lb_interval, self.config.f5xc_udp_lb_interval) > 0 else 0

        return {
            "config": {
                "port": self.config.f5xc_exp_http_port,
                "quota_interval": self.config.f5xc_quota_interval,
                "service_graph_interval": service_graph_interval,
                "security_interval": self.config.f5xc_security_interval,
                "synthetic_interval": self.config.f5xc_synthetic_interval,
            },
            "threads": {
                name: thread.is_alive()
                for name, thread in self.collection_threads.items()
            },
            "server_running": self.httpd is not None,
        }