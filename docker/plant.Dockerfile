# ARYA Industrial Demo - servicio plant (modelo P-101, servidor OPC UA, API de control)
FROM python:3.12.15-slim-bookworm

LABEL org.opencontainers.image.title="arya-industrial-demo/plant" \
      com.arya.project="arya-industrial-demo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements/runtime.lock /app/requirements.lock
RUN pip install -r /app/requirements.lock \
    && useradd --system --uid 10001 --no-create-home arya
COPY src/arya_plant /app/arya_plant

USER 10001
EXPOSE 4840 9001
CMD ["python", "-m", "arya_plant"]
