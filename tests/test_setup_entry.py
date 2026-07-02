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
