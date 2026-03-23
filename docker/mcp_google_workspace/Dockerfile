# Use a lightweight Python base
FROM python:3.11-slim

# Install uv to manage the package
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Install the workspace-mcp server
RUN uv pip install --system workspace-mcp

RUN mkdir -p /root/.credentials

# Expose the default MCP HTTP port
EXPOSE 8007

ENV WORKSPACE_MCP_PORT=8007
ENV WORKSPACE_MCP_HOST=0.0.0.0

# Set required environment variables for Google OAuth
# These should be passed at runtime, not hardcoded here
ENV GOOGLE_OAUTH_CLIENT_ID=""
ENV GOOGLE_OAUTH_CLIENT_SECRET=""

# Run the server using the streamable-http transport
# host 0.0.0.0 is required for Docker to allow external traffic
CMD ["bash"]
