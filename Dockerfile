# Stage 1: Build wheel
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy source files
COPY pyproject.toml README.md ./
COPY src/ src/

# Build wheel
RUN python -m build --wheel

# Stage 2: Runtime
FROM python:3.11-slim

LABEL maintainer="Benjamin Duthe"
LABEL description="MCP Server for Proxmox VE management"
LABEL version="0.1.0"

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash mcp

# Copy wheel from builder
COPY --from=builder /app/dist/*.whl .

# Install the package
RUN pip install --no-cache-dir *.whl && rm *.whl

# Create SSH directory for key mounting
RUN mkdir -p /home/mcp/.ssh && chown -R mcp:mcp /home/mcp/.ssh

# Switch to non-root user
USER mcp

# Set environment defaults
ENV PROXMOX_PORT=8006 \
    PROXMOX_VERIFY_SSL=false \
    PROXMOX_TIMEOUT=30 \
    PROXMOX_SSH_USER=root \
    PROXMOX_SSH_PORT=22

# Entry point
ENTRYPOINT ["proxmox-mcp"]
