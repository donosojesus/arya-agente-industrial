# 22 · Lo que salió mal y cómo se corrigió

Este capítulo reúne los errores reales encontrados al construir y probar ARYA. Casi ninguno se habría descubierto sin probar con el modelo real y en las condiciones reales de uso.

| Error | Cómo se manifestaba | Corrección |
|---|---|---|
| Datos inventados | Órdenes, fechas y recuerdos que no existían | Consulta obligatoria en el primer paso; verificación de lo citado con un reintento |
| Borradores no pedidos | El modelo creaba órdenes por iniciativa propia | La herramienta solo se ofrece si se pide una orden |
| Listas infinitas de herramientas | Ante pedidos de operar, cientos de llamadas | Las negativas se responden sin herramientas; límites por pregunta |
| Diagnóstico B confundido con A | Con un incidente de rodamiento en memoria, decía rodamiento | Método síntoma por síntoma y las 5 señales por defecto |
| "Se desvió primero" al revés | La línea base incluía la falla | Línea base acotada al comienzo de la ventana |
| Historia sin datos | El modelo recordaba valores que ya no tenía | La historia guarda los resultados reales de herramientas |
| Argumentos vacíos en streaming | La primera herramienta de cada pregunta fallaba | Herramienta exigida sin streaming |
| Orden larga cortada | `HTTP 400 Invalid JSON` | Más tokens para herramientas exigidas y reintento |
| Falsa negativa | "para la P-101" se leía como "parar" | El verbo debe abrir la frase |
| Negativa que suponía una alarma | "Revisaré las causas de la alarma" con la planta sana | El código entrega el estado real de alarmas |
| Fecha inventada que pasaba la verificación | Se verificaba solo el mes | Con día, se verifica el día exacto |
| Búsqueda con una palabra | La ficha técnica no aparecía | Títulos de sección precisos y ejemplos de consulta |
| Rango de proyección falso | "9,0 a 9,4 semanas"; o un cruce en 2047 con el historial sano | Rango entre tres ajustes; umbral de tendencia relevante |
| Gateway con escritura | Un atajo agregó un POST con token | Rechazado por las pruebas de arquitectura; la planta publica el perfil por OPC UA |
| Aviso que no cambiaba la pantalla | Ciclo infinito en modo REPOSO | Corrección y prueba en el estado real de uso |
| Causa revelada en una página | Un texto mencionaba la causa de la falla A | La prueba de "no revelar la causa" lo atrapó |

## Los patrones detrás de los errores

1. **El modelo llena los vacíos.** Cuando le falta un dato, lo supone. La solución casi siempre fue darle el dato real (el estado de alarmas, la conclusión hidráulica, una frase de resumen), no prohibirle suponer.
2. **Los modelos pequeños siguen ejemplos mejor que reglas abstractas.** Una descripción de herramienta con ejemplos de consultas funcionó mejor que la instrucción de "buscar con varias palabras".
3. **Los errores silenciosos son los peores.** Los argumentos vacíos no rompían nada: solo hacían al agente más lento y a veces peor. Por eso la traza y los ensayos que marcan las herramientas fallidas son esenciales.
4. **Las reglas de diseño deben ser pruebas.** Si una regla importante solo está en un documento, el primer atajo la rompe.
5. **Probar en el estado real de uso.** El modo REPOSO, la falla con la planta recién reiniciada, la ventana angosta del presentador: varios errores solo aparecían ahí.
