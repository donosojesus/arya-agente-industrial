# 19 · El gateway OT y el historian

El gateway es la única puerta entre la planta y la IA. Lee la planta por OPC UA, guarda lo que lee en un historian y ofrece una API HTTP **solo de lectura**. El agente nunca habla con la planta directamente.

## El historian

El historian es una base SQLite en modo WAL que guarda solo muestras realmente recibidas y de buena calidad. No interpola ni rellena: si no hay datos, la API lo dice.

@@code src/arya_ot_gateway/historian.py Historian.record

## Una API pensada para un modelo de lenguaje

Una lección temprana fue que un modelo no debe recibir datos crudos. Mil puntos de una serie de tiempo llenan el contexto y el modelo no los lee bien. Por eso la API entrega resúmenes ya calculados: valor inicial y final, cambio porcentual, tendencia y, sobre todo, **cuándo empezó la desviación**.

@@code src/arya_ot_gateway/analysis.py detect_onset

> [!leccion] La línea base no puede incluir la falla
> La primera versión tomaba como línea base una fracción fija de la ventana. Cuando la falla ya llevaba varios minutos, la línea base incluía parte del desvío, y el agente concluía mal qué señal se había desviado primero. La corrección fue acotar la línea base al comienzo de la ventana, entre 20 y 60 muestras.

Las rutas de la API son todas GET: etiquetas actuales, estado, alarmas activas, historia, comparación de dos señales, eventos de alarma y las cuatro del historial de 6 meses (capítulo 17). Hay una prueba de arquitectura que falla si alguien agrega otro método.

Así se declara la comparación. El decorador fija el método GET, y cada parámetro trae sus límites, para que una llamada del modelo no pueda pedir cualquier cosa:

@@grep src/arya_ot_gateway/app.py "@app.get("/api/v1/assets/{asset}/compare")" 8

Al final, compara cuándo empezó el desvío de cada señal para decir cuál se movió primero y con cuántos segundos de ventaja:

@@grep src/arya_ot_gateway/app.py "da, db = sa["deviation"], sb["deviation"]" 5

## Calidad de los datos

Cada respuesta del gateway trae un bloque de calidad: si la conexión OPC UA está activa y si el último dato está vigente. Si el dato tiene más de unos segundos, la respuesta viene marcada `STALE`, y una de las reglas del agente es advertirlo. Así, si se desconecta la planta, el agente no responde con datos viejos como si fueran actuales.
