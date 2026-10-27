# 8 · Paso 2 · La primera herramienta

En el paso 1, el modelo no podía saber nada de la planta. Ahora se le da una forma de pedir un dato real: una herramienta. El programa la describe, el modelo la pide, el programa la ejecuta y le devuelve el resultado. Es la secuencia del capítulo 3, convertida en código.

## Describir la herramienta

El modelo solo conoce las herramientas que el programa le describe en cada llamada:

@@grep tutorial/paso2_herramienta.py "HERRAMIENTAS = [{" 8

La descripción tiene tres partes. El **nombre** es el que el modelo usará para pedirla. La **descripción** es lo que el modelo lee para decidir si le sirve: hay que escribirla pensando en él. Los **parámetros** dicen qué argumentos acepta, en formato JSON Schema; esta herramienta no acepta ninguno, y `additionalProperties: false` dice que tampoco se le pueden agregar.

## Ejecutarla

La herramienta en sí es una función corriente. Esta hace una lectura GET al gateway y devuelve lo que responde:

@@code tutorial/paso2_herramienta.py get_active_alarms

No escribe nada en ninguna parte. Las herramientas de ARYA siguen la misma regla, con una sola excepción, el borrador de orden (capítulo 15).

## La ida y vuelta

La función principal hace las dos llamadas al modelo, con la ejecución de la herramienta entre ellas:

@@code tutorial/paso2_herramienta.py main

Tres detalles hacen que funcione:

1. **El pedido del modelo también queda en la conversación.** Antes del resultado va el mensaje `assistant` con su `tool_calls`. Sin él, el modelo recibiría un resultado sin saber de dónde viene.
2. **El resultado se une al pedido por su identificador.** Cada llamada trae un `id`, y el mensaje `tool` lo repite en `tool_call_id`. Así el modelo sabe qué resultado corresponde a qué pedido, aunque pida varias herramientas a la vez.
3. **El resultado viaja como texto.** El JSON del gateway se convierte en texto y entra a la ventana de contexto como cualquier otro mensaje.

## Ejecutarlo

Para que haya algo que encontrar, primero se simula la falla A. La alarma tarda unos minutos en aparecer, como en una planta real:

```bash
./scripts/inject-fault.sh alpha
python tutorial/paso2_herramienta.py
```

Qué deberías ver con el servidor de guion:

```text
→ el modelo pide: get_active_alarms({})
← el programa responde con 1041 caracteres de datos reales
ARYA: [guion] Consulté get_active_alarms. Un modelo real redactaría aquí la respuesta con esos datos.
```

El modelo pidió la herramienta, el programa la ejecutó y 1 041 caracteres de datos reales entraron a la conversación. Con Nemotron, la última línea es una respuesta redactada a partir de esas alarmas.

> [!leccion] Ofrecer una herramienta no obliga a usarla
> En la primera prueba de ARYA con Nemotron, el modelo tenía las herramientas a mano y aun así respondió cinco preguntas sin consultarlas, con datos inventados. El modelo decide si usa una herramienta, y a veces decide mal. La corrección está en el paso 6: en el primer paso de cada pregunta, el código exige usar al menos una herramienta.

## En ARYA: catorce herramientas

ARYA tiene catorce herramientas. Todas siguen el patrón de este paso: una descripción para el modelo y una función que consulta un servicio.

### Las 14 herramientas

| Herramienta | Fuente | Qué devuelve |
|---|---|---|
| `get_current_tags` | Gateway (OPC UA) | Valores actuales con su calidad |
| `get_equipment_status` | Gateway | Estado de operación y nivel de alarma |
| `get_active_alarms` | Gateway | Alarmas activas con valor, límite y desde cuándo |
| `get_historian_data` | Historian | Resumen por señal: inicio, fin, cambio, tendencia, inicio del desvío |
| `compare_signals` | Historian | Correlación y cuál señal se desvió primero |
| `search_maintenance_documents` | Documentos | Fragmentos de manuales y procedimientos, con su identificador |
| `search_previous_work_orders` | CMMS | Órdenes anteriores de la P-101 |
| `get_work_order` | CMMS | Una orden por su identificador |
| `search_agent_memory` | Memoria | Incidentes investigados antes y lo que decidieron las personas |
| `get_condition_overview` | Historial de 6 meses | Zona de vibración, comparación a igual carga, proyección |
| `get_condition_trend` | Historial de 6 meses | Indicadores semanales |
| `project_condition_trend` | Historial de 6 meses | Rango de semanas hasta el límite |
| `get_planned_shutdowns` | CMMS | Calendario de paradas programadas |
| `create_work_order_draft` | CMMS | **La única escritura**: un borrador pendiente de aprobación |

Ninguna herramienta escribe en el proceso. La pantalla de estado del agente lo publica explícitamente (`process_write_tools: []`), y una prueba lo verifica.
