# Cloudflare Containers builds this image from the repository root.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install the locked production dependencies before copying application code so
# dependency installation stays cached when only source files change.
COPY Test-LiveKit/pyproject.toml Test-LiveKit/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY Test-LiveKit/agent.py \
     Test-LiveKit/gmail_tools.py \
     Test-LiveKit/observability.py \
     Test-LiveKit/container_agent.py \
     ./

EXPOSE 8080

# container_agent.py runs a local health endpoint and supervises the LiveKit
# worker process. Runtime secrets are supplied by the Cloudflare Worker.
CMD ["uv", "run", "--no-sync", "python", "container_agent.py"]
