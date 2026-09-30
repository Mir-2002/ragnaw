FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /bin/uv

# HF Spaces run containers as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:$PATH \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /home/user/app

# Dependencies first so code changes don't invalidate this layer.
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=user . .
RUN uv sync --frozen --no-dev

EXPOSE 7860
# --proxy-headers so request.client is the visitor's IP behind HF's proxy (needed for rate limiting).
CMD ["uvicorn", "ragnaw.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
