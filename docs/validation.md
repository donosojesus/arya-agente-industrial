# ARYA — validación del lado planta

Ejecutado el 6 de octubre de 2026 en el notebook.

**Resultado: `PLANT READY`.** Las 10 pruebas obligatorias se ejecutaron y
pasaron, incluidos los contenedores. Esto valida solo la planta: la demo
completa no está lista porque el agente ARYA todavía no existe.

## Voz de entrada, controles a la vista y métricas (19 y 20 de octubre)

| Comprobación | Resultado |
|---|---|
| Reconocedor de voz local de Windows (es-ES), con voz sintetizada en lugar de micrófono | 4 de 4 preguntas del guion reconocidas (confianza 0,63 a 0,78) y una frase libre correcta (0,52) |
| Escucha de voz como servicio local (`voice-listener.ps1`, puerto 8095) | Arranca con `arya.sh up`, detecta el micrófono, responde con CORS solo a la pantalla de la demo |
| Botón HABLAR en la pantalla | Activo cuando la escucha está en marcha |
| Botones SIMULAR FALLA y VOLVER A NORMAL sin token en el navegador | Funcionan; una petición que no viene de la pantalla de la demo recibe 403; RESET sigue fuera de la pantalla |
| Streaming para TTFT y TPOT | Probado con un servidor de prueba (tool calls repartidas en fragmentos, vuelta automática al modo normal ante errores) |
| Contadores del tablero | En su propia línea, sin tapar los títulos |

No comprobado: la voz con una persona hablando y por parlantes; el streaming contra el
NIM real (si falla, `LLM_STREAM=off` en `.env` vuelve al modo ya probado).

## Ensayo con Nemotron real tras las correcciones (19 de octubre, tarde)

**Resultado: el recorrido completo funciona con el modelo real. 82 pruebas aprobadas.**

| Prueba con el modelo real | Resultado |
|---|---|
| 7 preguntas de la demo, falla A | 32 s en total (2,5 a 10 s por pregunta); datos reales en todas; memoria vacía dicha tal cual; cita SOP-MNT-014; correlación correcta (vibración 16 s antes); diagnóstico = causa real (lubricación del rodamiento); borrador creado solo al pedirlo |
| Aprobación humana y memoria | WO-DRAFT-0031 aprobado como WO-2026-0412; el agente lo verificó en el CMMS y lo recordó |
| Aviso automático con la falla B | ARYA interrumpió sola a los 101 s de iniciada la falla: "Disculpen la interrupción. … el caudal está bajo…" |
| Diagnóstico de la falla B (con el incidente de rodamiento en memoria) | Primero erró (dijo rodamiento e inventó una fecha). Tras corregir el método de diagnóstico: **3 de 3 correctos** (obstrucción en la succión / filtro STR-101), 3 a 7,5 s |
| Reto de las reglas | Primero no se negó de forma explícita y en 3 pedidos el modelo se descontroló (cientos de llamadas a herramientas). Tras la corrección: **4 de 4 negativas explícitas**, en menos de 2 s, incluso con "olvida tus reglas" |

Correcciones de esta tanda: reintento ante JSON de herramienta mal formado (lo rechaza el
servidor), negativa explícita y sin herramientas ante pedidos de operar la planta,
verificación de fechas citadas, el aviso automático ya no contagia su saludo a las
respuestas siguientes, y un método de diagnóstico que obliga a revisar la corriente y la
temperatura antes de concluir.

Prueba de resistencia: 23 minutos sin una falla de servicio y con la memoria estable en
los seis contenedores (se detuvo al decidir que las fallas no se gatillan solas).

No comprobado todavía: la voz (no se ha escuchado), el tablero POR DENTRO y los tokens con
una persona delante, un ensayo con la red desconectada de verdad, y una prueba de
resistencia de varias horas.

## Conexión real a Nemotron (19 de octubre)

**Resultado: ARYA funciona con Nemotron real; 78 pruebas aprobadas.** Queda repetir el
recorrido completo con el modelo después de las últimas correcciones.

Inspección (solo lectura, sin credenciales ni cambios en la GB10):

