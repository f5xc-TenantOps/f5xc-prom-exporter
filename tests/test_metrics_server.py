"""Tests for metrics server integration."""

import pytest
import threading
import time
import requests
from unittest.mock import Mock, patch

from f5xc_exporter.metrics_server import MetricsServer
from f5xc_exporter.config import Config


class TestMetricsServerIntegration:
    """Test metrics server integration scenarios."""

    @pytest.fixture
    def test_config(self):
        """Test configuration with unique port."""
        return Config(
            f5xc_tenant_url="https://test.console.ves.volterra.io",
            f5xc_access_token="test-token",
            f5xc_exp_http_port=8081,  # Use different port to avoid conflicts
            f5xc_exp_log_level="DEBUG",
        )

    def test_metrics_server_http_endpoint_integration(self, test_config):
        """Test complete metrics server with real HTTP endpoint."""
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

            mock_client.get_service_graph_data.return_value = {
                "nodes": [
                    {
                        "type": "load_balancer",
                        "name": "test-lb",
                        "stats": {
                            "http": {
                                "response_classes": {"2xx": 1000},
                                "active_connections": 25
                            }
                        }
                    }
                ]
            }

            # Mock failing security endpoints (like in real logs)
            mock_client.get_waf_metrics.side_effect = Exception("404 Not Found")
            mock_client.get_synthetic_monitoring_metrics.side_effect = Exception("404 Not Found")

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

                # Verify service graph metrics
                assert 'f5xc_service_graph_http_requests_total' in metrics_text
                assert 'f5xc_service_graph_collection_success' in metrics_text

                # Verify security collection success metrics (even if endpoints fail)
                assert 'f5xc_security_collection_success' in metrics_text
                assert 'f5xc_synthetic_collection_success' in metrics_text

                # Verify Content-Type header
                assert 'text/plain' in metrics_response.headers.get('Content-Type', '')

            finally:
                # Clean up
                server.stop()

    def test_metrics_server_registry_initialization(self, test_config):
        """Test that metrics server properly initializes Prometheus registry."""
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
            assert server.service_graph_collector is not None
            assert server.security_collector is not None
            assert server.synthetic_monitoring_collector is not None

            # Test that metrics can be generated from registry
            # This would have caught the original bug
            metrics_output = generate_latest(server.registry)
            assert metrics_output is not None

            # Should contain metric metadata even without data
            metrics_str = metrics_output.decode('utf-8')
            assert 'f5xc_quota_limit' in metrics_str
            assert 'f5xc_service_graph_http_requests_total' in metrics_str
            assert 'f5xc_security_collection_success' in metrics_str
            assert 'f5xc_synthetic_collection_success' in metrics_str

    def test_metrics_endpoint_error_handling(self, test_config):
        """Test metrics endpoint handles registry errors gracefully."""
        with patch('f5xc_exporter.metrics_server.F5XCClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            server = MetricsServer(test_config)

            # Start server
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            time.sleep(0.5)

            try:
                # Simulate registry error by corrupting it
                server.registry = None

                # Test that metrics endpoint returns 500 but doesn't crash
                metrics_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/metrics", timeout=5)
                assert metrics_response.status_code == 500

                # Server should still be responsive
                health_response = requests.get(f"http://localhost:{test_config.f5xc_exp_http_port}/health", timeout=5)
                assert health_response.status_code == 200

            finally:
                server.stop()

    def test_404_endpoint(self, test_config):
        """Test that unknown endpoints return 404."""
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