FROM public.ecr.aws/lambda/python:3.12-arm64

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Claude Code CLI
RUN uv pip install --system claude-code-cli

# Copy project files
COPY pyproject.toml .
COPY *.py ./

# Install dependencies
RUN uv pip install --system .

# Create ~/.claude directories for session files
RUN mkdir -p /root/.claude/projects /root/.claude/debug /root/.claude/todos

ENV HOME=/root

CMD ["handler.lambda_handler"]
