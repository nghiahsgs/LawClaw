FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ffmpeg \
    wget \
    openssh-client \
    && pip install --no-cache-dir yt-dlp \
    && rm -rf /var/lib/apt/lists/*

# Copy governance + source
COPY pyproject.toml README.md constitution.md judicial.md ./
COPY laws/ ./laws/
COPY skills/ ./skills/
COPY lawclaw/ ./lawclaw/

# Install lawclaw
RUN pip install --no-cache-dir -e .

# Non-root user for security
RUN useradd --create-home --shell /bin/bash lawclaw \
    && mkdir -p /data/workspace /data/.ssh \
    && ln -s /data/.ssh /home/lawclaw/.ssh \
    && chown -R lawclaw:lawclaw /data /app /home/lawclaw/.ssh

USER lawclaw

# Non-sensitive defaults only — secrets via env_file at runtime
ENV DB_PATH=/data/lawclaw.db
ENV WORKSPACE=/data/workspace
ENV LLM_PROVIDER=openrouter
ENV MODEL=google/gemini-2.5-pro

CMD ["lawclaw", "gateway"]