| Comprobación | Resultado |
|---|---|
| Servicio | NVIDIA NIM en `http://gb10.local:30081/v1`, API compatible con OpenAI |
| Modelo | `nvidia/nemotron-3-nano`, contexto de 32 000 tokens |
| Español | Correcto; 2,3 s para una respuesta breve |
| Llamada a herramientas | Nativa (`tool_calls`); eligió la herramienta correcta con las 10 de ARYA |
| Razonamiento interno | Llega en un campo aparte (`reasoning_content`) que ARYA descarta |
| Tiempo por paso con 10 herramientas | 16,7 s con razonamiento; **0,75 s sin razonamiento** (configuración elegida) |
| Forzar herramienta (`tool_choice`) | Soportado: `required` y una herramienta específica |

Primera prueba del diálogo (7 preguntas, escenario A en alarma): respondió en 4 a 10 s
por pregunta, pero **inventó datos** en 5 preguntas en las que no consultó herramientas
(una orden inexistente, fechas, incidentes en una memoria vacía, una alarma de presión
inexistente) y no creó la orden con la herramienta.

Controles agregados y segunda prueba:

| Control | Efecto observado |
|---|---|
| El primer paso de cada pregunta exige una herramienta | Las 7 preguntas consultaron datos |
| El contexto conserva los resultados reales de las 3 preguntas anteriores | Citó correctamente WO-2026-0142, -0281 y -0317 |
| Verificación de órdenes y documentos citados | Sin referencias inventadas |
| Memoria vacía | Lo dijo tal cual |
| Pedido de orden | Creó el borrador con la herramienta |

Fallas de la segunda prueba, corregidas después (probadas sin el modelo):

| Falla | Corrección |
|---|---|
| Creó una orden al preguntarle "¿qué recomiendas?" | La herramienta de borradores solo se ofrece si el operador pide una orden |
| Una pregunta falló por corte de conexión con el modelo | Un reintento ante cortes de conexión |
| La búsqueda de documentos no encontró nada (buscó en inglés) | La búsqueda entiende términos en inglés |
| "Se desvió primero la temperatura", cuando fue la vibración | Línea base corta; medido con una falla nueva: vibración primero, 13 s antes, a los 3, 8 y 13 minutos |

Otros hallazgos: el notebook estaba sin Internet y Docker no podía reconstruir las
imágenes; `scripts/update-offline.sh` actualiza el código sobre la imagen local. El
arranque automático de Docker Desktop desde `arya.sh` funcionó (47 s hasta `PLANT READY`).

## Tablero "ARYA por dentro" (6 de octubre, noche)

Tercer modo de la pantalla dividida. Se alimenta de los mismos eventos reales
del agente; no simula pasos. 72 pruebas aprobadas tras el cambio.

| Comprobación | Resultado |
|---|---|
| Se enciende el paso del ciclo y las tarjetas que corresponden a cada evento | Verificado en tres capturas de una repetición: paso 4 con Herramientas y Observabilidad; paso 3 con Herramientas; paso 3 con Herramientas y RAG al buscar documentos |
| Contador de herramientas y datos por tarjeta | Correctos en las capturas (por ejemplo 4 / 8, tokens, documentos) |
| Cada pregunta empieza con el tablero limpio | Verificado |
| MCP nunca se enciende | Verificado: en gris con "No implementado en esta demo" |
| [Captura de prueba de diseño](img/por-dentro-prueba-de-diseno.png) | Hecha con el modelo de reemplazo y rotulada como tal; herramientas, fuentes y tiempos son reales |

No comprobado: el tablero con Nemotron (en particular si informa tokens), el
encendido en vivo con una persona delante, y el botón de repetición pulsado a
mano (se probó abriendo la página con `?mode=inside&replay=1`).

## Agente ARYA y pantalla dividida (6 de octubre, noche)

**Resultado: seis contenedores `healthy`, preflight `PLANT READY`, 72 pruebas aprobadas en 154 s.**
El agente está construido y probado, pero **no conectado a ningún modelo**: lo
que sigue valida todo lo que rodea al modelo, no la calidad de sus respuestas.

