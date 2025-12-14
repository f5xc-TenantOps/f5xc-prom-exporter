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
    def test_config_8081(self):
        """Test configuration with port 8081."""
        return Config(
            F5XC_TENANT_URL="https://test.console.ves.volterra.io",
            F5XC_ACCESS_TOKEN="test-token",
            F5XC_EXP_HTTP_PORT=8081,
            F5XC_EXP_LOG_LEVEL="DEBUG",
        )

    @pytest.fixture
    def test_config_8082(self):
        """Test configuration with port 8082."""
        return Config(
            F5XC_TENANT_URL="https://test.console.ves.volterra.io",
            F5XC_ACCESS_TOKEN="test-token",
            F5XC_EXP_HTTP_PORT=8082,
            F5XC_EXP_LOG_LEVEL="DEBUG",
        )

    @pytest.fixture
    def test_config_8083(self):
        """Test configuration with port 8083."""
        return Config(
            F5XC_TENANT_URL="https://test.console.ves.volterra.io",
            F5XC_ACCESS_TOKEN="test-token",
            F5XC_EXP_HTTP_PORT=8083,
            F5XC_EXP_LOG_LEVEL="DEBUG",
        )

    @pytest.fixture
    def test_config_8084(self):
        """Test configuration with port 8084."""
        return Config(
            F5XC_TENANT_URL="https://test.console.ves.volterra.io",
            F5XC_ACCESS_TOKEN="test-token",
            F5XC_EXP_HTTP_PORT=8084,
            F5XC_EXP_LOG_LEVEL="DEBUG",
        )

    def test_metrics_server_http_endpoint_integration(self, test_config_8081):
        """Test complete metrics server with real HTTP endpoint."""
        test_config = test_config_8081
        # Mock the F5XC client to avoid real API calls
        with patch('f5xc_exporter.metrics_server.F5XCClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock successful API calls
            mock_client.get_quota_usage.return_value = {
                "quota_usage": {
                    "load_balancer": {
                        "limit": {"maximum": 10},
                        "usage": {"current": 5}
                    }
                }
            }

            mock_client.list_namespaces.return_value = ["test-ns"]
            mock_client.get_all_lb_metrics_for_namespace.return_value = {
                "http": [],
                "tcp": [],
                "udp": []
            }

            # Mock security API calls (2 calls per namespace)
            mock_client.get_app_firewall_metrics_for_namespace.return_value = {"data": []}
            mock_client.get_security_event_counts_for_namespace.return_value = {"aggs": {}}

            # Mock synthetic monitoring
            mock_client.get_synthetic_monitoring_metrics.return_value = {"monitors": []}

            # Create and start metrics server
            server = MetricsServer(test_config)

            # Start server in background thread
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()

            # Wait for server to start
            time.sleep(1.0)

            try:
                # Test health endpoint
                health_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/health", timeout=5)
                assert health_response.status_code == 200
                assert health_response.text == "OK"

                # Wait for initial metrics collection
                time.sleep(2.0)

                # Test metrics endpoint
                metrics_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/metrics", timeout=5)
                assert metrics_response.status_code == 200

                metrics_text = metrics_response.text

                # Verify metrics output is not empty
                assert len(metrics_text) > 0

                # Verify specific metrics are present
                assert 'f5xc_quota_limit' in metrics_text
                assert 'f5xc_quota_current' in metrics_text
                assert 'f5xc_quota_utilization' in metrics_text
                assert 'f5xc_quota_collection_success' in metrics_text

                # Verify LB metrics registration
                assert 'f5xc_http_lb_request_rate' in metrics_text

                # Verify security collection success metrics
                assert 'f5xc_security_collection_success' in metrics_text
                assert 'f5xc_synthetic_collection_success' in metrics_text

                # Verify Content-Type header
                assert 'text/plain' in metrics_response.headers.get('Content-Type', '')

            finally:
                # Clean up
                server.stop()
                time.sleep(0.5)

    def test_metrics_server_registry_initialization(self, test_config_8082):
        """Test that metrics server properly initializes Prometheus registry."""
        test_config = test_config_8082
        from prometheus_client import generate_latest

        with patch('f5xc_exporter.metrics_server.F5XCClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

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
            metrics_str = metrics_output.decode('utf-8')
            assert 'f5xc_quota_limit' in metrics_str
            assert 'f5xc_http_lb_request_rate' in metrics_str
            assert 'f5xc_security_collection_success' in metrics_str
            assert 'f5xc_synthetic_collection_success' in metrics_str

    def test_metrics_endpoint_error_handling(self, test_config_8083):
        """Test metrics endpoint handles registry errors gracefully."""
        test_config = test_config_8083
        with patch('f5xc_exporter.metrics_server.F5XCClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

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

    def test_404_endpoint(self, test_config_8084):
        """Test that unknown endpoints return 404."""
        test_config = test_config_8084
        with patch('f5xc_exporter.metrics_server.F5XCClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

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
