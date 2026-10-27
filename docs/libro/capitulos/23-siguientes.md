# 23 · Siguientes pasos

ARYA es una demo con una bomba simulada. Este capítulo dice qué le falta para un caso real, cómo sería un piloto y cómo escala el mismo diseño.

## Lo que falta en el agente

| Mejora | Qué aporta | Estado hoy |
|---|---|---|
| **MCP** | Exponer las herramientas como servidores MCP, el estándar abierto para conectar herramientas y datos a los agentes (planta, CMMS, documentos), para que cualquier agente las use con permisos definidos | Herramientas dentro del agente; MCP marcado como no implementado |
| **RAG con vectores** | Buscar por significado, no por palabras exactas: encontrar el procedimiento aunque la pregunta use otras palabras | BM25 sobre 10 documentos |
| **Medallón sobre datos reales** | Conectar bronce, plata y oro al historian de la planta del cliente | Simulado |
| **Más equipos** | Varios activos con sus fichas, curvas y límites | Una bomba |
| **Monitoreo de GPU en la traza** | Mostrar la GPU y la energía de la GB10 junto a TTFT/TPOT | Disponible en las métricas del NIM; aún no en la pantalla |

## Cómo sería un piloto

1. **Elegir un caso:** un equipo con un problema concreto y cómo se medirá el resultado.
2. **Conectar en solo lectura:** historian, órdenes de mantención y manuales.
3. **Probar en la planta:** una Dell Pro Max GB10 en sus instalaciones, con los datos sin salir de la planta.
4. **Medir y decidir:** con resultados reales, decidir si se escala a producción.

## De la GB10 a una AI Factory

El mismo diseño escala. Un agente pide poco cómputo: en la GB10, 16 consultas simultáneas entregaron entre 170 y 215 tokens por segundo con unos 37 W. Lo que lleva a una AI Factory es la cantidad de casos de uso y de plantas. La arquitectura de referencia de Dell con NVIDIA (configuración 2-8-5-200: 2 CPU, hasta 8 GPU y 5 tarjetas de red por servidor, con 200 Gb/s de red este-oeste por GPU) usa servidores PowerEdge XE7745 con GPU RTX PRO 6000, almacenamiento PowerScale y red Spectrum-X, con Kubernetes y el software NVIDIA AI Enterprise. Cada capa de ARYA tiene su equivalente ahí: Docker pasa a Kubernetes, la GB10 a PowerEdge y las bases locales a la plataforma de datos.

Lo que no cambia son los principios del capítulo 1: solo lectura por construcción, nunca inventar, decide una persona, todo visible.
