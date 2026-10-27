"""ARYA Industrial Demo - CMMS ficticio (ordenes de trabajo) con API REST.

Separacion de capacidades:
- Lectura: abierta dentro de la red de la demo.
- Crear BORRADOR: clave del agente (CMMS_AGENT_KEY).
- Aprobar / rechazar / reiniciar: token humano (CMMS_APPROVER_TOKEN), distinto del anterior.
El agente no puede aprobar sus propios borradores.
"""

__version__ = "0.1.0"
