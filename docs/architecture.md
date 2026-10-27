# ARYA — arquitectura del lado planta (notebook)

Actualizado el 6 de octubre de 2026.

Este documento describe **lo que está implementado**. Lo que pertenece a etapas
futuras aparece solo en la sección final y marcado como tal.

## Distribución física

```mermaid
flowchart LR
  subgraph Notebook["Notebook · planta / OT simulada (implementado)"]
    SIM["plant: modelo P-101 + alarmas"] --> UA["plant: servidor OPC UA · solo lectura · :4840"]
    CTRL["plant: API de control · token · :9001"] --> SIM
    UA -->|OPC UA| HMI["plant-view: pantalla de operación · :8080"]
    UA -->|OPC UA| GW["ot-gateway: historian + API de lectura · :8081"]
    CMMS["cmms: órdenes de trabajo · :8082"]
    NAV["Navegador del presentador"] --> HMI
    NAV -->|POST con token, solo loopback| CTRL
  end
    AG["agent: ARYA (hoy aquí; irá en la GB10)"] -->|solo lectura| GW
    AG -->|leer y crear borradores| CMMS
    UI["demo-ui: pantalla dividida · :8090"] --> AG
    NAV --> UI
    NAV -->|aprobar / rechazar con token humano| UI
  end
  subgraph GB10["Dell Pro Max GB10 · AI Compute Node (sin tocar todavía)"]
    NEM["Nemotron existente"]
  end
  AG -.->|pendiente de conectar| NEM
```

La planta funciona sola: no depende de la GB10 ni de ningún modelo de lenguaje.

## Los servicios del lado planta

| Servicio | Contiene | Fuente de datos | Puede modificar el proceso |
|---|---|---|---|
| `plant` | Modelo, escenarios, alarmas, servidor OPC UA, API de control | Su propio simulador | Solo el presentador, con token |
| `plant-view` | Cliente OPC UA y pantalla de operación | Solo OPC UA | No (solo GET) |
| `ot-gateway` | Cliente OPC UA, historian y API de lectura | Solo OPC UA | No (solo GET) |
| `cmms` | Órdenes de trabajo | Su base propia | No toca el proceso |

**El agente no hablará OPC UA.** Verá la planta únicamente a través de
`ot-gateway`, por HTTP y en solo lectura. Así OPC UA queda dentro del notebook
y no hay que exponerlo a la GB10.

La separación es estructural: las imágenes de `plant-view` y `ot-gateway` no
incluyen el paquete del simulador, así que no pueden importarlo, y ninguna
recibe el token de control. Lo que saben de la planta es el nombre del
namespace y de los nodos; unidades, descripciones y límites los leen del
servidor OPC UA al conectarse.

Todos los contenedores corren con usuario sin privilegios, sistema de archivos
de solo lectura, sin capacidades de Linux, reinicio automático, logs limitados
y un healthcheck que comprueba el servicio de verdad. El de `ot-gateway`, por
ejemplo, solo está sano si recibe OPC UA **y** está escribiendo en el historian.

## Modelo industrial

Bomba centrífuga P-101 a velocidad aproximadamente constante. Valores ficticios
para la demostración, no normativos.

| Señal | Normal | Con la falla completa |
|---|---|---|
| Temperatura del motor | 57 °C | ≈ 97 °C |
| Vibración | 2,0 mm/s RMS | ≈ 8,5 mm/s |
| Corriente | 11,5 A | ≈ 12,9 A (+12 %) |
| Presión de descarga | 4,8 bar | ≈ 4,46 bar (−7 %) |
| Caudal | 62 m³/h | ≈ 57 m³/h (−8 %) |
| Velocidad | 1480 rpm | ≈ 1476 rpm |

**Señales correlacionadas.** No hay un ruido independiente por tag. Todo deriva
de tres variables lentas y de la severidad de la falla:

- *Demanda hidráulica:* mueve juntos caudal y corriente, y en sentido contrario
  presión y velocidad (a velocidad fija, más caudal implica menos altura).
- *Excitación mecánica:* pequeña variación de la vibración, que crece con la falla.
- *Ambiente:* deriva lenta de la temperatura.

**Inercia térmica.** La temperatura sigue a su valor de equilibrio con una
respuesta de primer orden (constante de tiempo de 25 s), por eso sube después
que la vibración.

