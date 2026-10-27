# ARYA Industrial Demo - servicio plant-view (cliente OPC UA, API de lectura, SCADA)
# Esta imagen NO contiene el paquete del simulador: solo puede obtener datos por OPC UA.
FROM python:3.12.15-slim-bookworm

LABEL org.opencontainers.image.title="arya-industrial-demo/plant-view" \
      com.arya.project="arya-industrial-demo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements/runtime.lock /app/requirements.lock
RUN pip install -r /app/requirements.lock \
    && useradd --system --uid 10001 --no-create-home arya
COPY src/arya_otclient /app/arya_otclient
COPY src/arya_plant_view /app/arya_plant_view

USER 10001
EXPOSE 8080
CMD ["python", "-m", "arya_plant_view"]
