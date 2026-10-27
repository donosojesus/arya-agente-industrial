"""Servidor OPC UA de la planta (asyncua).

- Namespace propio con URI estable y NodeIds string estables.
- Todos los nodos son de solo lectura para los clientes; solo el propio
  servidor actualiza valores.
- Cada lote se publica con un unico SourceTimestamp UTC y protegido por el
  numero de secuencia RUN.SNAPSHOT_SEQ (impar mientras se actualiza).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from asyncua import Server, ua

from .simulator import Snapshot
from .tags import (
    BATCH_TAGS,
    FLOAT,
    LIMIT_TAGS,
    NAMESPACE_URI,
    PROCESS_TAGS,
    RUN_TAGS,
    SEQ_NODE,
    STRING,
    STRING_ARRAY,
    UINT32,
    UNECE_NAMESPACE,
    TagDef,
)

log = logging.getLogger("arya.plant.opcua")

APPLICATION_URI = "urn:arya:industrial-demo:plant:server"
_GOOD = ua.StatusCode(ua.StatusCodes.Good)


def _variant(tag: TagDef, value: object) -> ua.Variant:
    if tag.kind == FLOAT:
        return ua.Variant(float(value), ua.VariantType.Double)
    if tag.kind == STRING:
        return ua.Variant(str(value), ua.VariantType.String)
    if tag.kind == STRING_ARRAY:
        return ua.Variant([str(v) for v in value], ua.VariantType.String, is_array=True)
    if tag.kind == UINT32:
        return ua.Variant(int(value) % 2**32, ua.VariantType.UInt32)
    raise ValueError(f"unsupported tag kind {tag.kind}")


_INITIAL = {FLOAT: 0.0, STRING: "", STRING_ARRAY: [], UINT32: 0}


class PlantOpcUaServer:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._server: Server | None = None
        self._idx = 0
        self._seq = 0
        self.started = False

    def _nodeid(self, name: str) -> ua.NodeId:
        return ua.NodeId(name, self._idx)

    async def _add_variable(self, parent, tag: TagDef) -> None:
        node = await parent.add_variable(
            self._nodeid(tag.name),
            ua.QualifiedName(tag.browse_name, self._idx),
            _variant(tag, _INITIAL[tag.kind]),
        )
        await node.write_attribute(
            ua.AttributeIds.Description,
            ua.DataValue(ua.Variant(ua.LocalizedText(tag.description, "es"), ua.VariantType.LocalizedText)),
        )
        if tag.unit:
            eu = ua.EUInformation()
            eu.NamespaceUri = UNECE_NAMESPACE
            eu.UnitId = tag.unit_id
            eu.DisplayName = ua.LocalizedText(tag.unit)
            eu.Description = ua.LocalizedText(tag.unit)
            await node.add_property(
                self._nodeid(f"{tag.name}.EngineeringUnits"),
                ua.QualifiedName("EngineeringUnits", 0),
                eu,
            )
        # asyncua crea las variables sin permiso de escritura para clientes
        # (AccessLevel = CurrentRead). No se llama a set_writable().

    async def start(self, snapshot: Snapshot, limits: dict[str, float]) -> None:
        server = Server()
        await server.init()
        server.set_endpoint(self.endpoint)
        server.set_server_name("ARYA Industrial Demo - Plant P-101")
        await server.set_application_uri(APPLICATION_URI)
        # Red OT simulada y aislada, solo lectura: sin cifrado en esta etapa.
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self._idx = await server.register_namespace(NAMESPACE_URI)

        plant = await server.nodes.objects.add_folder(self._nodeid("Plant"), ua.QualifiedName("Plant", self._idx))
        pump = await plant.add_object(self._nodeid("P101"), ua.QualifiedName("P101", self._idx))
        run = await plant.add_object(self._nodeid("RUN"), ua.QualifiedName("RUN", self._idx))
        limits_obj = await pump.add_object(self._nodeid("P101.Limits"), ua.QualifiedName("Limits", self._idx))
        for tag in PROCESS_TAGS:
            await self._add_variable(pump, tag)
        for tag in RUN_TAGS:
            await self._add_variable(run, tag)
        for tag in LIMIT_TAGS:
            await self._add_variable(limits_obj, tag)

        self._server = server
        now = datetime.now(timezone.utc)
        for tag in LIMIT_TAGS:
            await self._write(tag, limits[tag.name], now)
        await self.publish(snapshot, now)
        await server.start()
        self.started = True
        log.info("OPC UA server listening on %s (namespace %s)", self.endpoint, NAMESPACE_URI)

    async def _write(self, tag: TagDef, value: object, source_ts: datetime) -> None:
        assert self._server is not None
        await self._server.write_attribute_value(
            self._nodeid(tag.name),
            ua.DataValue(_variant(tag, value), StatusCode=_GOOD, SourceTimestamp=source_ts, ServerTimestamp=source_ts),
        )

    async def publish(self, snapshot: Snapshot, source_ts: datetime) -> int:
        """Publica un lote completo. Devuelve el numero de secuencia (par) resultante."""
        if source_ts.tzinfo is None:
            raise ValueError("source_ts must be timezone-aware UTC")
        seq_tag = next(t for t in RUN_TAGS if t.name == SEQ_NODE)
        values = dict(snapshot.values)
        values["RUN.ID"] = snapshot.run_id
        values.setdefault("RUN.HISTORY_PROFILE", "H1")
        values["RUN.SIM_TIME_S"] = snapshot.sim_time_s
        self._seq = (self._seq + 1) % 2**32  # impar: lote en actualizacion
        await self._write(seq_tag, self._seq, source_ts)
        for tag in BATCH_TAGS:
            await self._write(tag, values[tag.name], source_ts)
        self._seq = (self._seq + 1) % 2**32  # par: lote completo
        await self._write(seq_tag, self._seq, source_ts)
        return self._seq

    async def stop(self) -> None:
        if self._server is not None and self.started:
            self.started = False
            await self._server.stop()
