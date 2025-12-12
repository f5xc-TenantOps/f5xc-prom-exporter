"""Tests for metric collectors."""

import pytest
from unittest.mock import Mock, patch
from prometheus_client import CollectorRegistry

from f5xc_exporter.collectors import (
    QuotaCollector,
    ServiceGraphCollector,
    SecurityCollector,
    SyntheticMonitoringCollector
)
from f5xc_exporter.client import F5XCAPIError


class TestQuotaCollector:
    """Test quota metrics collector."""

    def test_quota_collector_initialization(self, mock_client):
        """Test quota collector initializes correctly."""
        collector = QuotaCollector(mock_client)

        assert collector.client == mock_client
        assert collector.quota_limit is not None
        assert collector.quota_current is not None
        assert collector.quota_utilization is not None

    def test_quota_metrics_collection_success(self, mock_client, sample_quota_response):
        """Test successful quota metrics collection."""
        mock_client.get_quota_usage.return_value = sample_quota_response

        collector = QuotaCollector(mock_client)
        collector.collect_metrics("test-namespace")

        mock_client.get_quota_usage.assert_called_once_with("test-namespace")

        # Check that success metric is set
        success_metric = collector.quota_collection_success.labels(namespace="test-namespace")
        assert success_metric._value._value == 1

    def test_quota_metrics_collection_failure(self, mock_client):
        """Test quota metrics collection failure handling."""
        mock_client.get_quota_usage.side_effect = F5XCAPIError("API Error")

        collector = QuotaCollector(mock_client)

        with pytest.raises(F5XCAPIError):
            collector.collect_metrics("test-namespace")

        # Check that failure metric is set
        success_metric = collector.quota_collection_success.labels(namespace="test-namespace")
        assert success_metric._value._value == 0

    def test_quota_data_processing(self, mock_client, sample_quota_response):
        """Test quota data processing logic."""
        mock_client.get_quota_usage.return_value = sample_quota_response

        collector = QuotaCollector(mock_client)
        collector.collect_metrics("system")

        # Check that metrics were processed
        lb_limit = collector.quota_limit.labels(
            namespace="system", resource_type="quota", resource_name="load_balancer"
        )
        assert lb_limit._value._value == 10.0

        lb_current = collector.quota_current.labels(
            namespace="system", resource_type="quota", resource_name="load_balancer"
        )
        assert lb_current._value._value == 5.0

        lb_util = collector.quota_utilization.labels(
            namespace="system", resource_type="quota", resource_name="load_balancer"
        )
        assert lb_util._value._value == 50.0  # 5/10 * 100


class TestServiceGraphCollector:
    """Test service graph metrics collector."""

    def test_service_graph_collector_initialization(self, mock_client):
        """Test service graph collector initializes correctly."""
        collector = ServiceGraphCollector(mock_client)

        assert collector.client == mock_client
        assert collector.http_requests_total is not None
        assert collector.http_request_duration is not None
        assert collector.tcp_connections_total is not None

    def test_service_graph_metrics_collection(self, mock_client, sample_service_graph_response):
        """Test service graph metrics collection."""
        mock_client.get_service_graph_data.return_value = sample_service_graph_response

        collector = ServiceGraphCollector(mock_client)
        collector.collect_metrics("system")

        mock_client.get_service_graph_data.assert_called_once_with("system")

        # Check success metric
        success_metric = collector.service_graph_collection_success.labels(namespace="system")
        assert success_metric._value._value == 1

    def test_http_stats_processing(self, mock_client, sample_service_graph_response):
        """Test HTTP statistics processing."""
        mock_client.get_service_graph_data.return_value = sample_service_graph_response

        collector = ServiceGraphCollector(mock_client)
        collector.collect_metrics("system")

        # Check HTTP request metrics
        requests_2xx = collector.http_requests_total.labels(
            namespace="system", load_balancer="test-lb", backend="frontend", response_class="2xx"
        )
        assert requests_2xx._value._value == 1000.0


