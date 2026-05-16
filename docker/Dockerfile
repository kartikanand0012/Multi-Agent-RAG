# ── Stage 1: builder ─────────────────────────────────────────────────────────
# All COPY from build context happens here — Railway only passes context to stage 1
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY app ./app

RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
# Nothing copied from build context here — only from builder stage
FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/app ./app

RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    mkdir -p chroma_db logs data/raw data/processed && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD sh -c "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"
