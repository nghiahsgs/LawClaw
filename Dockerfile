FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy governance + source
COPY pyproject.toml README.md constitution.md judicial.md ./
COPY laws/ ./laws/
COPY skills/ ./skills/
COPY lawclaw/ ./lawclaw/

# Install lawclaw
RUN pip install --no-cache-dir -e .

# Runtime data dirs (overridden by volume mount)
RUN mkdir -p /data/workspace

ENV DB_PATH=/data/lawclaw.db
ENV WORKSPACE=/data/workspace
ENV LLM_PROVIDER=openrouter
ENV MODEL=google/gemini-2.5-flash

CMD ["lawclaw", "gateway"]
