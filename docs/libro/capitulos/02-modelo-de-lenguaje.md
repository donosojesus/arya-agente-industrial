# 2 · Qué es un modelo de lenguaje

Un modelo de lenguaje es un programa que, dado un texto, calcula cuál es la continuación más probable. Todo lo que hace (responder, resumir, pedir una herramienta) sale de esa sola operación, repetida muchas veces. Entender esto explica casi todas las decisiones de diseño de ARYA.

## Un texto entra, un trozo sale

El modelo no lee letras ni palabras: lee **tokens**, trozos de texto que pueden ser una palabra, una parte de palabra o un signo. Con todos los tokens a la vista, calcula qué token puede venir después, elige uno, lo agrega al final y repite. Una respuesta de doscientos tokens son doscientas vueltas de ese ciclo.

@@img docs/img/libro/tokens.svg Un modelo de lenguaje genera texto de a un token: lee la secuencia completa, calcula los candidatos para el siguiente, elige uno y lo agrega al final.

De aquí salen tres cosas que se usan en todo el libro:

- **La velocidad se mide en tokens.** El tiempo hasta el primer token (TTFT) y el tiempo por token (TPOT) son las dos medidas de velocidad del modelo (capítulo 7).
- **La respuesta puede mostrarse mientras se genera.** Eso se llama *streaming*.
- **Los límites también se cuentan en tokens**: cuánto texto puede leer el modelo de una vez y cuánto puede escribir.

## La ventana de contexto

El modelo no tiene memoria entre una llamada y la siguiente. En cada llamada recibe todo lo que necesita saber, en un solo bloque de texto: la **ventana de contexto**. En ARYA, Nemotron acepta hasta 32 000 tokens por llamada.

@@img docs/img/libro/contexto.svg Lo que ocupa la ventana de contexto en cada llamada de ARYA. Las cifras de caracteres salen del código; el tope de 32 000 tokens, de la configuración del modelo.

Esto tiene una consecuencia directa para quien construye un agente: **la memoria del agente es lo que el programa decide poner en la ventana**. Si un dato no está ahí, el modelo no lo sabe. Por eso ARYA guarda en el historial los resultados reales de las herramientas y no solo las respuestas (capítulo 11), y por eso los resultados se recortan: el espacio es finito.

## La temperatura: cuánto se arriesga al elegir

Cuando el modelo calcula los candidatos para el siguiente token, no elige siempre el más probable. La **temperatura** controla cuánto se arriesga. Se entiende mejor con un ejemplo, en tres pasos.

**1. Puntajes.** Para cada candidato, el modelo calcula un puntaje: más alto, más plausible. Supongamos que después de «La bomba P-101 está…» hay cuatro candidatos, con puntajes 3,0; 2,0; 1,0 y 0,5. Los números son ilustrativos, elegidos para el cálculo.

**2. Dividir por la temperatura.** Cada puntaje se divide por la temperatura T. Con T = 1 quedan igual; con T = 0,2 se multiplican por cinco: 15; 10; 5 y 2,5.

**3. Convertir en probabilidades.** Se calcula e (≈ 2,718) elevado a cada resultado, y cada uno se divide por la suma de todos, para que sumen 100 %:

probabilidad de un candidato = e^(puntaje ÷ T) ÷ suma de e^(puntaje ÷ T) de todos los candidatos

| Candidato | Puntaje | e^(puntaje) con T = 1 | Probabilidad con T = 1 | Probabilidad con T = 0,2 |
|---|---|---|---|---|
| en marcha | 3,0 | 20,1 | 63,1 % | 99,3 % |
| detenida | 2,0 | 7,4 | 23,2 % | 0,7 % |
| vibrando | 1,0 | 2,7 | 8,5 % | menos de 0,01 % |
| sana | 0,5 | 1,6 | 5,2 % | menos de 0,01 % |
| **Suma** | | **31,8** | **100 %** | **100 %** |

@@img docs/img/libro/temperatura.svg El mismo ejemplo, dibujado: con temperatura baja, el candidato con mejor puntaje se queda con casi toda la probabilidad.

Dividir por un número chico agranda las diferencias entre puntajes, y la exponencial las agranda todavía más. Con T = 0,2, el mejor candidato pasa de 63 % a más de 99 %. ARYA usa temperatura 0,2: para un agente que debe citar datos, la variación no ayuda.

## Por qué un modelo inventa

El modelo siempre produce la continuación más plausible. Si el dato que se le pide no está en la ventana de contexto, la continuación más plausible es un dato que *suena* correcto, aunque no exista. No es un error ocasional: es lo que el modelo hace por diseño.

En la primera prueba de ARYA con Nemotron, antes de agregar los controles, el agente respondió siete preguntas y **inventó datos en cinco** en las que no consultó herramientas: una orden de trabajo inexistente, fechas, incidentes en una memoria que estaba vacía y una alarma de presión que no existía.

La solución no fue pedirle que no inventara. Fue darle los datos reales en la ventana (capítulo 3) y verificar en el código lo que cita (capítulo 12).

## Dónde corre el modelo

En ARYA el modelo es `nvidia/nemotron-3-nano`, servido como **NIM** en la Dell Pro Max GB10. Un NIM es un servidor: recibe la conversación por HTTP y devuelve la respuesta. Usa la misma forma de API que los servicios de OpenAI (`/v1/chat/completions`), así que el código del agente no depende de la marca del modelo. Cambiar de modelo es cambiar una dirección y un nombre en la configuración.

Nemotron puede además "razonar" en privado antes de responder. En ARYA ese razonamiento está apagado: con él encendido, cada paso del agente tardaba unos 16,7 s; sin él, unos 0,75 s (capítulo 7).

> [!nota] Lo que hay que llevarse
> El modelo genera texto de a un token, a partir de lo que está en su ventana de contexto y de nada más. Todo el trabajo de construir un agente consiste en decidir qué entra en esa ventana, qué se le permite pedir al modelo y qué se hace con lo que responde.
