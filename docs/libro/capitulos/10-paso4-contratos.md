# 10 · Paso 4 · Herramientas con contrato

Las herramientas son la única forma que tiene el agente de saber algo sobre la planta. Su diseño decide qué puede y qué no puede hacer el agente. En el paso 3, el ejecutor del tutorial confiaba en lo que pedía el modelo: si llegaban argumentos absurdos, la herramienta los usaba igual. Este paso muestra cómo ARYA pone un contrato estricto a cada herramienta y un ejecutor que nunca se cae.

## Un contrato estricto por herramienta

Cada herramienta declara sus argumentos con un modelo de Pydantic, una librería que valida datos. En el tutorial, el esquema JSON se escribía a mano (paso 3); en ARYA sale del modelo de Pydantic, y con el mismo modelo se validan los argumentos que devuelve Nemotron. Una sola definición sirve para las dos cosas, así que no pueden contradecirse.

@@code src/arya_agent/tools.py HistoryArgs

La herramienta de historia acepta de 1 a 6 señales y una ventana de 1 a 240 minutos. Si el modelo pide 99 999 minutos o una señal que no existe, el argumento se rechaza antes de llegar al gateway. El modelo de argumentos del borrador de orden, el más largo, está en el capítulo 15.

## El ejecutor: nunca lanza errores

El ejecutor envuelve cada llamada: valida los argumentos, ejecuta con un tiempo límite de 8 s y devuelve siempre un resultado, con su fuente y un resumen breve para la traza. Si algo falla, el modelo recibe un error claro (`ERROR · Argumentos no válidos: …`) en vez de que el agente se caiga, y puede corregirse en el paso siguiente.

@@code src/arya_agent/tools.py execute

## Un manejador típico

Cada manejador consulta su servicio y devuelve tres cosas: los datos para el modelo, la fuente que se mostrará al operador y un resumen para la traza.

@@code src/arya_agent/tools.py _condition_projection

## Ofrecer solo las herramientas que corresponden

Un modelo pequeño se distrae con herramientas que no necesita. Por eso no todas se ofrecen siempre:

- La herramienta de borradores se ofrece **solo si la pregunta pide una orden** ("genera una orden", "crea un borrador").
- Las cuatro herramientas del historial de 6 meses se ofrecen **solo si la pregunta es de salud, tendencia o planificación**, o si ya se usaron en la conversación.

@@grep src/arya_agent/agent.py "_CONDITION_INTENT = re.compile(" 3

> [!leccion] Ofrecer menos mejoró las respuestas
> Sin esta regla, el modelo creaba borradores de órdenes que nadie había pedido, y en las preguntas de la falla A consultaba el historial de 6 meses sin necesidad. Con la oferta condicional, las preguntas reactivas siguen con el mismo contexto de siempre, y las predictivas reciben las herramientas que necesitan.

## Cómo agregar o cambiar una herramienta

Cada herramienta es un registro con cuatro piezas: nombre, descripción, modelo de argumentos y manejador.

@@code src/arya_agent/tools.py Tool

Para agregar una nueva:

1. **Los argumentos.** Una clase que hereda de `_Args`, que rechaza campos no previstos y quita espacios sobrantes. Con `Field` se fijan límites y descripciones: el modelo los ve en el esquema JSON.
2. **El manejador.** Una función `async` que recibe el contexto y los argumentos ya validados, consulta su servicio y devuelve datos, fuente y resumen. Si algo falla, lanza `ToolError` con un código y un mensaje, y el ejecutor se lo entrega al modelo como error controlado.
3. **El registro.** Una línea `Tool(...)` en la tupla `TOOLS`. La descripción es lo que el modelo lee para decidir cuándo usarla: conviene incluir ejemplos (capítulo 13). `creates_draft=True` marca la herramienta que crea borradores, y hoy solo la tiene `create_work_order_draft`.
4. **La oferta.** Si pertenece al historial de 6 meses, también va en `CONDITION_TOOLS`, y solo se ofrece con preguntas de salud, tendencia o planificación.
5. **El prompt.** Una línea en la guía "Qué herramienta usar" del prompt de sistema (capítulo 11) le dice al modelo en qué preguntas usarla.
6. **Las pruebas.** Dos pruebas de `tests/test_agent.py` cuentan las herramientas (`== 14`) y hay que actualizarlas. Después, una prueba con el modelo de guion y un ensayo con el modelo real (capítulo 21).

`CONDITION_TOOLS` está justo debajo de `TOOLS`:

@@grep src/arya_agent/tools.py "# Solo se ofrecen al modelo" 2

Ninguna herramienta nueva puede escribir en el proceso: la pantalla de estado del agente debe seguir publicando `process_write_tools: []`.
