"""Integration tests for LoadBalancerCollector."""

import responses

from f5xc_exporter.collectors.loadbalancer import LoadBalancerCollector

from .conftest import get_metric_value


class TestLoadBalancerCollectorIntegration:
    """Integration tests for LoadBalancerCollector using real client with mocked HTTP responses."""

    @responses.activate
    def test_successful_collection(self, real_client, mock_namespace_list, mock_loadbalancer_apis):
        """Test successful load balancer collection with valid API response."""
        mock_namespace_list(["prod"])
        mock_loadbalancer_apis("prod")

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify collection success
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_collection_success_metric(self, real_client, load_fixture, test_config):
        """Test that collection success metric is set to 1 on successful collection."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1

    @responses.activate
    def test_collection_duration_metric(self, real_client, load_fixture, test_config):
        """Test that collection duration metric is set."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        duration = get_metric_value(collector.collection_duration, tenant="test-tenant")
        assert duration >= 0

    @responses.activate
    def test_http_lb_metrics(self, real_client, load_fixture, test_config):
        """Test that HTTP LB metrics are correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify HTTP-specific metrics from fixture
        assert get_metric_value(collector.http_request_rate, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 150.5

        assert get_metric_value(collector.http_error_rate, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 2.5

        assert get_metric_value(collector.http_latency, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 0.025

    @responses.activate
    def test_http_latency_percentiles(self, real_client, load_fixture, test_config):
        """Test that HTTP latency percentile metrics are correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify latency percentiles
        assert get_metric_value(collector.http_latency_p50, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 0.02

        assert get_metric_value(collector.http_latency_p90, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 0.04

        assert get_metric_value(collector.http_latency_p99, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 0.08

    @responses.activate
    def test_tcp_lb_metrics(self, real_client, load_fixture, test_config):
        """Test that TCP LB metrics are correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify TCP-specific metrics from fixture
        assert get_metric_value(collector.tcp_connection_rate, tenant="test-tenant",
            namespace="prod",
            load_balancer="tcp-backend",
            site="ce-site-1",
            direction="downstream",) == 50.0

        assert get_metric_value(collector.tcp_error_rate, tenant="test-tenant",
            namespace="prod",
            load_balancer="tcp-backend",
            site="ce-site-1",
            direction="downstream",) == 0.5

        assert get_metric_value(collector.tcp_connection_duration, tenant="test-tenant",
            namespace="prod",
            load_balancer="tcp-backend",
            site="ce-site-1",
            direction="downstream",) == 10.5

    @responses.activate
    def test_udp_lb_metrics(self, real_client, load_fixture, test_config):
        """Test that UDP LB metrics are correctly processed (only common metrics)."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify UDP metrics (only common metrics like throughput)
        assert get_metric_value(collector.udp_request_throughput, tenant="test-tenant",
            namespace="prod",
            load_balancer="udp-service",
            site="ce-site-1",
            direction="downstream",) == 500000

        assert get_metric_value(collector.udp_response_throughput, tenant="test-tenant",
            namespace="prod",
            load_balancer="udp-service",
            site="ce-site-1",
            direction="downstream",) == 600000

    @responses.activate
    def test_upstream_downstream_direction(self, real_client, load_fixture, test_config):
        """Test that both upstream and downstream directions are correctly handled."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify downstream direction
        downstream_value = get_metric_value(collector.http_request_rate, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",)
        assert downstream_value == 150.5

        # Verify upstream direction
        upstream_value = get_metric_value(collector.http_request_rate, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="upstream",)
        assert upstream_value == 120.0

    @responses.activate
    def test_healthscore_metrics(self, real_client, load_fixture, test_config):
        """Test that healthscore metrics are correctly processed."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock per-namespace service graph endpoint
        lb_data = load_fixture("loadbalancer_response.json")
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json=lb_data,
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Verify healthscore metrics
        assert get_metric_value(collector.http_healthscore_overall, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 95.0

        assert get_metric_value(collector.http_healthscore_connectivity, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 98.0

        assert get_metric_value(collector.http_healthscore_performance, tenant="test-tenant",
            namespace="prod",
            load_balancer="app-frontend",
            site="ce-site-1",
            direction="downstream",) == 92.0

    @responses.activate
    def test_api_500_error(self, real_client, test_config):
        """Test that API 500 error on namespace is caught and logged but collection continues."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock service graph endpoint with error
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json={"error": "Internal server error"},
            status=500,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        # Should not raise - per-namespace errors are caught and logged
        collector.collect_metrics()

        # Collection should still succeed (partial success)
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1
        # LB counts should be 0 since namespace failed
        assert get_metric_value(collector.http_lb_count, tenant="test-tenant") == 0

    @responses.activate
    def test_empty_nodes(self, real_client, test_config):
        """Test that empty nodes array results in success=1 with counts=0."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock service graph endpoint
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json={"data": {"nodes": []}},
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1
        assert get_metric_value(collector.http_lb_count, tenant="test-tenant") == 0
        assert get_metric_value(collector.tcp_lb_count, tenant="test-tenant") == 0
        assert get_metric_value(collector.udp_lb_count, tenant="test-tenant") == 0

    @responses.activate
    def test_unknown_virtual_host_type(self, real_client, test_config):
        """Test that nodes without recognized LB type are skipped."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock service graph endpoint
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json={
                "data": {
                    "nodes": [
                        {
                            "id": {
                                "namespace": "prod",
                                "vhost": "unknown-lb",
                                "site": "ce-site-1",
                                "virtual_host_type": "UNKNOWN_TYPE",
                            },
                            "data": {"metric": {"downstream": [], "upstream": []}, "healthscore": {}},
                        }
                    ]
                }
            },
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Collection should succeed but no LBs should be counted
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1
        assert get_metric_value(collector.http_lb_count, tenant="test-tenant") == 0

    @responses.activate
    def test_missing_vhost(self, real_client, test_config):
        """Test that nodes without vhost identification are skipped."""
        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Mock service graph endpoint
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json={
                "data": {
                    "nodes": [
                        {
                            "id": {
                                "namespace": "prod",
                                "site": "ce-site-1",
                                "virtual_host_type": "HTTP_LOAD_BALANCER",
                            },
                            "data": {"metric": {"downstream": [], "upstream": []}, "healthscore": {}},
                        }
                    ]
                }
            },
            status=200,
        )

        collector = LoadBalancerCollector(real_client, "test-tenant")
        collector.collect_metrics()

        # Collection should succeed but no LBs should be counted
        assert get_metric_value(collector.collection_success, tenant="test-tenant") == 1
        assert get_metric_value(collector.http_lb_count, tenant="test-tenant") == 0

    @responses.activate
    def test_cardinality_limit_lb_count(self, real_client, test_config):
        """Test that collection stops when max LBs per namespace is exceeded."""
        # Create cardinality tracker with low LB limit
        from f5xc_exporter.cardinality import CardinalityTracker
        tracker = CardinalityTracker(
            max_namespaces=100,
            max_load_balancers_per_namespace=1,
            max_dns_zones=100,
            warn_cardinality_threshold=10000,
        )

        # Mock namespace list
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": "prod"}]},
            status=200,
        )

        # Create response with 2 LBs
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/prod/graph/service",
            json={
                "data": {
                    "nodes": [
                        {
                            "id": {
                                "namespace": "prod",
                                "vhost": "lb-1",
                                "site": "ce-site-1",
                                "virtual_host_type": "HTTP_LOAD_BALANCER",
                            },
                            "data": {"metric": {"downstream": [], "upstream": []}, "healthscore": {}},
                        },
                        {
                            "id": {
                                "namespace": "prod",
                                "vhost": "lb-2",
                                "site": "ce-site-1",
                                "virtual_host_type": "HTTP_LOAD_BALANCER",
                            },
                            "data": {"metric": {"downstream": [], "upstream": []}, "healthscore": {}},
                        },
                    ]
                }
            },
            status=200,
        )

        # Create collector with cardinality tracker
        collector = LoadBalancerCollector(real_client, "test-tenant", tracker)
        collector.collect_metrics()

        # Only 1 LB should be processed due to limit
        assert get_metric_value(collector.http_lb_count, tenant="test-tenant") == 1
