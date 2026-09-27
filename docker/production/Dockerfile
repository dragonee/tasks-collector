# Stage 1: Build frontend assets
FROM node:24-alpine AS frontend-builder

WORKDIR /app

# Copy package files first for better caching
COPY package.json package-lock.json ./
RUN npm ci

COPY rsbuild.config.ts ./
COPY tasks/assets/ ./tasks/assets/

# Build production assets (outputs to tasks/static/dist/)
RUN npm run build-dist


# Stage 2: Production Python image
FROM python:3.14-slim-bookworm AS production

# tasks/celery.py defaults to the local settings, so the worker container
# needs the production module set explicitly (wsgi.py already defaults to it).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=tasks.settings.dist

# Create non-root user
RUN groupadd --gid 9422 app && \
    useradd --uid 9422 --gid app --shell /bin/bash --create-home app

WORKDIR /app

COPY requirements/base.txt requirements/dist.txt ./requirements/
RUN pip install -r requirements/dist.txt

COPY tasks/ ./tasks/
COPY manage.dist.py ./
COPY docker/production/gunicorn.conf.py ./

COPY --from=frontend-builder /app/tasks/static/dist/ ./tasks/static/dist/

# The code stays root-owned (read-only for the app user), so make it readable
# regardless of the modes in the build context's checkout.
#
# Collect static files into the rsbuild output and gzip everything there, so
# WhiteNoise can serve compressed variants of the bundles as well. Dummy env
# vars are only for collectstatic - real values are provided at runtime.
RUN chmod -R a+rX /app && \
    SECRET_KEY=build-time-secret \
    DATABASE_URL=sqlite:////tmp/build.db \
    python manage.dist.py collectstatic --noinput && \
    python -m whitenoise.compress --quiet tasks/static/dist

ARG GIT_REVISION=unknown
RUN echo "${GIT_REVISION}" > tasks/REVISION

USER app

EXPOSE 9422

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9422/health/')" || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "tasks.wsgi:application"]
