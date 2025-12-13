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
        """Test HTTP statistics processing with actual F5XC API structure."""
        mock_client.get_service_graph_data.return_value = sample_service_graph_response

        collector = ServiceGraphCollector(mock_client)
        collector.collect_metrics("system")

        # Check HTTP request metrics - now using downstream/upstream with metric types
        requests_downstream = collector.http_requests_total.labels(
            namespace="system", load_balancer="test-lb", backend="downstream", response_class="total"
        )
        assert requests_downstream._value._value == 100.5

        # Check HTTP response latency
        latency = collector.http_request_duration.labels(
            namespace="system", load_balancer="test-lb", backend="downstream", percentile="avg"
        )
        assert latency._value._value == 0.15


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
        """Test WAF data processing with new API methods."""
        mock_client.get_app_firewall_metrics.return_value = sample_security_response

        collector = SecurityCollector(mock_client)
        collector._collect_waf_metrics("system")

        # Verify new API method was called
        mock_client.get_app_firewall_metrics.assert_called_once_with("system")


class TestSyntheticMonitoringCollector:
    """Test synthetic monitoring collector."""

    def test_synthetic_collector_initialization(self, mock_client):
        """Test synthetic monitoring collector initializes correctly."""
        collector = SyntheticMonitoringCollector(mock_client)

        assert collector.client == mock_client
        assert collector.http_check_success is not None
        assert collector.dns_check_success is not None
        assert collector.ping_check_success is not None

    def test_synthetic_metrics_collection(self, mock_client, sample_synthetic_response, sample_synthetic_summary_response):
        """Test synthetic monitoring metrics collection with new API methods."""
        mock_client.get_synthetic_monitoring_health.return_value = sample_synthetic_response
        mock_client.get_http_monitors_health.return_value = sample_synthetic_response
        mock_client.get_synthetic_monitoring_summary.return_value = sample_synthetic_summary_response

        collector = SyntheticMonitoringCollector(mock_client)
        collector.collect_metrics("system")

        # Verify new API methods were called
        mock_client.get_synthetic_monitoring_health.assert_called_once_with("system")
        mock_client.get_http_monitors_health.assert_called_once_with("system")
        mock_client.get_synthetic_monitoring_summary.assert_called_once_with("system")

        # Check success metric
        success_metric = collector.synthetic_collection_success.labels(namespace="system")
        assert success_metric._value._value == 1

    def test_http_monitor_processing(self, mock_client, sample_synthetic_response, sample_synthetic_summary_response):
        """Test HTTP monitor data processing with new API structure."""
        mock_client.get_synthetic_monitoring_health.return_value = sample_synthetic_response
        mock_client.get_http_monitors_health.return_value = sample_synthetic_response
        mock_client.get_synthetic_monitoring_summary.return_value = sample_synthetic_summary_response

        collector = SyntheticMonitoringCollector(mock_client)
        collector.collect_metrics("system")

        # Check HTTP success metric - using new structure
        http_success = collector.http_check_success.labels(
            namespace="system",
            monitor_name="test-monitor",
            location="global",
            target_url="https://example.com"
        )
        assert http_success._value._value == 1

        # Check response time metric (150ms -> 0.15s)
        response_time = collector.http_check_response_time.labels(
            namespace="system",
            monitor_name="test-monitor",
            location="global",
            target_url="https://example.com"
        )
        assert response_time._value._value == 0.15


class TestCollectorIntegration:
    """Test collector integration scenarios."""

    def test_all_collectors_with_prometheus_registry(self, mock_client):
        """Test all collectors can be properly registered with Prometheus registry."""
        from prometheus_client import CollectorRegistry, generate_latest

        # Create a custom registry for testing
        registry = CollectorRegistry()

        # Create collectors
        quota_collector = QuotaCollector(mock_client)
        service_graph_collector = ServiceGraphCollector(mock_client)
        security_collector = SecurityCollector(mock_client)
        synthetic_collector = SyntheticMonitoringCollector(mock_client)

        # Register individual metrics with registry (like MetricsServer does)
        registry.register(quota_collector.quota_limit)
        registry.register(quota_collector.quota_current)
        registry.register(quota_collector.quota_utilization)
        registry.register(quota_collector.quota_collection_success)
        registry.register(quota_collector.quota_collection_duration)

        registry.register(service_graph_collector.http_requests_total)
        registry.register(service_graph_collector.http_request_duration)
        registry.register(service_graph_collector.tcp_connections_total)
        registry.register(service_graph_collector.service_graph_collection_success)
        registry.register(service_graph_collector.service_graph_collection_duration)

        registry.register(security_collector.waf_requests_total)
        registry.register(security_collector.bot_requests_total)
        registry.register(security_collector.security_events_total)
        registry.register(security_collector.security_collection_success)
        registry.register(security_collector.security_collection_duration)

        registry.register(synthetic_collector.http_check_success)
        registry.register(synthetic_collector.dns_check_success)
        registry.register(synthetic_collector.ping_check_success)
        registry.register(synthetic_collector.http_check_response_time)
        registry.register(synthetic_collector.synthetic_collection_success)
        registry.register(synthetic_collector.synthetic_collection_duration)

        # Test that metrics can be generated (this would have caught the bug)
        metrics_output = generate_latest(registry)
        assert metrics_output is not None
        assert len(metrics_output) > 0

        # Test that metrics output contains expected metric names
        metrics_str = metrics_output.decode('utf-8')
        assert 'f5xc_quota_limit' in metrics_str
        assert 'f5xc_http_requests_total' in metrics_str  # Service graph HTTP metric
        assert 'f5xc_security_collection_success' in metrics_str
        assert 'f5xc_synthetic_collection_success' in metrics_str

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