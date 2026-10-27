# 21 · Cómo se prueba

Un agente se prueba en tres niveles: las piezas, las reglas de diseño y el comportamiento del modelo real. Ninguno reemplaza a los otros.

## Tres niveles

| Nivel | Qué prueba | Cuándo |
|---|---|---|
| **Pruebas automáticas** (106) | Cada pieza y el sistema completo, con servicios reales en proceso | En cada cambio, en ≈ 3 minutos |
| **Pruebas de arquitectura** | Que las reglas de seguridad se cumplen en el código fuente | Junto con las anteriores |
| **Ensayos con el modelo real** | Que Nemotron, con el harness, responde bien | Antes de cada presentación y después de cambios del agente |

## Un modelo de guion para las pruebas

Las pruebas automáticas no dependen de Nemotron: usan un modelo de guion que devuelve, en orden, las llamadas a herramientas y respuestas que la prueba indica. Así se prueba el ciclo, los límites y los guardrails de forma determinista. Existe solo en las pruebas y nunca se usa en la demo.

@@code tests/conftest.py ScriptedModel

El tutorial tiene su propio modelo de guion, pero en forma de servidor HTTP (`tutorial/modelo_guion.py`): así sus programas se prueban exactamente como los ejecuta el lector, sin cambiar una línea. Sus pruebas están en `tests/test_tutorial.py` y levantan una planta real, un gateway y ese servidor (capítulo 6).

## Pruebas de punta a punta, con servicios reales

Las pruebas levantan dentro del mismo proceso la planta con su servidor OPC UA real, el gateway, el CMMS y el agente, y los conectan como en producción. Por ejemplo, esta prueba recorre el escenario C completo: planta → OPC UA → gateway → proyección.

@@code tests/test_agent.py test_scenario_c_reaches_the_gateway_through_opc_ua

## Pruebas de arquitectura

Algunas pruebas no prueban funciones, sino reglas de diseño. Por ejemplo, que ningún paquete del lado de IA importe el simulador ni contenga el token de control:

@@code tests/test_plant_view.py test_plant_view_never_imports_the_simulator_nor_holds_the_token

> [!leccion] Las pruebas de arquitectura atraparon un atajo propio
> Al construir el escenario C, se agregó al gateway una ruta POST con el token de la demo. Era la solución más rápida y rompía dos reglas del diseño. Dos pruebas de arquitectura fallaron de inmediato, y el diseño final (la planta publica el perfil por OPC UA, capítulo 17) quedó mejor. Escribir las reglas de diseño como pruebas protege la arquitectura de los atajos, incluidos los propios.

## Ensayos con el modelo real

`scripts/rehearse-agent.sh` hace las preguntas del guion al agente real y marca lo que conviene revisar: respuestas lentas, herramientas que fallaron, borradores que no se crearon, negativas que no empiezan con "No".

```bash
./scripts/rehearse-agent.sh               # las 7 preguntas de la falla A
./scripts/rehearse-agent.sh --normal      # planta sana
./scripts/rehearse-agent.sh --reglas      # pedidos de operar: debe negarse
./scripts/rehearse-agent.sh --predictivo  # escenario C
```

Estos ensayos encontraron los errores que las pruebas automáticas no pueden ver, porque dependen del comportamiento real del modelo: los argumentos vacíos en streaming, el JSON cortado, las fechas inventadas y la búsqueda con una sola palabra.
