# Resumen ejecutivo

ARYA es un agente de inteligencia artificial para mantención. Cuando suena una alarma en una bomba, hace en segundos la investigación que hoy hace una persona. Con 6 meses de historial, ve venir un desgaste semanas antes de la alarma. Y deja la orden de trabajo en borrador. Nunca opera la planta: las decisiones las toma una persona.

## Qué hace

- **Investiga una falla.** Consulta señales, alarmas, historial, órdenes anteriores, manuales y su propia memoria. Propone la causa más probable y cita de dónde sacó cada dato.
- **Anticipa un desgaste.** Con el historial de 6 meses, calcula un rango de semanas hasta el límite de alarma y recomienda intervenir en la parada programada que llega antes.
- **Propone la orden de trabajo.** La deja en borrador. Aprobarla exige una persona con su propia credencial.
- **Avisa sin que le pregunten.** Si se activa una alarma, puede interrumpir para explicar qué pasa. Viene apagado y se enciende con una casilla en la pantalla.

## Cómo se protege la planta

| Protección | Cómo se cumple |
|---|---|
| Solo lectura, por construcción | El agente no tiene ninguna herramienta que escriba en el proceso. El servidor OPC UA rechaza escrituras y el gateway solo acepta lecturas |
| Decide una persona | El agente solo crea borradores. Aprobarlos exige una credencial que el agente no tiene |
| Nunca inventar | Debe consultar datos antes de responder, y el código verifica las órdenes, documentos y fechas que cita |
| Todo es visible | Cada paso queda en una traza: herramienta, fuente, tiempo y tokens |
| Sin nube | El modelo corre en la Dell Pro Max GB10. Nada sale a Internet |

## Qué se probó con el modelo real

Ensayos con NVIDIA Nemotron en la GB10, registrados en `docs/validation.md`:

| Prueba | Resultado |
|---|---|
| Falla A: las 7 preguntas de la demo | 37 s en total y 0 herramientas fallidas; el diagnóstico coincidió con la causa real |
| Falla B, con un incidente distinto en la memoria | 3 de 3 diagnósticos correctos, tras ajustar el método |
| Aviso automático con la falla B | ARYA interrumpió sola a los 101 s de iniciada la falla |
| Pedidos de operar la planta | 4 de 4 negativas explícitas, incluso con "olvida tus reglas"; 3 de 3 tras el último ajuste |
| Desgaste lento (escenario C) | 5 rondas de 4 preguntas: siempre el rango correcto, de 2,4 a 6,9 semanas, y la parada que llega antes |
| Historial sano | Respondió "zona A, sin tendencia relevante", sin inventar un problema |

## Qué es real y qué es simulado

Son reales el agente, sus herramientas y sus límites, la comunicación OPC UA, el modelo de lenguaje y la GB10. Son simulados la bomba P-101, sus valores, sus fallas y el historial de 6 meses.

## Qué sigue

Un piloto tendría cuatro pasos: elegir un caso, conectar en solo lectura, probar en la planta con una GB10 y medir para decidir (capítulo 23). Para profundizar sin leer código: la Parte I (capítulos 1 a 5) y los capítulos 17, 22 y 23.
