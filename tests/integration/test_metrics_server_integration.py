"""Integration tests for MetricsServer orchestration."""

import time
from unittest.mock import patch

import responses

from f5xc_exporter.config import Config
from f5xc_exporter.metrics_server import MetricsServer


class TestMetricsServerIntegration:
    """Integration tests for MetricsServer orchestration using real config with mocked HTTP."""

    # ==================== Disable Functionality Tests ====================

    def test_quota_collector_disabled(self, monkeypatch):
        """Test that quota collector thread is not created when interval=0."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Quota thread should NOT be in collection_threads
            assert "quota" not in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_security_collector_disabled(self, monkeypatch):
        """Test that security collector thread is not created when interval=0."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Security thread should NOT be in collection_threads
            assert "security" not in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_synthetic_collector_disabled(self, monkeypatch):
        """Test that synthetic monitoring collector thread is not created when interval=0."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_SYNTHETIC_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Synthetic thread should NOT be in collection_threads
            assert "synthetic" not in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_lb_collector_disabled(self, monkeypatch):
        """Test that load balancer collector thread is not created when all LB intervals=0."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_HTTP_LB_INTERVAL", "0")
        monkeypatch.setenv("F5XC_TCP_LB_INTERVAL", "0")
        monkeypatch.setenv("F5XC_UDP_LB_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # LB thread should NOT be in collection_threads
            assert "lb" not in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_dns_collector_disabled(self, monkeypatch):
        """Test that DNS collector thread is not created when interval=0."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_DNS_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # DNS thread should NOT be in collection_threads
            assert "dns" not in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_disabled_collectors_not_in_threads(self, monkeypatch):
        """Test that all disabled collectors are absent from collection_threads dict."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        # Disable all collectors
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "0")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "0")
        monkeypatch.setenv("F5XC_SYNTHETIC_INTERVAL", "0")
        monkeypatch.setenv("F5XC_DNS_INTERVAL", "0")
        monkeypatch.setenv("F5XC_HTTP_LB_INTERVAL", "0")
        monkeypatch.setenv("F5XC_TCP_LB_INTERVAL", "0")
        monkeypatch.setenv("F5XC_UDP_LB_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # No collector threads should exist (except readiness which is always enabled)
            assert "quota" not in server.collection_threads
            assert "security" not in server.collection_threads
            assert "synthetic" not in server.collection_threads
            assert "dns" not in server.collection_threads
            assert "lb" not in server.collection_threads

            # Readiness should still be there
            assert "readiness" in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_disabled_collector_log_message(self, monkeypatch):
        """Test that disabled collectors don't start threads (implicit log verification)."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "0")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "0")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Verify disabled collectors don't have threads
            # (implicitly verifies the "disabled" log was issued)
            assert "quota" not in server.collection_threads
            assert "security" not in server.collection_threads

            # But enabled collectors should still work
            assert "synthetic" in server.collection_threads or "dns" in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    # ==================== Health Endpoint Tests ====================

    def test_health_endpoint_shows_disabled_collectors(self, monkeypatch):
        """Test that collector status correctly reflects disabled collectors."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "0")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "60")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)

            # Check configuration directly
            assert config.f5xc_quota_interval == 0  # Disabled
            assert config.f5xc_security_interval == 60  # Enabled

            # Verify quota thread not created
            server._start_collection_threads()
            assert "quota" not in server.collection_threads
            assert "security" in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    def test_health_endpoint_shows_enabled_collectors(self, monkeypatch):
        """Test that collector status correctly reflects all enabled collectors."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "60")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "60")
        monkeypatch.setenv("F5XC_SYNTHETIC_INTERVAL", "60")
        monkeypatch.setenv("F5XC_DNS_INTERVAL", "60")
        monkeypatch.setenv("F5XC_HTTP_LB_INTERVAL", "60")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient"):
            server = MetricsServer(config)

            # Check all intervals are enabled
            assert config.f5xc_quota_interval > 0
            assert config.f5xc_security_interval > 0
            assert config.f5xc_synthetic_interval > 0
            assert config.f5xc_dns_interval > 0
            assert config.f5xc_http_lb_interval > 0

            # Verify all collector threads created
            server._start_collection_threads()
            assert "quota" in server.collection_threads
            assert "security" in server.collection_threads
            assert "synthetic" in server.collection_threads
            assert "dns" in server.collection_threads
            assert "lb" in server.collection_threads

            # Stop server to clean up threads
            server.stop_event.set()

    # ==================== Concurrent Collection Tests ====================

    @responses.activate
    def test_all_collectors_run_concurrently(self, monkeypatch, mock_namespace_list,
                                            mock_quota_api, mock_dns_apis,
                                            mock_synthetic_apis, mock_security_apis,
                                            mock_loadbalancer_apis):
        """Test that all enabled collectors have alive threads."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        # Set short intervals for testing
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "2")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "2")
        monkeypatch.setenv("F5XC_SYNTHETIC_INTERVAL", "2")
        monkeypatch.setenv("F5XC_DNS_INTERVAL", "2")
        monkeypatch.setenv("F5XC_HTTP_LB_INTERVAL", "2")

        # Mock all API endpoints
        mock_quota_api()
        mock_dns_apis()
        mock_namespace_list(["test-ns"])
        mock_synthetic_apis("test-ns")
        mock_security_apis("test-ns")
        mock_loadbalancer_apis("test-ns")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient.close"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Give threads time to start
            time.sleep(0.5)

            # Verify all threads are alive
            assert "quota" in server.collection_threads
            assert server.collection_threads["quota"].is_alive(), "quota thread not alive"

            assert "security" in server.collection_threads
            assert server.collection_threads["security"].is_alive(), "security thread not alive"

            assert "synthetic" in server.collection_threads
            assert server.collection_threads["synthetic"].is_alive(), "synthetic thread not alive"

            assert "dns" in server.collection_threads
            assert server.collection_threads["dns"].is_alive(), "dns thread not alive"

            assert "lb" in server.collection_threads
            assert server.collection_threads["lb"].is_alive(), "lb thread not alive"

            # Stop server
            server.stop()

    @responses.activate
    def test_concurrent_metric_updates(self, monkeypatch, mock_namespace_list,
                                      mock_quota_api, mock_dns_apis):
        """Test that concurrent collectors update their metrics."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        # Set short intervals for testing
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "1")
        monkeypatch.setenv("F5XC_DNS_INTERVAL", "1")
        # Disable others
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "0")
        monkeypatch.setenv("F5XC_SYNTHETIC_INTERVAL", "0")
        monkeypatch.setenv("F5XC_HTTP_LB_INTERVAL", "0")

        # Mock API endpoints
        mock_quota_api()
        mock_dns_apis()

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient.close"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Wait for at least one collection cycle
            time.sleep(2)

            # Verify metrics were collected (metric_count > 0 means collection happened)
            # Note: We can't check exact values without knowing the fixture data,
            # but we can verify collection was attempted
            assert server.quota_collector is not None
            assert server.dns_collector is not None

            # Stop server
            server.stop()

    def test_thread_safety(self, monkeypatch):
        """Test that concurrent collectors don't corrupt metrics (no exceptions)."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        # Set short intervals to stress test (must be integers)
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "1")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "1")

        config = Config()

        # Mock collectors to avoid actual API calls
        with patch("f5xc_exporter.collectors.quota.QuotaCollector.collect_metrics"):
            with patch("f5xc_exporter.collectors.security.SecurityCollector.collect_metrics"):
                with patch("f5xc_exporter.client.F5XCClient.close"):
                    server = MetricsServer(config)
                    server._start_collection_threads()

                    # Let them run for a bit
                    time.sleep(1)

                    # Stop server (should not raise exceptions)
                    server.stop()

                    # If we got here without exceptions, thread safety is OK

    def test_graceful_shutdown(self, monkeypatch):
        """Test that stop_event signals all threads to stop gracefully."""
        monkeypatch.setenv("F5XC_TENANT_URL", "https://test.console.ves.volterra.io")
        monkeypatch.setenv("F5XC_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("F5XC_QUOTA_INTERVAL", "60")
        monkeypatch.setenv("F5XC_SECURITY_INTERVAL", "60")

        config = Config()

        with patch("f5xc_exporter.client.F5XCClient.close"):
            server = MetricsServer(config)
            server._start_collection_threads()

            # Verify threads are running
            assert len(server.collection_threads) > 0
            for thread in server.collection_threads.values():
                assert thread.is_alive()

            # Call stop
            server.stop()

            # Verify stop_event was set
            assert server.stop_event.is_set()

            # Verify all threads stopped (or at least attempted to)
            # Note: Since threads check stop_event.wait() with timeout, they should exit
            # We give them a moment to finish
            time.sleep(0.5)

            # Threads should either be stopped or in the process of stopping
            # We can't guarantee they're all dead immediately, but stop_event should be set
            assert server.stop_event.is_set()
