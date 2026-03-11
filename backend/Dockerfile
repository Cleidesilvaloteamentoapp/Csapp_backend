# Stage 1: Build
FROM python:3.11-slim AS builder

WORKDIR /build

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Production
FROM python:3.11-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY backend/ .
COPY backend/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
