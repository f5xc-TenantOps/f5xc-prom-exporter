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
    with patch('f5xc_exporter.client.requests.Session'):
        client = F5XCClient(test_config)

        # Mock all client methods (both old and new names for compatibility)
        client.get_quota_usage = Mock()
        client.get_service_graph_data = Mock()

        # New correct API method names
        client.get_app_firewall_metrics = Mock()
        client.get_firewall_logs = Mock()
        client.get_access_logs_aggregation = Mock()
        client.get_synthetic_monitoring_health = Mock()
        client.get_synthetic_monitoring_summary = Mock()
        client.get_http_monitors_health = Mock()
        client.get_http_lb_metrics = Mock()
        client.get_tcp_lb_metrics = Mock()
        client.get_udp_lb_metrics = Mock()

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
    """Sample service graph API response - matches actual F5XC API structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "system",
                        "service": "test-service",
                        "vhost": "test-lb",
                        "site": "ce01"
                    },
                    "data": {
                        "healthscore": {},
                        "metric": {
                            "downstream": [
                                {
                                    "type": "HTTP_REQUEST_RATE",
                                    "unit": "per second",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 100.5}]
                                    }
                                },
                                {
                                    "type": "HTTP_RESPONSE_LATENCY",
                                    "unit": "seconds",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.15}]
                                    }
                                }
                            ],
                            "upstream": [
                                {
                                    "type": "HTTP_REQUEST_RATE",
                                    "unit": "per second",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 95.0}]
                                    }
                                }
                            ]
                        }
                    }
                }
            ],
            "edges": []
        },
        "step": "1m"
    }


@pytest.fixture
def sample_security_response():
    """Sample security API response - matches F5XC app_firewall/metrics structure."""
    return {
        "metrics": [
            {"vhost_name": "test-app", "attack_type": "sql_injection", "count": 15},
            {"vhost_name": "test-app", "attack_type": "xss", "count": 10}
        ]
    }


@pytest.fixture
def sample_firewall_logs_response():
    """Sample firewall logs API response."""
    return {
        "total": 25,
        "events": [
            {"vhost": "test-app", "type": "block", "severity": "high"},
            {"vhost": "test-app", "type": "alert", "severity": "medium"}
        ]
    }


@pytest.fixture
def sample_synthetic_response():
    """Sample synthetic monitoring API response - matches F5XC health endpoint structure."""
    return {
        "monitors": [
            {
                "name": "test-monitor",
                "type": "http",
                "target": "https://example.com",
                "status": "healthy",
                "response_time": 150
            }
        ]
    }


@pytest.fixture
def sample_synthetic_summary_response():
    """Sample synthetic monitoring summary response."""
    return {
        "total_monitors": 10,
        "healthy_monitors": 8,
        "unhealthy_monitors": 2,
        "monitors": [
            {"name": "test-monitor", "uptime": 99.5}
        ]
    }


@pytest.fixture
def sample_http_lb_response():
    """Sample HTTP LB metrics API response - matches QueryAllNamespaces structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "app-frontend",
                        "site": "ce-site-1"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {
                                    "type": "HTTP_REQUEST_RATE",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 150.5}]
                                    }
                                },
                                {
                                    "type": "HTTP_ERROR_RATE",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 2.5}]
                                    }
                                },
                                {
                                    "type": "HTTP_ERROR_RATE_4XX",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 1.5}]
                                    }
                                },
                                {
                                    "type": "HTTP_ERROR_RATE_5XX",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 1.0}]
                                    }
                                },
                                {
                                    "type": "HTTP_RESPONSE_LATENCY",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.025}]
                                    }
                                },
                                {
                                    "type": "HTTP_RESPONSE_LATENCY_PERCENTILE_50",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.020}]
                                    }
                                },
                                {
                                    "type": "HTTP_RESPONSE_LATENCY_PERCENTILE_90",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.050}]
                                    }
                                },
                                {
                                    "type": "HTTP_RESPONSE_LATENCY_PERCENTILE_99",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.100}]
                                    }
                                },
                                {
                                    "type": "HTTP_APP_LATENCY",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.015}]
                                    }
                                },
                                {
                                    "type": "REQUEST_THROUGHPUT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 1000000}]
                                    }
                                },
                                {
                                    "type": "RESPONSE_THROUGHPUT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 5000000}]
                                    }
                                },
                                {
                                    "type": "CLIENT_RTT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.010}]
                                    }
                                },
                                {
                                    "type": "SERVER_RTT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.005}]
                                    }
                                }
                            ]
                        }
                    }
                },
                {
                    "id": {
                        "namespace": "staging",
                        "vhost": "api-gateway",
                        "site": "ce-site-2"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {
                                    "type": "HTTP_REQUEST_RATE",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 50.0}]
                                    }
                                },
                                {
                                    "type": "HTTP_RESPONSE_LATENCY",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.030}]
                                    }
                                }
                            ]
                        }
                    }
                }
            ],
            "edges": []
        }
    }


@pytest.fixture
def sample_tcp_lb_response():
    """Sample TCP LB metrics API response - matches QueryAllNamespaces structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "tcp-backend",
                        "site": "ce-site-1"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {
                                    "type": "TCP_CONNECTION_RATE",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 50.0}]
                                    }
                                },
                                {
                                    "type": "TCP_ERROR_RATE",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 1.5}]
                                    }
                                },
                                {
                                    "type": "TCP_ERROR_RATE_CLIENT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.5}]
                                    }
                                },
                                {
                                    "type": "TCP_ERROR_RATE_UPSTREAM",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 1.0}]
                                    }
                                },
                                {
                                    "type": "TCP_CONNECTION_DURATION",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 30.5}]
                                    }
                                },
                                {
                                    "type": "REQUEST_THROUGHPUT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 500000}]
                                    }
                                },
                                {
                                    "type": "RESPONSE_THROUGHPUT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 2000000}]
                                    }
                                },
                                {
                                    "type": "CLIENT_RTT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.008}]
                                    }
                                },
                                {
                                    "type": "SERVER_RTT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.003}]
                                    }
                                }
                            ]
                        }
                    }
                }
            ],
            "edges": []
        }
    }


@pytest.fixture
def sample_udp_lb_response():
    """Sample UDP LB metrics API response - matches QueryAllNamespaces structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "udp-dns-lb",
                        "site": "ce-site-1"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {
                                    "type": "REQUEST_THROUGHPUT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 100000}]
                                    }
                                },
                                {
                                    "type": "RESPONSE_THROUGHPUT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 200000}]
                                    }
                                },
                                {
                                    "type": "CLIENT_RTT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.005}]
                                    }
                                },
                                {
                                    "type": "SERVER_RTT",
                                    "value": {
                                        "raw": [{"timestamp": 1234567890, "value": 0.002}]
                                    }
                                }
                            ]
                        }
                    }
                }
            ],
            "edges": []
        }
    }


@pytest.fixture(autouse=True)
def clean_env():
    """Clean environment variables and prometheus registry before each test."""
    # Clean environment variables
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

    # Clean up Prometheus registry to avoid conflicts
    from prometheus_client import REGISTRY
    try:
        # Clear all collectors from the default registry
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

    # Clean registry again after test
    try:
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            try:
                REGISTRY.unregister(collector)
            except KeyError:
                pass
    except Exception:
        pass