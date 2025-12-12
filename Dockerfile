# Multi-stage build for F5XC Prometheus Exporter
FROM python:3.9-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml ./

# Install dependencies to a local directory
RUN pip install --user .

# Production stage
FROM python:3.9-slim

# Create non-root user
RUN groupadd -r f5xc && useradd -r -g f5xc f5xc

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/f5xc/.local

# Copy source code
COPY src/ ./src/

# Set environment variables
ENV PATH=/home/f5xc/.local/bin:$PATH
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Set default configuration
ENV F5XC_EXP_HTTP_PORT=8080
ENV F5XC_EXP_LOG_LEVEL=INFO
ENV F5XC_QUOTA_INTERVAL=600
ENV F5XC_HTTP_LB_INTERVAL=120
ENV F5XC_TCP_LB_INTERVAL=120
ENV F5XC_UDP_LB_INTERVAL=120
ENV F5XC_SECURITY_INTERVAL=180
ENV F5XC_SYNTHETIC_INTERVAL=120

# Change ownership and switch to non-root user
RUN chown -R f5xc:f5xc /app /home/f5xc
USER f5xc

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)"

# Run the application
CMD ["python", "-m", "f5xc_exporter.main"]