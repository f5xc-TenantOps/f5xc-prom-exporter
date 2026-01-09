"""Tests for metrics server integration."""

import threading
import time
from unittest.mock import Mock, patch

import pytest
import requests

from f5xc_exporter.config import Config
from f5xc_exporter.metrics_server import MetricsServer


class TestMetricsServerIntegration:
    """Test metrics server integration scenarios."""

    @pytest.fixture
    def test_config(self, request):
        """Test configuration with unique port per test.

        Uses test name hash to generate unique port, safe for parallel execution.
        Port range: 8081-9080 (1000 ports available).
        """
        # Generate deterministic port from test name to avoid parallel test conflicts
        port = 8081 + (hash(request.node.name) % 1000)
        return Config(
            F5XC_TENANT_URL="https://test.console.ves.volterra.io",
            F5XC_ACCESS_TOKEN="test-token",
            F5XC_EXP_HTTP_PORT=port,
            F5XC_EXP_LOG_LEVEL="DEBUG",
        )

    @pytest.fixture
    def mock_f5xc_client(self):
        """Mock F5XC client with common default responses.

        Provides a pre-configured mock client with typical successful
        responses. Tests can override specific methods as needed.
        """
        with patch("f5xc_exporter.metrics_server.F5XCClient") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Default successful responses for all collectors
            mock_client.list_namespaces.return_value = ["test-ns"]
            mock_client.get_quota_usage.return_value = {"quota_usage": {}}
            mock_client.get_all_lb_metrics_for_namespace.return_value = {"http": [], "tcp": [], "udp": []}
            mock_client.get_app_firewall_metrics_for_namespace.return_value = {"data": []}
            mock_client.get_security_event_counts_for_namespace.return_value = {"aggs": {}}
            mock_client.get_synthetic_summary.return_value = {
                "critical_monitor_count": 0,
                "number_of_monitors": 0,
                "healthy_monitor_count": 0,
            }
            mock_client.get_dns_zone_metrics.return_value = {"items": []}
            mock_client.get_dns_lb_health_status.return_value = {"items": []}
            mock_client.get_dns_lb_pool_member_health.return_value = {"items": []}

            yield mock_client

    def test_metrics_server_http_endpoint_integration(self, test_config, mock_f5xc_client):
        """Test complete metrics server with real HTTP endpoint."""
        # Override quota response with specific test data
        mock_f5xc_client.get_quota_usage.return_value = {
            "quota_usage": {"load_balancer": {"limit": {"maximum": 10}, "usage": {"current": 5}}}
        }

        # Create and start metrics server
        server = MetricsServer(test_config)

        # Start server in background thread
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(1.0)

        try:
            # Test health endpoint - now returns JSON
            health_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/health", timeout=5)
            assert health_response.status_code == 200
            health_data = health_response.json()
            assert health_data["status"] == "healthy"

            # Wait for initial metrics collection
            time.sleep(2.0)

            # Test metrics endpoint
            metrics_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/metrics", timeout=5)
            assert metrics_response.status_code == 200

            metrics_text = metrics_response.text

            # Verify metrics output is not empty
            assert len(metrics_text) > 0

            # Verify specific metrics are present
            assert "f5xc_quota_limit" in metrics_text
            assert "f5xc_quota_current" in metrics_text
            assert "f5xc_quota_utilization" in metrics_text
            assert "f5xc_quota_collection_success" in metrics_text

            # Verify LB metrics registration
            assert "f5xc_http_lb_request_rate" in metrics_text

            # Verify security collection success metrics
            assert "f5xc_security_collection_success" in metrics_text
            assert "f5xc_synthetic_collection_success" in metrics_text

            # Verify Content-Type header
            assert "text/plain" in metrics_response.headers.get("Content-Type", "")

        finally:
            # Clean up
            server.stop()
            time.sleep(0.5)

    def test_metrics_server_registry_initialization(self, test_config, mock_f5xc_client):
        """Test that metrics server properly initializes Prometheus registry."""
        from prometheus_client import generate_latest

        # Create metrics server
        server = MetricsServer(test_config)

        # Test that registry is properly initialized
        assert server.registry is not None

        # Test that collectors are created
        assert server.quota_collector is not None
        assert server.lb_collector is not None
        assert server.security_collector is not None
        assert server.synthetic_monitoring_collector is not None

        # Test that metrics can be generated from registry
        # This would have caught the original bug
        metrics_output = generate_latest(server.registry)
        assert metrics_output is not None

        # Should contain metric metadata even without data
        metrics_str = metrics_output.decode("utf-8")
        assert "f5xc_quota_limit" in metrics_str
        assert "f5xc_http_lb_request_rate" in metrics_str
        assert "f5xc_security_collection_success" in metrics_str
        assert "f5xc_synthetic_collection_success" in metrics_str

    def test_metrics_endpoint_error_handling(self, test_config, mock_f5xc_client):
        """Test metrics endpoint handles registry errors gracefully."""
        server = MetricsServer(test_config)

        # Start server
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.5)

        try:
            # Simulate registry error by corrupting it on the httpd
            # (server.registry change alone won't affect the httpd reference)
            if server.httpd:
                server.httpd.registry = None

            # Test that metrics endpoint returns 500 but doesn't crash
            metrics_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/metrics", timeout=5)
            assert metrics_response.status_code == 500

            # Server should still be responsive
            health_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/health", timeout=5)
            assert health_response.status_code == 200

        finally:
            server.stop()
            time.sleep(0.5)

    def test_404_endpoint(self, test_config, mock_f5xc_client):
        """Test that unknown endpoints return 404."""
        server = MetricsServer(test_config)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.5)

        try:
            response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/unknown", timeout=5)
            assert response.status_code == 404
            assert response.text == "Not found"

        finally:
            server.stop()
            time.sleep(0.5)

    def test_health_endpoint_json_response(self, test_config, mock_f5xc_client):
        """Test /health endpoint returns detailed JSON response."""
        server = MetricsServer(test_config)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        time.sleep(0.5)

        try:
            response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/health", timeout=5)
            assert response.status_code == 200
            assert response.headers["Content-Type"] == "application/json"

            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert "version" in data
            assert "collectors" in data

            # Verify collector status
            collectors = data["collectors"]
            assert "quota" in collectors
            assert "security" in collectors
            assert "synthetic" in collectors
            assert "dns" in collectors
            assert "loadbalancer" in collectors

        finally:
            server.stop()
            time.sleep(1.0)  # Give more time for port cleanup

    def test_ready_endpoint_when_api_accessible(self, test_config, mock_f5xc_client):
        """Test /ready endpoint returns 200 when F5XC API is accessible."""
        # Override to return multiple namespaces
        mock_f5xc_client.list_namespaces.return_value = ["ns1", "ns2", "ns3"]

        server = MetricsServer(test_config)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        # Wait longer for initial readiness check to complete
        time.sleep(1.0)

        try:
            response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/ready", timeout=5)
            assert response.status_code == 200
            assert response.headers["Content-Type"] == "application/json"

            data = response.json()
            assert data["status"] == "ready"
            assert data["api_accessible"] is True
            assert data["namespace_count"] == 3
            assert "timestamp" in data
            assert "last_check" in data

        finally:
            server.stop()
            time.sleep(1.0)  # Give more time for port cleanup

    def test_ready_endpoint_when_api_not_accessible(self, test_config, mock_f5xc_client):
        """Test /ready endpoint returns 503 when F5XC API is not accessible."""
        # Make all list_namespaces calls fail to simulate API being down
        mock_f5xc_client.list_namespaces.side_effect = Exception("Connection refused")

        server = MetricsServer(test_config)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        # Wait longer for initial readiness check to complete
        time.sleep(1.0)

        try:
            response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/ready", timeout=5)
            assert response.status_code == 503
            assert response.headers["Content-Type"] == "application/json"

            data = response.json()
            assert data["status"] == "not_ready"
            assert data["api_accessible"] is False
            assert "error" in data
            assert "timestamp" in data
            assert "last_check" in data

        finally:
            server.stop()
            time.sleep(1.0)  # Give more time for port cleanup
