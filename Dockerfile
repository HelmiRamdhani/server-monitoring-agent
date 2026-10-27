# ==============================================================================
# Server Monitoring Agent - Dockerfile
# Production-ready, secure, non-root container image for Platform Bigdata
# ==============================================================================

FROM python:3.11-slim as base

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    AGENT_ENV=production

# Install essential system tools for health checks and network diagnostics
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    iputils-ping \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir kubernetes>=26.0.0

# Create non-root user for security (Kubernetes Pod Security Standard compliant)
RUN useradd -u 10001 -m appuser \
    && mkdir -p /app/output /app/kb /app/config \
    && chown -R appuser:appuser /app

# Copy application source code
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser kb/ /app/kb/
COPY --chown=appuser:appuser config/config.example.yaml /app/config/config.yaml

USER appuser

# Expose Webhook Receiver Port
EXPOSE 8080

# Kubernetes Liveness/Readiness Probe target
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default execution: Hybrid mode (Webhook Server + Scheduled Polling)
CMD ["python", "src/main.py", "--config", "config/config.yaml", "--webhook", "--loop"]

