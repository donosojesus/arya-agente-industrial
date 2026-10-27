# 5 · El ecosistema industrial

Un agente industrial no trabaja solo: vive al lado de un sistema de control que ya funciona y que no debe tocar. Este capítulo presenta las piezas de ese mundo, cómo se separan y qué puede hacer el agente en cada una. Las tablas de puertos y credenciales son de referencia para el equipo técnico: se pueden saltar sin perder el hilo.

## Las piezas de una planta

Para quien no viene de la industria, estas son las piezas que aparecen en todo el libro:

| Pieza | Qué es | En ARYA |
|---|---|---|
| PLC o DCS | El controlador que ejecuta el control del proceso | Lo reemplaza el simulador de la bomba |
| SCADA o HMI | La pantalla de operación: valores, alarmas y tendencias | `plant-view`, estilo ISA-101 |
| OPC UA | El estándar de comunicación industrial con que la planta publica sus señales | Un servidor OPC UA real, de solo lectura |
| Historian | La base de datos con la historia de las señales | Dentro del gateway, en SQLite |
| CMMS | El sistema de mantenimiento: órdenes de trabajo y paradas programadas | `cmms`, con borradores y aprobación humana |

## Las tres zonas

La arquitectura sigue la separación habitual de una planta industrial: cada zona solo puede hablar con la siguiente, y en una sola dirección para los datos de la planta.

@@img docs/img/libro/zonas.svg Las tres zonas de ARYA. Los datos de la planta solo fluyen hacia la IA; desde la IA no existe ningún camino de escritura hacia el proceso.

1. **Zona OT**: la planta y su servidor OPC UA. Nada de la IA vive aquí.
2. **Zona intermedia**: el gateway y el CMMS. El gateway es la única puerta hacia los datos de la planta, y solo deja leer.
3. **Zona de IA**: el agente, la pantalla y el modelo. Puede consultar, nunca escribir en el proceso.

La pregunta de diseño en cada frontera fue: si la pieza de este lado fallara o se comportara mal, ¿qué podría hacer al otro lado? Para el agente, la respuesta es: leer datos y crear un borrador de orden. Nada más.

## Seis servicios y un modelo

El sistema son seis servicios en contenedores Docker, que corren en un notebook, más el modelo de lenguaje en la GB10.

@@img docs/img/arquitectura.png Arquitectura completa: la planta y su OT a la izquierda, la capa de IA en el centro y la Dell Pro Max GB10 a la derecha. La figura es del 20 de octubre: desde entonces el agente pasó de 10 a 14 herramientas y de 9 a 10 documentos. «8 herramientas · 6 pasos · 2 min» son los límites por pregunta (capítulo 9).

| Servicio | Puerto | Qué hace |
|---|---|---|
| `plant` | 4840 (OPC UA), 9001 (control) | Simula la bomba P-101, evalúa alarmas y publica todo por un servidor OPC UA de solo lectura. Tiene una API de control para el presentador |
| `plant-view` | 8080 | La pantalla de operación estilo ISA-101: diagrama, alarmas, tendencias. Solo lee |
| `ot-gateway` | 8081 | Lee la planta por OPC UA, guarda el historian y ofrece una API de solo lectura al lado de IA |
| `cmms` | 8082 | Órdenes de trabajo y calendario de paradas. Separa la clave del agente del token humano |
| `agent` | 8091 | ARYA: el ciclo, las herramientas, los guardrails, la memoria y la traza |
| `demo-ui` | 8090 | La pantalla dividida de la demo: planta, conversación, tablero "por dentro" y la ventana de la AI Factory |
| NIM Nemotron | GB10 | El modelo de lenguaje, con llamadas a herramientas nativas |

## Las tres credenciales

Una credencial es un token: una clave secreta que un servicio exige para aceptar una acción.

| Credencial | Quién la tiene | Para qué |
|---|---|---|
| `DEMO_CONTROL_TOKEN` | La planta y la pantalla de la demo | Simular una falla o volver a normal. El gateway, el CMMS y el agente no la tienen |
| `CMMS_AGENT_KEY` | El agente | Crear borradores de órdenes |
| `CMMS_APPROVER_TOKEN` | Solo la persona que aprueba | Aprobar o rechazar un borrador |

Las tres se generan al primer arranque en un archivo `.env` que no se sube al repositorio. Hay pruebas automáticas que fallan si una credencial aparece donde no corresponde (capítulo 21). El capítulo 15 muestra cómo se usan las dos del CMMS.

## El flujo de una pregunta

1. El operador pregunta en la pantalla, escribiendo, pulsando un botón o por voz.
2. La pantalla reenvía la pregunta al agente.
3. El agente arma el contexto (reglas, historial reciente, herramientas permitidas) y llama al modelo en la GB10.
4. El modelo pide herramientas. El agente las ejecuta contra el gateway, el CMMS o los documentos, con tiempo límite, y le devuelve los resultados.
5. Se repite hasta que el modelo responde con texto, o hasta un límite.
6. El agente verifica la respuesta (que no cite nada que no consultó), la limpia y la publica con sus fuentes, sus tiempos y sus tokens.
7. Cada paso se publica en la traza, que la pantalla muestra en vivo.

La Parte II construye, paso a paso, el agente de este flujo. La Parte III explica cómo está hecho el resto: la planta, OPC UA, el gateway y el despliegue.
