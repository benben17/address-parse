FROM python:3.10-slim

# NOTE (issue #12): pyahocorasick is a C extension that requires gcc on some
# platforms (e.g. aarch64 without pre-built wheels). If build fails on ARM,
# install build deps: RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Pre-extract JioNLP dictionaries during image build so the container can start directly.
RUN python -c "import jionlp"

COPY data ./data
COPY app ./app
COPY README.md ./README.md

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Dynamic worker count: 2-4 x CPU cores, capped at 8 (issue #16)
CMD ["sh", "-c", "WORKERS=$(python -c \"import os; print(min(8, max(2, (os.cpu_count() or 1) * 2)))\") && exec gunicorn --bind 0.0.0.0:8000 --workers $WORKERS --threads 2 --timeout 120 app.api:app"]
