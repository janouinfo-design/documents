FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Runtime dependencies (explicit — independent from the Emergent-only pip freeze)
RUN pip install --no-cache-dir \
    "fastapi" "uvicorn[standard]" "motor" "pymongo" \
    "pydantic>=2" "python-dotenv" "requests" "python-multipart" "apscheduler" \
    "pymupdf" "pillow"

# Optional OCR support (GPT-4o via Emergent integrations). Best-effort:
# only needed if EMERGENT_LLM_KEY is configured. Build never fails if unavailable.
RUN pip install --no-cache-dir emergentintegrations \
    --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
    || echo "emergentintegrations non installé (OCR désactivé jusqu'à configuration)"

COPY server.py extraction.py technical_data.py ./

EXPOSE 8001

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
