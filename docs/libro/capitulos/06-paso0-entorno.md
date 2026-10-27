# 6 · Paso 0 · Preparar el entorno

Antes de escribir una línea del agente, todo lo que lo rodea tiene que estar funcionando: la planta, el gateway por donde se la lee y un modelo que responda. Este paso lo deja listo y lo comprueba con un programa de 52 líneas.

## Qué corre dónde

@@img docs/img/libro/que-corre-donde.svg Lo que corre durante el tutorial. Tu programa reemplaza al contenedor del agente: lee la planta a través del gateway y habla con el modelo, sea Nemotron en la GB10 o el servidor de guion.

Tu programa habla con el gateway igual que ARYA: por HTTP, en el puerto 8081 del notebook, y solo para leer. Con el modelo habla por `/v1/chat/completions`, la misma ruta en la GB10 que en el servidor de guion.

## Lo que necesitas

- El repositorio del proyecto y su entorno de Python 3.12 (`~/.venvs/arya-industrial-demo`), con las librerías ya instaladas.
- Docker Desktop.
- Un modelo: Nemotron en la GB10, otro servidor compatible con la API de OpenAI que soporte llamadas a herramientas, o el servidor de guion del tutorial, que no necesita hardware.

Todos los comandos se ejecutan en Ubuntu (WSL), desde la carpeta del proyecto. Para abreviar, el libro escribe `python`; en tu equipo es `~/.venvs/arya-industrial-demo/bin/python`.

## 1. Levantar la planta y el gateway

```bash
./arya.sh           # abre Docker si hace falta, levanta todo, verifica y abre la pantalla
./arya.sh status    # estado de los contenedores, de Nemotron y de la voz
```

## 2. Elegir el modelo

Sin GB10, en otra terminal, se deja corriendo el servidor de guion:

```bash
python tutorial/modelo_guion.py      # queda escuchando en 127.0.0.1:8099
```

Con Nemotron, los programas leen las mismas variables que ARYA: `NEMOTRON_BASE_URL`, `NEMOTRON_MODEL` y `NEMOTRON_API_KEY`. Si tu `.env` ya las define (así se conecta ARYA a la GB10), basta con exportarlas en la terminal donde vas a trabajar:

```bash
set -a; . ./.env; set +a
```

Si esas variables no están definidas, los programas usan el servidor de guion.

## 3. Comprobar

```bash
python tutorial/paso0_entorno.py
```

El programa hace tres pruebas. Cada una pasa por la misma función, que atrapa cualquier error y lo informa en vez de detenerse:

@@code tutorial/paso0_entorno.py revisar

La segunda prueba ya es una lectura real de la planta, la misma que hará el agente:

@@code tutorial/paso0_entorno.py lectura_de_la_bomba

Qué deberías ver (con el servidor de guion):

```text
[ OK ] Gateway: conexión OPC UA CONNECTED
[ OK ] Lectura de la bomba: vibración 2.06 mm/s, temperatura del motor 57.1 °C
[ OK ] Modelo: modelos: modelo-de-guion
Todo listo para el paso 1.
```

Tus valores serán otros, porque la planta simulada tiene ruido. Con Nemotron, la última prueba muestra el nombre del modelo.

> [!cuidado] Si algo falla
> Si fallan el gateway o la lectura de la bomba, la planta no está arriba: `./arya.sh status` muestra qué contenedor falta. Si falla el modelo con el servidor de guion, revisa que `modelo_guion.py` siga corriendo en la otra terminal. Si falla con Nemotron, la GB10 no responde desde el notebook: revisa el cable y la dirección en `.env`.

## Las pruebas del tutorial

Cada paso del tutorial tiene una prueba automática que lo ejecuta de verdad: levanta una planta con su servidor OPC UA, un gateway y el servidor de guion, y corre el programa como lo harías tú. Si cambias algo en el tutorial, esta es la forma rápida de saber si sigue funcionando:

```bash
python -m pytest -q tests/test_tutorial.py
```
