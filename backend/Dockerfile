FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN --mount=type=secret,id=custom_ca \
    if [ -f /run/secrets/custom_ca ]; then export PIP_CERT=/run/secrets/custom_ca; fi; \
    pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=custom_ca \
    if [ -f /run/secrets/custom_ca ]; then export SSL_CERT_FILE=/run/secrets/custom_ca UV_SYSTEM_CERTS=true; fi; \
    uv sync --frozen --no-dev
COPY app ./app
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
