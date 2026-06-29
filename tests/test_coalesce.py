"""Tests for fan/light write coalescing.

A successful duplicate command within WRITE_COALESCE_SECONDS is suppressed, but
a command that FAILS must never poison the cache: an immediate identical retry
must still be sent. conftest.py stubs HA + upstream so the real entity classes
import; instances are built with object.__new__ to bypass HA's __init__.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.ac_infinity_ble.fan import ACInfinityFan, ACInfinityPortFan
from custom_components.ac_infinity_ble.light import ACInfinityGrowLight


def _bare(cls):
    obj = object.__new__(cls)
    obj._device = MagicMock()
    obj._port = 1
    obj._last_write_speed = None
    obj._last_write_signature = None
    obj._last_write_at = 0.0
    obj._async_update_attrs = lambda: None
    obj.async_write_ha_state = lambda *a, **k: None
    return obj


class TestSinglePortFanCoalescing:
    def test_duplicate_successful_write_is_skipped(self):
        calls = []

        async def set_speed(speed):
            calls.append(speed)

        fan = _bare(ACInfinityFan)
        fan._device.set_speed = set_speed
        asyncio.run(fan.async_set_percentage(50))
        asyncio.run(fan.async_set_percentage(50))
        assert calls == [5]

    def test_failed_write_does_not_block_retry(self):
        calls = []

        async def set_speed(speed):
            calls.append(speed)
            raise RuntimeError("ble fail")

        fan = _bare(ACInfinityFan)
        fan._device.set_speed = set_speed
        with pytest.raises(RuntimeError):
            asyncio.run(fan.async_set_percentage(50))
        with pytest.raises(RuntimeError):
            asyncio.run(fan.async_set_percentage(50))
        assert calls == [5, 5]


class TestPortFanCoalescing:
    def test_failed_write_does_not_block_retry(self):
        calls = []

        async def set_port_level(port, work_type, level):
            calls.append((port, work_type, level))
            raise RuntimeError("ble fail")

        fan = _bare(ACInfinityPortFan)
        fan._device.set_port_level = set_port_level
        for _ in range(2):
            with pytest.raises(RuntimeError):
                asyncio.run(fan.async_set_percentage(50))
        assert calls == [(1, 2, 5), (1, 2, 5)]

    def test_duplicate_successful_write_is_skipped(self):
        calls = []

        async def set_port_level(port, work_type, level):
            calls.append((port, work_type, level))

        fan = _bare(ACInfinityPortFan)
        fan._device.set_port_level = set_port_level
        asyncio.run(fan.async_set_percentage(50))
        asyncio.run(fan.async_set_percentage(50))
        assert calls == [(1, 2, 5)]


class TestGrowLightCoalescing:
    def test_failed_write_does_not_block_retry(self):
        calls = []

        async def set_port_level(port, work_type, level):
            calls.append((port, work_type, level))
            raise RuntimeError("ble fail")

        light = _bare(ACInfinityGrowLight)
        light._device.set_port_level = set_port_level
        for _ in range(2):
            with pytest.raises(RuntimeError):
                asyncio.run(light.async_turn_off())
        assert calls == [(1, 1, 0), (1, 1, 0)]