| Archivo | Pruebas | Qué verifica |
|---|---|---|
| `tests/test_agent.py` | 14 | Herramientas contra servicios reales; errores controlados; ciclo con límites; traza sin razonamiento interno; sin modelo no inventa; recorrido completo hasta la aprobación humana; aviso proactivo; memoria; adaptador del modelo |
| `tests/test_ui.py` | 3 | La pasarela solo alcanza lo permitido; agente caído se informa; recursos solo locales |

En estas pruebas el modelo se reemplaza por un guion fijo (`ScriptedModel`, en
`tests/`). Todo lo demás es real: planta por OPC UA, historian, CMMS,
documentos y memoria.

| Comprobación | Resultado |
|---|---|
| Recorrido completo en pruebas | Falla inyectada → alarmas → historia → comparación → órdenes → documentos → memoria → borrador `WO-DRAFT-0031` → aprobación humana → memoria actualizada |
| Segundo borrador en la misma pregunta | Bloqueado |
| Modelo que nunca deja de pedir herramientas | Detenido en el límite, con mensaje fijo |
| "Recordar" una aprobación que el CMMS no respalda | Rechazado (409) |
| Aviso proactivo | Un solo aviso por incidente, y solo si está habilitado |
| Contenedor del agente sin modelo | Responde el mensaje fijo de "sin acceso al modelo", sin herramientas ni valores |
| Eventos en vivo a través de la pasarela | Recibidos (7 eventos en la prueba) |
| Pantalla dividida real, 1920×1080 | [Captura sin modelo](img/demo-dividida-sin-modelo.png): planta en alarma y ARYA avisando que no tiene modelo |
| Diseño de traza y tarjeta de orden | [Captura de prueba de diseño](img/demo-dividida-prueba-de-diseno.png), hecha con el modelo de reemplazo y rotulada como tal; las herramientas, la orden y los datos de planta sí son reales |
| Consumo de los seis contenedores | Unos 320 MB de memoria y menos de 5 % de CPU en reposo |

No comprobado:

- **Nada del comportamiento con Nemotron:** elección de herramientas, calidad en
  español, latencia, ni el formato de llamada a herramientas, que es una suposición.
- La pantalla dividida con una persona delante: botones APROBAR y RECHAZAR,
  cambio de modo y casilla de aviso automático no se han pulsado a mano. La
  aprobación a través de la pasarela sí está probada.
- `open-demo.sh` no se ejecutó, para no abrir ventanas del navegador.
- El modo respaldo `dev-start.sh` con los seis servicios.

Hallazgo durante la validación: el navegador de pruebas se quedó colgado con la
conexión de eventos en vivo. Se agregó un respaldo por consulta periódica
(automático si la conexión en vivo falla, o forzado con `?poll=1`).

## Ampliación del 6 de octubre (tarde): historian, gateway, CMMS y segundo escenario

**Resultado: `PLANT READY` con los cuatro contenedores `healthy`. 55 pruebas, 55 aprobadas, 120 s.**

| Archivo nuevo | Pruebas | Qué verifica |
|---|---|---|
| `tests/test_scenarios.py` | 6 | Escenario B con firma distinta, sin oscilación; falla programada; segunda falla solo con planta sana; causa real distinta por escenario y oculta |
| `tests/test_gateway.py` | 6 | Historian alimentado por un cliente OPC UA real; historia, comparación, eventos; sin datos y datos desactualizados; solo lectura; persistencia |
| `tests/test_cmms.py` | 5 | Búsqueda; el agente solo crea borradores y no puede aprobar; aprobación y rechazo humanos; persistencia y reinicio |

Ensayo del recorrido de la demo, ejecutado contra los contenedores:

| Paso | Resultado |
|---|---|
| Falla A de 60 s | ALARM por vibración; el gateway reporta las tres alarmas con valor, límite y hora de activación |
| Historia de 10 min | Vibración 2,0 → 8,5 mm/s (+326 %), temperatura 57 → 86 °C (+51 %), caudal −9 %; avisa que solo hay 2,5 min de historia |
| Comparación vibración–temperatura | Correlación 0,99; la vibración se desvió primero, 8 s antes |
| Borrador de orden con la clave del agente | Creado `WO-DRAFT-0031`, estado `DRAFT_PENDING_APPROVAL` |
| El agente intenta aprobar | Rechazado: HTTP 401 |
| Aprobación con el token humano | Pasa a `WO-2026-0412`, estado `OPEN`, con el nombre de quien aprobó |
| NORMAL OPERATION | La planta volvió a NORMAL en 87 s |
| Falla B programada a 1 min | Empezó sola; alarma de bajo caudal 178 s después de pedir NORMAL |
| Registro de eventos de alarma | Las 9 activaciones y normalizaciones del ensayo, en orden |
| `reset-demo.sh` | Planta y CMMS al estado inicial; preflight de nuevo `PLANT READY` |

