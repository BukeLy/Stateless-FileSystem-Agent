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

# Create /tmp/.claude directory and copy settings
RUN mkdir -p /tmp/.claude/projects /tmp/.claude/debug /tmp/.claude/todos
COPY claude-settings.json /tmp/.claude/settings.json
RUN chmod -R 777 /tmp/.claude

ENV HOME=/root
ENV CLAUDE_CONFIG_DIR=/tmp/.claude

CMD ["handler.lambda_handler"]
