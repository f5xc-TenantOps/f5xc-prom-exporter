"""Tests for F5XC API client."""

import json
import pytest
import responses
from unittest.mock import Mock, patch

from f5xc_exporter.client import F5XCClient, F5XCAPIError, F5XCAuthenticationError, F5XCRateLimitError


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
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/test",
            json={"status": "ok"},
            status=200
        )

        client = F5XCClient(test_config)
        result = client.get("/api/test")

        assert result == {"status": "ok"}
        assert len(responses.calls) == 1

    @responses.activate
    def test_successful_post_request(self, test_config):
        """Test successful POST request."""
        responses.add(
            responses.POST,
            "https://test.console.ves.volterra.io/api/test",
            json={"created": True},
            status=201
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
            responses.GET,
            "https://test.console.ves.volterra.io/api/test",
            json={"error": "Unauthorized"},
            status=401
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
            responses.GET,
            "https://test.console.ves.volterra.io/api/test",
            json={"error": "Server Error"},
            status=500
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
            status=200
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
            status=200
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
            status=200
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
        """Test security-related API methods."""
        # Mock all security endpoints
        security_endpoints = [
            "waf/metrics",
            "bot_defense/metrics",
            "api_security/metrics",
            "ddos/metrics",
            "security/events"
        ]

        for endpoint in security_endpoints:
            responses.add(
                responses.GET,
                f"https://test.console.ves.volterra.io/api/web/namespaces/system/{endpoint}",
                json={"data": f"test_{endpoint.replace('/', '_')}"},
                status=200
            )

        client = F5XCClient(test_config)

        # Test each method
        assert client.get_waf_metrics()["data"] == "test_waf_metrics"
        assert client.get_bot_defense_metrics()["data"] == "test_bot_defense_metrics"
        assert client.get_api_security_metrics()["data"] == "test_api_security_metrics"
        assert client.get_ddos_metrics()["data"] == "test_ddos_metrics"

        # Security events has query parameters
        events_result = client.get_security_events()
        assert events_result["data"] == "test_security_events"

    @responses.activate
    def test_get_synthetic_monitoring_metrics(self, test_config, sample_synthetic_response):
        """Test synthetic monitoring API method."""
        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/web/namespaces/system/synthetic_monitoring/metrics",
            json=sample_synthetic_response,
            status=200
        )

        client = F5XCClient(test_config)
        result = client.get_synthetic_monitoring_metrics()

        assert result == sample_synthetic_response

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
        config_with_slash = test_config.model_copy(update={
            'f5xc_tenant_url': 'https://test.console.ves.volterra.io/'
        })

        responses.add(
            responses.GET,
            "https://test.console.ves.volterra.io/api/test",
            json={"ok": True},
            status=200
        )

        client = F5XCClient(config_with_slash)
        result = client.get("/api/test")

        assert result == {"ok": True}
        # Should not have double slashes
        assert "//api" not in responses.calls[0].request.url