# Single image serving both the API and the Streamlit console. Which one runs
# is decided by the compose command, so there is one build to keep in sync
# rather than two.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so a source edit does not invalidate the layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY config/ ./config/
COPY evaluation/ ./evaluation/
RUN pip install --no-cache-dir -e .

# The signal corpus ships with the image. The competition dataset does not:
# it is licensed material and is bind-mounted at runtime instead.
COPY data/external/ ./data/external/
RUN mkdir -p data/raw data/processed data/vectorstore exports

RUN useradd --create-home --uid 1000 agent && chown -R agent:agent /app
USER agent

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "cardiac_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
