# syntax=docker/dockerfile:1
# Paperless-ngx MCP Server — Docker image
#
# Build:  docker build -t paperless-mcp .
# Run:    docker run -p 8000:8000 -v ./config:/config paperless-mcp
#
# The container reads its configuration from /config/config.toml.
# Mount a directory containing config.toml at /config, or override the path
# with the PAPERLESS_MCP_CONFIG environment variable.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

# ── Build stage: install dependencies ────────────────────────────────────────
FROM base AS builder

WORKDIR /app

# Copy the dependency manifest, lockfile, and source so uv generates the
# editable install finder with a populated MAPPING (not an empty dict).
COPY pyproject.toml uv.lock main.py ./

# Install production dependencies into the project virtual environment.
# --frozen ensures the lockfile is used as-is without updates.
# --no-dev excludes development-only dependencies.
RUN uv sync --frozen --no-dev

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM base AS runtime

WORKDIR /app

# Run as a non-root user for security.
RUN groupadd --gid 1001 mcp && \
    useradd --uid 1001 --gid mcp --shell /bin/sh --create-home mcp

# Copy the virtual environment produced by the builder.
COPY --from=builder --chown=mcp:mcp /app/.venv /app/.venv

# Copy application source and supporting files.
COPY --chown=mcp:mcp main.py ./
COPY --chown=mcp:mcp doc/ ./doc/

# Create the config directory. Users should mount their config.toml here.
RUN mkdir -p /config && chown mcp:mcp /config

USER mcp

# Tell the MCP server where to find the configuration file.
ENV PAPERLESS_MCP_CONFIG=/config/config.toml

# MCP server listens on this port (configured in main.py via FastMCP(port=8000)).
EXPOSE 8000

# uv run activates the project virtual environment and executes the entry point
# defined in pyproject.toml: [project.scripts] paperless-mcp = "main:main"
CMD ["uv", "run", "paperless-mcp"]
