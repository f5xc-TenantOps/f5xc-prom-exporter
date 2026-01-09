"""Prometheus metrics HTTP server."""

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

import structlog
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from . import __version__
from .client import F5XCClient
from .collectors import (
    DNSCollector,
    LoadBalancerCollector,
    QuotaCollector,
    SecurityCollector,
    SyntheticMonitoringCollector,
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
        elif self.path == "/ready":
            self._handle_ready()
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
        """Handle /health endpoint.

        Always returns 200 if the server is running.
        Returns JSON with status, version, and collector information.
        """
        try:
            server = getattr(self.server, 'metrics_server', None)
            if not server:
                self._send_error_response(500, "Server not properly initialized")
                return

            # Get collector status
            collectors = {
                "quota": "enabled" if server.config.f5xc_quota_interval > 0 else "disabled",
                "security": "enabled" if server.config.f5xc_security_interval > 0 else "disabled",
                "synthetic": "enabled" if server.config.f5xc_synthetic_interval > 0 else "disabled",
                "dns": "enabled" if server.config.f5xc_dns_interval > 0 else "disabled",
            }

            # Check load balancer collector (enabled if any LB interval > 0)
            lb_interval = max(
                server.config.f5xc_http_lb_interval,
                server.config.f5xc_tcp_lb_interval,
                server.config.f5xc_udp_lb_interval
            )
            collectors["loadbalancer"] = "enabled" if lb_interval > 0 else "disabled"

            response_data = {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": __version__,
                "collectors": collectors,
            }

            self._send_json_response(200, response_data)
        except Exception as e:
            logger.error("Error in health check", error=str(e), exc_info=True)
            self._send_error_response(500, "Health check failed")

    def _handle_ready(self) -> None:
        """Handle /ready endpoint.

        Returns cached readiness state (updated by background thread).
        Returns 200 if F5XC API is reachable and authenticated.
        Returns 503 if the API is not accessible.
        """
        try:
            server = getattr(self.server, 'metrics_server', None)
            if not server:
                self._send_error_response(500, "Server not properly initialized")
                return

            # Return cached readiness state (no blocking API call)
            with server._readiness_lock:
                is_ready = server._is_ready
                namespace_count = server._ready_namespace_count
                error = server._ready_error
                last_check = server._ready_last_check

            if is_ready:
                response_data = {
                    "status": "ready",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "api_accessible": True,
                    "namespace_count": namespace_count,
                    "last_check": last_check.isoformat(),
                }
                self._send_json_response(200, response_data)
            else:
                response_data = {
                    "status": "not_ready",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "api_accessible": False,
                    "error": error or "API check has not completed yet",
                    "last_check": last_check.isoformat(),
                }
                self._send_json_response(503, response_data)
        except Exception as e:
            logger.error("Error in readiness check", error=str(e), exc_info=True)
            self._send_error_response(500, "Readiness check failed")

    def _handle_not_found(self) -> None:
        """Handle 404 responses."""
        self._send_error_response(404, "Not found")

    def _send_json_response(self, status_code: int, data: dict[str, Any]) -> None:
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        json_data = json.dumps(data)
        self.wfile.write(json_data.encode('utf-8'))

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
        tenant = config.tenant_name
        self.quota_collector = QuotaCollector(self.client, tenant)
        self.security_collector = SecurityCollector(self.client, tenant)
        self.synthetic_monitoring_collector = SyntheticMonitoringCollector(self.client, tenant)
        self.lb_collector = LoadBalancerCollector(self.client, tenant)
        self.dns_collector = DNSCollector(self.client, tenant)

        # Register individual metrics with Prometheus registry
        # Quota metrics
        self.registry.register(self.quota_collector.quota_limit)
        self.registry.register(self.quota_collector.quota_current)
        self.registry.register(self.quota_collector.quota_utilization)
        self.registry.register(self.quota_collector.quota_collection_success)
        self.registry.register(self.quota_collector.quota_collection_duration)

        # Security metrics - Per-LB metrics (from app_firewall/metrics API)
        self.registry.register(self.security_collector.total_requests)
        self.registry.register(self.security_collector.attacked_requests)
        self.registry.register(self.security_collector.bot_detections)
        # Security metrics - Namespace event counts (from events/aggregation API)
        self.registry.register(self.security_collector.waf_events)
        self.registry.register(self.security_collector.bot_defense_events)
        self.registry.register(self.security_collector.api_events)
        self.registry.register(self.security_collector.service_policy_events)
        self.registry.register(self.security_collector.malicious_user_events)
        self.registry.register(self.security_collector.dos_events)
        # Security collection status
        self.registry.register(self.security_collector.collection_success)
        self.registry.register(self.security_collector.collection_duration)

        # Synthetic monitoring metrics (namespace-level aggregates)
        self.registry.register(self.synthetic_monitoring_collector.http_monitors_total)
        self.registry.register(self.synthetic_monitoring_collector.http_monitors_healthy)
        self.registry.register(self.synthetic_monitoring_collector.http_monitors_critical)
        self.registry.register(self.synthetic_monitoring_collector.dns_monitors_total)
        self.registry.register(self.synthetic_monitoring_collector.dns_monitors_healthy)
        self.registry.register(self.synthetic_monitoring_collector.dns_monitors_critical)
        self.registry.register(self.synthetic_monitoring_collector.collection_success)
        self.registry.register(self.synthetic_monitoring_collector.collection_duration)

        # Unified Load Balancer metrics (HTTP, TCP, UDP)
        # HTTP LB metrics
        self.registry.register(self.lb_collector.http_request_rate)
        self.registry.register(self.lb_collector.http_request_to_origin_rate)
        self.registry.register(self.lb_collector.http_error_rate)
        self.registry.register(self.lb_collector.http_error_rate_4xx)
        self.registry.register(self.lb_collector.http_error_rate_5xx)
        self.registry.register(self.lb_collector.http_latency)
        self.registry.register(self.lb_collector.http_latency_p50)
        self.registry.register(self.lb_collector.http_latency_p90)
        self.registry.register(self.lb_collector.http_latency_p99)
        self.registry.register(self.lb_collector.http_app_latency)
        self.registry.register(self.lb_collector.http_server_data_transfer_time)
        self.registry.register(self.lb_collector.http_request_throughput)
        self.registry.register(self.lb_collector.http_response_throughput)
        self.registry.register(self.lb_collector.http_client_rtt)
        self.registry.register(self.lb_collector.http_server_rtt)
        # TCP LB metrics
        self.registry.register(self.lb_collector.tcp_connection_rate)
        self.registry.register(self.lb_collector.tcp_connection_duration)
        self.registry.register(self.lb_collector.tcp_error_rate)
        self.registry.register(self.lb_collector.tcp_error_rate_client)
        self.registry.register(self.lb_collector.tcp_error_rate_upstream)
        self.registry.register(self.lb_collector.tcp_request_throughput)
        self.registry.register(self.lb_collector.tcp_response_throughput)
        self.registry.register(self.lb_collector.tcp_client_rtt)
        self.registry.register(self.lb_collector.tcp_server_rtt)
        # UDP LB metrics
        self.registry.register(self.lb_collector.udp_request_throughput)
        self.registry.register(self.lb_collector.udp_response_throughput)
        self.registry.register(self.lb_collector.udp_client_rtt)
        self.registry.register(self.lb_collector.udp_server_rtt)
        # Unified collection status metrics
        self.registry.register(self.lb_collector.collection_success)
        self.registry.register(self.lb_collector.collection_duration)
        self.registry.register(self.lb_collector.http_lb_count)
        self.registry.register(self.lb_collector.tcp_lb_count)
        self.registry.register(self.lb_collector.udp_lb_count)

        # DNS metrics
        self.registry.register(self.dns_collector.zone_query_count)
        self.registry.register(self.dns_collector.dns_lb_health)
        self.registry.register(self.dns_collector.dns_lb_pool_member_health)
        # DNS collection status
        self.registry.register(self.dns_collector.collection_success)
        self.registry.register(self.dns_collector.collection_duration)
        self.registry.register(self.dns_collector.zone_count)
        self.registry.register(self.dns_collector.dns_lb_count)

        # Collection threads
        self.collection_threads: dict[str, threading.Thread] = {}
        self.stop_event = threading.Event()

        # Readiness state (cached to avoid blocking API calls on every probe)
        self._readiness_lock = threading.Lock()
        self._is_ready = False
        self._ready_namespace_count = 0
        self._ready_error: Optional[str] = None
        self._ready_last_check = datetime.now(timezone.utc)

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
        # Start readiness monitoring thread (always enabled)
        readiness_thread = threading.Thread(
            target=self._monitor_readiness,
            name="readiness-monitor",
            daemon=True
        )
        readiness_thread.start()
        self.collection_threads["readiness"] = readiness_thread
        logger.info("Started readiness monitoring", interval=30)

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
        else:
            logger.info("Quota collector disabled (interval=0)")

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
        else:
            logger.info("Security collector disabled (interval=0)")

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
        else:
            logger.info("Synthetic monitoring collector disabled (interval=0)")

        # Unified Load Balancer metrics collection (HTTP, TCP, UDP)
        lb_interval = max(
            self.config.f5xc_http_lb_interval,
            self.config.f5xc_tcp_lb_interval,
            self.config.f5xc_udp_lb_interval
        )
        if lb_interval > 0:
            lb_thread = threading.Thread(
                target=self._collect_lb_metrics,
                name="lb-collector",
                daemon=True
            )
            lb_thread.start()
            self.collection_threads["lb"] = lb_thread
            logger.info("Started unified LB metrics collection (HTTP, TCP, UDP)", interval=lb_interval)
        else:
            logger.info("Load balancer collector disabled (interval=0)")

        # DNS metrics collection
        if self.config.f5xc_dns_interval > 0:
            dns_thread = threading.Thread(
                target=self._collect_dns_metrics,
                name="dns-collector",
                daemon=True
            )
            dns_thread.start()
            self.collection_threads["dns"] = dns_thread
            logger.info("Started DNS metrics collection", interval=self.config.f5xc_dns_interval)
        else:
            logger.info("DNS collector disabled (interval=0)")

    def _start_http_server(self) -> None:
        """Start HTTP server for metrics endpoint."""
        self.httpd = HTTPServer(("", self.config.f5xc_exp_http_port), MetricsHandler)
        self.httpd.registry = self.registry  # type: ignore[attr-defined]
        self.httpd.metrics_server = self  # type: ignore[attr-defined]

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

    def _collect_lb_metrics(self) -> None:
        """Collect all load balancer metrics (HTTP, TCP, UDP) periodically."""
        lb_interval = max(
            self.config.f5xc_http_lb_interval,
            self.config.f5xc_tcp_lb_interval,
            self.config.f5xc_udp_lb_interval
        )

        while not self.stop_event.is_set():
            try:
                self.lb_collector.collect_metrics()
            except Exception as e:
                logger.error(
                    "Error in LB metrics collection",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next collection interval
            if self.stop_event.wait(lb_interval):
                break

    def _collect_dns_metrics(self) -> None:
        """Collect DNS metrics periodically."""
        while not self.stop_event.is_set():
            try:
                self.dns_collector.collect_metrics()
            except Exception as e:
                logger.error(
                    "Error in DNS metrics collection",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next collection interval
            if self.stop_event.wait(self.config.f5xc_dns_interval):
                break

    def _check_readiness(self) -> None:
        """Check API readiness and update cached state.

        This method performs a lightweight API call to verify connectivity
        and authentication. The result is cached to avoid hammering the API
        on every readiness probe request.
        """
        try:
            # Lightweight API call to check connectivity
            namespaces = self.client.list_namespaces()

            # Update cached state
            with self._readiness_lock:
                self._is_ready = True
                self._ready_namespace_count = len(namespaces)
                self._ready_error = None
                self._ready_last_check = datetime.now(timezone.utc)

            logger.debug("Readiness check passed", namespace_count=len(namespaces))

        except Exception as e:
            # Update cached state with error
            with self._readiness_lock:
                self._is_ready = False
                self._ready_namespace_count = 0
                self._ready_error = "API connection failed"
                self._ready_last_check = datetime.now(timezone.utc)

            logger.warning("Readiness check failed", error=str(e))

    def _monitor_readiness(self) -> None:
        """Background thread to periodically check API readiness.

        Checks readiness every 30 seconds to keep cached state fresh
        without overloading the API or blocking readiness probes.
        """
        # Run initial check immediately
        self._check_readiness()

        while not self.stop_event.is_set():
            # Wait 30 seconds between checks
            if self.stop_event.wait(30):
                break

            self._check_readiness()

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

    def get_status(self) -> dict[str, Any]:
        """Get server status information."""
        lb_interval = max(
            self.config.f5xc_http_lb_interval,
            self.config.f5xc_tcp_lb_interval,
            self.config.f5xc_udp_lb_interval
        )

        return {
            "config": {
                "port": self.config.f5xc_exp_http_port,
                "quota_interval": self.config.f5xc_quota_interval,
                "security_interval": self.config.f5xc_security_interval,
                "synthetic_interval": self.config.f5xc_synthetic_interval,
                "lb_interval": lb_interval,
                "dns_interval": self.config.f5xc_dns_interval,
            },
            "threads": {
                name: thread.is_alive()
                for name, thread in self.collection_threads.items()
            },
            "server_running": self.httpd is not None,
        }