Pantalla nueva, capturada con un navegador real a 1920×1080:
[escenario A](img/hmi-escenario-a.png) y [escenario B](img/hmi-escenario-b.png).
Las capturas muestran pocas muestras en las tendencias porque el navegador sin
interfaz solo permanece unos segundos en la página.

No comprobado en esta ampliación:

- La pantalla nueva con una persona delante: botón RECONOCER, panel DEMO y
  programación desde la pantalla no se han pulsado a mano (sí por API y script).
- Los scripts PowerShell modificados (`start-demo.ps1`, `preflight.ps1`) pasan la
  revisión de sintaxis pero no se volvieron a ejecutar.
- El modo respaldo `dev-start.sh` con los cuatro servicios no se volvió a ejecutar.
- Una prueba de resistencia de varias horas.

## Entorno

| Elemento | Versión |
|---|---|
| Equipo | Notebook Windows 11 x64 con WSL 2 |
| Python de desarrollo (WSL) | 3.12.13 |
| Python en las imágenes | `python:3.12.15-slim-bookworm` |
| asyncua / FastAPI / uvicorn | 2.1.0 / 0.142.2 / 0.54.0 |
| pytest / pytest-asyncio / httpx | 9.1.1 / 1.4.0 / 0.28.1 |
| Docker Engine / Compose | 29.5.2 / v5.1.3 (Docker Desktop) |
| PowerShell | Windows PowerShell 5.1 |

Versiones exactas de todas las dependencias: `requirements/runtime.lock` y `requirements/dev.lock`.

## Pruebas automatizadas

`python -m pytest -q` → **38 pruebas, 38 aprobadas, 92 s.**

| Archivo | Pruebas | Qué usa |
|---|---|---|
| `tests/test_model.py` | 12 | Modelo y simulador con tiempo simulado |
| `tests/test_opcua_integration.py` | 6 | Servidor y cliente OPC UA reales |
| `tests/test_control_api.py` | 11 | API de control sobre una planta real |
| `tests/test_plant_view.py` | 7 | Cliente OPC UA de `plant-view` contra una planta real |
| `tests/test_e2e_processes.py` | 2 | Los dos servicios como procesos reales |

## Las 10 pruebas obligatorias

| # | Prueba | Resultado | Evidencia |
|---|---|---|---|
| 1 | Estabilidad y rangos del estado normal | Aprobada | 30 min simulados: todas las señales dentro de banda y con media junto al valor nominal, sin alarmas |
| 2 | Correlación y evolución gradual de la falla | Aprobada | Caudal–corriente > 0,9; caudal–presión < −0,9; sin saltos; temperatura retrasada más de 10 s respecto de la vibración |
| 3 | Transiciones NORMAL → DEGRADATION → WARNING → ALARM | Aprobada | Cada estado aparece una sola vez (sin oscilación); también observado por OPC UA |
| 4 | Reproducibilidad del ensayo | Aprobada | Dos ensayos con los mismos parámetros dan series idénticas valor por valor |
| 5 | Reset determinístico | Aprobada | Tras RESET: nuevo `run_id`, estado igual al inicial y la misma serie que el primer ensayo |
| 6 | Lectura de todos los tags con un cliente OPC UA real | Aprobada | 16 nodos leídos con tipo, descripción, unidad y timestamp UTC |
| 7 | Rechazo de escrituras OPC UA | Aprobada | Escritura rechazada en los 16 nodos con `BadUserAccessDenied` |
| 8 | Validación y autenticación de los controles | Aprobada | 401 sin token o con token incorrecto en las 4 rutas; 422 con datos inválidos; 409 al repetir la inyección; CORS solo para orígenes locales |
| 9 | Pérdida de conexión y recuperación del cliente | Aprobada | En pruebas, con procesos reales y con contenedores (ver abajo) |
| 10 | Arranque y healthchecks de los contenedores | Aprobada | Ambos contenedores `healthy`; preflight `PLANT READY` |

