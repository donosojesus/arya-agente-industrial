"""Contrato publico OPC UA de la planta: namespace, NodeIds, unidades y descripciones.

Todos los NodeIds son de tipo string dentro del namespace NAMESPACE_URI, por lo
que permanecen estables entre reinicios. Los clientes deben resolver el indice
del namespace por su URI.
"""

from __future__ import annotations

from dataclasses import dataclass

NAMESPACE_URI = "urn:arya:industrial-demo:plant"
UNECE_NAMESPACE = "http://www.opcfoundation.org/UA/units/un/cefact"

FLOAT = "float"
STRING = "string"
STRING_ARRAY = "string_array"
UINT32 = "uint32"


@dataclass(frozen=True)
class TagDef:
    name: str  # identificador string del NodeId, p. ej. "P101.MOTOR_TEMP"
    kind: str
    description: str
    unit: str | None = None
    unece_code: str | None = None  # codigo comun UNECE de 3 caracteres
    decimals: int | None = None

    @property
    def browse_name(self) -> str:
        return self.name.split(".", 1)[1]

    @property
    def unit_id(self) -> int | None:
        """UnitId OPC UA (Part 8): los 3 caracteres UNECE empaquetados en un Int32."""
        if not self.unece_code:
            return None
        a, b, c = (ord(ch) for ch in self.unece_code)
        return (a << 16) | (b << 8) | c


PROCESS_TAGS: tuple[TagDef, ...] = (
    TagDef("P101.MOTOR_TEMP", FLOAT, "Temperatura del motor de la bomba P-101", "°C", "CEL", 2),
    TagDef("P101.VIBRATION", FLOAT, "Vibración global de la bomba P-101 (velocidad RMS)", "mm/s", "C16", 3),
    TagDef("P101.CURRENT", FLOAT, "Corriente del motor de la bomba P-101", "A", "AMP", 2),
    TagDef("P101.DISCHARGE_PRESSURE", FLOAT, "Presión de descarga de la bomba P-101", "bar", "BAR", 3),
    TagDef("P101.FLOW", FLOAT, "Caudal de descarga de la bomba P-101", "m³/h", "MQH", 2),
    TagDef("P101.RPM", FLOAT, "Velocidad de giro de la bomba P-101", "rpm", "RPM", 1),
    TagDef("P101.STATUS", STRING, "Estado de operación de la bomba P-101 (RUNNING)"),
    TagDef("P101.ALARM_LEVEL", STRING, "Nivel de alarma más alto activo: NORMAL, WARNING o ALARM"),
    TagDef("P101.ACTIVE_ALARMS", STRING_ARRAY, "Códigos de las alarmas activas de P-101"),
)

RUN_TAGS: tuple[TagDef, ...] = (
    TagDef("RUN.ID", STRING, "Identificador del ensayo en curso; cambia con cada RESET"),
    TagDef("RUN.HISTORY_PROFILE", STRING, "Perfil del historial de 6 meses simulado que acompaña al ensayo (identificador opaco)"),
    TagDef("RUN.SIM_TIME_S", FLOAT, "Tiempo simulado transcurrido desde el inicio del ensayo", "s", "SEC", 3),
    TagDef(
        "RUN.SNAPSHOT_SEQ",
        UINT32,
        "Secuencia del lote publicado. Impar: lote en actualización. Un lote es "
        "coherente si se lee el mismo valor par antes y después de los demás nodos.",
    ),
)

# Limites demostrativos publicados como nodos de configuracion de solo lectura.
LIMIT_TAGS: tuple[TagDef, ...] = (
    TagDef("P101.MOTOR_TEMP.HI", FLOAT, "Límite WARNING de temperatura (demostrativo)", "°C", "CEL", 1),
    TagDef("P101.MOTOR_TEMP.HIHI", FLOAT, "Límite ALARM de temperatura (demostrativo)", "°C", "CEL", 1),
    TagDef("P101.VIBRATION.HI", FLOAT, "Límite WARNING de vibración (demostrativo)", "mm/s", "C16", 1),
    TagDef("P101.VIBRATION.HIHI", FLOAT, "Límite ALARM de vibración (demostrativo)", "mm/s", "C16", 1),
    TagDef("P101.FLOW.LO", FLOAT, "Límite WARNING de bajo caudal (demostrativo)", "m³/h", "MQH", 1),
    TagDef("P101.FLOW.LOLO", FLOAT, "Límite ALARM de bajo caudal (demostrativo)", "m³/h", "MQH", 1),
)

SEQ_NODE = "RUN.SNAPSHOT_SEQ"
# Nodos que se actualizan juntos en cada lote (el numero de secuencia va aparte).
BATCH_TAGS: tuple[TagDef, ...] = PROCESS_TAGS + tuple(t for t in RUN_TAGS if t.name != SEQ_NODE)
ALL_TAGS: tuple[TagDef, ...] = PROCESS_TAGS + RUN_TAGS + LIMIT_TAGS
