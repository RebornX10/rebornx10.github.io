FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates zstd && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ollama.com/install.sh | sh

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HOST=0.0.0.0 \
    PORT=7860 \
    OPEN_BROWSER=false \
    OLLAMA_URL=http://localhost:11434 \
    OLLAMA_MODEL=qwen2.5:0.5b \
    OUTPUT_BASENAME=/tmp/papers \
    OMP_NUM_THREADS=2 \
    OLLAMA_NUM_PARALLEL=1

WORKDIR /home/user/app

# Bust the build cache whenever master changes, so a rebuild always pulls the
# latest app code (otherwise the git clone layer is cached and stays stale).
ADD https://api.github.com/repos/RebornX10/rebornx10.github.io/git/refs/heads/master /tmp/ref.json
RUN git clone --depth 1 https://github.com/RebornX10/rebornx10.github.io.git . \
    && pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user start.sh /home/user/start.sh

EXPOSE 7860

CMD ["bash", "/home/user/start.sh"]