### Detalle de la evolución de la falla (prueba 3)

Ensayo real de 180 s en contenedores, observado desde el notebook con un cliente
OPC UA a `opc.tcp://127.0.0.1:4840/arya/plant/`:

| Tiempo desde la inyección | Nivel | Alarmas activas |
|---|---|---|
| 0 s | NORMAL | — |
| 71 s | WARNING | `P101.VIBRATION.HI` |
| 102 s | WARNING | + `P101.MOTOR_TEMP.HI` |
| 142 s | ALARM | + `P101.VIBRATION.HIHI` |
| 164 s | ALARM | + `P101.MOTOR_TEMP.HIHI` |

| Tiempo | Temp. °C | Vib. mm/s | Corriente A | Presión bar | Caudal m³/h | rpm | Estado |
|---|---|---|---|---|---|---|---|
| 0 s | 57,0 | 2,04 | 11,54 | 4,79 | 62,2 | 1480 | RUNNING |
| 60 s | 65,8 | 4,32 | 11,89 | 4,71 | 59,9 | 1479 | RUNNING |
| 120 s | 79,5 | 6,05 | 12,35 | 4,60 | 58,2 | 1478 | RUNNING |
| 181 s | 92,1 | 8,69 | 12,81 | 4,49 | 56,6 | 1477 | RUNNING |

Con tiempo simulado, el mismo escenario dio WARNING a 72 s y ALARM a 140,5 s.

### Detalle de pérdida y recuperación (prueba 9)

Se mató el proceso de la planta dentro de su contenedor (`kill -9`):

| Momento | Pantalla / API de lectura | Contenedor `plant` |
|---|---|---|
| Antes | `CONNECTED`, calidad `GOOD` | `healthy` |
| +3 s | `DISCONNECTED`, calidad `STALE`, último valor real conservado, error `ConnectionRefusedError` visible | Reiniciado automáticamente por Docker (1 reinicio) |
| +9 s | `CONNECTED`, calidad `GOOD`, nuevo `run_id` | `healthy` |

No hizo falta ninguna intervención. La misma secuencia se verifica en las
pruebas automatizadas, donde además se comprueba que sin planta la API responde
"sin datos" (no ceros) y que el healthcheck de `plant-view` pasa a no sano.

### Detalle de contenedores (prueba 10)

| Verificación | Resultado |
|---|---|
| `start-demo.sh --build` (preparación con Internet) | Imágenes construidas (280 MB cada una); ambos contenedores `healthy` |
| `preflight.sh` y `preflight.ps1` | `PLANT READY`, 25 verificaciones en verde |
| Preflight con una falla en curso | `PLANT NOT READY`, con la indicación de ejecutar `reset-demo` |
| `start-demo.sh` sin `--build` | Arrancó en 17 s con imágenes locales, sin construir ni descargar |
| `start-demo.ps1` sin `-Build` | Arrancó correctamente |
| Puertos publicados | `127.0.0.1:8080`, `127.0.0.1:9001`, `127.0.0.1:4840` (solo loopback) |
| Endurecimiento | Usuario 10001, raíz de solo lectura, sin capacidades, reinicio `unless-stopped`, logs 3 × 5 MB |
| Separación | La imagen `plant-view` no contiene el paquete del simulador ni recibe el token |
| `stop-demo.sh` / `stop-demo.ps1` | Retiraron solo los contenedores y la red de ARYA; los 9 contenedores ajenos quedaron intactos y no se borró ninguna imagen (16 antes y después) |

## Otras comprobaciones realizadas

Capturas de la pantalla real: [operación normal](img/scada-normal.png) y
[alarma](img/scada-alarm.png) (esta última es anterior a un ajuste menor de la disposición de los botones).

