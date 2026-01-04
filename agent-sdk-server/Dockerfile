FROM public.ecr.aws/lambda/python:3.12-arm64

# Set working directory (Lambda default)
WORKDIR ${LAMBDA_TASK_ROOT}

# Install uv and create uvx symlink
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN ln -s /usr/local/bin/uv /usr/local/bin/uvx

# Install Claude Code CLI (npm package, requires nodejs)
# hadolint ignore=DL3016,DL3041
RUN dnf install -y nodejs npm && \
    dnf clean all && \
    npm install -g @anthropic-ai/claude-code

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

# Create ~/.claude and ~/.aws directories and ensure writable
RUN mkdir -p /root/.claude/projects /root/.claude/debug /root/.claude/todos /root/.aws && \
    touch /root/.claude.json && \
    chmod -R 777 /root/.claude /root/.claude.json /root/.aws

ENV HOME=/root
# Redirect cache to /tmp (Lambda only allows writes to /tmp)
ENV XDG_CACHE_HOME=/tmp/.cache

CMD ["handler.lambda_handler"]
