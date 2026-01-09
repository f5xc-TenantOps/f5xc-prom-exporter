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
