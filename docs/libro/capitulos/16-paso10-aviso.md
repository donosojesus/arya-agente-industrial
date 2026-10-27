# 16 · Paso 10 · El aviso automático

Un agente no tiene que esperar a que le pregunten. ARYA puede vigilar las alarmas e intervenir por su cuenta: "Disculpen la interrupción: se activó una alarma de caudal bajo en la P-101…".

## El vigilante

@@code src/arya_agent/api.py ProactiveWatcher._run

Tres detalles hacen que sea útil y no molesto:

1. **Un aviso por incidente.** El vigilante se "arma" al ver la planta en NORMAL y se "desarma" al avisar. No vuelve a interrumpir hasta que la planta se normalice.
2. **Espera 15 s antes de investigar**, para que el historian junte algo de historia y el análisis tenga con qué trabajar.
3. **Está apagado por defecto.** Se activa con una casilla en la pantalla. En una presentación, el presentador decide cuándo.

## Probado con el modelo real

Con la falla B, ARYA interrumpió sola a los 101 s de iniciada la falla, habló del caudal y la corriente, y su diagnóstico apuntó a la causa correcta.

> [!leccion] Lo que no se probó en el modo real de uso
> El aviso funcionaba en las pruebas, pero la pantalla tenía un error que solo aparecía en modo REPOSO, que es como queda durante una presentación: la función que debía cambiar la pantalla a CONVERSACIÓN se llamaba a sí misma en un ciclo infinito. Se encontró al preguntarse si el momento más memorable de la demo de verdad iba a ocurrir. La lección: probar cada función en el estado en que se va a usar.