**Separación del reloj.** El modelo avanza un paso fijo de tiempo simulado por
llamada y no lee ningún reloj. El reloj real y OPC UA viven en otra capa
(`runtime.py`), lo que permite simular 30 minutos en milisegundos en las pruebas.

## Escenarios de falla

Hay dos escenarios, con identificadores públicos neutros (`alpha` y `bravo`,
"A" y "B" en la pantalla). En ambos la severidad crece linealmente de 0 a 1 en
`FAULT_DURATION_SECONDS` (180 s por defecto, entre 30 y 900).

| | Escenario A (`alpha`) | Escenario B (`bravo`) |
|---|---|---|
| Vibración | 2,0 → ≈ 8,5 mm/s | 2,0 → ≈ 3,6 mm/s, más irregular |
| Temperatura | 57 → ≈ 97 °C, con retraso | Casi sin cambio (+3 °C) |
| Corriente | +12 % | **−15 %** |
| Caudal | −8 % | **−36 %** |
| Presión | −7 % | −19 % |
| WARNING (con 180 s) | ≈ 1:10 por vibración | ≈ 1:15 por bajo caudal |
| ALARM (con 180 s) | ≈ 2:20 por vibración | ≈ 2:15 por caudal muy bajo |

Una falla solo puede empezar con la planta sana. Tras NORMAL OPERATION hay que
esperar a que la planta vuelva a NORMAL (unos 90 s) o usar RESET.

**Falla programada.** El presentador puede dejar una falla para dentro de N
minutos (hasta 4 horas). Empieza sola al cumplirse el plazo; si en ese momento
la planta no está en NORMAL, espera a que lo esté. RESET la cancela.

**Alarmas sin oscilación.** Cada alarma se activa solo si la condición persiste
2 s y se libera solo si la señal baja de su límite menos una banda muerta
(2 °C; 0,3 mm/s; 1 m³/h) durante 3 s. Las alarmas de caudal son por valor bajo.

**Estados.** `DEGRADATION` y `RECOVERY` son estados internos del escenario. Las
alarmas dependen únicamente de las señales y sus límites.

**Sin disparo de protección.** La bomba permanece `RUNNING` con alarma activa.
Simular una parada automática exigiría diseñar esa protección; queda fuera de
esta etapa.

**Causa real oculta.** La causa de cada escenario vive solo dentro del simulador
(`scenarios.py`), para una evaluación futura del agente. No aparece en los
tags OPC UA, en las APIs, en la pantalla ni en los logs; las pruebas lo verifican.

**Reproducibilidad.** La secuencia pseudoaleatoria usa una semilla fija. Con
los mismos parámetros y la falla inyectada en el mismo instante simulado, la
evolución es idéntica valor por valor. Si se inyecta en otro instante, la
tendencia es la misma y solo cambian las pequeñas variaciones superpuestas.

## Controles de demostración

API en `plant`, puerto 9001, publicada solo en loopback del notebook.
Autenticación con `Authorization: Bearer <token>`; el token se genera
localmente y se guarda en `.env`.

| Ruta | Efecto |
|---|---|
| `POST /api/demo/inject-fault` | Inicia la falla. Acepta `duration_seconds` y `scenario` (`alpha` o `bravo`) opcionales. Responde 409 si hay una falla activa o la planta aún se recupera. |
| `POST /api/demo/schedule-fault` | Programa una falla: `delay_seconds` obligatorio, `scenario` y `duration_seconds` opcionales. |
| `POST /api/demo/cancel-schedule` | Cancela la falla programada. |
| `POST /api/demo/normal` | Retira la falla: recuperación gradual en el mismo ensayo. Sin falla activa no hace nada y lo informa. |
| `POST /api/demo/reset` | Estado inicial, secuencia reiniciada y nuevo `run_id`. |
| `GET /api/demo/state` | Estado del escenario para el presentador. |
| `GET /healthz` | Salud del servicio (sin token). |

Estos controles son del presentador. No son herramientas del futuro agente.

CORS solo admite los orígenes locales de la pantalla
(`http://127.0.0.1:<SCADA_PORT>` y `http://localhost:<SCADA_PORT>`). El
navegador envía el token directamente a la API de control; `plant-view` nunca lo ve.

## Contrato OPC UA

