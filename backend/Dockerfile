# Cloud Run image: slim base, no build tools at runtime, non root user.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libraqm: Hindi text shaping on the cards (Pillow loads it at runtime).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libraqm0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --system --uid 10001 --no-create-home appuser
USER 10001

# Cloud Run injects PORT (default 8080).
CMD ["sh", "-c", "exec uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
