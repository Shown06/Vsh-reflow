FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY alembic/ ./alembic/ 2>/dev/null || true
COPY alembic.ini . 2>/dev/null || true

# Default command (overridden per service in docker-compose)
CMD ["python", "-m", "src"]
