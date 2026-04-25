# LLM-ROUTE Dockerfile
# Multi-stage build supporting headless and full targets

# ============================================
# Stage 1: Builder - Install Python dependencies
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================
# Stage 2: Headless runtime (default target)
# Minimal image for API routing only
# ============================================
FROM python:3.11-slim AS headless

WORKDIR /app

# Create non-root user and required directories
RUN useradd -m -u 1000 llmroute && \
    mkdir -p /app/logs && \
    chown -R llmroute:llmroute /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=llmroute:llmroute src/ ./src/
COPY --chown=llmroute:llmroute config.yaml .
COPY --chown=llmroute:llmroute presets/ ./presets/

# Copy entrypoint script
COPY --chown=llmroute:llmroute docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    LLM_ROUTE_HEADLESS=1

# Expose default port
EXPOSE 8087

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8087/health')" || exit 1

# Switch to non-root user
USER llmroute

# Entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["--headless"]
