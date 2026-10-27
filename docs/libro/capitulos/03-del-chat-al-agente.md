# 3 · Del chat al agente

Un chat responde con lo que el modelo aprendió al entrenarse; un agente consulta antes de responder. La diferencia la hacen dos piezas: las **herramientas**, que le permiten pedir datos reales, y un **ciclo** que las usa hasta tener la respuesta.

## Chat contra agente

@@img docs/img/libro/chat-agente.svg Un chat responde de memoria. Un agente pide datos a sistemas reales, a través de herramientas, y responde con ellos y con sus fuentes.

Las dos versiones usan el mismo modelo. Lo que cambia es el programa que lo rodea: en el chat, el programa le pasa la pregunta y devuelve la respuesta; en el agente, el programa le ofrece herramientas, ejecuta las que pide y le devuelve los resultados.

## Qué es una herramienta

Una herramienta es una función del programa que el modelo puede pedir que se ejecute. Para que el modelo sepa que existe, el programa se la describe en cada llamada: un nombre, para qué sirve y qué argumentos acepta, en un formato llamado JSON Schema. Así describe el tutorial su primera herramienta:

@@grep tutorial/paso2_herramienta.py "HERRAMIENTAS = [{" 8

El punto más importante de todo el libro está aquí: **el modelo nunca ejecuta nada**. Lo único que puede hacer es escribir un pedido con forma fija: "quiero la herramienta `get_active_alarms`, con estos argumentos". El programa lee ese pedido y decide si lo ejecuta. Por eso un agente puede ser seguro aunque el modelo se equivoque: el modelo solo puede pedir lo que el programa le ofrece, y el programa puede negarse.

## Una llamada a herramienta, de ida y vuelta

@@img docs/img/libro/llamada-herramienta.svg Una pregunta que necesita un dato: el programa llama dos veces al modelo y una vez al gateway.

1. El programa envía al modelo la conversación y la lista de herramientas disponibles.
2. El modelo no responde con texto: responde con un pedido de herramienta (`tool_calls`).
3. El programa ejecuta la herramienta, en este caso una lectura al gateway de la planta.
4. El gateway devuelve los datos en JSON.
5. El programa vuelve a llamar al modelo, ahora con el resultado agregado a la conversación.
6. Con el dato a la vista, el modelo redacta la respuesta.

El paso 2 del tutorial (capítulo 8) programa exactamente esta secuencia.

## El ciclo

Una pregunta difícil puede necesitar varias vueltas: el modelo mira las alarmas, después pide la historia de una señal, después compara dos señales. Esa repetición es el ciclo del agente.

@@img docs/img/libro/ciclo-agente.svg El ciclo del agente: percibir, razonar, actuar y observar, hasta que el modelo responde con texto o se alcanza un límite.

| Etapa | Qué pasa en ARYA | Quién lo hace |
|---|---|---|
| Percibir | Se arma la ventana de contexto con la pregunta y los datos ya consultados | El programa |
| Razonar | El modelo decide si pide una herramienta o si ya puede responder | El modelo |
| Actuar | Se ejecuta la herramienta pedida | El programa |
| Observar | El resultado entra a la conversación para la siguiente vuelta | El programa |

Cada vuelta del ciclo es una llamada al modelo. Sin un tope, un modelo confundido podría pedir herramientas para siempre: en un ensayo temprano de ARYA, frente a pedidos de operar la planta, generó listas de cientos de llamadas. Por eso el ciclo tiene límites (capítulo 9).

## Qué decide el modelo y qué decide el programa

| Lo decide el modelo | Lo decide el programa |
|---|---|
| Qué herramienta pedir y con qué argumentos | Qué herramientas ofrecer en cada momento |
| Cuándo tiene datos suficientes para responder | Si ejecuta o no lo que el modelo pidió |
| Cómo redactar la respuesta | Cuántas vueltas puede dar el ciclo y cuánto puede durar |
| | Qué entra a la ventana de contexto y qué se recorta |
| | Si la respuesta sale tal cual, se corrige o se marca como no verificada |

La columna de la derecha es el **harness**, el tema del capítulo siguiente. Es la parte que se programa, y la que hace que el agente sea confiable.
