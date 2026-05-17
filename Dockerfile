# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local

RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy only the application package (explicit path, no trailing slash ambiguity)
COPY app /app/app

RUN mkdir -p chroma_db logs data/raw data/processed && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Shell form so Railway's $PORT variable expands correctly
CMD sh -c "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"