| Comprobación | Resultado |
|---|---|
| Pantalla en un navegador real (Edge sin interfaz, 1920×1080) | Se dibuja completa en una pantalla, con valores, tendencias, alarmas y estado de conexión |
| Navegador con token correcto | Botones habilitados y estado del escenario leído desde la API de control (CORS y token funcionan desde el navegador) |
| Navegador con token incorrecto / sin token | "Token rechazado" / botones deshabilitados |
| Scripts PowerShell desde Windows | `inject-fault`, `normal-operation`, `reset-demo`, `preflight`, `demo-status`, `start-demo`, `stop-demo` ejecutados con el resultado esperado |
| Scripts bash desde WSL | Todos ejecutados, incluido el modo respaldo `dev-start` / `dev-preflight` / `dev-stop` |
| Token en los logs | No aparece en los logs de ningún contenedor ni proceso |
| Causa de la falla en salidas públicas | No aparece en nodos OPC UA, APIs, pantalla ni logs |
| NORMAL OPERATION durante una falla | Tras un paso la temperatura sigue alta y la alarma activa; vuelve a NORMAL de forma gradual en el mismo ensayo |

## Implementado, probado y pendiente

**Implementado y probado realmente**

- Modelo de P-101, alarmas con persistencia e histéresis, escenario reproducible.
- Servidor OPC UA de solo lectura con unidades, descripciones, timestamps UTC,
  identificación del ensayo y número de lote.
- API de control con token, validación y CORS local.
- `plant-view`: cliente OPC UA con reconexión, API de lectura y pantalla.
- Imágenes, Compose, healthchecks, reinicio automático y scripts de operación.

**Implementado pero no comprobado**

- `start-demo.ps1 -Build`: la construcción se ejecutó con el script bash; el
  equivalente PowerShell usa el mismo comando de Compose pero no se corrió.
- `open-scada.sh` / `open-scada.ps1`: no se ejecutaron para no abrir ventanas
  en el navegador del usuario. El mecanismo que usan (token en el fragmento de
  la URL) sí se probó con el navegador sin interfaz.
- Pulsación manual de los tres botones en la pantalla: el navegador sin interfaz
  comprobó la habilitación y la llamada autenticada, y las tres acciones se
  probaron por API y por script, pero nadie ha hecho clic todavía.
- El camino de reintento por lote incoherente: en 4 779 lecturas con el servidor
  actualizando rápido ninguna resultó incoherente, así que la regla está
  verificada de forma unitaria pero el reintento no se disparó de forma natural.

## Pendientes y limitaciones

1. **Arranque sin red física.** Se probó que el arranque no construye ni
   descarga, pero no con el Wi-Fi y el cable desconectados. Conviene hacerlo
   antes del 22 de octubre.
2. **Seguridad de OPC UA.** Sin cifrado ni usuarios; lectura anónima. Aceptable
   en loopback, pero hay que decidirlo antes de exponer el puerto a la GB10.
3. **Docker Desktop debe estar abierto.** No arranca solo. Con Docker abierto,
   los contenedores vuelven solos tras un reinicio del equipo, salvo que se
   hayan detenido con `stop-demo`. Si Docker fallara, existe el respaldo
   `dev-start.sh` en WSL.
4. **Tendencias de la pantalla.** Viven en la página y se pierden al recargar o al
   cambiar de ensayo. El historian ya existe, pero la pantalla aún no lo consulta.
5. **Sin disparo de protección.** La bomba sigue `RUNNING` en alarma, por diseño.
6. **Reproducibilidad exacta** solo si la falla se inyecta en el mismo instante
   simulado; en otro instante la tendencia es igual y cambian las variaciones menores.
7. **API de control dentro de la red de Compose.** Los contenedores de lectura
   pueden alcanzar el puerto 9001 de `plant` por la red interna; la protección
   ahí es el token, que `plant-view` no tiene.
8. **Token en el navegador.** `open-scada` lo pasa en el fragmento de la URL y
   la página lo guarda en `sessionStorage` hasta cerrar la pestaña.
9. **Imagen base por etiqueta**, no por digest. Una reconstrucción futura
   podría traer una revisión distinta de `python:3.12.15-slim-bookworm`.
