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
# Read at runtime by the settlement adapter in fixture mode (razorpay.yaml has
# enabled: false), so these are runtime data, not test data. Their absence surfaced as a
# 500 on the credit detail page in the built image - the kind of gap only a real image
# build finds. 68K.
COPY fixtures ./fixtures

# Run as a non-root user. Nothing in the request path writes to the image.
RUN useradd --create-home --uid 10001 residual \
 && mkdir -p /app/var \
 && chown -R residual:residual /app/var
USER residual

# RZ_PORT is deliberately NOT set here. `_port()` prefers RZ_PORT over PORT, so baking a
# value in would make the container ignore the port its platform assigns - on Render that
# means binding 8765 while the router probes $PORT, and the deploy fails its health check
# with the app apparently running fine. Leaving it unset lets PORT win, and the code
# default (8765) still applies when neither is set.
# /app/var is the only writable directory (chowned below). The AI investigation log and
# any per-organisation SQLite live here rather than in the read-only image tree.
ENV RZ_AI_AUDIT=/app/var/ai_audit.jsonl \
    RZ_TENANT_ROOT=/app/var/tenants \
    RZ_HOST=0.0.0.0 \
    RZ_ENV=production \
    RZ_AUTH_MODE=required \
    RZ_TRUST_PROXY=1

EXPOSE 8765

# /healthz is the liveness probe: it reports no financial data, touches no database, and
# needs no credential.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,os,sys; \
port=os.environ.get('RZ_PORT') or os.environ.get('PORT') or '8765'; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+port+'/healthz', timeout=4).status==200 else 1)"

CMD ["python", "-m", "residual_zero.console"]
