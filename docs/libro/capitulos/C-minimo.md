# C · Lo mínimo de Python, HTTP y JSON

Este apéndice reúne lo que hace falta para leer los programas del tutorial. No es un curso de Python: explica solo las piezas que aparecen en los pasos 0 a 3, con ejemplos tomados de esos mismos programas.

## JSON

JSON es un formato de texto para datos con estructura. Tiene objetos (pares nombre-valor, entre llaves), listas (entre corchetes), textos (entre comillas), números, `true`, `false` y `null`. Así responde el gateway cuando se le piden las alarmas, abreviado:

```json
{"alarm_level": "ALARM", "active_alarms": [{"code": "P101.VIBRATION.HI", "current_value": 8.489, "unit": "mm/s", "limit": 4.5}]}
```

En Python, un objeto JSON es un diccionario (`dict`) y una lista JSON es una lista (`list`). Dos funciones hacen la traducción: `json.loads` convierte texto en datos de Python, y `json.dumps` hace lo contrario. El paso 3 usa la primera para leer los argumentos que pide el modelo:

@@grep tutorial/paso3_ciclo.py "argumentos = json.loads(" 1

Y el paso 2 usa la segunda para convertir un resultado en el texto que entra a la conversación:

@@grep tutorial/paso2_herramienta.py "texto = json.dumps(resultado, ensure_ascii=False)" 1

## HTTP

HTTP es la forma en que los servicios de ARYA se hablan. Un programa envía una **petición** y el servicio devuelve una **respuesta**. La petición tiene:

- **Un método.** `GET` para leer, `POST` para enviar algo.
- **Una dirección.** Por ejemplo `http://127.0.0.1:8081/api/v1/assets/P-101/alarms`: la máquina (`127.0.0.1` es el mismo equipo), el puerto (`8081`, el gateway) y la ruta.
- **Cabeceras**, como `Authorization` cuando el servicio exige una credencial.
- **Un cuerpo**, en las peticiones `POST`: los datos enviados, en JSON.

La respuesta trae un código de estado y, casi siempre, un cuerpo en JSON:

| Código | Significa | Dónde aparece en ARYA |
|---|---|---|
| 200 | Todo bien | Cualquier lectura que funcionó |
| 201 | Se creó algo | El CMMS al crear un borrador |
| 401 | Falta la credencial, o no es la correcta | El CMMS cuando el agente intenta aprobar |
| 404 | No existe | Una orden con un identificador equivocado |
| 409 | No se puede en este estado | Decidir sobre una orden que ya no es borrador |
| 422 | Los datos enviados no son válidos | Un parámetro fuera de rango en el gateway |
| 503 | El servicio no está listo | El gateway sin datos frescos de la planta |

En el tutorial, las peticiones se hacen con la librería `httpx`. Así lee las alarmas el paso 2:

@@grep tutorial/paso2_herramienta.py "    respuesta = httpx.get(" 3

`raise_for_status()` convierte un código de error en una excepción, para no seguir trabajando con una respuesta fallida.

## Lo que usa el tutorial de Python

| Pieza | Ejemplo | Para qué |
|---|---|---|
| Variables de entorno | `os.environ.get("GATEWAY_URL", "http://127.0.0.1:8081")` | Leer la configuración sin escribirla en el código. Si la variable no existe, se usa el valor por defecto |
| Diccionarios y listas | `{"role": "user", "content": pregunta}` | La conversación es una lista de diccionarios |
| Textos con valores (f-strings) | `f"{GATEWAY}/api/v1/assets/P-101/alarms"` | Armar un texto con valores adentro |
| `try` y `except` | `revisar()` en el paso 0, `ejecutar()` en el paso 3 | Atrapar un error y convertirlo en información, en vez de que el programa se detenga |
| `if __name__ == "__main__":` | Al final de cada paso | Lo que corre al ejecutar el archivo, y no al importarlo. Las pruebas importan los pasos sin ejecutarlos |
| `sys.argv` | `python tutorial/paso1_hablar.py "otra pregunta"` | Leer lo que se escribe después del nombre del programa |

## Programación asíncrona, para leer ARYA

Los programas del tutorial esperan sin hacer nada mientras el modelo o el gateway responden. ARYA no puede: mientras espera, tiene que seguir publicando la traza, atendiendo la pantalla y vigilando las alarmas. Por eso usa programación asíncrona (`asyncio`). Las funciones se declaran con `async def` y cada espera se marca con `await`; mientras una función espera, el programa atiende otras.

La lógica es la misma que en el tutorial; cambia la forma de esperar. Esta es la herramienta de alarmas de ARYA, la misma del paso 2:

@@grep src/arya_agent/tools.py "async def _active_alarms" 4
