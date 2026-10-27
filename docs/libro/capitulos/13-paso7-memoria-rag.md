# 13 · Paso 7 · Memoria y RAG

ARYA recuerda de tres formas distintas, y cada una tiene su propia regla para no inventar.

## Tres tipos de memoria

| Memoria | Dónde vive | Cuánto dura | Qué guarda |
|---|---|---|---|
| Corta | En el proceso del agente | Las últimas 3 preguntas de una conversación | Preguntas, resultados reales de herramientas y respuestas |
| Larga | SQLite (`memory.py`) | Hasta un reinicio de la demo | Incidentes investigados, borradores creados y la decisión humana |
| Documental | Archivos Markdown (`data/documents/`) | Permanente | Manuales, procedimientos, recomendaciones del fabricante y la ficha técnica |

Cuando una persona aprueba o rechaza un borrador, la memoria larga registra la decisión solo después de verificarla en el CMMS. Esa parte se explica junto con la aprobación, en el capítulo 15.

## RAG: buscar antes de responder

RAG (*retrieval-augmented generation*) significa que el modelo no se aprendió los manuales: los busca en el momento, lee solo los fragmentos pertinentes y los cita.

Los documentos se dividen por sección. Cada fragmento lleva el identificador del documento, el título y la sección:

@@code src/arya_agent/documents.py DocumentIndex._load

La búsqueda usa BM25, el método clásico de los buscadores. La clase `Bm25Index` ocupa 26 líneas. El archivo completo, de 74 líneas, agrega la normalización del español (tildes, mayúsculas y plurales simples) y una lista de términos de inglés a español, porque el modelo a veces formula la consulta en inglés:

@@code src/arya_agent/textsearch.py Bm25Index

> [!leccion] Una sola palabra es una mala consulta
> Al preguntar por los límites de vibración del fabricante, el modelo buscaba solo "vibración", una palabra que aparece en casi todos los manuales, y la ficha técnica no aparecía. Hubo dos correcciones: una sección de la ficha con un título que nombra exactamente lo que contiene ("Límites de vibración y zonas de severidad"), y ejemplos de consultas de varias palabras en la descripción de la herramienta. Los modelos pequeños siguen muy bien los ejemplos.

## Los 10 documentos

Manual de operación (MAN-P101-001), ficha técnica (FT-P101-001), recomendaciones del fabricante (FAB-REC-P101), procedimientos de lubricación (SOP-MNT-014) y de limpieza del filtro (SOP-MNT-021), procedimientos de respuesta a alarmas (PRO-ALM-003, 005 y 007), procedimiento de seguridad y bloqueo (PRO-SEG-002) y la lista de inspección (CHK-INS-009).

> [!nota] Por qué BM25 y no vectores
> Con 10 documentos técnicos que usan un vocabulario preciso, BM25 encuentra lo pertinente y es explicable, rápido y sin dependencias. La búsqueda por significado (vectores) ayudaría cuando las preguntas usen palabras distintas a las del manual. Es uno de los siguientes pasos (capítulo 23).
