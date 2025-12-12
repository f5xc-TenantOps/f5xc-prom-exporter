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

    def get_waf_metrics(self, namespace: str = "system") -> Dict[str, Any]:
        """Get WAF metrics for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/waf/metrics"
        return self.get(endpoint)

    def get_bot_defense_metrics(self, namespace: str = "system") -> Dict[str, Any]:
        """Get bot defense metrics for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/bot_defense/metrics"
        return self.get(endpoint)

    def get_api_security_metrics(self, namespace: str = "system") -> Dict[str, Any]:
        """Get API security metrics for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/api_security/metrics"
        return self.get(endpoint)

    def get_ddos_metrics(self, namespace: str = "system") -> Dict[str, Any]:
        """Get DDoS metrics for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/ddos/metrics"
        return self.get(endpoint)

    def get_security_events(self, namespace: str = "system") -> Dict[str, Any]:
        """Get security events for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/security/events"

        # Security events API typically requires time range
        params = {
            "start_time": int(time.time() - 3600),  # Last hour
            "end_time": int(time.time())
        }

        return self.get(endpoint, params=params)

    def get_synthetic_monitoring_metrics(self, namespace: str = "system") -> Dict[str, Any]:
        """Get synthetic monitoring metrics for namespace."""
        endpoint = f"/api/web/namespaces/{namespace}/synthetic_monitoring/metrics"
        return self.get(endpoint)

    def close(self) -> None:
        """Close the session."""
        self.session.close()