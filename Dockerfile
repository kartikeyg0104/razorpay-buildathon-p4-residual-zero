# Residual Zero — production image.
#
# One process: the FastAPI ops console. No sidecar, no worker, no queue. Reconciliation is
# synchronous, deterministic and fast enough on this corpus that adding a broker would be
# infrastructure without a job.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a source change does not re-resolve the environment.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[postgres]"

# Configuration, the committed synthetic dev corpus, and the migrations. The corpus is the
# demo organisation's dataset; it is synthetic and public in the repository, and it is not
# any real merchant's data.
COPY config ./config
COPY migrations ./migrations
COPY data ./data
COPY scripts ./scripts
COPY artifacts ./artifacts
COPY extension ./extension

# Run as a non-root user. Nothing in the request path writes to the image.
RUN useradd --create-home --uid 10001 residual \
 && mkdir -p /app/var \
 && chown -R residual:residual /app/var
USER residual

ENV RZ_HOST=0.0.0.0 \
    RZ_PORT=8765 \
    RZ_ENV=production \
    RZ_AUTH_MODE=required \
    RZ_TRUST_PROXY=1

EXPOSE 8765

# /healthz is the liveness probe: it reports no financial data and needs no credential.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('RZ_PORT','8765')+'/healthz', timeout=4).status==200 else 1)"

CMD ["python", "-m", "residual_zero.console"]
