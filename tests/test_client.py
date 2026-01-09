"""Tests for F5XC API client."""

import json
import time
from unittest.mock import Mock

import pytest
import responses

from f5xc_exporter.client import (
    CircuitBreaker,
    CircuitBreakerState,
    F5XCAPIError,
    F5XCAuthenticationError,
    F5XCCircuitBreakerOpenError,
    F5XCClient,
    F5XCRateLimitError,
)


class TestF5XCClient:
    """Test F5XC API client."""

    def test_client_initialization(self, test_config):
        """Test client initializes correctly."""
        client = F5XCClient(test_config)

        assert client.config == test_config
        assert client.session is not None
        assert "APIToken test-token-123" in client.session.headers["Authorization"]
        assert "application/json" in client.session.headers["Content-Type"]

    @responses.activate
    def test_successful_get_request(self, test_config):
        """Test successful GET request."""
        responses.add(responses.GET, "https://test.console.ves.volterra.io/api/test", json={"status": "ok"}, status=200)

        client = F5XCClient(test_config)
        result = client.get("/api/test")

        assert result == {"status": "ok"}
        assert len(responses.calls) == 1

    @responses.activate
    def test_successful_post_request(self, test_config):
        """Test successful POST request."""
        responses.add(
            responses.POST, "https://test.console.ves.volterra.io/api/test", json={"created": True}, status=201
        )

        client = F5XCClient(test_config)
        result = client.post("/api/test", json={"data": "value"})

        assert result == {"created": True}
        assert len(responses.calls) == 1
        assert json.loads(responses.calls[0].request.body) == {"data": "value"}

    @responses.activate
    def test_authentication_error(self, test_config):
        """Test authentication error handling."""
        responses.add(
            responses.GET, "https://test.console.ves.volterra.io/api/test", json={"error": "Unauthorized"}, status=401
        )

        client = F5XCClient(test_config)

        with pytest.raises(F5XCAuthenticationError) as exc_info:
            client.get("/api/test")

        assert "Invalid F5XC access token" in str(exc_info.value)

    def test_rate_limit_error(self, test_config):
        """Test rate limit error handling."""
        # Create client with no retries to test our 429 detection
        client = F5XCClient(test_config)

        # Mock the session to return a 429 response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_response.json.return_value = {"error": "Too Many Requests"}

        client.session.request = Mock(return_value=mock_response)

        with pytest.raises(F5XCRateLimitError) as exc_info:
            client.get("/api/test")

        assert "Rate limited. Retry after 60 seconds" in str(exc_info.value)

    @responses.activate
    def test_general_api_error(self, test_config):
        """Test general API error handling."""
        responses.add(
            responses.GET, "https://test.console.ves.volterra.io/api/test", json={"error": "Server Error"}, status=500
        )

        client = F5XCClient(test_config)

        with pytest.raises(F5XCAPIError) as exc_info:
            client.get("/api/test")

        assert "API request failed" in str(exc_info.value)

    @responses.activate
    def test_get_quota_usage(self, test_config, sample_quota_response):
        """Test get quota usage method."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/web/namespaces/system/quota/usage",
            json=sample_quota_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_quota_usage()

        assert result == sample_quota_response
        assert "namespaces/system/quota/usage" in responses.calls[0].request.url

    @responses.activate
    def test_get_quota_usage_custom_namespace(self, test_config, sample_quota_response):
        """Test get quota usage with custom namespace."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/web/namespaces/custom/quota/usage",
            json=sample_quota_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_quota_usage("custom")

        assert result == sample_quota_response
        assert "namespaces/custom/quota/usage" in responses.calls[0].request.url

    @responses.activate
    def test_get_service_graph_data(self, test_config, sample_service_graph_response):
        """Test get service graph data method."""
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/system/graph/service",
            json=sample_service_graph_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_service_graph_data()

        assert result == sample_service_graph_response
        assert len(responses.calls) == 1

        # Check POST payload
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["agg_type"] == "avg"
        assert request_body["namespace"] == "system"
        assert request_body["tenant"] == "test"  # from test.console.ves.volterra.io
        assert "overallHealth" in request_body["metrics"]

    @responses.activate
    def test_get_security_methods(self, test_config):
        """Test security-related API methods with correct endpoints."""
        # Mock the correct API endpoints for new security methods
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/demo-shop/app_firewall/metrics",
            json={"data": [], "step": "5m"},
            status=200,
        )
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/demo-shop/app_security/events/aggregation",
            json={"aggs": {}, "total_hits": "0"},
            status=200,
        )

        client = F5XCClient(test_config)

        # Test security API methods (2 calls per namespace)
        result = client.get_app_firewall_metrics_for_namespace("demo-shop")
        assert "data" in result

        result = client.get_security_event_counts_for_namespace("demo-shop", ["waf_sec_event"])
        assert "aggs" in result

    @responses.activate
    def test_get_synthetic_summary(self, test_config, sample_synthetic_http_summary_response):
        """Test synthetic monitoring summary API with GET method."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/observability/synthetic_monitor/namespaces/demo-shop/global-summary",
            json=sample_synthetic_http_summary_response,
            status=200,
        )

        client = F5XCClient(test_config)

        # Test HTTP monitor summary
        result = client.get_synthetic_summary("demo-shop", "http")
        assert result["number_of_monitors"] == 2
        assert result["healthy_monitor_count"] == 2
        assert result["critical_monitor_count"] == 0

    @responses.activate
    def test_get_http_lb_metrics(self, test_config, sample_http_lb_response):
        """Test HTTP LB metrics API method with QueryAllNamespaces endpoint."""
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/system/graph/all_ns_service",
            json=sample_http_lb_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_http_lb_metrics()

        assert result == sample_http_lb_response
        assert len(responses.calls) == 1

        # Check POST payload contains expected fields
        import json

        request_body = json.loads(responses.calls[0].request.body)
        assert "field_selector" in request_body
        assert "node" in request_body["field_selector"]
        assert "downstream" in request_body["field_selector"]["node"]["metric"]
        assert "HTTP_REQUEST_RATE" in request_body["field_selector"]["node"]["metric"]["downstream"]
        assert "label_filter" in request_body
        assert request_body["label_filter"][0]["label"] == "LABEL_VHOST_TYPE"
        assert request_body["label_filter"][0]["value"] == "HTTP_LOAD_BALANCER"
        assert "group_by" in request_body
        assert "NAMESPACE" in request_body["group_by"]
        assert "VHOST" in request_body["group_by"]
        assert "SITE" in request_body["group_by"]

    @responses.activate
    def test_get_tcp_lb_metrics(self, test_config, sample_tcp_lb_response):
        """Test TCP LB metrics API method with QueryAllNamespaces endpoint."""
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/system/graph/all_ns_service",
            json=sample_tcp_lb_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_tcp_lb_metrics()

        assert result == sample_tcp_lb_response
        assert len(responses.calls) == 1

        # Check POST payload contains expected fields
        import json

        request_body = json.loads(responses.calls[0].request.body)
        assert "field_selector" in request_body
        assert "node" in request_body["field_selector"]
        assert "downstream" in request_body["field_selector"]["node"]["metric"]
        assert "TCP_CONNECTION_RATE" in request_body["field_selector"]["node"]["metric"]["downstream"]
        assert "label_filter" in request_body
        assert request_body["label_filter"][0]["label"] == "LABEL_VHOST_TYPE"
        assert request_body["label_filter"][0]["value"] == "TCP_LOAD_BALANCER"
        assert "group_by" in request_body
        assert "NAMESPACE" in request_body["group_by"]
        assert "VHOST" in request_body["group_by"]
        assert "SITE" in request_body["group_by"]

    @responses.activate
    def test_get_udp_lb_metrics(self, test_config, sample_udp_lb_response):
        """Test UDP LB metrics API method with QueryAllNamespaces endpoint."""
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/system/graph/all_ns_service",
            json=sample_udp_lb_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_udp_lb_metrics()

        assert result == sample_udp_lb_response
        assert len(responses.calls) == 1

        # Check POST payload contains expected fields
        import json

        request_body = json.loads(responses.calls[0].request.body)
        assert "field_selector" in request_body
        assert "node" in request_body["field_selector"]
        assert "downstream" in request_body["field_selector"]["node"]["metric"]
        assert "REQUEST_THROUGHPUT" in request_body["field_selector"]["node"]["metric"]["downstream"]
        assert "label_filter" in request_body
        assert request_body["label_filter"][0]["label"] == "LABEL_VHOST_TYPE"
        assert request_body["label_filter"][0]["value"] == "UDP_LOAD_BALANCER"
        assert "group_by" in request_body
        assert "NAMESPACE" in request_body["group_by"]
        assert "VHOST" in request_body["group_by"]
        assert "SITE" in request_body["group_by"]

    @responses.activate
    def test_list_namespaces(self, test_config):
        """Test list namespaces method."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/web/namespaces",
            json={
                "items": [
                    {"name": "default"},
                    {"name": "prod"},
                    {"name": "staging"},
                    {"name": "system"},  # Should be filtered out (aggregates all namespaces)
                    {"name": "ves-io-system"},  # Should be filtered out
                    {"name": "ves-io-internal"},  # Should be filtered out
                ]
            },
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.list_namespaces()

        # Should filter out ves-io-* namespaces and system namespace
        assert result == ["default", "prod", "staging"]
        assert "system" not in result  # system namespace causes duplicate data
        assert "ves-io-system" not in result
        assert "ves-io-internal" not in result

    @responses.activate
    def test_get_all_lb_metrics_for_namespace(self, test_config, sample_http_lb_response):
        """Test get all LB metrics for a single namespace."""
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/prod/graph/service",
            json=sample_http_lb_response,
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_all_lb_metrics_for_namespace("prod")

        assert result == sample_http_lb_response
        assert len(responses.calls) == 1

        # Check POST payload contains expected fields
        request_body = json.loads(responses.calls[0].request.body)
        assert "field_selector" in request_body
        assert "node" in request_body["field_selector"]
        assert "downstream" in request_body["field_selector"]["node"]["metric"]
        # Should include HTTP, TCP, and common metrics
        assert "HTTP_REQUEST_RATE" in request_body["field_selector"]["node"]["metric"]["downstream"]
        assert "TCP_CONNECTION_RATE" in request_body["field_selector"]["node"]["metric"]["downstream"]
        assert "REQUEST_THROUGHPUT" in request_body["field_selector"]["node"]["metric"]["downstream"]
        # Should NOT have label_filter (get all LB types)
        assert "label_filter" not in request_body
        # Should have VIRTUAL_HOST_TYPE in group_by
        assert "VIRTUAL_HOST_TYPE" in request_body["group_by"]
        assert "VHOST" in request_body["group_by"]
        assert "SITE" in request_body["group_by"]

    @responses.activate
    def test_get_all_lb_metrics(self, test_config, sample_http_lb_response):
        """Test get all LB metrics across all namespaces."""
        # Mock list_namespaces
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/web/namespaces",
            json={
                "items": [
                    {"name": "prod"},
                    {"name": "staging"},
                ]
            },
            status=200,
        )

        # Mock per-namespace service graph calls
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/prod/graph/service",
            json={
                "data": {
                    "nodes": [
                        {
                            "id": {"vhost": "app-1", "site": "site-1", "virtual_host_type": "HTTP_LOAD_BALANCER"},
                            "data": {"metric": {"downstream": []}},
                        }
                    ],
                    "edges": [],
                }
            },
            status=200,
        )
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/staging/graph/service",
            json={
                "data": {
                    "nodes": [
                        {
                            "id": {"vhost": "app-2", "site": "site-2", "virtual_host_type": "TCP_LOAD_BALANCER"},
                            "data": {"metric": {"downstream": []}},
                        }
                    ],
                    "edges": [],
                }
            },
            status=200,
        )

        client = F5XCClient(test_config)
        result = client.get_all_lb_metrics()

        # Should have nodes from both namespaces
        assert len(result["data"]["nodes"]) == 2

        # Each node should have namespace added to its ID
        node_ids = [node["id"] for node in result["data"]["nodes"]]
        assert any(n.get("namespace") == "prod" and n.get("vhost") == "app-1" for n in node_ids)
        assert any(n.get("namespace") == "staging" and n.get("vhost") == "app-2" for n in node_ids)

    @responses.activate
    def test_get_all_lb_metrics_handles_namespace_failure(self, test_config):
        """Test get_all_lb_metrics continues if individual namespace fails."""
        # Mock list_namespaces
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/web/namespaces",
            json={
                "items": [
                    {"name": "prod"},
                    {"name": "broken"},
                ]
            },
            status=200,
        )

        # Mock prod namespace - success
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/prod/graph/service",
            json={
                "data": {
                    "nodes": [
                        {
                            "id": {"vhost": "app-1", "site": "site-1", "virtual_host_type": "HTTP_LOAD_BALANCER"},
                            "data": {"metric": {"downstream": []}},
                        }
                    ],
                    "edges": [],
                }
            },
            status=200,
        )

        # Mock broken namespace - failure
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/data/namespaces/broken/graph/service",
            json={"error": "Internal Server Error"},
            status=500,
        )

        client = F5XCClient(test_config)
        result = client.get_all_lb_metrics()

        # Should still have node from successful namespace
        assert len(result["data"]["nodes"]) == 1
        assert result["data"]["nodes"][0]["id"]["namespace"] == "prod"

    def test_client_close(self, test_config):
        """Test client close method."""
        client = F5XCClient(test_config)
        mock_session = Mock()
        client.session = mock_session

        client.close()

        mock_session.close.assert_called_once()

    @responses.activate
    def test_url_construction(self, test_config):
        """Test URL construction handles trailing slashes correctly."""
        # Test with trailing slash in config
        config_with_slash = test_config.model_copy(update={"f5xc_tenant_url": "https://test.console.ves.volterra.io/"})

        responses.add(responses.GET, "https://test.console.ves.volterra.io/api/test", json={"ok": True}, status=200)

        client = F5XCClient(config_with_slash)
        result = client.get("/api/test")

        assert result == {"ok": True}
        # Should not have double slashes
        assert "//api" not in responses.calls[0].request.url


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_is_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=60, success_threshold=2)

        assert cb.is_call_allowed("/api/test")
        assert cb.get_state_value("/api/test") == CircuitBreakerState.CLOSED.value
        assert cb.get_failure_count("/api/test") == 0

    def test_transitions_to_open_after_threshold_failures(self):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=60, success_threshold=2)
        endpoint = "/api/test"

        # Record 2 failures - should stay CLOSED
        cb.record_failure(endpoint)
        cb.record_failure(endpoint)
        assert cb.is_call_allowed(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.CLOSED.value

        # 3rd failure - should transition to OPEN
        cb.record_failure(endpoint)
        assert not cb.is_call_allowed(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.OPEN.value
        assert cb.get_failure_count(endpoint) == 3

    def test_open_circuit_rejects_calls(self):
        """Test OPEN circuit rejects all calls."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=60, success_threshold=2)
        endpoint = "/api/test"

        # Open the circuit
        cb.record_failure(endpoint)
        cb.record_failure(endpoint)

        assert cb.get_state_value(endpoint) == CircuitBreakerState.OPEN.value
        assert not cb.is_call_allowed(endpoint)

    def test_transitions_to_half_open_after_timeout(self):
        """Test circuit transitions to HALF_OPEN after timeout."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1, success_threshold=2)
        endpoint = "/api/test"

        # Open the circuit
        cb.record_failure(endpoint)
        cb.record_failure(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.OPEN.value

        # Wait for timeout
        time.sleep(1.1)

        # Should transition to HALF_OPEN and allow call
        assert cb.is_call_allowed(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.HALF_OPEN.value

    def test_half_open_closes_after_success_threshold(self):
        """Test circuit closes after success threshold in HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1, success_threshold=2)
        endpoint = "/api/test"

        # Open the circuit
        cb.record_failure(endpoint)
        cb.record_failure(endpoint)

        # Wait and transition to HALF_OPEN
        time.sleep(1.1)
        assert cb.is_call_allowed(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.HALF_OPEN.value

        # First success - should stay HALF_OPEN
        cb.record_success(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.HALF_OPEN.value

        # Second success - should close circuit
        cb.record_success(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.CLOSED.value
        assert cb.get_failure_count(endpoint) == 0

    def test_half_open_reopens_on_failure(self):
        """Test circuit reopens on failure in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1, success_threshold=2)
        endpoint = "/api/test"

        # Open the circuit
        cb.record_failure(endpoint)
        cb.record_failure(endpoint)

        # Wait and transition to HALF_OPEN
        time.sleep(1.1)
        assert cb.is_call_allowed(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.HALF_OPEN.value

        # Failure in HALF_OPEN - should reopen
        cb.record_failure(endpoint)
        assert cb.get_state_value(endpoint) == CircuitBreakerState.OPEN.value
        assert not cb.is_call_allowed(endpoint)

    def test_success_resets_failure_count_in_closed_state(self):
        """Test success resets failure count in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=60, success_threshold=2)
        endpoint = "/api/test"

        # Record failures
        cb.record_failure(endpoint)
        cb.record_failure(endpoint)
        assert cb.get_failure_count(endpoint) == 2

        # Record success - should reset count
        cb.record_success(endpoint)
        assert cb.get_failure_count(endpoint) == 0
        assert cb.get_state_value(endpoint) == CircuitBreakerState.CLOSED.value

    def test_multiple_endpoints_tracked_independently(self):
        """Test different endpoints are tracked independently."""
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=60, success_threshold=2)
        endpoint1 = "/api/test1"
        endpoint2 = "/api/test2"

        # Open circuit for endpoint1
        cb.record_failure(endpoint1)
        cb.record_failure(endpoint1)

        assert cb.get_state_value(endpoint1) == CircuitBreakerState.OPEN.value
        assert not cb.is_call_allowed(endpoint1)

        # endpoint2 should still be CLOSED
        assert cb.get_state_value(endpoint2) == CircuitBreakerState.CLOSED.value
        assert cb.is_call_allowed(endpoint2)

    def test_get_all_endpoints(self):
        """Test getting all tracked endpoints."""
        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=60, success_threshold=2)

        cb.record_failure("/api/test1")
        cb.record_failure("/api/test2")
        cb.record_failure("/api/test3")

        endpoints = cb.get_all_endpoints()
        assert "/api/test1" in endpoints
        assert "/api/test2" in endpoints
        assert "/api/test3" in endpoints


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with F5XCClient."""

    def test_circuit_breaker_open_raises_exception(self, test_config):
        """Test that open circuit breaker raises exception."""
        client = F5XCClient(test_config)
        endpoint = "/api/test"

        # Manually open the circuit
        client.circuit_breaker.record_failure(endpoint)
        client.circuit_breaker.record_failure(endpoint)
        client.circuit_breaker.record_failure(endpoint)
        client.circuit_breaker.record_failure(endpoint)
        client.circuit_breaker.record_failure(endpoint)

        # Attempt to make request should raise circuit breaker exception
        with pytest.raises(F5XCCircuitBreakerOpenError) as exc_info:
            client.get(endpoint)

        assert "Circuit breaker is open" in str(exc_info.value)

    @responses.activate
    def test_successful_request_records_success(self, test_config):
        """Test successful request records success in circuit breaker."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/test",
            json={"status": "ok"},
            status=200
        )

        client = F5XCClient(test_config)
        endpoint = "/api/test"

        # Make successful request
        result = client.get(endpoint)

        assert result == {"status": "ok"}
        # Verify circuit breaker recorded success
        assert client.circuit_breaker.get_failure_count(endpoint) == 0
        assert client.circuit_breaker.get_state_value(endpoint) == CircuitBreakerState.CLOSED.value

    def test_failed_request_records_failure(self, test_config):
        """Test failed request records failure in circuit breaker."""
        import requests.exceptions

        client = F5XCClient(test_config)
        endpoint = "/api/test"

        # Mock session to raise connection error
        client.session.request = Mock(side_effect=requests.exceptions.ConnectionError("Connection failed"))

        # Attempt request
        with pytest.raises(F5XCAPIError):
            client.get(endpoint)

        # Verify circuit breaker recorded failure
        assert client.circuit_breaker.get_failure_count(endpoint) == 1

    def test_rate_limit_records_failure(self, test_config):
        """Test rate limit error records failure in circuit breaker."""
        client = F5XCClient(test_config)
        endpoint = "/api/test"

        # Mock the session to return a 429 response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_response.json.return_value = {"error": "Too Many Requests"}

        client.session.request = Mock(return_value=mock_response)

        with pytest.raises(F5XCRateLimitError):
            client.get(endpoint)

        # Verify circuit breaker recorded failure
        assert client.circuit_breaker.get_failure_count(endpoint) >= 1

    def test_auth_error_does_not_record_failure(self, test_config):
        """Test authentication error does not record circuit breaker failure."""
        client = F5XCClient(test_config)
        endpoint = "/api/test"

        # Mock the session to return a 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Unauthorized"}

        client.session.request = Mock(return_value=mock_response)

        with pytest.raises(F5XCAuthenticationError):
            client.get(endpoint)

        # Auth errors should NOT record circuit breaker failure
        assert client.circuit_breaker.get_failure_count(endpoint) == 0

    @responses.activate
    def test_circuit_breaker_metrics_updated(self, test_config):
        """Test circuit breaker metrics are updated."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/test",
            json={"status": "ok"},
            status=200
        )

        client = F5XCClient(test_config)
        endpoint = "/api/test"

        # Make successful request
        client.get(endpoint)

        # Verify metrics exist
        assert client.circuit_breaker_state_metric is not None
        assert client.circuit_breaker_failures_metric is not None