- **Endpoint:** `opc.tcp://127.0.0.1:4840/arya/plant/` (dentro de la red de
  Compose: `opc.tcp://plant:4840/arya/plant/`).
- **Namespace URI:** `urn:arya:industrial-demo:plant`. Los clientes deben
  resolver el índice por la URI (hoy es `ns=2`).
- **NodeIds:** de tipo string, estables entre reinicios.
- **Acceso:** todos los nodos son de solo lectura para clientes. Una escritura
  devuelve `BadUserAccessDenied`.
- **Seguridad:** sin cifrado ni usuarios en esta etapa (ver límites).

| NodeId (`ns=2;s=…`) | Tipo | Unidad | Contenido |
|---|---|---|---|
| `P101.MOTOR_TEMP` | Double | °C | Temperatura del motor |
| `P101.VIBRATION` | Double | mm/s | Vibración global, velocidad RMS |
| `P101.CURRENT` | Double | A | Corriente del motor |
| `P101.DISCHARGE_PRESSURE` | Double | bar | Presión de descarga |
| `P101.FLOW` | Double | m³/h | Caudal |
| `P101.RPM` | Double | rpm | Velocidad |
| `P101.STATUS` | String | — | `RUNNING` |
| `P101.ALARM_LEVEL` | String | — | `NORMAL`, `WARNING` o `ALARM` |
| `P101.ACTIVE_ALARMS` | String[] | — | Códigos activos, p. ej. `P101.VIBRATION.HI` |
| `RUN.ID` | String | — | Identificador del ensayo; cambia con cada RESET |
| `RUN.SIM_TIME_S` | Double | s | Tiempo simulado desde el inicio del ensayo |
| `RUN.SNAPSHOT_SEQ` | UInt32 | — | Número de lote (ver coherencia) |
| `P101.MOTOR_TEMP.HI` / `.HIHI` | Double | °C | Límites WARNING / ALARM (75 / 88) |
| `P101.VIBRATION.HI` / `.HIHI` | Double | mm/s | Límites WARNING / ALARM (4,5 / 7,1) |
| `P101.FLOW.LO` / `.LOLO` | Double | m³/h | Límites WARNING / ALARM por bajo caudal (52 / 45) |

Códigos de alarma: `P101.VIBRATION.HI`, `P101.VIBRATION.HIHI`,
`P101.MOTOR_TEMP.HI`, `P101.MOTOR_TEMP.HIHI`, `P101.FLOW.LO`, `P101.FLOW.LOLO`.

Cada señal con unidad tiene la propiedad estándar `EngineeringUnits`
(EUInformation con código UNECE) y todos los nodos tienen `Description`.

**Timestamps.** Todos los valores de un lote llevan el mismo `SourceTimestamp`
en UTC, tomado al calcular la muestra.

**Coherencia de un lote.** El servidor actualiza los nodos uno por uno. Para
que un cliente no mezcle dos lotes:

1. El servidor pone `RUN.SNAPSHOT_SEQ` en un valor **impar**, escribe todos los
   nodos y luego lo pone en el siguiente valor **par**.
2. El cliente lee, en una sola petición, `SEQ`, todos los nodos y `SEQ` otra vez.
3. El lote es válido si los dos `SEQ` son iguales y pares. Si no, reintenta
   (hasta 4 veces) y, si persiste, lo trata como error de lectura.

## Calidad de datos en `plant-view`

| Calidad | Significado |
|---|---|
| `GOOD` | Conectado, lote coherente, estados OPC UA buenos y muestra reciente |
| `BAD` | El servidor reportó algún estado no válido |
| `STALE` | Sin conexión o muestra más antigua que `STALE_AFTER_SECONDS` (5 s) |
| sin snapshot | Aún no se recibió ninguna muestra real |

En `STALE` se conserva la última muestra real con su antigüedad y el error
observado. El cliente reintenta la conexión con espera creciente (0,5 s a 5 s).

## Historian y gateway de lectura (`ot-gateway`)

**Historian.** SQLite en modo WAL, en un volumen propio (`arya-historian`).
Guarda cada lote nuevo y de buena calidad que llega por OPC UA, a 1 muestra por
segundo, con su timestamp de origen y su `run_id`. Si se pierde la conexión no
escribe nada: no fabrica muestras. Deriva además un registro de eventos de
alarma (activación y normalización). Conserva 7 días.