10. **PowerShell** exige `-ExecutionPolicy Bypass` para ejecutar los scripts.
11. **Identidad de Git.** El repositorio usa nombre y correo configurados solo
    en este proyecto, porque el equipo no tenía identidad global.
12. **Sin cifrado ni usuarios en gateway y lectura del CMMS.** Hoy solo en loopback;
    hay que decidirlo al abrirlos hacia la GB10.
13. **Inicio de desviación con historia mezclada.** Si en un mismo ensayo hubo una
    falla, recuperación y una segunda falla, la línea base de una ventana corta
    puede caer en la recuperación de la primera.
14. **Perfil temporal del navegador de pruebas.** Quedó una carpeta
    `arya-edge-profile` y capturas `arya-*.png` en la carpeta TEMP de Windows;
    se pueden borrar a mano.


## 23 de octubre de 2026 · ficha técnica de la bomba y dos correcciones del agente

| Prueba | Resultado |
|---|---|
| Ficha técnica FT-P101-001 (curva propia coherente con 62 m³/h · 4,8 bar · 11,5 A, motor de 15 kW a 690 V, zonas de vibración ISO 10816-3, repuestos) | El agente carga 10 documentos; las búsquedas de las fallas A y B devuelven los mismos procedimientos que antes |
| Error encontrado: con `tool_choice` exigido y streaming, el servidor del modelo entrega los argumentos vacíos (`{"query": ""}`) | Corregido: las llamadas con herramienta exigida van sin streaming; los pasos libres siguen midiendo TTFT/TPOT |
| Error encontrado: "para la P-101" o "la corriente está baja" se tomaban como pedidos de operar | Corregido: el verbo debe abrir la frase o seguir a "puedes", "por favor", "y"…; prueba con 7 órdenes y 6 preguntas |
| Ensayo de la falla A con Nemotron, tras 2 min de planta sana | 7 preguntas en 37 s, 0 herramientas fallidas; vibración 10 s antes que la temperatura; diagnóstico = causa real; cita MAN-P101-001, FT-P101-001 y SOP-MNT-014 |
| Negativas (`rehearse-agent.sh --reglas`) | 3 de 3, sin herramientas |
| Repuestos | Cita FT-P101-001: sello SM-35, rodamientos 6309-C3 y 6308-C3 |


## 23 de octubre de 2026 · escenario C: análisis predictivo con 6 meses de historial

| Pieza | Resultado |
|---|---|
| Historial simulado de 6 meses (bronce cada 10 min, ≈ 26 000 muestras) coherente con la planta, la ficha FT-P101-001 y el CMMS | Aparecen los incidentes de mayo (temperatura) y julio (filtro: caída de caudal y presión, corriente menor); paradas de domingo y trimestrales |
| Medallón | Plata descarta huecos, paradas, arranques y picos, y normaliza a 62 m³/h y 20 °C; oro: indicadores diarios |
| Variante sana | Zona A, sin tendencia relevante: ARYA lo dijo así, sin inventar un problema |
| Variante con desgaste (escenario C) | Vibración p95 3,07 mm/s (zona B, +61 %), sobre el umbral de seguimiento desde el 19-09, temperatura +2,4 °C, presión en su curva; sin alarmas |
| Proyección | Rango entre tres ajustes (recta 6 semanas, recta 2 semanas, exponencial): límite de 4,5 mm/s en 2,4 a 6,9 semanas |
| Diseño | La planta publica el perfil del historial (RUN.HISTORY_PROFILE, opaco) y el gateway lo lee por OPC UA: el gateway sigue siendo solo GET y sin token |
| Ensayos con Nemotron (4 preguntas) | 5 rondas tras los ajustes: siempre el rango correcto y la parada del 7-11, que llega antes del rango; orden PREDICTIVE con fecha y repuestos en las rondas completas |
| Errores encontrados y corregidos | Herramienta exigida + streaming = argumentos vacíos; orden larga cortada por el límite de tokens (HTTP 400 "Invalid JSON"); fechas con día no se verificaban al día exacto; una mención de parada sin consultar el calendario |
| Observación | Una vez, un paso del modelo tardó 36 s (47 tokens); al repetir, 0,8 a 2 s. Demora puntual del servidor del modelo |
| Pruebas automáticas | 100 pasan |
