# ARYA Industrial Demo - servicio agent
FROM python:3.12.15-slim-bookworm

LABEL org.opencontainers.image.title="arya-industrial-demo/agent" \
      com.arya.project="arya-industrial-demo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements/runtime.lock /app/requirements.lock
RUN pip install -r /app/requirements.lock \
    && useradd --system --uid 10001 --no-create-home arya \
    && mkdir /data && chown 10001 /data
COPY src/arya_agent /app/arya_agent
COPY data/documents /app/data/documents

USER 10001
VOLUME /data
EXPOSE 8091
CMD ["python", "-m", "arya_agent"]