Se eligió SQLite en lugar de InfluxDB o TimescaleDB porque son 6 señales a 1 Hz
y es una pieza menos que pueda fallar. El contrato HTTP permite cambiarlo después.

**API.** Todas las rutas son GET, bajo `/api/v1`. El activo acepta `P-101` o `P101`.

| Ruta | Devuelve |
|---|---|
| `/assets/P-101/tags` | Valores actuales con unidad, calidad y antigüedad |
| `/assets/P-101/status` | Estado de operación y nivel de alarma |
| `/assets/P-101/alarms` | Alarmas activas con valor, límite y desde cuándo; límites configurados |
| `/assets/P-101/history?signals=&minutes=&max_points=` | Por señal: mínimo, máximo, media, valor inicial y final, cambio porcentual, tendencia, **inicio de la desviación** y puntos resumidos |
| `/assets/P-101/compare?signal_a=&signal_b=&minutes=` | Resumen de ambas, correlación y cuál se desvió primero |
| `/assets/P-101/alarm-events?minutes=` | Historial de activaciones y normalizaciones |
| `/signals` | Señales disponibles: `motor_temp`, `vibration`, `current`, `discharge_pressure`, `flow`, `rpm` |

Reglas pensadas para que un agente no pueda inventar:

- Sin datos de la planta responde 503 con la explicación, no con valores.
- Con datos desactualizados devuelve el último valor real marcado `STALE` y una advertencia explícita.
- Con pocas muestras no calcula correlación ni inicio de desviación; lo dice.
- Por defecto consulta solo el ensayo actual (`scope=current_run`), para que la
  historia de un ensayo anterior no se mezcle tras un RESET. `scope=all` trae todo.

**Inicio de la desviación.** Toma como línea base el primer 25 % de la ventana
y busca el momento desde el cual la señal queda fuera de esa base (más de
4 desviaciones estándar o 3 %) hasta el final. Es un cálculo determinista, no
una estimación del modelo de lenguaje.

## CMMS (`cmms`)

Órdenes de trabajo en SQLite, en su volumen (`arya-cmms`), sembradas desde
`data/work-orders/seed.json` con cinco órdenes históricas ficticias.

| Ruta | Credencial | Efecto |
|---|---|---|
| `GET /api/v1/work-orders?asset=&q=&status=&limit=` | Ninguna | Búsqueda por activo y texto (ignora tildes) |
| `GET /api/v1/work-orders/{id}` | Ninguna | Una orden |
| `POST /api/v1/work-orders/drafts` | Clave del agente | Crea `WO-DRAFT-00NN` en estado `DRAFT_PENDING_APPROVAL` |
| `POST /api/v1/work-orders/{id}/approve` | Token humano | El borrador pasa a `OPEN` con número definitivo `WO-AAAA-NNNN` |
| `POST /api/v1/work-orders/{id}/reject` | Token humano | El borrador pasa a `REJECTED` |
| `POST /api/v1/admin/reset` | Token humano | Vuelve a las órdenes históricas |

La aprobación humana está garantizada por diseño y no por instrucción al
modelo: la clave del agente (`CMMS_AGENT_KEY`) no sirve para aprobar, rechazar
ni reiniciar, y el servicio se niega a arrancar si ambas credenciales son iguales.

## Agente ARYA (`agent`)

Construido y probado, salvo la conexión real al modelo. Hoy corre en el notebook;
el día de la demo irá en la GB10 junto a Nemotron, y puede quedarse en el
notebook apuntando al modelo de la GB10 como plan B.

**Principio: razonamiento del modelo dentro de un envoltorio determinista.**
El modelo decide qué herramientas usar. El código decide cuáles existen, con
qué argumentos, cuántas y por cuánto tiempo.

| Límite | Valor por defecto |
|---|---|
| Llamadas al modelo por pregunta | 6 |
| Herramientas por pregunta | 8 |
| Tiempo máximo por herramienta | 8 s |
| Tiempo máximo por pregunta | 120 s |
| Borradores de orden por pregunta | 1 |
| Preguntas simultáneas | 1 (la segunda recibe "ocupada") |

**Herramientas.** Diez, todas con esquema explícito, validación, timeout y
error controlado. Ninguna escribe en el proceso.

