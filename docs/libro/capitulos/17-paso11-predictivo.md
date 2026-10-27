# 17 · Paso 11 · De reactivo a predictivo

Los capítulos anteriores describen un agente reactivo: suena una alarma y ARYA investiga. Este capítulo describe el paso siguiente: **ver la falla venir semanas antes**, cuando el SCADA todavía no muestra nada. Se lee sin saber programar: el código está reunido al final, para el equipo técnico.

## La historia que cuenta el escenario C

> [!nota] El escenario C en un párrafo
> La bomba funciona y no hay ninguna alarma. Pero en el historial simulado de 6 meses, la vibración p95 llegó a 3,1 mm/s, un 61 % sobre la referencia de 1,9 mm/s, y el motor está 2,4 °C más caliente con la misma carga. ARYA proyecta que el límite de alarma se alcanzaría en 2,4 a 6,9 semanas, ve que la próxima parada programada llega antes y recomienda intervenir ahí, con los repuestos. Deja la orden predictiva en borrador.

## La ficha técnica

El análisis necesita referencias: ¿cuánto debería vibrar esta bomba? ¿Qué presión debería dar a este caudal? La ficha técnica FT-P101-001 tiene el formato de un catálogo de fabricante, con valores coherentes con la planta: una curva de prestaciones propia, el motor, los límites de uso, las zonas de vibración según ISO 10816-3 (A < 2,3; B hasta 4,5; C hasta 7,1; D sobre 7,1 mm/s), el valor de referencia de 1,9 mm/s y la regla del 25 %. La curva también está en el código, para comparar la presión medida con la esperada.

## Seis meses de historial simulado

El generador reproduce la operación de la planta: la carga diaria, los sábados con menos producción, las paradas de domingo, las paradas trimestrales, la temperatura ambiente según la estación y ruido de los sensores. Incluye también **los dos incidentes que ya estaban en el CMMS** (mayo y julio), para que el historial y las órdenes calcen.

## La arquitectura medallón

El historial se organiza en tres capas, como en una plataforma de datos industrial:

| Capa | Qué contiene | Para qué |
|---|---|---|
| **Bronce** | Una muestra cada 10 min, tal como llega: con huecos de comunicación, paradas, arranques y picos de sensor | Auditar |
| **Plata** | Solo la bomba en marcha, sin transitorios ni picos, **normalizada a 62 m³/h y 20 °C**, con el déficit de presión frente a la curva | Comparar peras con peras |
| **Oro** | Indicadores diarios: vibración p95, temperatura a igual carga, corriente, déficit de presión, horas, arranques | Tendencia y proyección |

> [!nota] Por qué normalizar por carga
> La vibración y la temperatura cambian con el caudal y el ambiente. Sin normalizar, un mes de invierno con menos carga podría parecer una "mejora", y un día caluroso, una "degradación". La capa plata lleva todo a las mismas condiciones antes de comparar.

## La proyección la calcula una herramienta, no el modelo

Un modelo de lenguaje no debe hacer cálculos: puede equivocarse y dar números que suenan creíbles. La proyección la calcula el gateway, y entrega **un rango** entre tres ajustes: una recta sobre 6 semanas (la más lenta si el desgaste se acelera), una recta sobre 2 semanas y una curva exponencial del exceso sobre la referencia (la más rápida).

> [!leccion] Un rango demasiado estrecho es una mentira
> La primera versión usaba una sola recta con su intervalo estadístico, y daba "9,0 a 9,4 semanas": una precisión que ningún ingeniero de confiabilidad creería, porque una recta no capta un desgaste que se acelera. El rango entre tres ajustes es más ancho y más honesto. Además, con el historial sano, la primera versión proyectaba un cruce para el año 2047. Ahora dice "sin tendencia relevante".

## Diagnóstico diferencial

La comparación de periodos incluye una conclusión hidráulica: si la presión sigue en su curva, la parte hidráulica (el rodete) está sana y el problema es mecánico. Esa es una forma de razonar de un ingeniero, y ARYA la usa.

## El calendario de paradas y la orden predictiva

El CMMS tiene un calendario de paradas calculado desde la fecha de hoy, para que la historia funcione cualquier día: una parada parcial en unas 2 semanas y la trimestral en unas 7. La recomendación de ARYA es intervenir en la parada que llega antes del inicio del rango. La orden sale con el tipo `PREDICTIVE`, la fecha planificada y los repuestos de la ficha técnica.

## El gateway sigue siendo de solo lectura

El escenario C se activa con un botón en la pantalla, que habla con la planta. Para que el gateway sepa qué historial mostrar, **la planta publica por OPC UA una variable más**, `RUN.HISTORY_PROFILE`, con un valor opaco ("H1" o "H2"). El gateway la lee como cualquier otra señal y elige el historial. Nadie escribe en el gateway, y el valor no revela ninguna causa. La primera versión resolvía esto con un atajo que rompía la regla de solo lectura; el capítulo 21 cuenta cómo lo atraparon las pruebas.

## El gráfico de evidencia

Cuando una respuesta usa el historial de 6 meses, la pantalla dibuja debajo un gráfico: la vibración semanal, las líneas de referencia, seguimiento y límite, el cono de la proyección y las paradas programadas.

@@img docs/img/predictivo-evidencia.png El escenario C en la pantalla: sin alarmas en la planta, y el gráfico de evidencia bajo la respuesta de ARYA.

## Resultado con Nemotron

En cinco rondas de 4 preguntas, ARYA dio siempre el rango correcto y recomendó la parada que llega antes del riesgo. En las rondas completas, la orden salió como `PREDICTIVE`, con fecha y repuestos.

## Para el equipo técnico: el código

### La curva de la ficha

@@code src/arya_ot_gateway/condition.py expected_pressure

### Los incidentes del historial bronce

El generador usa la misma semilla para las dos variantes del historial, sana y con desgaste: solo cambia el desgaste de las últimas 8 semanas. Los incidentes de mayo y julio coinciden con sus órdenes en el CMMS:

@@grep src/arya_ot_gateway/condition.py "# Incidentes registrados en el CMMS" 4

### La capa plata

Descarta huecos, paradas, arranques (los 30 min después de una parada) y picos de vibración. Lleva la temperatura y la corriente a 62 m³/h (la temperatura, también a 20 °C) y calcula el déficit de presión frente a la curva:

@@code src/arya_ot_gateway/condition.py build_silver

### La proyección

Primero exige una tendencia relevante: que la recta de 6 semanas suba y que la de 2 semanas suba al menos un 3 % de la distancia al límite por semana. Después calcula los ajustes y toma el más rápido, el más lento y la mediana:

@@grep src/arya_ot_gateway/condition.py "# Tendencia relevante" 15

### La conclusión hidráulica

Con un déficit de presión menor a 2 % frente a la curva, la parte hidráulica se declara sana:

@@grep src/arya_ot_gateway/condition.py "deficit = out["pressure_deficit_pct"]["recent"]" 3

### El perfil de historial en el gateway

El gateway lee el perfil que publica la planta cada vez que entrega la capa oro:

@@grep src/arya_ot_gateway/app.py "    async def gold()" 9
