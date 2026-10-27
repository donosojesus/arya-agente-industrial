"""Lo que plant-view sabe de la planta: solo el contrato publico OPC UA.

Unidades, descripciones y limites se leen del propio servidor al conectar.
"""

NAMESPACE_URI = "urn:arya:industrial-demo:plant"

PROCESS_NODES = (
    "P101.MOTOR_TEMP",
    "P101.VIBRATION",
    "P101.CURRENT",
    "P101.DISCHARGE_PRESSURE",
    "P101.FLOW",
    "P101.RPM",
    "P101.STATUS",
    "P101.ALARM_LEVEL",
    "P101.ACTIVE_ALARMS",
)
RUN_ID_NODE = "RUN.ID"
SIM_TIME_NODE = "RUN.SIM_TIME_S"
HISTORY_PROFILE_NODE = "RUN.HISTORY_PROFILE"  # perfil opaco del historial de 6 meses simulado (H1, H2)
SEQ_NODE = "RUN.SNAPSHOT_SEQ"
LIMIT_NODES = (
    "P101.MOTOR_TEMP.HI",
    "P101.MOTOR_TEMP.HIHI",
    "P101.VIBRATION.HI",
    "P101.VIBRATION.HIHI",
    "P101.FLOW.LO",
    "P101.FLOW.LOLO",
)
