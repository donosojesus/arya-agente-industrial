# 18 · La planta simulada

Para demostrar un agente industrial hace falta una planta. Una planta real no se puede llevar a una sala de reuniones, y tampoco se le puede provocar una falla para mostrarla. Por eso la planta de ARYA es simulada. Pero el agente no lo sabe: la ve igual que vería una planta real, por OPC UA, con señales correlacionadas, alarmas con histéresis y fallas cuya causa no se revela.

## La bomba P-101

El equipo simulado es una bomba centrífuga de agua de proceso, la P-101, con estos valores en operación normal: caudal de 62 m³/h, presión de descarga de 4,8 bar, corriente de 11,5 A, 1480 rpm, temperatura de motor de 57 °C y vibración de 2,0 mm/s. Todos calzan con su ficha técnica (capítulo 17): una curva de prestaciones propia y un motor de 15 kW a 690 V.

## Señales que se comportan como señales

Una simulación que suma ruido independiente a cada valor se nota enseguida: las señales no se mueven juntas. En una bomba real, cuando sube la demanda sube el caudal, baja un poco la presión, sube la corriente y, más lento, la temperatura.

Por eso el modelo genera las señales a partir de tres variables ocultas que evolucionan suavemente (demanda hidráulica, excitación mecánica y ambiente), cada una como un proceso de Ornstein-Uhlenbeck:

@@code src/arya_plant/model.py PumpModel._ou

La temperatura tiene además inercia térmica: no salta, sino que se acerca a su equilibrio con una constante de tiempo de 25 s.

@@code src/arya_plant/model.py PumpModel.step

## Fallas con causa oculta

Una falla se describe como un perfil: cuánto afecta a cada señal cuando la degradación es completa.

@@code src/arya_plant/model.py FaultProfile

Hay tres escenarios. Sus identificadores públicos son neutros a propósito (`alpha`, `bravo`, `charlie`), y la causa real queda en un módulo que ningún servicio público importa:

| Escenario | Qué se ve | Causa real (oculta) |
|---|---|---|
| A (`alpha`) | Sube la vibración y, con retraso, la temperatura; la corriente algo mayor | Pérdida de lubricación del rodamiento |
| B (`bravo`) | Cae el caudal y la presión; la corriente **baja**; la vibración se vuelve irregular | Obstrucción del filtro de succión |
| C (`charlie`) | Sin alarmas: desgaste lento en 6 meses de historial | Desgaste incipiente con la relubricación atrasada |

Ocultar la causa no es un adorno. Permite evaluar al agente: si llega a la causa correcta, la dedujo de los datos, las órdenes y los manuales, no la leyó. En la demo, la causa va en un sobre cerrado que se abre al final.

> [!cuidado] La causa no puede filtrarse
> Hay una prueba automática que revisa todas las salidas públicas (OPC UA, APIs, pantallas) y falla si aparece alguna palabra de las causas reales, como "lubricación" o "rodamiento". Esa prueba atrapó un texto de la pantalla de la AI Factory que mencionaba la causa de la falla A.

## Alarmas como las de un SCADA

Una alarma real no se activa ni se apaga en cuanto el valor toca el límite: tiene un retardo de activación, otro de liberación y una banda muerta, para no parpadear.

@@code src/arya_plant/alarms.py AlarmEvaluator.update

## El servidor OPC UA

La planta publica cada instante como un lote de variables en un servidor OPC UA real (librería `asyncua`), con NodeIds de texto estables (`P101.VIBRATION`, `RUN.ID`…), unidades UNECE y los límites como nodos de configuración. Es de solo lectura: cualquier intento de escritura recibe `BadUserAccessDenied`.

Un problema de cualquier lectura de muchas variables es la coherencia: si el cliente lee mientras el servidor escribe, puede mezclar valores de dos instantes. La solución es un número de secuencia que funciona como un *seqlock*: es impar mientras el lote se escribe y par cuando está completo.

@@code src/arya_plant/opcua_server.py PlantOpcUaServer.publish

El cliente lee la secuencia antes y después del lote, y lo acepta solo si no cambió y es par:

@@code src/arya_otclient/poller.py is_coherent

## La API de control del presentador

Las fallas no empiezan solas: solo cuando el presentador pulsa SIMULAR FALLA. La API de control exige el token de la demo, y la pantalla solo acepta acciones que vengan de su propio origen.

@@code src/arya_plant/simulator.py PlantSimulator.inject_fault
