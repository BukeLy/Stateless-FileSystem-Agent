FROM public.ecr.aws/lambda/python:3.12-arm64

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Claude Code CLI (npm package, requires nodejs)
RUN dnf install -y nodejs npm && npm install -g @anthropic-ai/claude-code

# Install Python dependencies
RUN uv pip install --system boto3 claude-agent-sdk

# Copy Lambda code and ensure readable
COPY *.py ./
RUN chmod 644 *.py

# Copy config files (MCP servers, SubAgents) to /opt (read-only at runtime)
# setup_lambda_environment() will copy to /tmp/.claude-code at runtime
COPY claude-config/ /opt/claude-config/

# Create ~/.claude and ~/.aws directories and ensure writable
RUN mkdir -p /root/.claude/projects /root/.claude/debug /root/.claude/todos /root/.aws && \
    touch /root/.claude.json && \
    chmod -R 777 /root/.claude /root/.claude.json /root/.aws

ENV HOME=/root

CMD ["handler.lambda_handler"]
