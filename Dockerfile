# syntax=docker/dockerfile:1

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
# Not editable: the runtime image gets the virtual environment only, no source tree.
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
# WeasyPrint lays out the PDF report with Pango; DejaVu stands in for the page's
# system-ui and monospace fonts. Pinned to the upstream release, not the Debian
# revision: security updates still apply, a new release fails the build.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        'libpango-1.0-0=1.56.3-*' 'libpangoft2-1.0-0=1.56.3-*' \
        'libharfbuzz-subset0=10.2.0-*' 'fonts-dejavu-core=2.37-*' \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --no-create-home aaspect
COPY --from=build /app/.venv /app/.venv
# All interfaces inside the container only; who can reach it is decided by the port
# mapping (see compose.yaml). Fontconfig keeps its cache in /tmp, the only writable
# place in the read-only container.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/cache \
    AASPECT_HOST=0.0.0.0
USER aaspect
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"]
CMD ["aaspect"]
