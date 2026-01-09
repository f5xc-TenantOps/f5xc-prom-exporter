"""Integration tests for DNSCollector."""

import pytest
import responses

from f5xc_exporter.collectors.dns import DNSCollector

from .conftest import get_metric_value


class TestDNSCollectorIntegration:
    """Integration tests for DNSCollector using real client with mocked HTTP responses."""

    @responses.activate
    def test_successful_collection(self, real_client, mock_dns_apis):
        """Test successful DNS collection with all 3 API calls succeeding."""
        mock_dns_apis()  # Setup all DNS API mocks with default fixtures

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify collection success
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_collection_duration_metric(self, real_client, mock_dns_apis):
        """Test that collection duration metric is set."""
        mock_dns_apis()

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        duration = get_metric_value(collector.collection_duration, tenant="test-tenant")
        assert duration >= 0

    @responses.activate
    def test_zone_metrics_processing(self, real_client, load_fixture, test_config):
        """Test that DNS zone query counts are extracted correctly."""
        zone_data = load_fixture("dns_zone_metrics_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json=zone_data,
            status=200,
        )

        # Mock other APIs (empty)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify zone metrics (values from dns_zone_metrics_response.json fixture)
        # example.com: 21833 (fixture line 10), mysite.net: 15093 (line 21), test.org: 1049 (line 32)
        assert get_metric_value(collector.zone_query_count, tenant="test-tenant", zone="example.com") == 21833
        assert get_metric_value(collector.zone_query_count, tenant="test-tenant", zone="mysite.net") == 15093
        assert get_metric_value(collector.zone_query_count, tenant="test-tenant", zone="test.org") == 1049

    @responses.activate
    def test_zone_count_metric(self, real_client, load_fixture, test_config):
        """Test that zone_count metric reflects discovered zones."""
        zone_data = load_fixture("dns_zone_metrics_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json=zone_data,
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify zone count
        assert get_metric_value(collector.zone_count, tenant="test-tenant") == 3

    @responses.activate
    def test_lb_health_status(self, real_client, load_fixture, test_config):
        """Test that DNS LB health status is set correctly (HEALTHY=1, UNHEALTHY=0)."""
        # Mock empty zone metrics
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={"data": []},
            status=200,
        )

        # Mock LB health API
        lb_health_data = load_fixture("dns_lb_health_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json=lb_health_data,
            status=200,
        )

        # Mock pool member health API
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify HEALTHY=1
        assert get_metric_value(collector.dns_lb_health, tenant="test-tenant", dns_lb="global-dns-lb") == 1.0

        # Verify UNHEALTHY=0
        assert get_metric_value(collector.dns_lb_health, tenant="test-tenant", dns_lb="regional-dns-lb") == 0.0

    @responses.activate
    def test_lb_count_metric(self, real_client, load_fixture, test_config):
        """Test that dns_lb_count metric reflects discovered LBs."""
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={"data": []},
            status=200,
        )

        lb_health_data = load_fixture("dns_lb_health_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json=lb_health_data,
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify LB count
        assert get_metric_value(collector.dns_lb_count, tenant="test-tenant") == 2

    @responses.activate
    def test_pool_member_health(self, real_client, load_fixture, test_config):
        """Test that DNS LB pool member health status is set correctly."""
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={"data": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        pool_health_data = load_fixture("dns_pool_health_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json=pool_health_data,
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify healthy pool members
        assert get_metric_value(collector.dns_lb_pool_member_health, tenant="test-tenant",
            dns_lb="global-dns-lb",
            pool="primary-pool",
            member="10.0.0.1",) == 1.0

        assert get_metric_value(collector.dns_lb_pool_member_health, tenant="test-tenant",
            dns_lb="global-dns-lb",
            pool="primary-pool",
            member="10.0.0.2",) == 1.0

        # Verify unhealthy pool member
        assert get_metric_value(collector.dns_lb_pool_member_health, tenant="test-tenant",
            dns_lb="regional-dns-lb",
            pool="backup-pool",
            member="10.1.0.1",) == 0.0

    @responses.activate
    def test_api_500_error(self, real_client, test_config):
        """Test that API 500 error on zone metrics is logged as warning but collection continues."""
        # Zone metrics fails with 500
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={"error": "Internal server error"},
            status=500,
        )

        # Mock other APIs to succeed
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        # Should not raise - individual API errors are caught and logged
        collector.collect_metrics()

        # Collection should still succeed (partial success)
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1
        # Zone count should be 0 since zone metrics failed
        assert get_metric_value(collector.zone_count, tenant="test-tenant") == 0

    @responses.activate
    def test_empty_zone_data(self, real_client, test_config):
        """Test that empty data array results in success=1 with zone_count=0."""
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={"data": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1
        assert get_metric_value(collector.zone_count, tenant="test-tenant") == 0

    @responses.activate
    def test_partial_api_failure(self, real_client, load_fixture, test_config):
        """Test that one API failing doesn't stop the others from continuing."""
        # Zone metrics succeeds
        zone_data = load_fixture("dns_zone_metrics_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json=zone_data,
            status=200,
        )

        # LB health API fails
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"error": "Internal server error"},
            status=500,
        )

        # Pool member health API succeeds
        pool_health_data = load_fixture("dns_pool_health_response.json")
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json=pool_health_data,
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Overall collection should succeed
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

        # Verify zone metrics are still set
        assert get_metric_value(collector.zone_query_count, tenant="test-tenant", zone="example.com") == 21833

        # Verify pool member health metrics are still set
        assert get_metric_value(collector.dns_lb_pool_member_health, tenant="test-tenant",
            dns_lb="global-dns-lb",
            pool="primary-pool",
            member="10.0.0.1",) == 1.0

    @responses.activate
    def test_unknown_zone_name(self, real_client, test_config):
        """Test that zones with 'unknown' name are skipped."""
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={
                "data": [
                    {
                        "labels": {"DNS_ZONE_NAME": "unknown"},
                        "value": [{"timestamp": 1765850829, "value": "1000"}],
                    }
                ]
            },
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        collector = DNSCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Zone count should be 0 (unknown zone skipped)
        assert get_metric_value(collector.zone_count, tenant="test-tenant") == 0

    @responses.activate
    def test_cardinality_limit_dns_zones(self, real_client, test_config):
        """Test that collection stops when max DNS zones is exceeded."""
        # Create cardinality tracker with low DNS zone limit
        from f5xc_exporter.cardinality import CardinalityTracker
        tracker = CardinalityTracker(
            max_namespaces=100,
            max_load_balancers_per_namespace=50,
            max_dns_zones=2,
            warn_cardinality_threshold=10000,
        )

        # Create response with 3 zones
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json={
                "data": [
                    {"labels": {"DNS_ZONE_NAME": "zone1.com"}, "value": [{"timestamp": 1765850829, "value": "100"}]},
                    {"labels": {"DNS_ZONE_NAME": "zone2.com"}, "value": [{"timestamp": 1765850829, "value": "200"}]},
                    {"labels": {"DNS_ZONE_NAME": "zone3.com"}, "value": [{"timestamp": 1765850829, "value": "300"}]},
                ]
            },
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json={"items": []},
            status=200,
        )

        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json={"items": []},
            status=200,
        )

        # Create collector with cardinality tracker
        collector = DNSCollector(real_client, "test-tenant", tracker)
        collector.collect_metrics()

        # Only 2 zones should be processed due to limit
        assert get_metric_value(collector.zone_count, tenant="test-tenant") == 2
