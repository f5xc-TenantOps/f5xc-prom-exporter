"""Configuration management for F5XC Prometheus Exporter."""

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Configuration for F5XC Prometheus Exporter."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required F5XC settings
    f5xc_tenant_url: HttpUrl = Field(..., alias="F5XC_TENANT_URL")
    f5xc_access_token: str = Field(..., alias="F5XC_ACCESS_TOKEN")

    # HTTP server settings
    f5xc_exp_http_port: int = Field(default=8080, alias="F5XC_EXP_HTTP_PORT")
    f5xc_exp_log_level: str = Field(default="INFO", alias="F5XC_EXP_LOG_LEVEL")

    # Collection intervals (seconds) - set to 0 to disable a collector
    f5xc_quota_interval: int = Field(default=600, alias="F5XC_QUOTA_INTERVAL")
    f5xc_http_lb_interval: int = Field(default=120, alias="F5XC_HTTP_LB_INTERVAL")
    f5xc_tcp_lb_interval: int = Field(default=120, alias="F5XC_TCP_LB_INTERVAL")
    f5xc_udp_lb_interval: int = Field(default=120, alias="F5XC_UDP_LB_INTERVAL")
    f5xc_dns_interval: int = Field(default=120, alias="F5XC_DNS_INTERVAL")
    f5xc_security_interval: int = Field(default=120, alias="F5XC_SECURITY_INTERVAL")
    f5xc_synthetic_interval: int = Field(default=120, alias="F5XC_SYNTHETIC_INTERVAL")

    # Rate limiting
    f5xc_max_concurrent_requests: int = Field(default=5, alias="F5XC_MAX_CONCURRENT_REQUESTS")
    f5xc_request_timeout: int = Field(default=30, alias="F5XC_REQUEST_TIMEOUT")
    f5xc_retry_max_attempts: int = Field(default=3, alias="F5XC_RETRY_MAX_ATTEMPTS")

    # Circuit breaker settings
    f5xc_circuit_breaker_failure_threshold: int = Field(default=5, alias="F5XC_CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    f5xc_circuit_breaker_timeout: int = Field(default=60, alias="F5XC_CIRCUIT_BREAKER_TIMEOUT")
    f5xc_circuit_breaker_success_threshold: int = Field(default=2, alias="F5XC_CIRCUIT_BREAKER_SUCCESS_THRESHOLD")
    f5xc_circuit_breaker_endpoint_ttl_hours: int = Field(default=24, alias="F5XC_CIRCUIT_BREAKER_ENDPOINT_TTL_HOURS")
    f5xc_circuit_breaker_cleanup_interval: int = Field(default=21600, alias="F5XC_CIRCUIT_BREAKER_CLEANUP_INTERVAL")

    # Cardinality limits
    f5xc_max_namespaces: int = Field(default=100, alias="F5XC_MAX_NAMESPACES")
    f5xc_max_load_balancers_per_namespace: int = Field(default=50, alias="F5XC_MAX_LOAD_BALANCERS_PER_NAMESPACE")
    f5xc_max_dns_zones: int = Field(default=100, alias="F5XC_MAX_DNS_ZONES")
    f5xc_warn_cardinality_threshold: int = Field(default=10000, alias="F5XC_WARN_CARDINALITY_THRESHOLD")

    @property
    def tenant_url_str(self) -> str:
        """Get tenant URL as string without trailing slash."""
        return str(self.f5xc_tenant_url).rstrip("/")

    @property
    def tenant_name(self) -> str:
        """Extract tenant name from tenant URL, normalized to lowercase."""
        # Extract tenant name from URL like https://f5-sales-demo.console.ves.volterra.io
        hostname = str(self.f5xc_tenant_url).split("//")[1]
        return hostname.split(".")[0].lower()


def get_config() -> Config:
    """Get configuration instance from environment variables."""
    return Config()  # type: ignore[call-arg]
