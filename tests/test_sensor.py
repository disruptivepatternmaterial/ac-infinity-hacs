"""Tests for ac_infinity_ble sensor data fidelity.

Verifies that temperature, humidity, and VPD sensors pass through
raw state values (including None) without fabricating 0 for missing readings.
"""
from __future__ import annotations

# conftest.py stubs HA and upstream library before these imports.
from unittest.mock import MagicMock

from custom_components.ac_infinity_ble.sensor import (
    HumiditySensor,
    TemperatureSensor,
    VpdSensor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sensor_instance(cls, tmp=None, hum=None, vpd=None):
    """Create a bare sensor with a mocked device, bypassing __init__."""
    state = MagicMock()
    state.tmp = tmp
    state.hum = hum
    state.vpd = vpd

    device = MagicMock()
    device.state = state

    sensor = object.__new__(cls)
    sensor._device = device
    sensor._attr_native_value = None
    sensor._async_update_attrs()
    return sensor


# ---------------------------------------------------------------------------
# TemperatureSensor
# ---------------------------------------------------------------------------

class TestTemperatureSensor:
    def test_none_when_state_tmp_is_none(self):
        s = _make_sensor_instance(TemperatureSensor, tmp=None)
        assert s._attr_native_value is None

    def test_passthrough_when_state_tmp_is_zero(self):
        s = _make_sensor_instance(TemperatureSensor, tmp=0.0)
        assert s._attr_native_value == 0.0

    def test_passthrough_real_value(self):
        s = _make_sensor_instance(TemperatureSensor, tmp=22.5)
        assert s._attr_native_value == 22.5

    def test_does_not_use_upstream_temperature_property(self):
        """device.temperature (upstream) returns 0 for None; sensor must not use it."""
        state = MagicMock()
        state.tmp = None
        device = MagicMock()
        device.state = state
        device.temperature = 0  # what the upstream property fabricates

        s = object.__new__(TemperatureSensor)
        s._device = device
        s._attr_native_value = "sentinel"
        s._async_update_attrs()

        assert s._attr_native_value is None


# ---------------------------------------------------------------------------
# HumiditySensor
# ---------------------------------------------------------------------------

class TestHumiditySensor:
    def test_none_when_state_hum_is_none(self):
        s = _make_sensor_instance(HumiditySensor, hum=None)
        assert s._attr_native_value is None

    def test_passthrough_when_state_hum_is_zero(self):
        s = _make_sensor_instance(HumiditySensor, hum=0.0)
        assert s._attr_native_value == 0.0

    def test_passthrough_real_value(self):
        s = _make_sensor_instance(HumiditySensor, hum=65.3)
        assert s._attr_native_value == 65.3

    def test_does_not_use_upstream_humidity_property(self):
        state = MagicMock()
        state.hum = None
        device = MagicMock()
        device.state = state
        device.humidity = 0

        s = object.__new__(HumiditySensor)
        s._device = device
        s._attr_native_value = "sentinel"
        s._async_update_attrs()

        assert s._attr_native_value is None


# ---------------------------------------------------------------------------
# VpdSensor
# ---------------------------------------------------------------------------

class TestVpdSensor:
    def test_none_when_state_vpd_is_none(self):
        s = _make_sensor_instance(VpdSensor, vpd=None)
        assert s._attr_native_value is None

    def test_passthrough_when_state_vpd_is_zero(self):
        s = _make_sensor_instance(VpdSensor, vpd=0.0)
        assert s._attr_native_value == 0.0

    def test_passthrough_real_value(self):
        s = _make_sensor_instance(VpdSensor, vpd=1.2)
        assert s._attr_native_value == 1.2

    def test_does_not_use_upstream_vpd_property(self):
        state = MagicMock()
        state.vpd = None
        device = MagicMock()
        device.state = state
        device.vpd = 0

        s = object.__new__(VpdSensor)
        s._device = device
        s._attr_native_value = "sentinel"
        s._async_update_attrs()

        assert s._attr_native_value is None

