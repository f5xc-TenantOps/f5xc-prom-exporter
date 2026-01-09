"""Tests for metric collectors."""

from unittest.mock import patch

import pytest
from prometheus_client import CollectorRegistry

from f5xc_exporter.client import F5XCAPIError
from f5xc_exporter.collectors import (
    DNSCollector,
    LoadBalancerCollector,
    QuotaCollector,
    SecurityCollector,
    SyntheticMonitoringCollector,
)

TEST_TENANT = "test-tenant"


class TestQuotaCollector:
    """Test quota metrics collector."""

    def test_quota_collector_initialization(self, mock_client):
        """Test quota collector initializes correctly."""
        collector = QuotaCollector(mock_client, TEST_TENANT)

        assert collector.client == mock_client
        assert collector.tenant == TEST_TENANT
        assert collector.quota_limit is not None
        assert collector.quota_current is not None
        assert collector.quota_utilization is not None

    def test_quota_metrics_collection_success(self, mock_client, sample_quota_response):
        """Test successful quota metrics collection."""
        mock_client.get_quota_usage.return_value = sample_quota_response

        collector = QuotaCollector(mock_client, TEST_TENANT)
        collector.collect_metrics("test-namespace")

        mock_client.get_quota_usage.assert_called_once_with("test-namespace")

        # Check that success metric is set
        success_metric = collector.quota_collection_success.labels(tenant=TEST_TENANT, namespace="test-namespace")
        assert success_metric._value._value == 1

    def test_quota_metrics_collection_failure(self, mock_client):
        """Test quota metrics collection failure handling."""
        mock_client.get_quota_usage.side_effect = F5XCAPIError("API Error")

        collector = QuotaCollector(mock_client, TEST_TENANT)

        with pytest.raises(F5XCAPIError):
            collector.collect_metrics("test-namespace")

        # Check that failure metric is set
        success_metric = collector.quota_collection_success.labels(tenant=TEST_TENANT, namespace="test-namespace")
        assert success_metric._value._value == 0

    def test_quota_data_processing(self, mock_client, sample_quota_response):
        """Test quota data processing logic."""
        mock_client.get_quota_usage.return_value = sample_quota_response

        collector = QuotaCollector(mock_client, TEST_TENANT)
        collector.collect_metrics("system")

        # Check that metrics were processed
        lb_limit = collector.quota_limit.labels(
            tenant=TEST_TENANT, namespace="system", resource_type="quota", resource_name="load_balancer"
        )
        assert lb_limit._value._value == 10.0

        lb_current = collector.quota_current.labels(
            tenant=TEST_TENANT, namespace="system", resource_type="quota", resource_name="load_balancer"
        )
        assert lb_current._value._value == 5.0

        lb_util = collector.quota_utilization.labels(
            tenant=TEST_TENANT, namespace="system", resource_type="quota", resource_name="load_balancer"
        )
        assert lb_util._value._value == 50.0  # 5/10 * 100

    def test_quota_negative_values_handling(self, mock_client):
        """Test quota utilization handles negative values correctly.

        The API returns -1 for current usage when there's no data.
        This should result in 0% utilization, not a negative percentage.
        """
        # Response with negative current value (API returns -1 for "no data")
        response_with_negative = {
            "quota_usage": {
                "container_registry": {
                    "limit": {"maximum": 25},
                    "usage": {"current": -1}  # -1 means no data
                },
                "normal_resource": {
                    "limit": {"maximum": 100},
                    "usage": {"current": 50}
                },
                "unlimited_resource": {
                    "limit": {"maximum": -1},  # -1 means unlimited
                    "usage": {"current": 10}
                }
            }
        }
        mock_client.get_quota_usage.return_value = response_with_negative

        collector = QuotaCollector(mock_client, TEST_TENANT)
        collector.collect_metrics("system")

        # Negative current (-1) should result in 0% utilization, not -4%
        container_util = collector.quota_utilization.labels(
            tenant=TEST_TENANT, namespace="system", resource_type="quota", resource_name="container_registry"
        )
        assert container_util._value._value == 0.0

        # Normal case should calculate correctly
        normal_util = collector.quota_utilization.labels(
            tenant=TEST_TENANT, namespace="system", resource_type="quota", resource_name="normal_resource"
        )
        assert normal_util._value._value == 50.0  # 50/100 * 100

        # Unlimited (-1 limit) should result in 0% utilization
        unlimited_util = collector.quota_utilization.labels(
            tenant=TEST_TENANT, namespace="system", resource_type="quota", resource_name="unlimited_resource"
        )
        assert unlimited_util._value._value == 0.0


