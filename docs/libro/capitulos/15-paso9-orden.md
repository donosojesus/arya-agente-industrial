# 15 · Paso 9 · La orden en borrador y la aprobación humana

ARYA puede escribir en un solo lugar, el CMMS, y solo un borrador de orden de trabajo. Aprobarlo es trabajo de una persona, con una credencial que el agente no tiene. Este paso muestra cómo se separan las dos cosas en el código, de modo que el agente no pueda aprobar aunque quisiera.

## El recorrido completo

@@img docs/img/libro/borrador-aprobacion.svg Del pedido a la decisión. El agente crea el borrador con su clave; aprobarlo exige el token de una persona; y el agente recuerda la decisión solo después de verificarla en el CMMS. Los identificadores son los del ensayo registrado en docs/validation.md.

1. **El modelo pide el borrador**, y solo puede hacerlo si el operador pidió una orden: la herramienta no se ofrece de otro modo, y si igual la pide, el código bloquea la llamada (capítulo 12).
2. **El agente lo crea en el CMMS** con su propia clave. El CMMS lo guarda como `DRAFT_PENDING_APPROVAL`, con el agente como autor.
3. **Si el agente intentara aprobarlo, el CMMS lo rechazaría**: aprobar exige otra credencial. En el ensayo registrado, ese intento recibió HTTP 401.
4. **Una persona aprueba en la pantalla**, con su nombre y el token de aprobación. El borrador pasa a ser una orden abierta, con un número nuevo.
5. **El agente verifica antes de recordar.** La pantalla le avisa que hubo una decisión, pero el agente no se fía del aviso: lee la orden en el CMMS y solo entonces la guarda en su memoria.

## Lo que el modelo tiene que llenar

El borrador es la herramienta con más argumentos. Cada campo tiene límites, por la misma razón que en el paso 4: el modelo no puede mandar cualquier cosa.

@@code src/arya_agent/tools.py DraftArgs

El tipo `PREDICTIVE` y la fecha planificada se usan en el escenario predictivo (capítulo 17). La evidencia, de 1 a 8 fuentes, obliga a que la orden diga de dónde sale.

## La herramienta que crea el borrador

@@code src/arya_agent/tools.py _create_draft

La llamada al CMMS lleva la clave del agente en la cabecera `Authorization`. Después, la herramienta registra el incidente en la memoria del agente y agrega una nota explícita para el modelo: el borrador no está aprobado.

## Dos credenciales, dos permisos

En el CMMS, cada ruta declara qué credencial exige. Crear un borrador exige la clave del agente:

@@grep src/arya_cmms/app.py "@app.post("/api/v1/work-orders/drafts"" 2

Aprobar exige el token de una persona:

@@grep src/arya_cmms/app.py "@app.post("/api/v1/work-orders/{order_id}/approve"" 3

Y para que nadie pueda confundirlas, el CMMS se niega a arrancar si las dos credenciales son iguales:

@@grep src/arya_cmms/app.py "if hmac.compare_digest(agent_key, approver_token):" 2

## La memoria se verifica contra el CMMS

Cuando ARYA crea un borrador, registra el incidente en su memoria. Cuando una persona lo aprueba o lo rechaza, la memoria **no confía en lo que dice la pantalla**: lee la orden en el CMMS, que es la fuente de verdad, y solo entonces registra la decisión.

@@code src/arya_agent/memory.py AgentMemory.record_decision

Así, en la conversación siguiente, ARYA puede decir con respaldo: "en un incidente anterior con los mismos síntomas, la persona aprobó la relubricación".

La pantalla avisa la decisión con una llamada al agente. El agente lee la orden en el CMMS y, si el CMMS no registra una decisión humana para ese borrador, responde con un error 409 y no recuerda nada:

@@grep src/arya_agent/api.py "    @app.post("/api/v1/work-orders/{draft_id}/sync")" 14

## Probado

| Prueba | Resultado |
|---|---|
| Borrador con la clave del agente | Creado `WO-DRAFT-0031`, estado `DRAFT_PENDING_APPROVAL` |
| El agente intenta aprobar | Rechazado: HTTP 401 |
| Aprobación con el token de una persona | Pasa a `WO-2026-0412`, estado `OPEN`, con el nombre de quien aprobó |
| Con Nemotron, de punta a punta | `WO-DRAFT-0031` aprobado como `WO-2026-0412`; el agente lo verificó en el CMMS y lo recordó |
| "Recordar" una aprobación que el CMMS no respalda | Rechazado: HTTP 409 |
