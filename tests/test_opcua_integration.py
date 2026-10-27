"""Pruebas 6 y 7 (y coherencia de lotes): servidor OPC UA real + cliente OPC UA real."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from asyncua import Client, ua

from arya_plant.tags import ALL_TAGS, BATCH_TAGS, LIMIT_TAGS, NAMESPACE_URI, PROCESS_TAGS
from arya_otclient.poller import OpcUaPoller, is_coherent

from conftest import assert_no_leak

EXPECTED_PROCESS_NODES = {
    "P101.MOTOR_TEMP": "°C", "P101.VIBRATION": "mm/s", "P101.CURRENT": "A",
    "P101.DISCHARGE_PRESSURE": "bar", "P101.FLOW": "m³/h", "P101.RPM": "rpm",
    "P101.STATUS": None, "P101.ALARM_LEVEL": None, "P101.ACTIVE_ALARMS": None,
}


async def wait_for(predicate, timeout: float = 10.0, interval: float = 0.05):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not reached in time")


def test_contract_lists_the_required_tags():
    assert {t.name: t.unit for t in PROCESS_TAGS} == EXPECTED_PROCESS_NODES


async def test_real_client_reads_every_tag_with_units_description_and_utc_timestamps(runtime_factory):
    runtime = await runtime_factory()
    async with Client(runtime.settings.opcua_endpoint, timeout=4) as client:
        idx = await client.get_namespace_index(NAMESPACE_URI)  # namespace propio con URI estable
        assert idx >= 2
        await asyncio.sleep(0.3)
        now = datetime.now(timezone.utc)
        texts = []
        for tag in ALL_TAGS:
            node = client.get_node(ua.NodeId(tag.name, idx))  # NodeId string estable
            dv = await node.read_data_value()
            assert dv.StatusCode.is_good(), tag.name
            value = dv.Value.Value
            if tag.kind == "float":
                assert isinstance(value, float)
            elif tag.kind == "string":
                assert isinstance(value, str) and value
            elif tag.kind == "string_array":
                assert isinstance(value, list)
            else:
                assert isinstance(value, int)
            # Timestamp de origen en UTC y reciente.
            assert dv.SourceTimestamp is not None and dv.SourceTimestamp.tzinfo is not None
            assert dv.SourceTimestamp.utcoffset() == timedelta(0)
            assert abs((now - dv.SourceTimestamp).total_seconds()) < 5
            description = (await node.read_description()).Text
            assert description and len(description) > 10
            texts += [description, str(value), (await node.read_browse_name()).Name]
            if tag.unit:
                props = {(await p.read_browse_name()).Name: p for p in await node.get_properties()}
                eu = await props["EngineeringUnits"].read_value()
                assert eu.DisplayName.Text == tag.unit and eu.UnitId == tag.unit_id
        values = {t.name: await client.get_node(ua.NodeId(t.name, idx)).read_value() for t in PROCESS_TAGS}
        assert values["P101.STATUS"] == "RUNNING" and values["P101.ALARM_LEVEL"] == "NORMAL"
        assert 50 < values["P101.MOTOR_TEMP"] < 65 and 1400 < values["P101.RPM"] < 1550
        run_id = await client.get_node(ua.NodeId("RUN.ID", idx)).read_value()
        assert run_id == runtime.simulator.run_id  # identificacion del ensayo
        limits = {t.name: await client.get_node(ua.NodeId(t.name, idx)).read_value() for t in LIMIT_TAGS}
        assert limits == {"P101.MOTOR_TEMP.HI": 75.0, "P101.MOTOR_TEMP.HIHI": 88.0,
                          "P101.VIBRATION.HI": 4.5, "P101.VIBRATION.HIHI": 7.1,
                          "P101.FLOW.LO": 52.0, "P101.FLOW.LOLO": 45.0}
        assert_no_leak(" ".join(texts))  # ni valores ni descripciones delatan la causa


async def test_client_writes_are_rejected_on_every_node(runtime_factory):
    runtime = await runtime_factory()
    samples = {"float": 1.0, "string": "HACKED", "string_array": ["X"], "uint32": 4}
    variant_types = {"float": ua.VariantType.Double, "string": ua.VariantType.String,
                     "string_array": ua.VariantType.String, "uint32": ua.VariantType.UInt32}
    async with Client(runtime.settings.opcua_endpoint, timeout=4) as client:
        idx = await client.get_namespace_index(NAMESPACE_URI)
        for tag in ALL_TAGS:
            node = client.get_node(ua.NodeId(tag.name, idx))
            before = await node.read_value()
            with pytest.raises(ua.UaStatusCodeError) as excinfo:
                await node.write_value(ua.DataValue(ua.Variant(samples[tag.kind], variant_types[tag.kind])))
            assert ua.StatusCode(excinfo.value.code).name in {"BadUserAccessDenied", "BadNotWritable"}, tag.name
            if tag.name not in {"RUN.SNAPSHOT_SEQ", "RUN.SIM_TIME_S"} and tag.kind != "float":
                assert await node.read_value() == before
        # El proceso sigue sin alterar tras los intentos de escritura.
        assert await client.get_node(ua.NodeId("P101.STATUS", idx)).read_value() == "RUNNING"
        access = await client.get_node(ua.NodeId("P101.MOTOR_TEMP", idx)).read_attribute(ua.AttributeIds.UserAccessLevel)
        assert access.Value.Value == 1  # solo CurrentRead


def test_seqlock_rule():
    assert is_coherent(4, 4)
    assert not is_coherent(5, 5)  # impar: lote en actualizacion
    assert not is_coherent(4, 6)  # cambio durante la lectura
    assert not is_coherent(None, None)


async def test_batches_read_under_fast_updates_are_coherent(runtime_factory):
    """Con el servidor actualizando rapido, toda muestra aceptada pertenece a un unico lote."""
    runtime = await runtime_factory(tick_s=0.1, steps_per_tick=3)
    names = ["RUN.SNAPSHOT_SEQ"] + [t.name for t in BATCH_TAGS] + ["RUN.SNAPSHOT_SEQ"]
    accepted = rejected = 0
    async with Client(runtime.settings.opcua_endpoint, timeout=4) as client:
        idx = await client.get_namespace_index(NAMESPACE_URI)
        nodes = [client.get_node(ua.NodeId(n, idx)) for n in names]
        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            dvs = await client.read_attributes(nodes, ua.AttributeIds.Value)
            if is_coherent(dvs[0].Value.Value, dvs[-1].Value.Value):
                accepted += 1
                stamps = {dv.SourceTimestamp for dv in dvs[1:-1]}
                assert len(stamps) == 1, "accepted batch mixes two publications"
                assert dvs[0].SourceTimestamp in stamps
            else:
                rejected += 1
    assert accepted > 50
    print(f"coherent batches accepted={accepted} rejected={rejected}")


async def test_full_scenario_observed_through_real_opcua_client(runtime_factory):
    """NORMAL -> (DEGRADATION) -> WARNING -> ALARM visto solo por OPC UA, con tiempo simulado acelerado."""
    runtime = await runtime_factory(tick_s=0.1, steps_per_tick=20)  # 2 s simulados por tick
    poller = OpcUaPoller(runtime.settings.opcua_endpoint, sample_s=0.05, stale_after_s=2.0)
    poller.start()
    try:
        await wait_for(lambda: poller.state.sample is not None)
        assert poller.state.sample.tags["P101.ALARM_LEVEL"]["value"] == "NORMAL"
        runtime.simulator.inject_fault()
        assert runtime.simulator.mode == "DEGRADATION"
        seen: list[str] = []
        temps_at: dict[str, float] = {}

        def observe() -> bool:
            sample = poller.state.sample
            level = sample.tags["P101.ALARM_LEVEL"]["value"]
            if not seen or seen[-1] != level:
                seen.append(level)
                temps_at[level] = sample.tags["P101.MOTOR_TEMP"]["value"]
            return level == "ALARM"

        await wait_for(observe, timeout=30)
        assert seen == ["NORMAL", "WARNING", "ALARM"], seen
        sample = poller.state.sample
        assert sample.tags["P101.STATUS"]["value"] == "RUNNING"
        assert sample.tags["P101.ACTIVE_ALARMS"]["value"]
        assert sample.tags["P101.VIBRATION"]["unit"] == "mm/s"  # unidad leida del servidor
        assert poller.state.limits["P101.VIBRATION.HIHI"] == 7.1
        assert_no_leak(str(poller.public_view()))
    finally:
        await poller.stop()
