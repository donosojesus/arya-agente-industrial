# 9 · Paso 3 · El ciclo y sus límites

En el paso 2 había exactamente dos llamadas al modelo: una para que pidiera la herramienta y otra para que respondiera. Con varias herramientas eso ya no alcanza: el modelo puede mirar las alarmas, después pedir la historia de una señal y recién entonces responder. No se sabe de antemano cuántas vueltas va a necesitar. Para eso está el ciclo.

## El ciclo, dibujado

@@img docs/img/libro/ciclo-limites.svg El ciclo del agente con sus límites. Termina de dos formas: cuando el modelo responde con texto, o cuando se acaban las llamadas permitidas.

## El código

El programa de este paso ofrece tres herramientas: los valores actuales, las alarmas activas y la historia de las señales. La tercera tiene argumentos: qué señales y cuántos minutos hacia atrás. Su descripción usa `enum` para que el modelo solo pueda pedir señales que existen, y `minimum` y `maximum` para acotar la ventana.

El ciclo completo cabe en una función:

@@code tutorial/paso3_ciclo.py ciclo

Línea por línea, lo importante:

1. **`for vuelta in range(1, MAX_VUELTAS + 1)`**: el ciclo tiene un número máximo de vueltas. Cada vuelta es una llamada al modelo.
2. **`ofrecer = HERRAMIENTAS if usadas < MAX_HERRAMIENTAS else None`**: si ya se usaron todas las herramientas permitidas, no se ofrecen más, y al modelo solo le queda responder.
3. **`if not llamadas`**: si el modelo respondió con texto, la pregunta terminó.
4. **El pedido y cada resultado se agregan a la conversación**, como en el paso 2, y el ciclo vuelve a empezar.
5. **`[:MAX_CARACTERES]`**: cada resultado se recorta antes de entrar al contexto, porque la ventana es finita (capítulo 2).
6. **Si se acaban las vueltas**, el ciclo responde con un mensaje fijo. No inventa una respuesta.

Las herramientas se ejecutan a través de una sola función. Si el modelo pide una herramienta que no existe o manda argumentos que no se pueden leer, el error vuelve como dato y el modelo puede corregirse en la vuelta siguiente:

@@code tutorial/paso3_ciclo.py ejecutar

## Ejecutarlo

Con la falla A activa del paso anterior:

```bash
python tutorial/paso3_ciclo.py
```

Qué deberías ver con el servidor de guion:

```text
vuelta 1 · el modelo pide get_active_alarms({})
           el programa devuelve 1043 caracteres
vuelta 2 · el modelo pide get_historian_data({"signals": ["vibration", "motor_temp"], "minutes": 10})
           el programa devuelve 951 caracteres
vuelta 3 · el modelo responde con texto
ARYA: [guion] Consulté get_active_alarms, get_historian_data. Un modelo real redactaría aquí la respuesta con esos datos.
mensajes en la conversación: 7
```

Tres llamadas al modelo: dos para pedir herramientas y una para responder. Con Nemotron, el número de vueltas y las herramientas elegidas dependen de la pregunta y de lo que el modelo encuentre.

## La conversación, mensaje por mensaje

Al terminar, la conversación tiene siete mensajes. Así se ven, abreviados, en una ejecución con la falla A:

@@img docs/img/libro/conversacion.svg La conversación del paso 3. Cada llamada al modelo envía todos los mensajes anteriores y recibe uno nuevo.

Esta lista es todo lo que el modelo sabe en cada vuelta. Las instrucciones de sistema y la pregunta viajan las tres veces; los resultados se van sumando.

## Por qué hacen falta los límites

> [!leccion] Sin límites, el ciclo puede no terminar
> En un ensayo temprano de ARYA, frente a pedidos de operar la planta, el modelo generó listas de cientos de llamadas a herramientas. Desde entonces el ciclo tiene topes: llamadas al modelo, herramientas y tiempo. El paso 3 del tutorial usa los mismos dos primeros topes que ARYA, 6 llamadas y 8 herramientas por pregunta.

Una prueba automática del tutorial reemplaza al modelo por uno que nunca deja de pedir herramientas, y comprueba que el ciclo se detiene a las 6 llamadas, ejecuta solo 8 herramientas y deja de ofrecerlas cuando se acaban.

## Lo que le falta a este ciclo

El ciclo del tutorial funciona, pero confía demasiado. Los pasos siguientes agregan lo que ARYA necesitó:

| Le falta | Por qué | Paso |
|---|---|---|
| Validar los argumentos antes de ejecutar | Un modelo puede pedir 99 999 minutos de historia | 4 |
| Reglas y una guía de qué herramienta usar | Sin guía, el modelo elige mal o no consulta | 5 |
| Reglas que el código haga cumplir | Exigir datos antes de responder, negarse a operar la planta, verificar lo citado | 6 |
| Memoria y documentos | Recordar incidentes y citar manuales | 7 |
| Una traza | Saber qué pasó en cada vuelta | 8 |

## En ARYA: el ciclo real

El ciclo de ARYA hace lo mismo que el del tutorial, con tres diferencias: atiende una pregunta a la vez, con un tiempo máximo por pregunta; decide en cada vuelta si alguna herramienta es obligatoria; y revisa cada pedido antes de ejecutarlo.

### Una pregunta, de punta a punta

Cada pregunta entra por un único punto, que la serializa (una a la vez), le pone un tiempo máximo de 120 s y publica en la traza la pregunta y la respuesta con todos sus tiempos y tokens:

@@code src/arya_agent/agent.py Agent.handle

### Los límites

@@grep src/arya_agent/config.py "tool_timeout_s: float" 4

| Límite | Valor | Qué pasa si se alcanza |
|---|---|---|
| Llamadas al modelo por pregunta | 6 | El ciclo se detiene y lo dice |
| Herramientas por pregunta | 8 | Ya no se ofrecen herramientas; el modelo debe responder |
| Tiempo por herramienta | 8 s | Esa herramienta devuelve un error de tiempo |
| Tiempo por pregunta | 120 s | La pregunta termina con un mensaje claro |

Con estos límites, el agente nunca queda girando.

### El corazón del ciclo

El método `_run` es el ciclo propiamente tal. Antes del primer paso, decide qué herramientas ofrecer (capítulo 10):

@@grep src/arya_agent/agent.py "        wants_draft = bool(_DRAFT_INTENT" 6

Después, en cada paso:

1. Decide si alguna herramienta es obligatoria: en el primer paso, consultar datos; si se pidió una orden y el modelo iba a responder sin crearla, la de borradores. En un pedido de operar no ofrece ninguna (capítulo 12).
2. Llama al modelo.
3. Si el modelo pidió herramientas, las ejecuta y agrega sus resultados al contexto.
4. Si respondió con texto, lo verifica y lo limpia (capítulo 12), y termina.

Los pasos 1 y 2:

@@grep src/arya_agent/agent.py "        for step in range(1, s.max_steps + 1):" 16

El paso 3 revisa cada llamada antes de ejecutarla. Un borrador que nadie pidió, un segundo borrador en la misma pregunta o una llamada por sobre el límite no se ejecutan: el modelo recibe un error claro y sigue.

@@grep src/arya_agent/agent.py "            for call in turn.tool_calls:" 14

