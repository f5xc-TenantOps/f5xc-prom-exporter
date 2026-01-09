"""Main entry point for F5XC Prometheus exporter."""

import logging
import signal
import sys
from typing import Any

import structlog

from .config import get_config
from .metrics_server import MetricsServer


def setup_logging(log_level: str) -> None:
    """Set up structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Set log level
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def main() -> None:
    """Main entry point."""
    # Load configuration
    try:
        config = get_config()
    except Exception:
        sys.exit(1)

    # Setup logging
    setup_logging(config.f5xc_exp_log_level)
    logger = structlog.get_logger()

    logger.info(
        "Starting F5XC Prometheus Exporter",
        version="0.1.0",
        tenant_url=config.tenant_url_str,
        port=config.f5xc_exp_http_port,
    )

    # Create and start metrics server
    server = MetricsServer(config)

    # Handle shutdown signals
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received shutdown signal", signal=signum)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
        server.stop()
        sys.exit(0)
    except Exception as e:
        logger.error("Failed to start metrics server", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
