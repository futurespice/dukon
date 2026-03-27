# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps:
#   libpq-dev      — psycopg2
#   libjpeg-dev    — Pillow JPEG support
#   libwebp-dev    — Pillow WebP support
#   zlib1g-dev     — Pillow PNG / zlib support
#   wget           — used by docker-compose healthcheck (wget -qO- /health/)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libjpeg-dev \
    libwebp-dev \
    zlib1g-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer — only rebuilds when requirements.txt changes)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy project source (after deps so the layer is not invalidated on every code change)
COPY . .

# Collect static files at build time so the image is self-contained.
# Uses a dummy SECRET_KEY — collectstatic does not connect to the DB.
# DEVOPS: removed the trailing '|| true' that was silently hiding errors
# (e.g. a missing template tag or broken STATICFILES_DIRS).
# If collectstatic fails the image build fails, which is the correct behaviour.
# collectstatic не обращается к БД, но base.py требует DB_USER/DB_PASSWORD
# без дефолтов (security fix). Передаём dummy-значения только на этапе сборки.
RUN SECRET_KEY=build-only \
    DB_USER=build-only \
    DB_PASSWORD=build-only \
    DB_HOST=build-only \
    REDIS_URL=redis://localhost:6379/0 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    python manage.py collectstatic --noinput

# Run as a non-root user — reduces blast radius if the app is compromised.
RUN addgroup --system dukon && adduser --system --ingroup dukon dukon
RUN chown -R dukon:dukon /app
USER dukon

EXPOSE 8000

# Workers are configured via GUNICORN_WORKERS env var (default 4).
# See docker-compose.production.yml where the value is injected at runtime.
CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
