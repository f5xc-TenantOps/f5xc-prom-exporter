"""Pytest configuration for integration tests."""

import json
import os
from pathlib import Path

import pytest
from prometheus_client import REGISTRY

from f5xc_exporter.cardinality import CardinalityTracker
from f5xc_exporter.client import F5XCClient
from f5xc_exporter.config import Config


@pytest.fixture(autouse=True)
def clean_env_and_registry():
    """Clean environment variables and Prometheus registry before and after each test.

    Adapted from tests/conftest.py:582-633 (clean_env fixture).
    """
    # Environment variables to clean
    env_vars = [
        "F5XC_TENANT_URL",
        "F5XC_ACCESS_TOKEN",
        "F5XC_EXP_HTTP_PORT",
        "F5XC_EXP_LOG_LEVEL",
        "F5XC_QUOTA_INTERVAL",
        "F5XC_HTTP_LB_INTERVAL",
        "F5XC_TCP_LB_INTERVAL",
        "F5XC_UDP_LB_INTERVAL",
        "F5XC_SECURITY_INTERVAL",
        "F5XC_SYNTHETIC_INTERVAL",
        "F5XC_DNS_INTERVAL",
        "F5XC_MAX_CONCURRENT_REQUESTS",
        "F5XC_REQUEST_TIMEOUT",
        "F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        "F5XC_CIRCUIT_BREAKER_TIMEOUT",
        "F5XC_CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
        "F5XC_MAX_NAMESPACES",
        "F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE",
        "F5XC_MAX_DNS_ZONES",
        "F5XC_WARN_CARDINALITY_THRESHOLD",
    ]

    # Clean environment before test
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]

    # Clean up Prometheus registry before test
    try:
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            try:
                REGISTRY.unregister(collector)
            except KeyError:
                pass  # Already unregistered
    except Exception:
        pass  # Registry might be in inconsistent state

    yield

    # Clean up after test
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]

    # Clean registry after test
    try:
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            try:
                REGISTRY.unregister(collector)
            except KeyError:
                pass
    except Exception:
        pass


@pytest.fixture
def test_config():
    """Create test configuration with required environment variables."""
    os.environ["F5XC_TENANT_URL"] = "https://test-tenant.console.ves.volterra.io"
    os.environ["F5XC_ACCESS_TOKEN"] = "test-access-token-123"
    os.environ["F5XC_EXP_HTTP_PORT"] = "8080"
    os.environ["F5XC_EXP_LOG_LEVEL"] = "DEBUG"

    return Config()


@pytest.fixture
def real_client(test_config):
    """Create a real F5XCClient instance (HTTP will be mocked at the HTTP layer).

    This creates an actual F5XCClient with real configuration, but HTTP requests
    will be intercepted by @responses.activate decorator in individual tests.
    """
    client = F5XCClient(test_config)
    yield client
    # Clean up client resources
    client.close()


@pytest.fixture
def cardinality_tracker():
    """Create a CardinalityTracker for testing."""
    return CardinalityTracker(
        max_namespaces=100,
        max_load_balancers_per_namespace=50,
        max_dns_zones=100,
        warn_cardinality_threshold=10000,
    )


@pytest.fixture
def load_fixture():
    """Load JSON fixture from tests/integration/fixtures/ directory.

    Usage:
        quota_data = load_fixture("quota_response.json")

    Returns:
        Function that loads and parses JSON fixture files.
    """

    def _load_fixture(filename: str) -> dict:
        """Load a JSON fixture file."""
        fixtures_dir = Path(__file__).parent / "fixtures"
        fixture_path = fixtures_dir / filename

        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {fixture_path}")

        with open(fixture_path, "r") as f:
            return json.load(f)

    return _load_fixture


@pytest.fixture
def mock_namespace_list(test_config):
    """Helper to mock namespace list API.

    Usage:
        @responses.activate
        def test_something(mock_namespace_list):
            mock_namespace_list(["prod", "staging"])
            # ... rest of test

    Returns:
        Function that adds namespace list mock to responses.
    """
    import responses

    def _mock_namespace_list(namespaces: list[str], status: int = 200):
        """Add namespace list mock."""
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces",
            json={"items": [{"name": ns} for ns in namespaces]},
            status=status,
        )

    return _mock_namespace_list


@pytest.fixture
def mock_dns_apis(test_config, load_fixture):
    """Helper to mock all DNS-related APIs with fixtures.

    Usage:
        @responses.activate
        def test_something(mock_dns_apis):
            mock_dns_apis()  # Uses default fixtures
            # ... rest of test

    Returns:
        Function that adds all DNS API mocks to responses.
    """
    import responses

    def _mock_dns_apis(
        zone_fixture: str = "dns_zone_metrics_response.json",
        lb_health_fixture: str = "dns_lb_health_response.json",
        pool_health_fixture: str = "dns_pool_health_response.json",
        zone_status: int = 200,
        lb_health_status: int = 200,
        pool_health_status: int = 200,
    ):
        """Add all DNS API mocks."""
        zone_data = load_fixture(zone_fixture)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_zones/metrics",
            json=zone_data,
            status=zone_status,
        )

        lb_health_data = load_fixture(lb_health_fixture)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/health_status",
            json=lb_health_data,
            status=lb_health_status,
        )

        pool_health_data = load_fixture(pool_health_fixture)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/system/dns_load_balancers/pool_members_health_status",
            json=pool_health_data,
            status=pool_health_status,
        )

    return _mock_dns_apis


