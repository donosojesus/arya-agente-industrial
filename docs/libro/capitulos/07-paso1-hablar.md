# 7 · Paso 1 · Hablar con el modelo

El primer paso es lo mínimo: enviar una pregunta al modelo y leer su respuesta. Todavía sin herramientas, para ver con claridad qué sabe el modelo y qué no.

## Qué se envía y qué vuelve

@@img docs/img/libro/peticion-respuesta.svg Una llamada al modelo: lo que envía el programa y lo que devuelve el servidor. A la izquierda, los valores del tutorial; a la derecha, la forma de la respuesta, cuyo texto y cifras cambian en cada llamada.

La conversación es una lista de mensajes, cada uno con un rol:

| Rol | Quién lo escribe | Para qué |
|---|---|---|
| `system` | El programa | Las instrucciones fijas: quién es el agente y qué reglas sigue. Va primero, en cada llamada |
| `user` | El operador | La pregunta |
| `assistant` | El modelo | Sus respuestas, y desde el paso 2, sus pedidos de herramientas |
| `tool` | El programa | Los resultados de las herramientas (paso 2) |

Como el modelo no recuerda nada entre llamadas (capítulo 2), el programa envía la lista completa cada vez.

## El código

Una función envía la conversación y devuelve la respuesta tal como llega:

@@code tutorial/paso1_hablar.py preguntar

Es una sola petición HTTP de tipo POST. Lleva el nombre del modelo, la conversación, la temperatura (0,2, como ARYA), un tope de 300 tokens para la respuesta y un campo propio de Nemotron que apaga su razonamiento previo. Si hay una clave de acceso, va en la cabecera `Authorization`.

La función principal arma la conversación con dos mensajes, llama al modelo y mide cuánto tardó:

@@code tutorial/paso1_hablar.py main

## Ejecutarlo

```bash
python tutorial/paso1_hablar.py
python tutorial/paso1_hablar.py "¿Qué es una bomba centrífuga?"
```

Qué deberías ver con el servidor de guion:

```text
ARYA: [guion] No soy un modelo: no conozco la planta ni puedo consultarla. Un modelo real respondería con lo que aprendió al entrenarse.
tiempo: 0.1 s · tokens de entrada: n/d · tokens de salida: n/d
```

El servidor de guion no cuenta tokens; Nemotron sí, y el programa los muestra.

## Qué pasa con un modelo real

Con Nemotron, la pregunta por defecto deja a la vista el problema del capítulo 2: el modelo no tiene cómo saber la temperatura del motor. Puede decir que no tiene el dato, o puede inventar uno que suene bien. En la primera prueba de ARYA, sin herramientas obligatorias, inventó datos en cinco de las siete preguntas.

La segunda pregunta es distinta: qué es una bomba centrífuga es conocimiento general, y ahí el modelo sí puede responder bien. La diferencia entre las dos preguntas es la razón de ser de un agente.

## Lo que este paso enseña

- El modelo solo ve la conversación que le envías, y no recuerda nada entre llamadas.
- Las instrucciones de sistema van primero, en cada llamada.
- Sin datos reales en la conversación, el modelo responde con lo que suena plausible.

## En ARYA: el mismo paso, con más cuidado

ARYA hace lo mismo que `preguntar`, con tres agregados: una interfaz que permite reemplazar el modelo en las pruebas, streaming para medir la velocidad y reintentos ante fallas del servidor. El resto de este capítulo los muestra en el código real.

### NVIDIA Nemotron como NIM en la GB10

El modelo es `nvidia/nemotron-3-nano`, servido como NIM en la Dell Pro Max GB10, con 32 000 tokens de contexto. Un NIM expone la misma API que usan los servicios de OpenAI (`/v1/chat/completions`), con **llamadas a herramientas nativas**: el modelo no escribe texto que haya que interpretar, sino que devuelve una estructura con el nombre de la herramienta y sus argumentos en JSON.

