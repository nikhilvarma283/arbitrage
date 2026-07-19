FROM python:3.11-slim

WORKDIR /app

# Install system dependencies. git is required for requirements.txt's
# tinyman-py-sdk, which has no PyPI release and is only pip-installable
# via its GitHub source (git+https://...).
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for logs and database
RUN mkdir -p /data/logs && chmod -R 777 /data

# Set environment
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Expose query API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/status || exit 1

# Run bot v3 (multi-DEX with query API)
CMD ["python", "-m", "src.main_v3", "--config", "config/bot.multi-dex.yaml"]
