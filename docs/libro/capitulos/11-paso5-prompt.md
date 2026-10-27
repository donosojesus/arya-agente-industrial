# 11 · Paso 5 · El prompt de sistema y el contexto

El prompt de sistema es el primer mensaje de cada llamada: le dice al modelo quién es, qué reglas sigue y qué herramienta usar para cada tipo de pregunta. Es la pieza más fácil de cambiar del harness, y también la más fácil de romper. Este paso muestra qué contiene el de ARYA y qué más entra a la ventana de contexto en cada llamada.

## El contexto que ve el modelo

En cada llamada, el modelo recibe:

1. **Las instrucciones de sistema**: el rol, las 4 reglas fijas, una guía de qué herramienta usar para cada tipo de pregunta y el método de diagnóstico.
2. **Las últimas 3 preguntas de la conversación, con los resultados reales de sus herramientas.**
3. **La pregunta actual.**
4. **Los resultados de las herramientas de esta pregunta**, a medida que llegan, cada uno recortado a 6 000 caracteres.

El comienzo del prompt de sistema, hasta la regla de diagnóstico:

@@grep src/arya_agent/agent.py "SYSTEM_PROMPT = " 16

> [!leccion] La historia debe guardar los datos, no solo las respuestas
> Al principio, la historia guardaba solo las preguntas y las respuestas. En la pregunta siguiente, el modelo "recordaba" valores que ya no tenía delante y a veces los inventaba. Guardar los resultados reales de las herramientas, recortados a 1500 caracteres, eliminó esas invenciones.

## El método de diagnóstico

La regla de diagnóstico, la última línea del fragmento anterior, es la más trabajada del prompt. Le pide al modelo revisar primero cómo cambiaron las cinco señales y luego compararlas, una por una, con la guía de diagnóstico del manual MAN-P101-001. Debe fijarse sobre todo en si la corriente subió o bajó y en si la temperatura cambió, y presentar la causa como "más probable", no como certeza.

El prompt es el primer lugar donde mirar para cambiar el comportamiento del agente. Cada cambio conviene ensayarlo con el modelo real (capítulo 21), porque las pruebas automáticas usan el modelo de guion y no ven cómo responde Nemotron.

> [!leccion] La falla B se diagnosticaba como la A
> Con un incidente de rodamiento en la memoria, el modelo diagnosticaba la falla B (filtro obstruido) también como rodamiento, e incluso inventó una fecha. La corrección fue doble: un método síntoma por síntoma en el prompt, y que la herramienta de historia devuelva por defecto las cinco señales clave. Después del ajuste: 3 de 3 diagnósticos correctos.