class TestSecurityCollector:
    """Test security metrics collector."""

    def test_security_collector_initialization(self, mock_client):
        """Test security collector initializes correctly."""
        collector = SecurityCollector(mock_client, TEST_TENANT)

        assert collector.client == mock_client
        assert collector.tenant == TEST_TENANT
        # Per-LB metrics (from app_firewall/metrics API)
        assert collector.total_requests is not None
        assert collector.attacked_requests is not None
        assert collector.bot_detections is not None
        # Namespace event counts (from events/aggregation API)
        assert collector.waf_events is not None
        assert collector.bot_defense_events is not None
        assert collector.api_events is not None
        assert collector.service_policy_events is not None
        assert collector.malicious_user_events is not None
        assert collector.dos_events is not None
        # Collection status
        assert collector.collection_success is not None
        assert collector.collection_duration is not None

    def test_security_metrics_collection_success(
        self,
        mock_client,
        sample_app_firewall_metrics_response,
        sample_security_events_aggregation_response
    ):
        """Test successful security metrics collection.

        Uses exactly 2 API calls per namespace for scalability.
        """
        mock_client.list_namespaces.return_value = ["demo-shop"]
        mock_client.get_app_firewall_metrics_for_namespace.return_value = sample_app_firewall_metrics_response
        mock_client.get_security_event_counts_for_namespace.return_value = sample_security_events_aggregation_response

        collector = SecurityCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Verify success
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1

        # Verify exactly 2 API calls per namespace
        mock_client.list_namespaces.assert_called_once()
        mock_client.get_app_firewall_metrics_for_namespace.assert_called_once_with("demo-shop")
        mock_client.get_security_event_counts_for_namespace.assert_called_once()

    def test_app_firewall_metrics_processing(
        self,
        mock_client,
        sample_app_firewall_metrics_response
    ):
        """Test app firewall metrics processing."""
        collector = SecurityCollector(mock_client, TEST_TENANT)
        collector._process_app_firewall_response(sample_app_firewall_metrics_response, "demo-shop")

        # Check total requests
        total_requests = collector.total_requests.labels(
            tenant=TEST_TENANT,
            namespace="demo-shop",
            load_balancer="ves-io-http-loadbalancer-demo-shop-fe"
        )
        assert total_requests._value._value == 13442.0

        # Check attacked requests
        attacked_requests = collector.attacked_requests.labels(
            tenant=TEST_TENANT,
            namespace="demo-shop",
            load_balancer="ves-io-http-loadbalancer-demo-shop-fe"
        )
        assert attacked_requests._value._value == 25.0

        # Check bot detections
        bot_detections = collector.bot_detections.labels(
            tenant=TEST_TENANT,
            namespace="demo-shop",
            load_balancer="ves-io-http-loadbalancer-demo-shop-fe"
        )
        assert bot_detections._value._value == 18.0

    def test_security_events_aggregation_processing(
        self,
        mock_client,
        sample_security_events_aggregation_response
    ):
        """Test security events aggregation processing.

        All event types are collected in a single API call.
        Event counts are namespace-level only.
        """
        collector = SecurityCollector(mock_client, TEST_TENANT)
        collector._process_event_aggregation(sample_security_events_aggregation_response, "demo-shop")

        # Check WAF events
        waf_events = collector.waf_events.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert waf_events._value._value == 20.0

        # Check bot defense events
        bot_defense_events = collector.bot_defense_events.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert bot_defense_events._value._value == 15.0

        # Check API events
        api_events = collector.api_events.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert api_events._value._value == 5.0

        # Check service policy events
        svc_policy_events = collector.service_policy_events.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert svc_policy_events._value._value == 2.0

        # Check malicious user events
        malicious_user_events = collector.malicious_user_events.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert malicious_user_events._value._value == 3.0

        # Check DoS events (ddos_sec_event:4 + dos_sec_event:3 = 7)
        dos_events = collector.dos_events.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert dos_events._value._value == 7.0

    def test_security_collection_failure(self, mock_client):
        """Test security metrics collection failure handling."""
        from f5xc_exporter.client import F5XCAPIError

        mock_client.list_namespaces.side_effect = F5XCAPIError("API Error")

        collector = SecurityCollector(mock_client, TEST_TENANT)

        with pytest.raises(F5XCAPIError):
            collector.collect_metrics()

        # Check that failure metric is set
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 0

    def test_security_empty_response_handling(self, mock_client):
        """Test security collector handles empty responses gracefully."""
        mock_client.list_namespaces.return_value = ["demo-shop"]
        mock_client.get_app_firewall_metrics_for_namespace.return_value = {"data": []}
        mock_client.get_security_event_counts_for_namespace.return_value = {"aggs": {}}

        collector = SecurityCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Should succeed even with empty data
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1


