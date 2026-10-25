# syntax=docker/dockerfile:1

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
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

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home aaspect
COPY --from=build /app/.venv /app/.venv
# All interfaces inside the container only; who can reach it is decided by the port
# mapping (see compose.yaml).
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AASPECT_HOST=0.0.0.0
USER aaspect
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"]
CMD ["aaspect"]
