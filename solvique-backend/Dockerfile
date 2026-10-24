# ==============================================================================
# Solvique Backend — Production Containerfile for Cloud Run
# ==============================================================================

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    SOLVIQUE_DATA_DIR="/app/data" \
    LOG_FILE_PATH="/app/logs/app.log"

WORKDIR /app

# Install minimal OS dependencies for compilation and file handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first to leverage Docker layer caching
COPY pyproject.toml README.md ./

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Copy application source code
COPY api.py config.py graph.py main.py ./
COPY src/ ./src/

# Copy only public Olist domain reference assets and schema DDLs
COPY data/schema.sql data/seed_data.sql ./data/
COPY data/sql_rag_sources/ ./data/sql_rag_sources/

# Create runtime directories for conversation SQLite and report assets
RUN mkdir -p /app/data/report_assets /app/logs && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# Run FastAPI backend via Uvicorn
CMD exec uvicorn api:app --host 0.0.0.0 --port ${PORT}
