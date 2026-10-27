# 20 · Despliegue sin Internet

ARYA corre completo en un notebook y una GB10, sin conexión a Internet. Este capítulo explica cómo se levanta, se actualiza y se verifica.

## Docker Compose

Los seis servicios corren con Docker Compose, en una red propia (`arya-ot`), con los puertos publicados solo en `127.0.0.1`, verificaciones de salud y tres volúmenes de datos: historian, CMMS y memoria del agente.

## Actualizar sin Internet

Reconstruir una imagen normalmente necesita Internet, porque Docker consulta la imagen base. Para trabajar sin red, `update-offline.sh` construye solo la capa del código sobre la imagen local que ya existe y reinicia el servicio:

```bash
./scripts/update-offline.sh agent demo-ui    # uno o varios servicios
```

## El atajo del día a día

```bash
./arya.sh           # abre Docker si hace falta, levanta todo, verifica y abre la pantalla
./arya.sh status    # estado de los contenedores, de Nemotron y de la voz
./arya.sh down      # apaga la demo; imágenes y datos se conservan
./scripts/reset-demo.sh          # planta, CMMS, memoria y historial a cero
```

## Cambiar un parámetro del agente

Los parámetros del agente están en `AgentSettings` (Apéndice A), y cada uno se lee de una variable de entorno. Docker Compose solo le pasa al contenedor del agente las variables que declara en `docker-compose.yml`. Hoy son, entre otras, `NEMOTRON_BASE_URL`, `NEMOTRON_MODEL`, `LLM_THINKING`, `LLM_STREAM` y `AGENT_PROACTIVE`, y se fijan en `.env`. Para cambiar otra, como `AGENT_MAX_STEPS`, primero hay que agregarla a esa lista. El cambio se aplica al recrear el servicio, por ejemplo con `docker compose up -d agent`.

## El chequeo previo

`preflight.sh` verifica cada servicio, la lectura OPC UA, la coherencia del lote y si Nemotron responde, y termina con un veredicto: `PLANT READY` o qué falta.

## La voz

La voz también funciona sin Internet:

- **Salida:** usa las voces en español que trae Windows.
- **Entrada:** un pequeño servicio de PowerShell usa el reconocedor de voz de Windows en español, con una gramática prioritaria de las frases del guion y dictado libre para el resto.
