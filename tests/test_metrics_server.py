"""Tests for metrics server."""

import json
import pytest
import threading
import time
from http.server import HTTPServer
from unittest.mock import Mock, patch, MagicMock

from f5xc_exporter.metrics_server import MetricsServer, MetricsHandler


class TestMetricsHandler:
    """Test metrics HTTP handler."""

    def test_handler_initialization(self):
        """Test handler can be instantiated."""
        # Note: Actual HTTP handler testing requires more complex setup
        # This is a basic smoke test
        assert MetricsHandler is not None

    def test_log_message_override(self):
        """Test log message override method."""
        handler = MetricsHandler()

        # Mock the logger to avoid actual logging during tests
        with patch('f5xc_exporter.metrics_server.logger') as mock_logger:
            handler.log_message("Test message %s", "arg1")
            mock_logger.info.assert_called_once_with("HTTP request", message="Test message arg1")


class TestMetricsServer:
    """Test metrics server."""

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_metrics_server_initialization(self, mock_client_class, test_config):
        """Test metrics server initializes correctly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        server = MetricsServer(test_config)

        assert server.config == test_config
        assert server.registry is not None
        assert server.quota_collector is not None
        assert server.service_graph_collector is not None
        assert server.security_collector is not None
        assert server.synthetic_monitoring_collector is not None
        assert server.collection_threads == {}
        assert server.httpd is None

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    @patch('f5xc_exporter.metrics_server.HTTPServer')
    def test_start_http_server(self, mock_http_server, mock_client_class, test_config):
        """Test HTTP server startup."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_httpd = Mock()
        mock_http_server.return_value = mock_httpd

        server = MetricsServer(test_config)

        # Mock the serve_forever to avoid blocking
        mock_httpd.serve_forever.side_effect = KeyboardInterrupt()

        with patch.object(server, '_start_collection_threads'):
            try:
                server.start()
            except SystemExit:
                pass  # Expected from signal handler

        mock_http_server.assert_called_once_with(("", 8080), MetricsHandler)
        assert server.httpd == mock_httpd

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_start_collection_threads_quota_enabled(self, mock_client_class, test_config):
        """Test collection threads start when quota interval > 0."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        server = MetricsServer(test_config)

        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance

            server._start_collection_threads()

            # Should start quota thread (interval = 60 in test config)
            assert mock_thread.call_count >= 1
            mock_thread_instance.start.assert_called()

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_start_collection_threads_quota_disabled(self, mock_client_class, test_config):
        """Test collection threads don't start when quota interval = 0."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Disable quota collection
        test_config.f5xc_quota_interval = 0

        server = MetricsServer(test_config)

        with patch('threading.Thread') as mock_thread:
            server._start_collection_threads()

            # Should not start any threads for quota
            # (other threads might start based on other intervals)
            quota_calls = [call for call in mock_thread.call_args_list
                          if 'quota-collector' in str(call)]
            assert len(quota_calls) == 0

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_collection_method_quota(self, mock_client_class, test_config):
        """Test quota collection method."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        server = MetricsServer(test_config)
        server.stop_event = threading.Event()

        # Mock the collector
        server.quota_collector.collect_metrics = Mock()

        # Set stop event immediately to avoid infinite loop
        server.stop_event.set()

        server._collect_quota_metrics()

        # Should have attempted collection once
        server.quota_collector.collect_metrics.assert_called_once()

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_collection_method_error_handling(self, mock_client_class, test_config):
        """Test collection method handles errors gracefully."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        server = MetricsServer(test_config)
        server.stop_event = threading.Event()

        # Mock the collector to raise an exception
        server.quota_collector.collect_metrics = Mock(side_effect=Exception("Test error"))

        # Set stop event immediately to avoid infinite loop
        server.stop_event.set()

        # Should not raise exception
        server._collect_quota_metrics()

        server.quota_collector.collect_metrics.assert_called_once()

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_server_stop(self, mock_client_class, test_config):
        """Test server stop functionality."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        server = MetricsServer(test_config)

        # Mock HTTP server
        server.httpd = Mock()

        # Mock collection threads
        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        server.collection_threads["test"] = mock_thread

        server.stop()

        # Check that stop event is set
        assert server.stop_event.is_set()

        # Check that HTTP server is shut down
        server.httpd.shutdown.assert_called_once()

        # Check that client is closed
        mock_client.close.assert_called_once()

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_get_status(self, mock_client_class, test_config):
        """Test status information gathering."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        server = MetricsServer(test_config)

        # Mock some threads
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        server.collection_threads["quota"] = mock_thread

        # Mock HTTP server
        server.httpd = Mock()

        status = server.get_status()

        assert "config" in status
        assert "threads" in status
        assert "server_running" in status

        assert status["config"]["port"] == 8080
        assert status["config"]["quota_interval"] == 60
        assert status["threads"]["quota"] == True
        assert status["server_running"] == True

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_service_graph_interval_calculation(self, mock_client_class, test_config):
        """Test service graph interval calculation."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Set different intervals
        test_config.f5xc_http_lb_interval = 60
        test_config.f5xc_tcp_lb_interval = 90
        test_config.f5xc_udp_lb_interval = 120

        server = MetricsServer(test_config)

        status = server.get_status()

        # Should use minimum interval (60)
        assert status["config"]["service_graph_interval"] == 60

    @patch('f5xc_exporter.metrics_server.F5XCClient')
    def test_all_collection_threads_start(self, mock_client_class, test_config):
        """Test that all collection threads start with non-zero intervals."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Ensure all intervals are non-zero
        test_config.f5xc_quota_interval = 60
        test_config.f5xc_http_lb_interval = 30
        test_config.f5xc_tcp_lb_interval = 30
        test_config.f5xc_udp_lb_interval = 30
        test_config.f5xc_security_interval = 60
        test_config.f5xc_synthetic_interval = 60

        server = MetricsServer(test_config)

        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance

            server._start_collection_threads()

            # Should start threads for quota, service graph, security, and synthetic
            assert mock_thread.call_count == 4
            assert mock_thread_instance.start.call_count == 4