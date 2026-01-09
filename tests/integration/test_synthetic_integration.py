"""Integration tests for SyntheticMonitoringCollector."""

import pytest
import responses

from f5xc_exporter.collectors.synthetic_monitoring import SyntheticMonitoringCollector

from .conftest import get_metric_value


class TestSyntheticMonitoringCollectorIntegration:
    """Integration tests for SyntheticMonitoringCollector using real client with mocked HTTP responses."""

    @responses.activate
    def test_successful_collection(self, real_client, load_fixture, test_config):
        """Test successful collection with both HTTP and DNS summaries collected."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock HTTP summary API
        http_data = load_fixture("synthetic_http_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=http",
            json=http_data,
            status=200,
        )

        # Mock DNS summary API
        dns_data = load_fixture("synthetic_dns_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=dns",
            json=dns_data,
            status=200,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify collection success
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_http_summary_processing(self, real_client, load_fixture, test_config):
        """Test that HTTP monitor counts (total, healthy, critical) are correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock HTTP summary API (with query parameter)
        http_data = load_fixture("synthetic_http_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=http",
            json=http_data,
            status=200,
        )

        # Mock DNS summary API (empty, with query parameter)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=dns",
            json={"number_of_monitors": 0, "healthy_monitor_count": 0, "critical_monitor_count": 0},
            status=200,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify HTTP monitor metrics
        assert get_metric_value(collector.http_monitors_total, tenant="test-tenant", namespace="test-ns") == 5
        assert get_metric_value(collector.http_monitors_healthy, tenant="test-tenant", namespace="test-ns") == 4
        assert get_metric_value(collector.http_monitors_critical, tenant="test-tenant", namespace="test-ns") == 1

    @responses.activate
    def test_dns_summary_processing(self, real_client, load_fixture, test_config):
        """Test that DNS monitor counts (total, healthy, critical) are correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock HTTP summary API (empty, with query parameter)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=http",
            json={"number_of_monitors": 0, "healthy_monitor_count": 0, "critical_monitor_count": 0},
            status=200,
        )

        # Mock DNS summary API (with query parameter)
        dns_data = load_fixture("synthetic_dns_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=dns",
            json=dns_data,
            status=200,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify DNS monitor metrics
        assert get_metric_value(collector.dns_monitors_total, tenant="test-tenant", namespace="test-ns") == 3
        assert get_metric_value(collector.dns_monitors_healthy, tenant="test-tenant", namespace="test-ns") == 3
        assert get_metric_value(collector.dns_monitors_critical, tenant="test-tenant", namespace="test-ns") == 0

    @responses.activate
    def test_api_500_error(self, real_client, test_config):
        """Test that API 500 error logs warning and continues."""
        # Mock namespace list with error
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"error": "Internal server error"},
            status=500,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        # Should not raise, but should set success=0
        collector.collect_metrics()

        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 0

    @responses.activate
    def test_404_no_monitors(self, real_client, test_config):
        """Test that 404 is treated as no monitors (debug log, not warning)."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock HTTP summary API with 404
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=http",
            json={"error": "Not found"},
            status=404,
        )

        # Mock DNS summary API with 404
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=dns",
            json={"error": "Not found"},
            status=404,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Collection should succeed even with 404s
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_empty_namespace_list(self, real_client, test_config):
        """Test that empty namespace list results in success=1 with no metrics."""
        # Mock empty namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": []},
            status=200,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Collection should succeed
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_missing_count_fields(self, real_client, test_config):
        """Test that missing count fields default to 0."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock HTTP summary API with missing fields
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=http",
            json={},  # No fields
            status=200,
        )

        # Mock DNS summary API with missing fields
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/test-ns/global-summary?monitorType=dns",
            json={},  # No fields
            status=200,
        )

        collector = SyntheticMonitoringCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify all metrics default to 0
        assert get_metric_value(collector.http_monitors_total, tenant="test-tenant", namespace="test-ns") == 0
        assert get_metric_value(collector.http_monitors_healthy, tenant="test-tenant", namespace="test-ns") == 0
        assert get_metric_value(collector.http_monitors_critical, tenant="test-tenant", namespace="test-ns") == 0

        assert get_metric_value(collector.dns_monitors_total, tenant="test-tenant", namespace="test-ns") == 0
        assert get_metric_value(collector.dns_monitors_healthy, tenant="test-tenant", namespace="test-ns") == 0
        assert get_metric_value(collector.dns_monitors_critical, tenant="test-tenant", namespace="test-ns") == 0
