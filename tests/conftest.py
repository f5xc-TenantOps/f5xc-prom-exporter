"""Pytest configuration and fixtures."""

import os
import pytest
from unittest.mock import Mock, patch

from f5xc_exporter.config import Config
from f5xc_exporter.client import F5XCClient


@pytest.fixture
def test_config():
    """Test configuration fixture."""
    os.environ["F5XC_TENANT_URL"] = "https://test.console.ves.volterra.io"
    os.environ["F5XC_ACCESS_TOKEN"] = "test-token-123"
    os.environ["F5XC_EXP_HTTP_PORT"] = "8080"
    os.environ["F5XC_EXP_LOG_LEVEL"] = "DEBUG"
    os.environ["F5XC_QUOTA_INTERVAL"] = "60"
    os.environ["F5XC_HTTP_LB_INTERVAL"] = "30"
    os.environ["F5XC_TCP_LB_INTERVAL"] = "30"
    os.environ["F5XC_UDP_LB_INTERVAL"] = "30"
    os.environ["F5XC_SECURITY_INTERVAL"] = "60"
    os.environ["F5XC_SYNTHETIC_INTERVAL"] = "60"

    return Config()


@pytest.fixture
def mock_client(test_config):
    """Mock F5XC client fixture."""
    with patch('f5xc_exporter.client.requests.Session') as mock_session:
        client = F5XCClient(test_config)
        client.session = Mock()
        yield client


@pytest.fixture
def sample_quota_response():
    """Sample quota API response."""
    return {
        "quota_usage": {
            "load_balancer": {
                "limit": {"maximum": 10},
                "usage": {"current": 5}
            },
            "origin_pool": {
                "limit": {"maximum": 20},
                "usage": {"current": 12}
            }
        },
        "resources": {
            "virtual_host": {
                "limit": {"maximum": 50},
                "usage": {"current": 25}
            }
        }
    }


@pytest.fixture
def sample_service_graph_response():
    """Sample service graph API response."""
    return {
        "nodes": [
            {
                "type": "load_balancer",
                "name": "test-lb",
                "stats": {
                    "http": {
                        "response_classes": {"2xx": 1000, "4xx": 50, "5xx": 10},
                        "request_duration_percentiles": {"p50": 100, "p95": 250, "p99": 500},
                        "active_connections": 25
                    }
                }
            },
            {
                "type": "origin_pool",
                "name": "test-pool",
                "stats": {
                    "http": {
                        "response_classes": {"2xx": 980, "5xx": 15},
                        "active_connections": 20
                    }
                }
            }
        ],
        "edges": []
    }


@pytest.fixture
def sample_security_response():
    """Sample security API response."""
    return {
        "requests": [
            {"app": "test-app", "action": "block", "rule_type": "owasp", "count": 25},
            {"app": "test-app", "action": "allow", "rule_type": "custom", "count": 1000}
        ],
        "blocked_requests": [
            {"app": "test-app", "attack_type": "sql_injection", "count": 15}
        ],
        "rule_hits": [
            {"app": "test-app", "rule_id": "rule-001", "rule_type": "owasp", "count": 30}
        ]
    }


@pytest.fixture
def sample_synthetic_response():
    """Sample synthetic monitoring API response."""
    return {
        "http_monitors": [
            {
                "name": "test-monitor",
                "target_url": "https://example.com",
                "results": [
                    {
                        "location": "us-east-1",
                        "success": True,
                        "response_time": 150,
                        "status_code": 200,
                        "connect_time": 50,
                        "ttfb": 100
                    }
                ]
            }
        ],
        "dns_monitors": [
            {
                "name": "dns-test",
                "target_domain": "example.com",
                "results": [
                    {
                        "location": "us-west-2",
                        "success": True,
                        "response_time": 25,
                        "records": [{"type": "A"}, {"type": "A"}]
                    }
                ]
            }
        ]
    }


@pytest.fixture(autouse=True)
def clean_env():
    """Clean environment variables before each test."""
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
    ]

    for var in env_vars:
        if var in os.environ:
            del os.environ[var]

    yield

    # Clean up after test
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]