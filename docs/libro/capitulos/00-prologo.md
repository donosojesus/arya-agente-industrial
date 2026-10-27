# Prólogo

Este libro enseña a construir un agente de inteligencia artificial desde cero, con un caso real: ARYA, un agente que investiga fallas en una bomba industrial, recomienda qué hacer, cita de dónde sacó cada dato, anticipa desgastes con meses de historial y deja la orden de trabajo lista para que una persona la apruebe. ARYA nunca opera la planta.

El agente corre sobre una planta simulada con comunicación industrial real (OPC UA) y razona con NVIDIA Nemotron, un modelo de lenguaje que corre en una Dell Pro Max GB10, sin nube y sin Internet.

## Para quién es

El libro tiene tres lectores, y cada uno puede recorrerlo de una forma distinta:

| Lector | Qué leer | Para qué |
|---|---|---|
| Clientes y líderes de mantención u operaciones | El resumen ejecutivo, la Parte I y los capítulos 17, 22 y 23 | Entender qué hace un agente, qué no hace, cómo se protege la planta y qué haría falta para un piloto |
| Quien quiere construir un agente | Todo, en orden, ejecutando cada paso | Construir el agente, su harness y el ecosistema que lo rodea, y poder modificarlos |
| Consulta rápida | El índice y los apéndices | Encontrar dónde está cada cosa, qué comando la ejecuta y qué significa cada término |

Para seguir la Parte II basta con saber leer y ejecutar un programa corto de Python. Lo demás (HTTP, JSON, modelos de lenguaje, OPC UA) se explica en el camino, y el Apéndice C reúne lo mínimo.

## Cómo está organizado

| Parte | Qué contiene |
|---|---|
| I · Fundamentos | Qué es un modelo de lenguaje, qué lo convierte en agente, qué es el harness y cómo es el mundo industrial donde trabaja. Sin código |
| II · Construir el agente paso a paso | Doce pasos. Los primeros usan una versión mínima que se ejecuta y crece de a una pieza; los siguientes muestran cómo lo resuelve ARYA en su código real |
| III · Construir el ecosistema | La planta simulada, OPC UA, el gateway y el despliegue sin Internet |
| IV · Probar y aprender | Cómo se prueba, lo que salió mal y los siguientes pasos |

Los fragmentos de código no se copiaron a mano. El generador del libro (`docs/libro/build.py`) los lee directamente de los archivos del repositorio, con su archivo y sus líneas. Si el código cambia, basta volver a generar el libro para que los fragmentos se actualicen. Los programas del tutorial (carpeta `tutorial/`) también tienen pruebas automáticas, para que lo que muestra el libro siga funcionando.

Los recuadros naranjas, **Lección aprendida**, cuentan errores reales que aparecieron al probar con el modelo y cómo se corrigieron. El capítulo 22 los reúne todos. Para quien quiera construir un agente propio, probablemente son la parte más útil del libro.

> [!nota] Lo simulado y lo real
> La planta, sus valores y su historial de 6 meses son simulados. La comunicación OPC UA, el agente, sus herramientas, sus límites, el modelo de lenguaje y la GB10 son reales. El libro lo indica cada vez que importa.

## Las cifras clave

| Dato | Valor |
|---|---|
| Código del sistema | ≈ 4 900 líneas de Python en 7 paquetes, más la interfaz web |
| Código del agente | ≈ 1 500 líneas, sin frameworks de agentes |
| Herramientas del agente | 14, todas de lectura salvo el borrador de orden |
| Pruebas automáticas | 106, incluidas las del tutorial |
| Modelo | NVIDIA Nemotron (`nvidia/nemotron-3-nano`, 32 000 tokens de contexto), servido como NIM en la GB10 |
| Tiempo de respuesta | 7 preguntas en 37 s en el último ensayo; primer token en ≈ 0,4 s |