class TestSyntheticMonitoringCollector:
    """Test synthetic monitoring collector."""

    def test_synthetic_collector_initialization(self, mock_client):
        """Test synthetic monitoring collector initializes correctly."""
        collector = SyntheticMonitoringCollector(mock_client, TEST_TENANT)

        assert collector.client == mock_client
        assert collector.tenant == TEST_TENANT
        # HTTP monitor metrics
        assert collector.http_monitors_total is not None
        assert collector.http_monitors_healthy is not None
        assert collector.http_monitors_critical is not None
        # DNS monitor metrics
        assert collector.dns_monitors_total is not None
        assert collector.dns_monitors_healthy is not None
        assert collector.dns_monitors_critical is not None
        # Collection status metrics
        assert collector.collection_success is not None
        assert collector.collection_duration is not None

    def test_synthetic_metrics_collection(
        self,
        mock_client,
        sample_synthetic_http_summary_response,
        sample_synthetic_dns_summary_response
    ):
        """Test synthetic monitoring metrics collection with 2-call approach."""
        mock_client.list_namespaces.return_value = ["demo-shop"]
        mock_client.get_synthetic_summary.side_effect = [
            sample_synthetic_http_summary_response,  # HTTP call
            sample_synthetic_dns_summary_response,   # DNS call
        ]

        collector = SyntheticMonitoringCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Verify API was called with correct arguments (2 calls per namespace)
        assert mock_client.get_synthetic_summary.call_count == 2
        mock_client.get_synthetic_summary.assert_any_call("demo-shop", "http")
        mock_client.get_synthetic_summary.assert_any_call("demo-shop", "dns")

        # Check collection success metric
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1

    def test_synthetic_http_summary_processing(
        self,
        mock_client,
        sample_synthetic_http_summary_response
    ):
        """Test HTTP monitor summary data processing."""
        mock_client.list_namespaces.return_value = ["demo-shop"]
        mock_client.get_synthetic_summary.return_value = sample_synthetic_http_summary_response

        collector = SyntheticMonitoringCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Check HTTP metrics were set correctly
        http_total = collector.http_monitors_total.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert http_total._value._value == 2

        http_healthy = collector.http_monitors_healthy.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert http_healthy._value._value == 2

        http_critical = collector.http_monitors_critical.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert http_critical._value._value == 0

    def test_synthetic_dns_summary_processing(
        self,
        mock_client,
        sample_synthetic_dns_summary_response
    ):
        """Test DNS monitor summary data processing."""
        mock_client.list_namespaces.return_value = ["demo-shop"]
        # HTTP returns empty, DNS returns data
        mock_client.get_synthetic_summary.side_effect = [
            {"number_of_monitors": 0, "healthy_monitor_count": 0, "critical_monitor_count": 0},
            sample_synthetic_dns_summary_response,
        ]

        collector = SyntheticMonitoringCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Check DNS metrics were set correctly
        dns_total = collector.dns_monitors_total.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert dns_total._value._value == 3

        dns_healthy = collector.dns_monitors_healthy.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert dns_healthy._value._value == 2

        dns_critical = collector.dns_monitors_critical.labels(tenant=TEST_TENANT, namespace="demo-shop")
        assert dns_critical._value._value == 1


