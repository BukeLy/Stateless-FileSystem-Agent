FROM public.ecr.aws/lambda/python:3.12-arm64

# Set working directory (Lambda default)
WORKDIR ${LAMBDA_TASK_ROOT}

# Install uv and create uvx symlink
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN ln -s /usr/local/bin/uv /usr/local/bin/uvx

# Install Node.js 20+ (required for MCP's undici dependency)
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# hadolint ignore=DL3016,DL3041
RUN curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - && \
    dnf install -y nodejs && \
    dnf clean all && \
    npm install -g @anthropic-ai/claude-code
SHELL ["/bin/sh", "-c"]

# Fix npm cache permissions for Lambda
RUN mkdir -p /tmp/.npm && chmod -R 777 /tmp/.npm
ENV npm_config_cache=/tmp/.npm

# Install Python dependencies
RUN uv pip install --system boto3 claude-agent-sdk

# Copy Lambda code and ensure readable
COPY ./*.py ./
RUN chmod 644 ./*.py

# Copy config files (MCP servers, SubAgents) to /opt (read-only at runtime)
# setup_lambda_environment() will copy to /tmp/.claude-code at runtime
COPY claude-config/ /opt/claude-config/
RUN chmod -R 755 /opt/claude-config/

# Copy skills to /opt/claude-skills (will be copied to /tmp/.claude-code/skills at runtime)
COPY claude-config/skills/ /opt/claude-skills/
RUN chmod -R 755 /opt/claude-skills/

# Lambda only allows writes to /tmp
# Set HOME=/tmp so:
# - mcp-remote writes to /tmp/.mcp-auth/ instead of /root/.mcp-auth/
# - Claude SDK writes to /tmp/.claude/ instead of /root/.claude/
# - AWS SDK reads from /tmp/.aws/ instead of /root/.aws/
# Directories are created at runtime in setup_lambda_environment()
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache
ENV npm_config_cache=/tmp/.npm

CMD ["handler.lambda_handler"]
