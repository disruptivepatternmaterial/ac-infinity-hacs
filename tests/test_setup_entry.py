"""Tests for setup-module helpers: _read_ports precedence and unload platforms.

The package __init__ is stubbed by conftest (so importing the package doesn't
cascade), so the real custom_components/ac_infinity_ble/__init__.py is loaded
here explicitly via importlib under the package's namespace, which keeps its
relative imports working against the same stubs the other tests use.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.ac_infinity_ble.const import CONF_PORTS, DOMAIN
from custom_components.ac_infinity_ble.models import ACInfinityData

ADDR = "AA:BB:CC:DD:EE:FF"
PORTS_RAW = [{"port": 1, "kind": "fan", "name": "Fan 1"}]


def _load_integration_init():
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "custom_components",
        "ac_infinity_ble",
        "__init__.py",
    )
    spec = importlib.util.spec_from_file_location(
        "custom_components.ac_infinity_ble.integration_init", path
    )
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the module's relative imports resolve.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


integration_init = _load_integration_init()


def _entry(options: dict | None = None, data: dict | None = None):
    return SimpleNamespace(
        entry_id="entry-1", options=options or {}, data=data or {}
    )


class TestReadPorts:
    def test_data_ports_used_when_options_absent(self):
        ports = integration_init._read_ports(_entry(data={CONF_PORTS: PORTS_RAW}))
        assert [p.port for p in ports] == [1]

    def test_options_ports_take_precedence(self):
        ports = integration_init._read_ports(
            _entry(
                options={CONF_PORTS: [{"port": 2, "kind": "fan", "name": "F2"}]},
                data={CONF_PORTS: PORTS_RAW},
            )
        )
        assert [p.port for p in ports] == [2]

    def test_explicit_empty_options_list_clears_data_ports(self):
        """ports: [] in options must clear the map, not fall through to data."""
        ports = integration_init._read_ports(
            _entry(options={CONF_PORTS: []}, data={CONF_PORTS: PORTS_RAW})
        )
        assert ports == []


class TestDetachContaminatedDevice:
    def test_clean_device_not_contaminated(self):
        device = SimpleNamespace(
            identifiers={(DOMAIN, ADDR)},
            connections={("bluetooth", ADDR)},
        )
        assert integration_init._device_is_contaminated(device, ADDR) is False

    def test_foreign_identifier_is_contaminated(self):
        device = SimpleNamespace(
            identifiers={(DOMAIN, ADDR), ("yalexs_ble", "L5V810063E")},
            connections={("bluetooth", ADDR), ("bluetooth", "78:9C:85:34:72:C4")},
        )
        assert integration_init._device_is_contaminated(device, ADDR) is True

    def test_detach_strips_our_identity_and_config_entry(self):
        device = SimpleNamespace(
            id="lock-device",
            name="L50063E",
            name_by_user="Back Door Lock",
            model="ASL-05",
            identifiers={
                (DOMAIN, ADDR),
                ("yalexs_ble", "L5V810063E"),
                ("august", "abc"),
            },
            connections={
                ("bluetooth", ADDR),
                ("bluetooth", "78:9C:85:34:72:C4"),
            },
            config_entries={"entry-1", "august-entry"},
        )
        updated = {}

        def _update(device_id, **kwargs):
            updated["device_id"] = device_id
            updated.update(kwargs)
            return device

        registry = SimpleNamespace(
            async_get_device=MagicMock(return_value=device),
            async_update_device=_update,
        )
        hass = SimpleNamespace()
        # Patch the stub registry used by the loaded module.
        import homeassistant.helpers.device_registry as dr

        original = dr.async_get
        dr.async_get = MagicMock(return_value=registry)
        try:
            entry = _entry(data={"address": ADDR})
            assert (
                integration_init._async_detach_from_contaminated_device(
                    hass, entry, ADDR
                )
                is True
            )
        finally:
            dr.async_get = original

        assert updated["device_id"] == "lock-device"
        assert updated["new_identifiers"] == {
            ("yalexs_ble", "L5V810063E"),
            ("august", "abc"),
        }
        assert updated["new_connections"] == {("bluetooth", "78:9C:85:34:72:C4")}
        assert updated["remove_config_entry_id"] == "entry-1"

    def test_detach_noop_for_clean_device(self):
        device = SimpleNamespace(
            id="aci-device",
            identifiers={(DOMAIN, ADDR)},
            connections={("bluetooth", ADDR)},
            config_entries={"entry-1"},
        )
        registry = SimpleNamespace(
            async_get_device=MagicMock(return_value=device),
            async_update_device=MagicMock(),
        )
        import homeassistant.helpers.device_registry as dr

        original = dr.async_get
        dr.async_get = MagicMock(return_value=registry)
        try:
            assert (
                integration_init._async_detach_from_contaminated_device(
                    SimpleNamespace(), _entry(data={"address": ADDR}), ADDR
                )
                is False
            )
        finally:
            dr.async_get = original
        registry.async_update_device.assert_not_called()

    def test_detach_scrubs_connection_hit_even_if_identifier_clean(self):
        clean = SimpleNamespace(
            id="aci-device",
            name="G-SGR1J",
            name_by_user="Library AC Infinity",
            model="Controller 69 Pro",
            identifiers={(DOMAIN, ADDR)},
            connections={("bluetooth", ADDR)},
            config_entries={"entry-1"},
        )
        lock = SimpleNamespace(
            id="lock-device",
            name="L50063E",
            name_by_user="Back Door Lock",
            model="ASL-05",
            identifiers={("yalexs_ble", "L5V810063E")},
            connections={
                ("bluetooth", ADDR),
                ("bluetooth", "78:9C:85:34:72:C4"),
            },
            config_entries={"august-entry"},
        )
        updated = []

        def _get_device(*, identifiers=None, connections=None):
            if identifiers:
                return clean
            if connections:
                return lock
            return None

        registry = SimpleNamespace(
            async_get_device=_get_device,
            async_update_device=lambda device_id, **kwargs: updated.append(
                (device_id, kwargs)
            ),
        )
        import homeassistant.helpers.device_registry as dr

        original = dr.async_get
        dr.async_get = MagicMock(return_value=registry)
        try:
            assert (
                integration_init._async_detach_from_contaminated_device(
                    SimpleNamespace(), _entry(data={"address": ADDR}), ADDR
                )
                is True
            )
        finally:
            dr.async_get = original

        assert len(updated) == 1
        assert updated[0][0] == "lock-device"
        assert updated[0][1]["new_connections"] == {
            ("bluetooth", "78:9C:85:34:72:C4")
        }

    def test_rebind_moves_entities_to_clean_device(self):
        device = SimpleNamespace(
            id="aci-device",
            name="G-SGR1J",
            name_by_user="Library AC Infinity",
            identifiers={(DOMAIN, ADDR)},
            connections={("bluetooth", ADDR)},
        )
        updated = []
        ent_reg = SimpleNamespace(
            async_update_entity=lambda entity_id, **kwargs: updated.append(
                (entity_id, kwargs.get("device_id"))
            )
        )
        import homeassistant.helpers.device_registry as dr
        import homeassistant.helpers.entity_registry as er

        old_dr_get, old_er_get, old_entries = (
            dr.async_get,
            er.async_get,
            er.async_entries_for_config_entry,
        )
        dr.async_get = MagicMock(
            return_value=SimpleNamespace(async_get_device=MagicMock(return_value=device))
        )
        er.async_get = MagicMock(return_value=ent_reg)
        er.async_entries_for_config_entry = MagicMock(
            return_value=[
                SimpleNamespace(entity_id="fan.library_ac_infinity_fan", device_id="lock"),
                SimpleNamespace(
                    entity_id="sensor.library_ac_infinity_temperature",
                    device_id="aci-device",
                ),
            ]
        )
        try:
            moved = integration_init._async_rebind_entry_entities(
                SimpleNamespace(), _entry(data={"address": ADDR}), ADDR
            )
        finally:
            dr.async_get, er.async_get = old_dr_get, old_er_get
            er.async_entries_for_config_entry = old_entries

        assert moved == 1
        assert updated == [("fan.library_ac_infinity_fan", "aci-device")]


class TestUnloadEntry:
    def _hass(self, data: ACInfinityData):
        ble_manager = MagicMock()
        hass = SimpleNamespace(
            data={DOMAIN: {"entry-1": data, "ble_manager": ble_manager}},
            config_entries=SimpleNamespace(
                async_unload_platforms=AsyncMock(return_value=True)
            ),
        )
        return hass, ble_manager

    def test_unload_uses_setup_time_platforms(self):
        data = ACInfinityData(
            "t", MagicMock(), MagicMock(), [], ["sensor", "fan", "light"]
        )
        hass, ble_manager = self._hass(data)
        entry = _entry(data={"address": ADDR})

        assert asyncio.run(integration_init.async_unload_entry(hass, entry)) is True
        hass.config_entries.async_unload_platforms.assert_awaited_once_with(
            entry, ["sensor", "fan", "light"]
        )
        ble_manager.clear_address.assert_called_once_with(ADDR)
        assert "entry-1" not in hass.data[DOMAIN]

    def test_failed_unload_keeps_entry_data(self):
        data = ACInfinityData("t", MagicMock(), MagicMock(), [], ["sensor"])
        hass, ble_manager = self._hass(data)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = _entry(data={"address": ADDR})

        assert asyncio.run(integration_init.async_unload_entry(hass, entry)) is False
        ble_manager.clear_address.assert_not_called()
        assert "entry-1" in hass.data[DOMAIN]
