"""Integration tests for SecurityCollector."""

import pytest
import responses
from f5xc_exporter.client import F5XCAPIError
from f5xc_exporter.collectors.security import SecurityCollector

from .conftest import get_metric_value


class TestSecurityCollectorIntegration:
    """Integration tests for SecurityCollector using real client with mocked HTTP responses."""

    @responses.activate
    def test_successful_collection(self, real_client, load_fixture, test_config):
        """Test successful security metrics collection with both API calls succeeding."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API
        app_firewall_data = load_fixture("security_app_firewall_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json=app_firewall_data,
            status=200,
        )

        # Mock security events aggregation API
        events_data = load_fixture("security_events_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json=events_data,
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify collection success
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_app_firewall_metrics_processing(self, real_client, load_fixture, test_config):
        """Test that app firewall metrics are correctly processed per load balancer."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API
        app_firewall_data = load_fixture("security_app_firewall_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json=app_firewall_data,
            status=200,
        )

        # Mock security events aggregation API (empty)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json={"aggs": {"by_event_type": {"field_aggregation": {"buckets": []}}}},
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify per-LB metrics from app firewall API
        lb_name = "ves-io-http-loadbalancer-demo-shop-fe"
        assert get_metric_value(collector.total_requests, tenant="test-tenant",
            namespace="test-ns",
            load_balancer=lb_name,) == 13442

        assert get_metric_value(collector.attacked_requests, tenant="test-tenant",
            namespace="test-ns",
            load_balancer=lb_name,) == 25

        assert get_metric_value(collector.bot_detections, tenant="test-tenant",
            namespace="test-ns",
            load_balancer=lb_name,) == 18

    @responses.activate
    def test_event_aggregation_processing(self, real_client, load_fixture, test_config):
        """Test that security events aggregation is correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API (empty)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json={"data": [], "step": "5m"},
            status=200,
        )

        # Mock security events aggregation API
        events_data = load_fixture("security_events_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json=events_data,
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify namespace-level event counts
        assert get_metric_value(collector.waf_events, tenant="test-tenant", namespace="test-ns") == 20
        assert get_metric_value(collector.bot_defense_events, tenant="test-tenant", namespace="test-ns") == 15
        assert get_metric_value(collector.api_events, tenant="test-tenant", namespace="test-ns") == 5
        assert get_metric_value(collector.service_policy_events, tenant="test-tenant", namespace="test-ns") == 2
        assert get_metric_value(collector.malicious_user_events, tenant="test-tenant", namespace="test-ns") == 3

    @responses.activate
    def test_collection_success_metric(self, real_client, load_fixture, test_config):
        """Test that collection success metric is set to 1 on successful collection."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API
        app_firewall_data = load_fixture("security_app_firewall_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json=app_firewall_data,
            status=200,
        )

        # Mock security events aggregation API
        events_data = load_fixture("security_events_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json=events_data,
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_api_500_error(self, real_client, test_config):
        """Test that API 500 error sets success=0."""
        # Mock namespace list with error
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"error": "Internal server error"},
            status=500,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        with pytest.raises(F5XCAPIError):
            collector.collect_metrics()

        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 0

    @responses.activate
    def test_dos_event_aggregation(self, real_client, load_fixture, test_config):
        """Test that ddos_sec_event + dos_sec_event are combined into dos_events metric."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API (empty)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json={"data": [], "step": "5m"},
            status=200,
        )

        # Mock security events aggregation API
        events_data = load_fixture("security_events_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json=events_data,
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify DoS events are combined (ddos: 4 + dos: 3 = 7)
        assert get_metric_value(collector.dos_events, tenant="test-tenant", namespace="test-ns") == 7

    @responses.activate
    def test_empty_buckets(self, real_client, test_config):
        """Test that empty aggregation buckets result in success=1 with no events."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API (empty)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json={"data": [], "step": "5m"},
            status=200,
        )

        # Mock security events aggregation API (empty buckets)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json={"aggs": {"by_event_type": {"field_aggregation": {"buckets": []}}}},
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Collection should succeed with empty data
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_partial_api_failure(self, real_client, load_fixture, test_config):
        """Test that one API failing doesn't stop the other from succeeding."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "test-ns"}]},
            status=200,
        )

        # Mock app firewall metrics API with error
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_firewall/metrics",
            json={"error": "Internal server error"},
            status=500,
        )

        # Mock security events aggregation API (succeeds)
        events_data = load_fixture("security_events_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/test-ns/app_security/events/aggregation",
            json=events_data,
            status=200,
        )

        collector = SecurityCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Collection should succeed even if one API fails
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

        # Verify event metrics are still set from the successful API call
        assert get_metric_value(collector.waf_events, tenant="test-tenant", namespace="test-ns") == 20