@pytest.fixture
def mock_loadbalancer_apis(test_config, load_fixture):
    """Helper to mock load balancer APIs per namespace.

    Usage:
        @responses.activate
        def test_something(mock_namespace_list, mock_loadbalancer_apis):
            mock_namespace_list(["prod"])
            mock_loadbalancer_apis("prod")
            # ... rest of test

    Returns:
        Function that adds load balancer API mocks for a namespace.
    """
    import responses

    def _mock_loadbalancer_apis(
        namespace: str,
        fixture: str = "loadbalancer_response.json",
        status: int = 200,
    ):
        """Add load balancer API mock for specific namespace."""
        lb_data = load_fixture(fixture)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/{namespace}/graph/service",
            json=lb_data,
            status=status,
        )

    return _mock_loadbalancer_apis


@pytest.fixture
def mock_synthetic_apis(test_config, load_fixture):
    """Helper to mock synthetic monitoring APIs per namespace.

    Usage:
        @responses.activate
        def test_something(mock_namespace_list, mock_synthetic_apis):
            mock_namespace_list(["test-ns"])
            mock_synthetic_apis("test-ns")
            # ... rest of test

    Returns:
        Function that adds synthetic monitoring API mocks for a namespace.
    """
    import responses

    def _mock_synthetic_apis(
        namespace: str,
        http_fixture: str = "synthetic_http_response.json",
        dns_fixture: str = "synthetic_dns_response.json",
        http_status: int = 200,
        dns_status: int = 200,
    ):
        """Add synthetic monitoring API mocks for specific namespace."""
        http_data = load_fixture(http_fixture)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/{namespace}/global-summary?monitorType=http",
            json=http_data,
            status=http_status,
        )

        dns_data = load_fixture(dns_fixture)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/observability/synthetic_monitor/namespaces/{namespace}/global-summary?monitorType=dns",
            json=dns_data,
            status=dns_status,
        )

    return _mock_synthetic_apis


@pytest.fixture
def mock_security_apis(test_config, load_fixture):
    """Helper to mock security APIs per namespace.

    Usage:
        @responses.activate
        def test_something(mock_namespace_list, mock_security_apis):
            mock_namespace_list(["test-ns"])
            mock_security_apis("test-ns")
            # ... rest of test

    Returns:
        Function that adds security API mocks for a namespace.
    """
    import responses

    def _mock_security_apis(
        namespace: str,
        app_firewall_fixture: str = "security_app_firewall_response.json",
        events_fixture: str = "security_events_response.json",
        app_firewall_status: int = 200,
        events_status: int = 200,
    ):
        """Add security API mocks for specific namespace."""
        app_firewall_data = load_fixture(app_firewall_fixture)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/{namespace}/app_firewall/metrics",
            json=app_firewall_data,
            status=app_firewall_status,
        )

        events_data = load_fixture(events_fixture)
        responses.add(
            method="POST",
            url=f"{test_config.tenant_url_str}/api/data/namespaces/{namespace}/app_security/events/aggregation",
            json=events_data,
            status=events_status,
        )

    return _mock_security_apis


@pytest.fixture
def mock_quota_api(test_config, load_fixture):
    """Helper to mock quota API.

    Usage:
        @responses.activate
        def test_something(mock_quota_api):
            mock_quota_api()
            # ... rest of test

    Returns:
        Function that adds quota API mock to responses.
    """
    import responses

    def _mock_quota_api(
        fixture: str = "quota_response.json",
        status: int = 200,
    ):
        """Add quota API mock."""
        quota_data = load_fixture(fixture)
        responses.add(
            method="GET",
            url=f"{test_config.tenant_url_str}/api/web/namespaces/system/quota/usage",
            json=quota_data,
            status=status,
        )

    return _mock_quota_api


def get_metric_value(metric, **labels):
    """Helper function to get metric value without accessing internal _value.get().

    This uses the public collect() API to avoid coupling tests to implementation details.

    Usage:
        value = get_metric_value(collector.quota_limit, tenant="test-tenant", resource="lb")

    Args:
        metric: Prometheus metric object (Gauge, Counter, etc.)
        **labels: Label key-value pairs to identify the metric series

    Returns:
        The metric value, or None if metric not found
    """
    for sample in metric.collect():
        for s in sample.samples:
            if all(s.labels.get(k) == v for k, v in labels.items()):
                return s.value
    return None
