"""Tests for configuration management."""

import os

import pytest
from pydantic import ValidationError

from f5xc_exporter.config import Config, get_config


class TestConfig:
    """Test configuration management."""

    def test_config_with_valid_values(self):
        """Test configuration with valid values."""
        os.environ["F5XC_TENANT_URL"] = "https://test.console.ves.volterra.io"
        os.environ["F5XC_ACCESS_TOKEN"] = "test-token-123"

        config = Config()

        assert str(config.f5xc_tenant_url) == "https://test.console.ves.volterra.io/"
        assert config.f5xc_access_token == "test-token-123"
        assert config.f5xc_exp_http_port == 8080  # default
        assert config.f5xc_quota_interval == 600  # default

    def test_config_missing_required_fields(self):
        """Test configuration fails with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            Config()

        errors = exc_info.value.errors()
        assert len(errors) == 2  # tenant_url and access_token are required

        error_fields = [error["loc"][0] for error in errors]
        assert "F5XC_TENANT_URL" in error_fields
        assert "F5XC_ACCESS_TOKEN" in error_fields

    def test_config_invalid_url(self):
        """Test configuration fails with invalid URL."""
        os.environ["F5XC_TENANT_URL"] = "not-a-url"
        os.environ["F5XC_ACCESS_TOKEN"] = "test-token"

        with pytest.raises(ValidationError):
            Config()

    def test_config_from_environment(self):
        """Test configuration loaded from environment variables."""
        os.environ["F5XC_TENANT_URL"] = "https://env.console.ves.volterra.io"
        os.environ["F5XC_ACCESS_TOKEN"] = "env-token-456"
        os.environ["F5XC_EXP_HTTP_PORT"] = "9090"
        os.environ["F5XC_QUOTA_INTERVAL"] = "300"

        config = get_config()

        assert str(config.f5xc_tenant_url) == "https://env.console.ves.volterra.io/"
        assert config.f5xc_access_token == "env-token-456"
        assert config.f5xc_exp_http_port == 9090
        assert config.f5xc_quota_interval == 300

    def test_tenant_url_str_property(self):
        """Test tenant URL string property removes trailing slash."""
        os.environ["F5XC_TENANT_URL"] = "https://test.console.ves.volterra.io/"
        os.environ["F5XC_ACCESS_TOKEN"] = "test-token"

        config = Config()

        assert config.tenant_url_str == "https://test.console.ves.volterra.io"

    def test_tenant_name_property(self):
        """Test tenant name extraction from URL."""
        os.environ["F5XC_TENANT_URL"] = "https://my-tenant.console.ves.volterra.io"
        os.environ["F5XC_ACCESS_TOKEN"] = "test-token"

        config = Config()

        assert config.tenant_name == "my-tenant"

    def test_all_interval_defaults(self):
        """Test all collection interval defaults."""
        os.environ["F5XC_TENANT_URL"] = "https://test.console.ves.volterra.io"
        os.environ["F5XC_ACCESS_TOKEN"] = "test-token"

        config = Config()

        assert config.f5xc_quota_interval == 600
        assert config.f5xc_http_lb_interval == 120
        assert config.f5xc_tcp_lb_interval == 120
        assert config.f5xc_udp_lb_interval == 120
        assert config.f5xc_security_interval == 180
        assert config.f5xc_synthetic_interval == 120

    def test_rate_limiting_defaults(self):
        """Test rate limiting configuration defaults."""
        os.environ["F5XC_TENANT_URL"] = "https://test.console.ves.volterra.io"
        os.environ["F5XC_ACCESS_TOKEN"] = "test-token"

        config = Config()

        assert config.f5xc_max_concurrent_requests == 5
        assert config.f5xc_request_timeout == 30
        assert config.f5xc_retry_max_attempts == 3
