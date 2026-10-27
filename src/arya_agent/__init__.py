"""ARYA - agente de asistencia al operador (solo lectura sobre el proceso).

Arquitectura hibrida: el modelo de lenguaje decide que herramientas usar; un
envoltorio determinista limita cuantas, cuales, con que argumentos y por cuanto
tiempo. No existe ninguna herramienta que escriba en el proceso.
"""

__version__ = "0.1.0"
