"""ARYA Industrial Demo - OT Gateway: historian local + API HTTP de solo lectura.

Es la unica puerta por la que el lado de IA observa la planta. Obtiene todo por
OPC UA (cliente real) y lo guarda en un historian SQLite. No importa el simulador
y no ofrece ninguna ruta que modifique el proceso.
"""

__version__ = "0.1.0"