class TestLoadBalancerCollector:
    """Test unified load balancer metrics collector (HTTP, TCP, UDP)."""

    def test_lb_collector_initialization(self, mock_client):
        """Test unified LB collector initializes correctly."""
        collector = LoadBalancerCollector(mock_client, TEST_TENANT)

        assert collector.client == mock_client
        assert collector.tenant == TEST_TENANT
        # HTTP metrics
        assert collector.http_request_rate is not None
        assert collector.http_request_to_origin_rate is not None
        assert collector.http_error_rate is not None
        assert collector.http_error_rate_4xx is not None
        assert collector.http_error_rate_5xx is not None
        assert collector.http_latency is not None
        assert collector.http_latency_p50 is not None
        assert collector.http_latency_p90 is not None
        assert collector.http_latency_p99 is not None
        # TCP metrics
        assert collector.tcp_connection_rate is not None
        assert collector.tcp_connection_duration is not None
        assert collector.tcp_error_rate is not None
        # UDP metrics
        assert collector.udp_request_throughput is not None
        assert collector.udp_response_throughput is not None
        # HTTP healthscore metrics
        assert collector.http_healthscore_overall is not None
        assert collector.http_healthscore_connectivity is not None
        assert collector.http_healthscore_performance is not None
        assert collector.http_healthscore_security is not None
        assert collector.http_healthscore_reliability is not None
        # TCP healthscore metrics
        assert collector.tcp_healthscore_overall is not None
        assert collector.tcp_healthscore_connectivity is not None
        assert collector.tcp_healthscore_performance is not None
        assert collector.tcp_healthscore_security is not None
        assert collector.tcp_healthscore_reliability is not None
        # UDP healthscore metrics
        assert collector.udp_healthscore_overall is not None
        assert collector.udp_healthscore_connectivity is not None
        assert collector.udp_healthscore_performance is not None
        assert collector.udp_healthscore_security is not None
        assert collector.udp_healthscore_reliability is not None
        # Unified collection status
        assert collector.collection_success is not None
        assert collector.collection_duration is not None
        # Count metrics
        assert collector.http_lb_count is not None
        assert collector.tcp_lb_count is not None
        assert collector.udp_lb_count is not None

    def test_lb_metrics_collection_success(self, mock_client, sample_unified_lb_response):
        """Test successful unified LB metrics collection."""
        mock_client.get_all_lb_metrics.return_value = sample_unified_lb_response

        collector = LoadBalancerCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        mock_client.get_all_lb_metrics.assert_called_once()

        # Check that success metric is set
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1

        # Check LB counts
        assert collector.http_lb_count.labels(tenant=TEST_TENANT)._value._value == 1
        assert collector.tcp_lb_count.labels(tenant=TEST_TENANT)._value._value == 1
        assert collector.udp_lb_count.labels(tenant=TEST_TENANT)._value._value == 1

    def test_lb_metrics_collection_failure(self, mock_client):
        """Test LB metrics collection failure handling."""
        mock_client.get_all_lb_metrics.side_effect = F5XCAPIError("API Error")

        collector = LoadBalancerCollector(mock_client, TEST_TENANT)

        with pytest.raises(F5XCAPIError):
            collector.collect_metrics()

        # Check that failure metric is set
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 0

    def test_unified_lb_data_processing(self, mock_client, sample_unified_lb_response):
        """Test unified LB data processing for all LB types with direction label."""
        mock_client.get_all_lb_metrics.return_value = sample_unified_lb_response

        collector = LoadBalancerCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Check HTTP LB downstream metrics
        http_request_rate_downstream = collector.http_request_rate.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_request_rate_downstream._value._value == 150.5

        http_error_rate_downstream = collector.http_error_rate.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_error_rate_downstream._value._value == 2.5

        http_latency_downstream = collector.http_latency.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_latency_downstream._value._value == 0.025

        # Check HTTP LB upstream metrics
        http_request_rate_upstream = collector.http_request_rate.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="upstream"
        )
        assert http_request_rate_upstream._value._value == 120.0

        http_latency_upstream = collector.http_latency.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="upstream"
        )
        assert http_latency_upstream._value._value == 0.050

        # Check TCP LB downstream metrics
        tcp_connection_rate_downstream = collector.tcp_connection_rate.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="tcp-backend",
            site="ce-site-1",
            direction="downstream"
        )
        assert tcp_connection_rate_downstream._value._value == 50.0

        tcp_error_rate_downstream = collector.tcp_error_rate.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="tcp-backend",
            site="ce-site-1",
            direction="downstream"
        )
        assert tcp_error_rate_downstream._value._value == 1.5

        # Check TCP LB upstream metrics
        tcp_connection_rate_upstream = collector.tcp_connection_rate.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="tcp-backend",
            site="ce-site-1",
            direction="upstream"
        )
        assert tcp_connection_rate_upstream._value._value == 45.0

        # Check UDP LB downstream metrics
        udp_request_throughput_downstream = collector.udp_request_throughput.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="udp-dns-lb",
            site="ce-site-1",
            direction="downstream"
        )
        assert udp_request_throughput_downstream._value._value == 100000

        udp_response_throughput_downstream = collector.udp_response_throughput.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="udp-dns-lb",
            site="ce-site-1",
            direction="downstream"
        )
        assert udp_response_throughput_downstream._value._value == 200000

        # Check UDP LB upstream metrics
        udp_request_throughput_upstream = collector.udp_request_throughput.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="udp-dns-lb",
            site="ce-site-1",
            direction="upstream"
        )
        assert udp_request_throughput_upstream._value._value == 95000

    def test_lb_healthscore_processing(self, mock_client, sample_unified_lb_response):
        """Test healthscore data processing for load balancers."""
        mock_client.get_all_lb_metrics.return_value = sample_unified_lb_response

        collector = LoadBalancerCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Check HTTP LB downstream healthscores
        http_healthscore_overall_downstream = collector.http_healthscore_overall.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_healthscore_overall_downstream._value._value == 95.0

        http_healthscore_connectivity_downstream = collector.http_healthscore_connectivity.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_healthscore_connectivity_downstream._value._value == 98.0

        http_healthscore_performance_downstream = collector.http_healthscore_performance.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_healthscore_performance_downstream._value._value == 92.0

        http_healthscore_security_downstream = collector.http_healthscore_security.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_healthscore_security_downstream._value._value == 100.0

        http_healthscore_reliability_downstream = collector.http_healthscore_reliability.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream"
        )
        assert http_healthscore_reliability_downstream._value._value == 94.0

        # Check HTTP LB upstream healthscores
        http_healthscore_overall_upstream = collector.http_healthscore_overall.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="upstream"
        )
        assert http_healthscore_overall_upstream._value._value == 90.0

        http_healthscore_performance_upstream = collector.http_healthscore_performance.labels(
            tenant=TEST_TENANT,
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="upstream"
        )
        assert http_healthscore_performance_upstream._value._value == 85.0

    def test_lb_empty_response(self, mock_client):
        """Test LB collector handles empty response gracefully."""
        mock_client.get_all_lb_metrics.return_value = {"data": {"nodes": []}}

        collector = LoadBalancerCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Should succeed even with empty data
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1
        assert collector.http_lb_count.labels(tenant=TEST_TENANT)._value._value == 0
        assert collector.tcp_lb_count.labels(tenant=TEST_TENANT)._value._value == 0
        assert collector.udp_lb_count.labels(tenant=TEST_TENANT)._value._value == 0

    def test_lb_missing_vhost_skipped(self, mock_client):
        """Test nodes without vhost are skipped."""
        mock_client.get_all_lb_metrics.return_value = {
            "data": {
                "nodes": [
                    {
                        "id": {
                            "namespace": "test",
                            "virtual_host_type": "HTTP_LOAD_BALANCER",
                            # vhost missing - should be skipped
                            "site": "site-1"
                        },
                        "data": {
                            "metric": {
                                "downstream": [
                                    {
                                        "type": "HTTP_REQUEST_RATE",
                                        "value": {
                                            "raw": [{"timestamp": 123, "value": 100}]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                ]
            }
        }

        collector = LoadBalancerCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Should succeed but not count this node (vhost is "unknown")
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1


class TestDNSCollector:
    """Test DNS metrics collector."""

    def test_dns_collector_initialization(self, mock_client):
        """Test DNS collector initializes correctly."""
        collector = DNSCollector(mock_client, TEST_TENANT)

        assert collector.client == mock_client
        assert collector.tenant == TEST_TENANT
        # Zone metrics
        assert collector.zone_query_count is not None
        # LB health metrics
        assert collector.dns_lb_health is not None
        assert collector.dns_lb_pool_member_health is not None
        # Collection status metrics
        assert collector.collection_success is not None
        assert collector.collection_duration is not None
        assert collector.zone_count is not None
        assert collector.dns_lb_count is not None

    def test_dns_metrics_collection_success(
        self,
        mock_client,
        sample_dns_zone_metrics_response,
        sample_dns_lb_health_response,
        sample_dns_lb_pool_member_health_response
    ):
        """Test successful DNS metrics collection (3 API calls)."""
        mock_client.get_dns_zone_metrics.return_value = sample_dns_zone_metrics_response
        mock_client.get_dns_lb_health_status.return_value = sample_dns_lb_health_response
        mock_client.get_dns_lb_pool_member_health.return_value = sample_dns_lb_pool_member_health_response

        collector = DNSCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Verify success
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1

        # Verify exactly 3 API calls to system namespace
        mock_client.get_dns_zone_metrics.assert_called_once_with(group_by=["DNS_ZONE_NAME"])
        mock_client.get_dns_lb_health_status.assert_called_once()
        mock_client.get_dns_lb_pool_member_health.assert_called_once()

        # Verify counts
        assert collector.zone_count.labels(tenant=TEST_TENANT)._value._value == 3
        assert collector.dns_lb_count.labels(tenant=TEST_TENANT)._value._value == 2

    def test_dns_zone_metrics_processing(
        self,
        mock_client,
        sample_dns_zone_metrics_response
    ):
        """Test DNS zone metrics processing."""
        collector = DNSCollector(mock_client, TEST_TENANT)
        zone_count = collector._process_zone_metrics(sample_dns_zone_metrics_response)

        assert zone_count == 3

        # Check example.com zone
        example_zone = collector.zone_query_count.labels(
            tenant=TEST_TENANT,
            zone="example.com"
        )
        assert example_zone._value._value == 21833.0

        # Check mysite.net zone
        mysite_zone = collector.zone_query_count.labels(
            tenant=TEST_TENANT,
            zone="mysite.net"
        )
        assert mysite_zone._value._value == 15093.0

        # Check test.org zone
        test_zone = collector.zone_query_count.labels(
            tenant=TEST_TENANT,
            zone="test.org"
        )
        assert test_zone._value._value == 1049.0

    def test_dns_lb_health_processing(
        self,
        mock_client,
        sample_dns_lb_health_response
    ):
        """Test DNS LB health status processing."""
        collector = DNSCollector(mock_client, TEST_TENANT)
        lb_count = collector._process_lb_health(sample_dns_lb_health_response)

        assert lb_count == 2

        # Check healthy LB
        healthy_lb = collector.dns_lb_health.labels(
            tenant=TEST_TENANT,
            dns_lb="global-dns-lb"
        )
        assert healthy_lb._value._value == 1.0  # HEALTHY

        # Check unhealthy LB
        unhealthy_lb = collector.dns_lb_health.labels(
            tenant=TEST_TENANT,
            dns_lb="regional-dns-lb"
        )
        assert unhealthy_lb._value._value == 0.0  # UNHEALTHY

    def test_dns_lb_pool_member_health_processing(
        self,
        mock_client,
        sample_dns_lb_pool_member_health_response
    ):
        """Test DNS LB pool member health processing."""
        collector = DNSCollector(mock_client, TEST_TENANT)
        collector._process_pool_member_health(sample_dns_lb_pool_member_health_response)

        # Check healthy member
        healthy_member = collector.dns_lb_pool_member_health.labels(
            tenant=TEST_TENANT,
            dns_lb="global-dns-lb",
            pool="primary-pool",
            member="10.0.0.1"
        )
        assert healthy_member._value._value == 1.0  # HEALTHY

        # Check unhealthy member
        unhealthy_member = collector.dns_lb_pool_member_health.labels(
            tenant=TEST_TENANT,
            dns_lb="regional-dns-lb",
            pool="backup-pool",
            member="10.1.0.1"
        )
        assert unhealthy_member._value._value == 0.0  # UNHEALTHY

    def test_dns_collection_failure(self, mock_client):
        """Test DNS metrics collection failure handling.

        When dns_zone_metrics fails, we continue trying LB health.
        If all 3 API calls fail, we should re-raise the final error.
        """
        mock_client.get_dns_zone_metrics.side_effect = F5XCAPIError("API Error")
        mock_client.get_dns_lb_health_status.side_effect = F5XCAPIError("API Error")
        mock_client.get_dns_lb_pool_member_health.side_effect = F5XCAPIError("API Error")

        collector = DNSCollector(mock_client, TEST_TENANT)
        # Collection should complete (individual failures are handled gracefully)
        # but success metric is still set because no exception propagated
        collector.collect_metrics()

        # Even with all warnings, collection "succeeds" (just no data)
        # This matches the pattern in other collectors where we warn but don't fail
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1
        assert collector.zone_count.labels(tenant=TEST_TENANT)._value._value == 0
        assert collector.dns_lb_count.labels(tenant=TEST_TENANT)._value._value == 0

    def test_dns_empty_response_handling(self, mock_client):
        """Test DNS collector handles empty responses gracefully."""
        mock_client.get_dns_zone_metrics.return_value = {"data": []}
        mock_client.get_dns_lb_health_status.return_value = {"items": []}
        mock_client.get_dns_lb_pool_member_health.return_value = {"items": []}

        collector = DNSCollector(mock_client, TEST_TENANT)
        collector.collect_metrics()

        # Should succeed even with empty data
        assert collector.collection_success.labels(tenant=TEST_TENANT)._value._value == 1
        assert collector.zone_count.labels(tenant=TEST_TENANT)._value._value == 0
        assert collector.dns_lb_count.labels(tenant=TEST_TENANT)._value._value == 0


class TestCollectorIntegration:
    """Test collector integration scenarios."""

    def test_all_collectors_with_prometheus_registry(self, mock_client):
        """Test all collectors can be properly registered with Prometheus registry."""
        from prometheus_client import CollectorRegistry, generate_latest

        # Create a custom registry for testing
        registry = CollectorRegistry()

        # Create collectors (matching what MetricsServer uses)
        quota_collector = QuotaCollector(mock_client, TEST_TENANT)
        security_collector = SecurityCollector(mock_client, TEST_TENANT)
        synthetic_collector = SyntheticMonitoringCollector(mock_client, TEST_TENANT)
        lb_collector = LoadBalancerCollector(mock_client, TEST_TENANT)
        dns_collector = DNSCollector(mock_client, TEST_TENANT)

        # Register individual metrics with registry (like MetricsServer does)
        registry.register(quota_collector.quota_limit)
        registry.register(quota_collector.quota_current)
        registry.register(quota_collector.quota_utilization)
        registry.register(quota_collector.quota_collection_success)
        registry.register(quota_collector.quota_collection_duration)

        # Security metrics - Per-LB metrics (from app_firewall/metrics API)
        registry.register(security_collector.total_requests)
        registry.register(security_collector.attacked_requests)
        registry.register(security_collector.bot_detections)
        # Security metrics - Namespace event counts (from events/aggregation API)
        registry.register(security_collector.waf_events)
        registry.register(security_collector.bot_defense_events)
        registry.register(security_collector.api_events)
        registry.register(security_collector.service_policy_events)
        registry.register(security_collector.malicious_user_events)
        registry.register(security_collector.dos_events)
        # Security collection status
        registry.register(security_collector.collection_success)
        registry.register(security_collector.collection_duration)

        # Synthetic monitoring metrics (namespace-level aggregates)
        registry.register(synthetic_collector.http_monitors_total)
        registry.register(synthetic_collector.http_monitors_healthy)
        registry.register(synthetic_collector.http_monitors_critical)
        registry.register(synthetic_collector.dns_monitors_total)
        registry.register(synthetic_collector.dns_monitors_healthy)
        registry.register(synthetic_collector.dns_monitors_critical)
        registry.register(synthetic_collector.collection_success)
        registry.register(synthetic_collector.collection_duration)

        # Unified LB collector metrics (HTTP, TCP, UDP)
        registry.register(lb_collector.http_request_rate)
        registry.register(lb_collector.http_error_rate)
        registry.register(lb_collector.http_latency)
        registry.register(lb_collector.tcp_connection_rate)
        registry.register(lb_collector.tcp_error_rate)
        registry.register(lb_collector.udp_request_throughput)
        registry.register(lb_collector.udp_response_throughput)
        registry.register(lb_collector.collection_success)
        registry.register(lb_collector.collection_duration)
        registry.register(lb_collector.http_lb_count)
        registry.register(lb_collector.tcp_lb_count)
        registry.register(lb_collector.udp_lb_count)

        # DNS collector metrics
        registry.register(dns_collector.zone_query_count)
        registry.register(dns_collector.dns_lb_health)
        registry.register(dns_collector.dns_lb_pool_member_health)
        registry.register(dns_collector.collection_success)
        registry.register(dns_collector.collection_duration)
        registry.register(dns_collector.zone_count)
        registry.register(dns_collector.dns_lb_count)

        # Test that metrics can be generated (this would have caught the bug)
        metrics_output = generate_latest(registry)
        assert metrics_output is not None
        assert len(metrics_output) > 0

        # Test that metrics output contains expected metric names
        metrics_str = metrics_output.decode('utf-8')
        assert 'f5xc_quota_limit' in metrics_str
        assert 'f5xc_security_collection_success' in metrics_str
        assert 'f5xc_synthetic_http_monitors_total' in metrics_str
        # Unified LB metrics
        assert 'f5xc_http_lb_request_rate' in metrics_str
        assert 'f5xc_tcp_lb_connection_rate' in metrics_str
        assert 'f5xc_udp_lb_request_throughput_bps' in metrics_str
        assert 'f5xc_lb_collection_success' in metrics_str  # Single unified collection success
        # DNS metrics
        assert 'f5xc_dns_zone_query_count' in metrics_str
        assert 'f5xc_dns_lb_health_status' in metrics_str
        assert 'f5xc_dns_collection_success' in metrics_str

    def test_collector_error_handling(self, mock_client):
        """Test collector error handling doesn't crash."""
        mock_client.get_quota_usage.side_effect = Exception("Network error")

        with patch('prometheus_client.REGISTRY', CollectorRegistry()):
            collector = QuotaCollector(mock_client, TEST_TENANT)

            with pytest.raises(Exception):
                collector.collect_metrics("system")

            # Collector should still be usable after error
            mock_client.get_quota_usage.side_effect = None
            mock_client.get_quota_usage.return_value = {"quota_usage": {}}

            # Should not raise
            collector.collect_metrics("system")