class TestSecurityCollector:
    """Test security metrics collector."""

    def test_security_collector_initialization(self, mock_client):
        """Test security collector initializes correctly."""
        collector = SecurityCollector(mock_client)

        assert collector.client == mock_client
        assert collector.waf_requests_total is not None
        assert collector.bot_requests_total is not None
        assert collector.security_events_total is not None

    @patch.object(SecurityCollector, '_collect_waf_metrics')
    @patch.object(SecurityCollector, '_collect_bot_defense_metrics')
    @patch.object(SecurityCollector, '_collect_api_security_metrics')
    @patch.object(SecurityCollector, '_collect_ddos_metrics')
    @patch.object(SecurityCollector, '_collect_security_events')
    def test_security_metrics_collection_calls_all_methods(
        self, mock_events, mock_ddos, mock_api, mock_bot, mock_waf, mock_client
    ):
        """Test that security collection calls all sub-methods."""
        collector = SecurityCollector(mock_client)
        collector.collect_metrics("system")

        mock_waf.assert_called_once_with("system")
        mock_bot.assert_called_once_with("system")
        mock_api.assert_called_once_with("system")
        mock_ddos.assert_called_once_with("system")
        mock_events.assert_called_once_with("system")

    def test_waf_data_processing(self, mock_client, sample_security_response):
        """Test WAF data processing."""
        mock_client.get_waf_metrics.return_value = sample_security_response

        collector = SecurityCollector(mock_client)
        collector._collect_waf_metrics("system")

        # Verify WAF metrics would be updated (checking calls)
        mock_client.get_waf_metrics.assert_called_once_with("system")


class TestSyntheticMonitoringCollector:
    """Test synthetic monitoring collector."""

    def test_synthetic_collector_initialization(self, mock_client):
        """Test synthetic monitoring collector initializes correctly."""
        collector = SyntheticMonitoringCollector(mock_client)

        assert collector.client == mock_client
        assert collector.http_check_success is not None
        assert collector.dns_check_success is not None
        assert collector.ping_check_success is not None

    def test_synthetic_metrics_collection(self, mock_client, sample_synthetic_response):
        """Test synthetic monitoring metrics collection."""
        mock_client.get_synthetic_monitoring_metrics.return_value = sample_synthetic_response

        collector = SyntheticMonitoringCollector(mock_client)
        collector.collect_metrics("system")

        mock_client.get_synthetic_monitoring_metrics.assert_called_once_with("system")

        # Check success metric
        success_metric = collector.synthetic_collection_success.labels(namespace="system")
        assert success_metric._value._value == 1

    def test_http_monitor_processing(self, mock_client, sample_synthetic_response):
        """Test HTTP monitor data processing."""
        mock_client.get_synthetic_monitoring_metrics.return_value = sample_synthetic_response

        collector = SyntheticMonitoringCollector(mock_client)
        collector.collect_metrics("system")

        # Check HTTP success metric
        http_success = collector.http_check_success.labels(
            namespace="system",
            monitor_name="test-monitor",
            location="us-east-1",
            target_url="https://example.com"
        )
        assert http_success._value._value == 1

        # Check response time metric (converted from ms to seconds)
        response_time = collector.http_check_response_time.labels(
            namespace="system",
            monitor_name="test-monitor",
            location="us-east-1",
            target_url="https://example.com"
        )
        assert response_time._value._value == 0.15  # 150ms -> 0.15s


class TestCollectorIntegration:
    """Test collector integration scenarios."""

    def test_all_collectors_with_prometheus_registry(self, mock_client):
        """Test all collectors can be used with Prometheus registry."""
        # Use a custom registry to avoid conflicts
        from prometheus_client import CollectorRegistry

        # Create collectors one at a time to test they don't conflict
        with patch('prometheus_client.REGISTRY', CollectorRegistry()):
            quota_collector = QuotaCollector(mock_client)
            assert quota_collector is not None

        with patch('prometheus_client.REGISTRY', CollectorRegistry()):
            service_graph_collector = ServiceGraphCollector(mock_client)
            assert service_graph_collector is not None

        with patch('prometheus_client.REGISTRY', CollectorRegistry()):
            security_collector = SecurityCollector(mock_client)
            assert security_collector is not None

        with patch('prometheus_client.REGISTRY', CollectorRegistry()):
            synthetic_collector = SyntheticMonitoringCollector(mock_client)
            assert synthetic_collector is not None

    def test_collector_error_handling(self, mock_client):
        """Test collector error handling doesn't crash."""
        mock_client.get_quota_usage.side_effect = Exception("Network error")

        with patch('prometheus_client.REGISTRY', CollectorRegistry()):
            collector = QuotaCollector(mock_client)

            with pytest.raises(Exception):
                collector.collect_metrics("system")

            # Collector should still be usable after error
            mock_client.get_quota_usage.side_effect = None
            mock_client.get_quota_usage.return_value = {"quota_usage": {}}

            # Should not raise
            collector.collect_metrics("system")