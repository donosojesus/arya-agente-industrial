# 1 · El problema y los principios

## Lo que ya resuelve el sistema de control

Una planta industrial ya tiene un sistema que la gobierna: el PLC o DCS ejecuta el control, y el SCADA muestra los valores, compara cada señal con su límite y levanta una alarma cuando lo cruza. Eso funciona y no hay que reemplazarlo.

Lo que el sistema de control no hace es lo que viene después de la alarma. Cuando suena "vibración alta", alguien tiene que mirar las tendencias, buscar en el CMMS si pasó antes, abrir el manual del fabricante, preguntarle al técnico con más experiencia, formarse una hipótesis y escribir la orden de trabajo. Es un trabajo de varios pasos, y su resultado depende mucho de quién esté de turno.

La idea de ARYA es exactamente esa: **el SCADA detecta; el agente investiga.** El agente hace en segundos la investigación que hoy hace una persona después de la alarma, y con el historial suficiente puede ir un paso más allá: ver que una tendencia va hacia el límite semanas antes de que suene la alarma.

## Qué es un agente

Un asistente de chat responde con lo que aprendió al entrenarse. No sabe qué está pasando hoy en la planta y puede sonar seguro aunque no tenga el dato.

Un agente es distinto en cuatro cosas:

1. **Consulta sistemas reales**: señales, alarmas, historial, órdenes de trabajo y manuales, mediante herramientas.
2. **Decide qué revisar y en qué orden.** Nadie le da un guion: el modelo elige la siguiente herramienta según lo que encontró.
3. **Cita de dónde sacó cada dato.**
4. **Trabaja con límites fijos**, y las decisiones las toma una persona.

Ese funcionamiento es un ciclo: percibir, razonar, actuar (que aquí significa consultar) y observar el resultado, hasta tener la respuesta. El capítulo 3 lo explica en detalle.

## Los principios que guiaron todo el diseño

Cinco principios explican casi todas las decisiones técnicas de los capítulos siguientes.

| Principio | Qué significa en la práctica |
|---|---|
| **Solo lectura, por construcción** | El agente no tiene ninguna herramienta que escriba en el proceso. No es una regla que el modelo deba respetar: no existe el camino. El gateway solo acepta lecturas y el servidor OPC UA rechaza escrituras |
| **Nunca inventar** | Todo dato que el agente mencione debe venir de una herramienta consultada en esa conversación. El código lo verifica |
| **Decide una persona** | El agente solo crea borradores de órdenes. Aprobarlas exige la credencial de una persona (un token), que el agente no tiene |
| **Todo es visible** | Cada paso queda en una traza: qué herramienta usó, qué fuente, cuánto tardó, cuántos tokens (los trozos de texto que procesa el modelo) usó |
| **Funciona sin Internet** | El modelo corre en la GB10 y todo lo demás en un notebook. Nada sale a la nube |

> [!leccion] Las reglas importantes van en el código
> Un modelo de lenguaje sigue las instrucciones casi siempre, pero no siempre. Por eso cada regla crítica de ARYA tiene una implementación en el código además de la instrucción en el prompt: el agente no puede escribir porque no tiene cómo, no porque se le pidió. A lo largo del libro, cada vez que una regla depende solo del prompt, se dice explícitamente.

Los capítulos 2 a 4 explican, desde la base, qué hay detrás de estos principios: cómo funciona un modelo de lenguaje, cómo se convierte en un agente y qué código lo rodea para que los principios se cumplan.
