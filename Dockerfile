FROM python:3.11-slim

LABEL org.opencontainers.image.title="sci_paper_llm" \
      org.opencontainers.image.authors="Samuel Adone (RebornX10)" \
      org.opencontainers.image.source="https://github.com/RebornX10/sci_paper_llm" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    OPEN_BROWSER=false \
    OLLAMA_URL=http://host.docker.internal:11434

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
