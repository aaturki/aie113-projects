# The fraud-alerts service, packed with everything it needs to run the same way everywhere.
#
# The base image is pinned by its digest: every build starts from exactly the same bits.
ARG PYTHON_IMAGE=python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# ---------- Stage 1, builder: install the locked libraries into a virtual environment ----------
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.lock /tmp/requirements.lock
# --no-deps: exactly the locked list, nothing more. pip check: fails if the list is incomplete.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-deps -r /tmp/requirements.lock \
    && /opt/venv/bin/pip check \
    && /opt/venv/bin/pip uninstall --yes pip          # nothing is installed at run time

# ---------- Stage 2, runtime: only what the service needs to run ----------
FROM ${PYTHON_IMAGE} AS runtime

# Security fixes Debian published after the pinned base image was built.
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# A normal user, not root. No pip and no curl in the final image: fewer tools for an attacker,
# fewer things to patch. The health check uses Python itself.
RUN useradd --create-home --uid 10001 app \
    && python -m pip uninstall --yes pip

WORKDIR /app

# Ordered from "changes rarely" to "changes often", so a code change rebuilds only the last layer.
# 1) The libraries: hundreds of MB, change when the lock changes.
COPY --from=builder /opt/venv /opt/venv
# 2) The model and its facts: 0.6 MB, change when the model is retrained.
COPY artifacts/fraud_model.joblib artifacts/model_info.json /app/artifacts/
# 3) The code: a few KB, changes with every commit.
COPY src/ /app/src

ARG GIT_SHA=dev
LABEL org.opencontainers.image.title="fraud-alerts" \
      org.opencontainers.image.description="Card-fraud alerts with reasons (SDA-AIE-113 fraud track, SDAIA Academy)" \
      org.opencontainers.image.source="https://github.com/aaturki/aie113-projects" \
      org.opencontainers.image.revision=$GIT_SHA
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    FRAUD_MODEL_DIR=/app/artifacts

USER app
EXPOSE 8000

# The container is healthy when the service is READY (model loaded), not merely alive.
# urlopen raises on a 503, so a service without its model reports unhealthy.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/ready', timeout=2)"]

# Exec form: uvicorn is process 1, receives the stop signal, and shuts down cleanly.
CMD ["uvicorn", "fraud_alerts.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