| Herramienta | Fuente |
|---|---|
| `get_current_tags`, `get_equipment_status`, `get_active_alarms` | OPC UA, vía gateway |
| `get_historian_data`, `compare_signals` | Historian, vía gateway |
| `search_maintenance_documents` | Documentos de planta (local) |
| `search_previous_work_orders`, `get_work_order` | CMMS |
| `search_agent_memory` | Memoria del agente |
| `create_work_order_draft` | CMMS; solo crea un borrador |

Si una herramienta falla, el modelo recibe un error explícito
(`{"ok": false, "error": ..., "message": ...}`) y nunca valores. Si el modelo
no está disponible, ARYA responde un mensaje fijo que lo dice.

**Solo lectura por construcción.** No hay herramienta de escritura, el agente
no recibe el token de control de la planta, el gateway solo acepta GET y el
servidor OPC UA rechaza escrituras. La regla también está en las instrucciones
del modelo, pero no depende de que el modelo la obedezca.

**Documentos (RAG local).** Nueve documentos ficticios en `data/documents/`
(manual, procedimientos de alarma, lubricación, filtro de succión, bloqueo,
checklist y recomendaciones del fabricante), troceados por sección. La
búsqueda es léxica (BM25) con normalización de tildes: no necesita un modelo
de embeddings ni servicios externos. Cada resultado lleva el identificador del
documento para que ARYA lo cite. Se eligió así por ser pocos documentos cortos;
si hiciera falta búsqueda semántica, el modelo de embeddings iría en la GB10.

**Memoria.** SQLite en el volumen del agente. Se escribe de forma determinista,
no por decisión del modelo: al crear un borrador queda registrado el incidente
(problema, causa probable, evidencia, ensayo), y cuando una persona decide, el
agente **verifica la decisión en el CMMS** antes de recordarla. No se puede
hacer que "recuerde" una aprobación que el CMMS no respalda.

**Aviso proactivo.** Un vigilante consulta las alarmas por el gateway. Si está
habilitado y la planta pasa de NORMAL a alarma, espera unos segundos y lanza a
ARYA sin que nadie pregunte. Un solo aviso por incidente.

**Traza operacional.** Cada pregunta, llamada al modelo (latencia y tokens),
herramienta (argumentos, fuente, duración, resultado), respuesta y decisión
humana queda como evento con identificador de conversación y de turno, en
memoria y en `trace.jsonl`. No se registra razonamiento interno: si el modelo
emite bloques `<think>`, se eliminan antes de mostrar o guardar nada.

**Adaptador del modelo.** `OpenAICompatModel` habla el protocolo "chat
completions" con llamadas a herramientas. Es una suposición sobre cómo está
expuesto Nemotron, pendiente de confirmar; el resto del agente depende solo de
una interfaz, así que el adaptador se cambia sin tocar nada más.

Se usó un ciclo propio y acotado en lugar de LangGraph: son unas 80 líneas,
sin dependencias adicionales que construir para ARM, y los límites quedan a la
vista. Si más adelante se necesitan flujos con ramas, se puede migrar.

## Pantalla dividida (`demo-ui`)

Se sirve desde el notebook en el puerto 8090. Muestra la planta (vista
compacta, incrustada) y ARYA. Reenvía al agente y al CMMS **solo** las rutas
que la pantalla necesita: estado, conversación, eventos en vivo, sincronizar
una decisión, y aprobar o rechazar. No reenvía administración ni creación de
borradores. Así el navegador habla siempre con el mismo origen local, sin
importar en qué equipo corra el agente, y el micrófono quedará disponible para
la voz (el navegador solo lo entrega a páginas locales).

El token de aprobación viaja únicamente desde el navegador del presentador; el
servicio de la pantalla no lo guarda.

## Etapas futuras (no implementado)

- Conexión real a Nemotron, tras inspeccionar la GB10 en solo lectura.
- Voz de entrada y de salida.
- Abrir `ot-gateway`, `cmms` y el agente hacia la interfaz del cable, y decidir
  si la lectura llevará clave.
- Construir la imagen del agente para la arquitectura de la GB10.
- Indicador de uso de la GB10 y ambientación al rubro del cliente.

## Referencias

- [asyncua: servidor mínimo](https://opcua-asyncio.readthedocs.io/en/latest/usage/get-started/minimal-server.html)
- [FastAPI: lifespan](https://fastapi.tiangolo.com/advanced/events/)
