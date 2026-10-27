# Parte II · Construir el agente paso a paso

En esta parte se construye el agente desde cero, una pieza por vez. Los pasos 0 a 3 usan una versión mínima, la carpeta `tutorial/`: programas cortos que se ejecutan contra la planta real y que crecen de a una pieza. Desde el paso 4, cada capítulo muestra cómo resuelve ARYA esa pieza en su código (`src/arya_agent/`).

| Paso | Capítulo | Qué agrega |
|---|---|---|
| 0 | 6 | El entorno: la planta, el gateway y un modelo que responda |
| 1 | 7 | Hablar con el modelo |
| 2 | 8 | La primera herramienta |
| 3 | 9 | El ciclo y sus límites |
| 4 | 10 | Herramientas con contrato y un ejecutor que no se cae |
| 5 | 11 | El prompt de sistema y el contexto |
| 6 | 12 | Guardrails en el código |
| 7 | 13 | Memoria y RAG |
| 8 | 14 | La traza |
| 9 | 15 | La orden en borrador y la aprobación humana |
| 10 | 16 | El aviso automático |
| 11 | 17 | De reactivo a predictivo |

Los pasos del tutorial tienen la misma forma: qué problema resuelven, el código, cómo ejecutarlo, qué deberías ver y la trampa real que apareció en ese punto al construir ARYA.

> [!nota] Sin GB10
> Todos los pasos del tutorial funcionan con el servidor de guion (`tutorial/modelo_guion.py`): un programa que imita la API del modelo con reglas fijas y marca sus textos con [guion]. Sirve para aprender la mecánica sin hardware. Para ver razonar a un modelo de verdad se usa Nemotron en la GB10, o cualquier servidor compatible con la API de OpenAI que soporte llamadas a herramientas.
