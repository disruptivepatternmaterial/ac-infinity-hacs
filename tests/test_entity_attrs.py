"""Tests for fan/light attribute derivation, esp. unknown-vs-zero fidelity.

A reading that was never observed must surface as None (HA "unknown"), never
as a fabricated 0% / off. A real 0 must stay 0.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.ac_infinity_ble.fan import ACInfinityFan, ACInfinityPortFan
from custom_components.ac_infinity_ble.light import ACInfinityGrowLight
from custom_components.ac_infinity_ble.models import PortState


def _bare(cls, port_state: PortState | None):
    obj = object.__new__(cls)
    obj._device = MagicMock()
    obj._port = 1
    obj._device.port_states = {} if port_state is None else {1: port_state}
    return obj


class TestSingleFanAttrs:
    def _fan(self, fan_value, is_on=False):
        fan = object.__new__(ACInfinityFan)
        fan._device = MagicMock()
        fan._device.is_on = is_on
        fan._device.state = SimpleNamespace(fan=fan_value)
        return fan

    def test_unknown_speed_is_none_not_zero(self):
        fan = self._fan(None)
        fan._async_update_attrs()
        assert fan._attr_percentage is None

    def test_zero_speed_is_real_zero(self):
        fan = self._fan(0)
        fan._async_update_attrs()
        assert fan._attr_percentage == 0

    def test_positive_speed_maps_to_percentage(self):
        fan = self._fan(5)
        fan._async_update_attrs()
        assert fan._attr_percentage == 50


class TestPortFanAttrs:
    def test_unpolled_port_is_unknown(self):
        """MultiPortController seeds empty PortState; work_type None = unknown."""
        fan = _bare(ACInfinityPortFan, PortState())
        fan._async_update_attrs()
        assert fan._attr_is_on is None
        assert fan._attr_percentage is None

    def test_polled_on_port(self):
        fan = _bare(ACInfinityPortFan, PortState(work_type=2, level_on=7))
        fan._async_update_attrs()
        assert fan._attr_is_on is True
        assert fan._attr_percentage == 70

    def test_polled_off_port_is_real_zero(self):
        fan = _bare(ACInfinityPortFan, PortState(work_type=1, level_off=0))
        fan._async_update_attrs()
        assert fan._attr_is_on is False
        assert fan._attr_percentage == 0


class TestGrowLightAttrs:
    def test_unpolled_port_is_unknown(self):
        light = _bare(ACInfinityGrowLight, PortState())
        light._async_update_attrs()
        assert light._attr_is_on is None
        assert light._attr_brightness is None

    def test_polled_on_port(self):
        light = _bare(ACInfinityGrowLight, PortState(work_type=2, level_on=10))
        light._async_update_attrs()
        assert light._attr_is_on is True
        assert light._attr_brightness == 255

    def test_polled_off_port_is_real_zero(self):
        light = _bare(ACInfinityGrowLight, PortState(work_type=1, level_off=0))
        light._async_update_attrs()
        assert light._attr_is_on is False
        assert light._attr_brightness == 0
