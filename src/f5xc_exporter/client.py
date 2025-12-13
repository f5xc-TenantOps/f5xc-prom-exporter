"""F5 Distributed Cloud API client."""

import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
import structlog
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config

logger = structlog.get_logger()


class F5XCAPIError(Exception):
    """Base exception for F5XC API errors."""
    pass


class F5XCAuthenticationError(F5XCAPIError):
    """Authentication error."""
    pass


class F5XCRateLimitError(F5XCAPIError):
    """Rate limit error."""
    pass


class F5XCClient:
    """F5 Distributed Cloud API client."""

    def __init__(self, config: Config):
        """Initialize F5XC API client."""
        self.config = config
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=config.f5xc_retry_max_attempts,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set headers
        self.session.headers.update({
            "Authorization": f"APIToken {config.f5xc_access_token}",
            "Content-Type": "application/json",
            "User-Agent": "f5xc-prom-exporter/0.1.0",
        })

        # Set timeout
        self.session.timeout = config.f5xc_request_timeout

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Make HTTP request to F5XC API."""
        url = urljoin(self.config.tenant_url_str, endpoint)

        logger.info(
            "Making F5XC API request",
            method=method,
            url=url,
            endpoint=endpoint,
        )

        try:
            response = self.session.request(method, url, **kwargs)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(
                    "Rate limited by F5XC API",
                    retry_after=retry_after,
                    endpoint=endpoint,
                )
                raise F5XCRateLimitError(f"Rate limited. Retry after {retry_after} seconds")

            # Handle authentication errors
            if response.status_code == 401:
                logger.error("Authentication failed", endpoint=endpoint)
                raise F5XCAuthenticationError("Invalid F5XC access token")

            # Handle other HTTP errors
            response.raise_for_status()

            # Parse JSON response
            data = response.json()

            logger.info(
                "F5XC API request successful",
                endpoint=endpoint,
                status_code=response.status_code,
                response_size=len(response.content),
            )

            return data

        except requests.exceptions.RequestException as e:
            logger.error(
                "F5XC API request failed",
                endpoint=endpoint,
                error=str(e),
                exc_info=True,
            )
            raise F5XCAPIError(f"API request failed: {e}") from e

    def get(self, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
        """Make GET request."""
        return self._make_request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
        """Make POST request."""
        return self._make_request("POST", endpoint, **kwargs)

    def get_quota_usage(self, namespace: str = "system") -> Dict[str, Any]:
        """Get quota usage for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/quota/usage"
        return self.get(endpoint)

    def get_service_graph_data(self, namespace: str = "system") -> Dict[str, Any]:
        """Get service graph data for namespace."""
        endpoint = f"/api/data/namespaces/{namespace}/graph/service"

        # Service graph API requires POST with query parameters
        payload = {
            "agg_type": "avg",
            "namespace": namespace,
            "tenant": self.config.tenant_name,
            "metrics": ["overallHealth"],
            "step": "1m",
            "time": {
                "end": int(time.time()),
                "start": int(time.time() - 3600)  # Last hour
            }
        }

        return self.post(endpoint, json=payload)

    def get_app_firewall_metrics(self, namespace: str = "system") -> Dict[str, Any]:
        """Get app firewall (WAF) metrics for namespace.

        Uses the correct F5XC API endpoint: /api/data/namespaces/{namespace}/app_firewall/metrics
        """
        endpoint = f"/api/data/namespaces/{namespace}/app_firewall/metrics"

        # App firewall metrics requires POST with query parameters
        payload = {
            "namespace": namespace,
            "agg_type": "sum",
            "group_by": ["vhost_name", "attack_type"],
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time())
        }

        return self.post(endpoint, json=payload)

    def get_firewall_logs(self, namespace: str = "system") -> Dict[str, Any]:
        """Get firewall logs (security events) for namespace.

        Uses the correct F5XC API endpoint: /api/data/namespaces/{namespace}/firewall_logs
        """
        endpoint = f"/api/data/namespaces/{namespace}/firewall_logs"

        # Firewall logs requires POST with query parameters
        payload = {
            "namespace": namespace,
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time()),
            "agg": {
                "type": "cardinality",
                "field": "req_id"
            }
        }

        return self.post(endpoint, json=payload)

    def get_access_logs_aggregation(self, namespace: str = "system") -> Dict[str, Any]:
        """Get aggregated access logs for namespace.

        Uses the correct F5XC API endpoint: /api/data/namespaces/{namespace}/access_logs/aggregation
        """
        endpoint = f"/api/data/namespaces/{namespace}/access_logs/aggregation"

        # Access logs aggregation requires POST with query parameters
        payload = {
            "namespace": namespace,
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time()),
            "aggs": {
                "response_codes": {
                    "field": "rsp_code_class",
                    "topk": 10
                }
            }
        }

        return self.post(endpoint, json=payload)

    def get_synthetic_monitoring_health(self, namespace: str = "system") -> Dict[str, Any]:
        """Get synthetic monitoring health status for namespace.

        Uses the correct F5XC API endpoint: /api/observability/synthetic_monitor/namespaces/{namespace}/health
        """
        endpoint = f"/api/observability/synthetic_monitor/namespaces/{namespace}/health"

        # Synthetic monitoring health requires POST
        payload = {
            "namespace": namespace
        }

        return self.post(endpoint, json=payload)

    def get_synthetic_monitoring_summary(self, namespace: str = "system") -> Dict[str, Any]:
        """Get synthetic monitoring global summary for namespace.

        Uses the correct F5XC API endpoint: /api/observability/synthetic_monitor/namespaces/{namespace}/global-summary
        """
        endpoint = f"/api/observability/synthetic_monitor/namespaces/{namespace}/global-summary"

        # Global summary requires POST with time range
        payload = {
            "namespace": namespace,
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time())
        }

        return self.post(endpoint, json=payload)

    def get_http_monitors_health(self, namespace: str = "system") -> Dict[str, Any]:
        """Get HTTP monitors health for namespace.

        Uses the correct F5XC API endpoint: /api/observability/synthetic_monitor/namespaces/{namespace}/http-monitors-health
        """
        endpoint = f"/api/observability/synthetic_monitor/namespaces/{namespace}/http-monitors-health"

        # HTTP monitors health requires POST
        payload = {
            "namespace": namespace
        }

        return self.post(endpoint, json=payload)

    def close(self) -> None:
        """Close the session."""
        self.session.close()