El agente lo usa a través de una interfaz mínima, que permite reemplazarlo en las pruebas por un modelo de guion:

@@code src/arya_agent/llm.py ChatModel

### Tres decisiones que cambiaron la velocidad

**1. Razonamiento interno apagado.** Nemotron puede "pensar" antes de responder. Con el razonamiento encendido, cada paso del agente tardaba unos 16,7 s; apagado (`enable_thinking=false`), unos 0,75 s. Como una pregunta típica usa dos o tres pasos, apagarlo es la diferencia entre una respuesta en 5 s y una en 45 s. La calidad no bajó de forma apreciable, porque el razonamiento lo estructura el propio ciclo del agente: consultar, observar, volver a consultar. Si hiciera falta, se puede encender solo en las preguntas de diagnóstico con `LLM_THINKING=diagnosis` en el archivo `.env`; el valor por defecto es `off`.

**2. Temperatura baja (0,2).** Para un agente que debe citar datos, la creatividad no ayuda.

**3. Streaming para medir.** Con la respuesta en flujo (streaming) se puede medir el TTFT (tiempo hasta el primer token) y el TPOT (tiempo por token). En la GB10, con ARYA: TTFT de ≈ 0,4 s y TPOT de ≈ 21,6 ms, es decir, unos 46 tokens por segundo.

### El armado de las llamadas a herramientas en streaming

En streaming, los argumentos de una herramienta llegan en pedazos que hay que juntar. Cada pedazo trae el índice de su llamada, y el nombre y los argumentos se van sumando en el casillero de ese índice hasta que termina el flujo:

@@grep src/arya_agent/llm.py "for tc in delta.get("tool_calls") or []:" 7

Al terminar se calculan las dos métricas. El TTFT es el tiempo hasta el primer pedazo con texto o con una herramienta. El TPOT reparte el resto del tiempo entre los tokens generados después del primero:

@@grep src/arya_agent/llm.py "ttft = int(" 2

### Cuándo no usar streaming

Si el paso exige una herramienta, la llamada va en el modo normal, sin streaming. Si el streaming falla por un corte de conexión, un JSON rechazado o una respuesta vacía, la misma petición se repite en el modo normal, que no mide TTFT ni TPOT:

@@code src/arya_agent/llm.py OpenAICompatModel.complete

> [!leccion] Con una herramienta exigida, el servidor entregaba los argumentos vacíos
> ARYA obliga al modelo a usar una herramienta en el primer paso (`tool_choice: "required"`). En streaming, el servidor del modelo devolvía esa llamada en un solo pedazo con los argumentos vacíos (`{"query": ""}`). Como el agente se recuperaba en el paso siguiente, el error pasó desapercibido durante días: solo se notaba como respuestas algo más lentas.
>
> Se descubrió en un ensayo en que fallaba la primera herramienta de cada pregunta, y se confirmó con una consulta directa al servidor. La corrección: las llamadas con herramienta exigida van sin streaming, y los pasos libres, que son los que redactan la respuesta y donde se mide la velocidad, siguen en streaming.

### Reintentos y márgenes

El modo normal reintenta una vez ante un corte de conexión, y una vez si el servidor rechaza el JSON de una herramienta. Un tiempo de espera agotado no se reintenta, para no duplicar la espera:

@@grep src/arya_agent/llm.py "for attempt in (1, 2):" 16

Cuando el paso exige una herramienta, el límite de respuesta sube a 1600 tokens:

@@grep src/arya_agent/llm.py "if tool_choice not in (None, "auto", "none"):" 4

> [!leccion] Una orden de trabajo larga se cortaba
> El límite de respuesta era de 700 tokens. Una orden predictiva, con problema, causa, acción, repuestos y evidencia, lo superaba, el JSON quedaba cortado y el servidor respondía `HTTP 400 "Invalid JSON: EOF while parsing"`. La corrección: 1600 tokens cuando se exige una herramienta, y reconocer ese mensaje para reintentar.
