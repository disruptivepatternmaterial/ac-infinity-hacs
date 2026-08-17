"""Tests for the options flow merge semantics.

Saving the options form must merge over existing entry.options so keys not on
the form (e.g. a manually-added CONF_PORTS list) survive the save.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.ac_infinity_ble.const import (
    CONF_COMMAND_RETRY_COUNT,
    CONF_MIN_CONNECT_GAP_SECONDS,
    CONF_PASSIVE_ONLY,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_PORTS,
)
from custom_components.ac_infinity_ble.options_flow import ACInfinityOptionsFlow

PORTS = [{"port": 1, "kind": "fan", "name": "Fan 1"}]


def _flow(options: dict) -> ACInfinityOptionsFlow:
    entry = SimpleNamespace(options=options, data={})
    flow = ACInfinityOptionsFlow(entry)
    # OptionsFlow base is stubbed to `object` in conftest; capture the entry
    # payload instead of exercising HA's flow machinery.
    flow.async_create_entry = lambda **kwargs: kwargs
    return flow


def _form_input() -> dict:
    return {
        CONF_POLL_INTERVAL_SECONDS: 300,
        CONF_PASSIVE_ONLY: False,
        CONF_MIN_CONNECT_GAP_SECONDS: 3,
        CONF_COMMAND_RETRY_COUNT: 2,
    }


class TestOptionsMerge:
    def test_save_preserves_non_form_keys(self):
        flow = _flow({CONF_PORTS: PORTS, CONF_POLL_INTERVAL_SECONDS: 60})
        result = asyncio.run(flow.async_step_init(_form_input()))
        assert result["data"][CONF_PORTS] == PORTS

    def test_save_applies_form_values_over_existing(self):
        flow = _flow({CONF_POLL_INTERVAL_SECONDS: 60})
        result = asyncio.run(flow.async_step_init(_form_input()))
        assert result["data"][CONF_POLL_INTERVAL_SECONDS] == 300
        assert result["data"][CONF_COMMAND_RETRY_COUNT] == 2

    def test_save_with_empty_existing_options(self):
        flow = _flow({})
        result = asyncio.run(flow.async_step_init(_form_input()))
        assert result["data"] == _form_input()
