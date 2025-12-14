"""Pytest configuration and fixtures."""

import os
from unittest.mock import Mock, patch

import pytest

from f5xc_exporter.client import F5XCClient
from f5xc_exporter.config import Config


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

        # Unified LB metrics methods (used by LoadBalancerCollector)
        client.list_namespaces = Mock()
        client.get_all_lb_metrics_for_namespace = Mock()
        client.get_all_lb_metrics = Mock()

        # Security collector methods (new)
        client.get_app_firewall_metrics_for_namespace = Mock()
        client.get_malicious_bot_metrics_for_namespace = Mock()
        client.get_security_event_counts_for_namespace = Mock()
        client.get_security_events_by_country_for_namespace = Mock()

        yield client


@pytest.fixture
def sample_unified_lb_response():
    """Sample unified LB metrics API response - contains HTTP, TCP, and UDP LBs with upstream/downstream."""
    return {
        "data": {
            "nodes": [
                # HTTP LB
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "app-frontend",
                        "site": "ce-site-1",
                        "virtual_host_type": "HTTP_LOAD_BALANCER"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {"type": "HTTP_REQUEST_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 150.5}]}},
                                {"type": "HTTP_ERROR_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 2.5}]}},
                                {"type": "HTTP_RESPONSE_LATENCY", "value": {"raw": [{"timestamp": 1234567890, "value": 0.025}]}},
                                {"type": "REQUEST_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 1000000}]}},
                                {"type": "CLIENT_RTT", "value": {"raw": [{"timestamp": 1234567890, "value": 0.010}]}},
                            ],
                            "upstream": [
                                {"type": "HTTP_REQUEST_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 120.0}]}},
                                {"type": "HTTP_ERROR_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 1.0}]}},
                                {"type": "HTTP_RESPONSE_LATENCY", "value": {"raw": [{"timestamp": 1234567890, "value": 0.050}]}},
                                {"type": "REQUEST_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 800000}]}},
                                {"type": "SERVER_RTT", "value": {"raw": [{"timestamp": 1234567890, "value": 0.015}]}},
                            ]
                        }
                    }
                },
                # TCP LB
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "tcp-backend",
                        "site": "ce-site-1",
                        "virtual_host_type": "TCP_LOAD_BALANCER"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {"type": "TCP_CONNECTION_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 50.0}]}},
                                {"type": "TCP_ERROR_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 1.5}]}},
                                {"type": "REQUEST_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 500000}]}},
                                {"type": "CLIENT_RTT", "value": {"raw": [{"timestamp": 1234567890, "value": 0.008}]}},
                            ],
                            "upstream": [
                                {"type": "TCP_CONNECTION_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 45.0}]}},
                                {"type": "TCP_ERROR_RATE", "value": {"raw": [{"timestamp": 1234567890, "value": 0.5}]}},
                                {"type": "REQUEST_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 450000}]}},
                                {"type": "SERVER_RTT", "value": {"raw": [{"timestamp": 1234567890, "value": 0.012}]}},
                            ]
                        }
                    }
                },
                # UDP LB
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "udp-dns-lb",
                        "site": "ce-site-1",
                        "virtual_host_type": "UDP_LOAD_BALANCER"
                    },
                    "data": {
                        "metric": {
                            "downstream": [
                                {"type": "REQUEST_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 100000}]}},
                                {"type": "RESPONSE_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 200000}]}},
                                {"type": "CLIENT_RTT", "value": {"raw": [{"timestamp": 1234567890, "value": 0.005}]}},
                            ],
                            "upstream": [
                                {"type": "REQUEST_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 95000}]}},
                                {"type": "RESPONSE_THROUGHPUT", "value": {"raw": [{"timestamp": 1234567890, "value": 190000}]}},
                                {"type": "SERVER_RTT", "value": {"raw": [{"timestamp": 1234567890, "value": 0.008}]}},
                            ]
                        }
                    }
                }
            ],
            "edges": []
        }
    }


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
def sample_app_firewall_metrics_response():
    """Sample app firewall metrics response from /api/data/namespaces/{ns}/app_firewall/metrics."""
    return {
        "data": [
            {
                "type": "TOTAL_REQUESTS",
                "data": [
                    {
                        "key": {"VIRTUAL_HOST": "ves-io-http-loadbalancer-demo-shop-fe"},
                        "value": [{"timestamp": 1765738201, "value": "13442"}]
                    }
                ],
                "unit": "UNIT_COUNT"
            },
            {
                "type": "ATTACKED_REQUESTS",
                "data": [
                    {
                        "key": {"VIRTUAL_HOST": "ves-io-http-loadbalancer-demo-shop-fe"},
                        "value": [{"timestamp": 1765738201, "value": "25"}]
                    }
                ],
                "unit": "UNIT_COUNT"
            },
            {
                "type": "BOT_DETECTION",
                "data": [
                    {
                        "key": {"VIRTUAL_HOST": "ves-io-http-loadbalancer-demo-shop-fe"},
                        "value": [{"timestamp": 1765738201, "value": "18"}]
                    }
                ],
                "unit": "UNIT_COUNT"
            }
        ],
        "step": "5m"
    }


@pytest.fixture
def sample_malicious_bot_metrics_response():
    """Sample malicious bot metrics response (filtered by BOT_CLASSIFICATION=malicious)."""
    return {
        "data": [
            {
                "type": "BOT_DETECTION",
                "data": [
                    {
                        "key": {"VIRTUAL_HOST": "ves-io-http-loadbalancer-demo-shop-fe"},
                        "value": [{"timestamp": 1765738201, "value": "5"}]
                    }
                ],
                "unit": "UNIT_COUNT"
            }
        ],
        "step": "5m"
    }


@pytest.fixture
def sample_security_events_aggregation_response():
    """Sample security events aggregation response from app_security/events/aggregation.

    Uses single-level aggregation by SEC_EVENT_TYPE because nested sub_aggs
    (VH_NAME -> SEC_EVENT_TYPE) don't work in the F5 XC API.
    """
    return {
        "total_hits": "42",
        "aggs": {
            "by_event_type": {
                "field_aggregation": {
                    "buckets": [
                        {"key": "waf_sec_event", "count": "20"},
                        {"key": "bot_defense_sec_event", "count": "15"},
                        {"key": "api_sec_event", "count": "5"},
                        {"key": "svc_policy_sec_event", "count": "2"}
                    ]
                }
            }
        }
    }


@pytest.fixture
def sample_malicious_user_events_response():
    """Sample malicious user events aggregation response.

    Uses single-level aggregation by SEC_EVENT_TYPE at namespace level.
    """
    return {
        "total_hits": "3",
        "aggs": {
            "by_event_type": {
                "field_aggregation": {
                    "buckets": [
                        {"key": "malicious_user_sec_event", "count": "3"}
                    ]
                }
            }
        }
    }


@pytest.fixture
def sample_dos_events_response():
    """Sample DoS events aggregation response.

    Uses single-level aggregation by SEC_EVENT_TYPE at namespace level.
    May include both ddos_sec_event and dos_sec_event types.
    """
    return {
        "total_hits": "7",
        "aggs": {
            "by_event_type": {
                "field_aggregation": {
                    "buckets": [
                        {"key": "ddos_sec_event", "count": "4"},
                        {"key": "dos_sec_event", "count": "3"}
                    ]
                }
            }
        }
    }


@pytest.fixture
def sample_country_attack_sources_response():
    """Sample country and attack sources aggregation response."""
    return {
        "total_hits": "1517",
        "aggs": {
            "by_country": {
                "field_aggregation": {
                    "buckets": [
                        {"key": "DE", "count": "1200"},
                        {"key": "US", "count": "250"},
                        {"key": "CN", "count": "67"}
                    ]
                }
            },
            "top_attack_sources": {
                "multi_field_aggregation": {
                    "buckets": [
                        {
                            "keys": {"country": "DE", "src_ip": "188.68.49.235"},
                            "count": "1000"
                        },
                        {
                            "keys": {"country": "US", "src_ip": "45.33.32.156"},
                            "count": "200"
                        },
                        {
                            "keys": {"country": "DE", "src_ip": "95.217.163.246"},
                            "count": "150"
                        }
                    ]
                }
            }
        }
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
    """Sample HTTP LB metrics API response - matches per-namespace service graph structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "app-frontend",
                        "site": "ce-site-1",
                        "virtual_host_type": "HTTP_LOAD_BALANCER"
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
                        "site": "ce-site-2",
                        "virtual_host_type": "HTTP_LOAD_BALANCER"
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
    """Sample TCP LB metrics API response - matches per-namespace service graph structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "tcp-backend",
                        "site": "ce-site-1",
                        "virtual_host_type": "TCP_LOAD_BALANCER"
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
    """Sample UDP LB metrics API response - matches per-namespace service graph structure."""
    return {
        "data": {
            "nodes": [
                {
                    "id": {
                        "namespace": "prod",
                        "vhost": "udp-dns-lb",
                        "site": "ce-site-1",
                        "virtual_host_type": "UDP_LOAD_BALANCER"
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
