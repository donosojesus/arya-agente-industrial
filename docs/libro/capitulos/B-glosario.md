# B · Glosario

| Término | Qué significa en este libro |
|---|---|
| 2-8-5-200 | Nomenclatura de las arquitecturas de referencia de NVIDIA: 2 CPU, hasta 8 GPU y 5 tarjetas de red por servidor, con 200 Gb/s de red este-oeste por GPU ([NVIDIA](https://docs.nvidia.com/enterprise-reference-architectures/white-paper/latest/key-building-blocks.html)). Capítulo 23 |
| Agente | Programa que usa un modelo de lenguaje para decidir qué consultar, consulta sistemas reales con herramientas y responde citando lo que encontró. Capítulo 3 |
| BM25 | Método clásico de búsqueda por palabras. ARYA lo usa para encontrar fragmentos de manuales. Capítulo 13 |
| CMMS | Sistema de gestión de mantenimiento: órdenes de trabajo y calendario de paradas |
| Credencial | Clave secreta (un token) que un servicio exige para aceptar una acción. ARYA usa tres. Capítulos 5 y 15 |
| Guardrail | Regla que el código hace cumplir, no solo una instrucción para el modelo. Capítulo 12 |
| Harness | Todo el programa que rodea al modelo y lo convierte en un agente: prompt, herramientas, ciclo, guardrails, memoria, traza y aprobación humana. Capítulo 4 |
| Historian | Base de datos que guarda la historia de las señales de la planta. Capítulo 19 |
| HTTP | El protocolo con que se comunican los servicios: una petición (GET para leer, POST para enviar) y una respuesta con un código de estado. Apéndice C |
| JSON | Formato de texto para datos estructurados, con objetos `{}` y listas `[]`. Apéndice C |
| Llamada a herramienta | Pedido estructurado del modelo para que el programa ejecute una herramienta, con su nombre y sus argumentos (`tool_calls`). Capítulo 3 |
| MCP | Model Context Protocol: estándar abierto para conectar herramientas y datos a los agentes. ARYA no lo implementa todavía. Capítulo 23 |
| Medallón | Organización de los datos en tres capas: bronce (tal como llegan), plata (limpios y normalizados) y oro (indicadores diarios). Capítulo 17 |
| NIM | Microservicio de inferencia de NVIDIA: empaqueta un modelo como un servicio, con la misma API que usan los servicios de OpenAI. Capítulos 2 y 7 |
| OPC UA | Estándar de comunicación industrial con el que la planta publica sus señales. Capítulo 18 |
| p95 | Percentil 95: el valor bajo el cual queda el 95 % de las mediciones de un día. Resume la vibración sin que la arrastre un pico aislado |
| PLC / DCS | Controladores que ejecutan el control de la planta |
| Prompt de sistema | Instrucciones fijas que el modelo recibe en cada llamada: rol, reglas y guía de herramientas. Capítulo 11 |
| RAG | *Retrieval-augmented generation*: el modelo busca los documentos en el momento y cita los fragmentos que usó. Capítulo 13 |
| RAG con vectores | Búsqueda por significado en vez de por palabras exactas: encuentra un texto aunque la pregunta use otras palabras |
| SCADA | Sistema que muestra las señales de la planta y levanta alarmas |
| Servidor de guion | Programa del tutorial que imita la API del modelo con reglas fijas, para practicar sin hardware. Capítulo 6 |
| Streaming | Recibir la respuesta del modelo a medida que se genera, en vez de esperar a que termine |
| Temperatura | Cuánto se arriesga el modelo al elegir el siguiente token. Con temperatura baja elige casi siempre el más probable. Capítulo 2 |
| Token (del modelo) | Trozo de texto, en promedio más corto que una palabra, que el modelo lee y genera. El contexto y la velocidad del modelo se miden en tokens |
| TTFT / TPOT | Tiempo hasta el primer token y tiempo por token: las dos medidas de velocidad del modelo. Capítulo 7 |
| Ventana de contexto | Todo lo que el modelo recibe en una llamada. En ARYA, hasta 32 000 tokens. Lo que no está ahí, el modelo no lo sabe. Capítulo 2 |
