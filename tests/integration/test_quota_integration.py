"""Integration tests for QuotaCollector."""

import pytest
import responses

from f5xc_exporter.client import F5XCAPIError
from f5xc_exporter.collectors.quota import QuotaCollector

from .conftest import get_metric_value


class TestQuotaCollectorIntegration:
    """Integration tests for QuotaCollector using real client with mocked HTTP responses."""

    @responses.activate
    def test_successful_collection(self, real_client, mock_quota_api):
        """Test successful quota collection with valid API response."""
        mock_quota_api()

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        # Verify metrics are set correctly
        assert get_metric_value(collector.quota_limit, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="load_balancer",) == 10

        assert get_metric_value(collector.quota_current, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="load_balancer",) == 5

        assert get_metric_value(collector.quota_utilization, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="load_balancer",) == 50.0

    @responses.activate
    def test_metric_values_accuracy(self, real_client, load_fixture, test_config):
        """Test that metric values match response data exactly."""
        quota_data = load_fixture("quota_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json=quota_data,
            status=200,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        # Verify quota_usage section
        assert get_metric_value(collector.quota_limit, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="origin_pool",) == 20
        assert get_metric_value(collector.quota_current, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="origin_pool",) == 12
        assert get_metric_value(collector.quota_utilization, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="origin_pool",) == 60.0

        # Verify resources section
        assert get_metric_value(collector.quota_limit, tenant="test-tenant",
            namespace="system",
            resource_type="resource",
            resource_name="virtual_host",) == 50
        assert get_metric_value(collector.quota_current, tenant="test-tenant",
            namespace="system",
            resource_type="resource",
            resource_name="virtual_host",) == 25
        assert get_metric_value(collector.quota_utilization, tenant="test-tenant",
            namespace="system",
            resource_type="resource",
            resource_name="virtual_host",) == 50.0

    @responses.activate
    def test_collection_success_metric(self, real_client, load_fixture, test_config):
        """Test that collection success metric is set to 1 on successful collection."""
        quota_data = load_fixture("quota_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json=quota_data,
            status=200,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        assert get_metric_value(collector.quota_collection_success, tenant="test-tenant", namespace="system") == 1

    @responses.activate
    def test_collection_duration_metric(self, real_client, load_fixture, test_config):
        """Test that collection duration metric is set."""
        quota_data = load_fixture("quota_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json=quota_data,
            status=200,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        duration = get_metric_value(collector.quota_collection_duration, tenant="test-tenant", namespace="system")
        assert duration >= 0

    @responses.activate
    def test_api_500_error(self, real_client, test_config):
        """Test that API 500 error sets success=0 and raises F5XCAPIError."""
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json={"error": "Internal server error"},
            status=500,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        with pytest.raises(F5XCAPIError):
            collector.collect_metrics("system")

        assert get_metric_value(collector.quota_collection_success, tenant="test-tenant", namespace="system") == 0

    @responses.activate
    def test_api_429_rate_limit(self, real_client, test_config):
        """Test that API 429 rate limit exhausts retries and raises F5XCAPIError."""
        # Mock all retry attempts (3 times)
        for _ in range(3):
            responses.add(
                method="GET",
                url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
                json={"error": "Rate limit exceeded"},
                status=429,
            )

        collector = QuotaCollector(real_client, "test-tenant")
        with pytest.raises(F5XCAPIError):
            collector.collect_metrics("system")

        assert get_metric_value(collector.quota_collection_success, tenant="test-tenant", namespace="system") == 0

    @responses.activate
    def test_empty_response_data(self, real_client, test_config):
        """Test that empty quota_usage sets success=1 with no metrics."""
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json={"quota_usage": {}, "resources": {}, "objects": {}},
            status=200,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        assert get_metric_value(collector.quota_collection_success, tenant="test-tenant", namespace="system") == 1
        assert collector.quota_metric_count == 0

    @responses.activate
    def test_negative_values_handling(self, real_client, test_config):
        """Test that negative values result in 0% utilization."""
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json={
                "quota_usage": {
                    "test_resource": {
                        "limit": {"maximum": -1},
                        "usage": {"current": -1},
                    }
                }
            },
            status=200,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        # Verify utilization is 0% for negative values
        assert get_metric_value(collector.quota_utilization, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="test_resource",) == 0.0

    @responses.activate
    def test_three_response_formats(self, real_client, test_config):
        """Test that all three response sections (quota_usage, resources, objects) are processed."""
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json={
                "quota_usage": {
                    "quota_item": {
                        "limit": {"maximum": 10},
                        "usage": {"current": 5},
                    }
                },
                "resources": {
                    "resource_item": {
                        "limit": {"maximum": 20},
                        "usage": {"current": 10},
                    }
                },
                "objects": {
                    "object_item": {
                        "limit": {"maximum": 30},
                        "usage": {"current": 15},
                    }
                },
            },
            status=200,
        )

        collector = QuotaCollector(real_client, "test-tenant")
        collector.collect_metrics("system")

        # Verify all three sections are processed
        assert collector.quota_metric_count == 3

        # Verify quota_usage
        assert get_metric_value(collector.quota_limit, tenant="test-tenant",
            namespace="system",
            resource_type="quota",
            resource_name="quota_item",) == 10

        # Verify resources
        assert get_metric_value(collector.quota_limit, tenant="test-tenant",
            namespace="system",
            resource_type="resource",
            resource_name="resource_item",) == 20

        # Verify objects
        assert get_metric_value(collector.quota_limit, tenant="test-tenant",
            namespace="system",
            resource_type="object",
            resource_name="object_item",) == 30
