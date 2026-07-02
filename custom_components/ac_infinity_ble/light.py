"""The ac_infinity grow-light platform.

A UIS grow light plugged into a controller port responds to the same
``set_level`` protocol as a fan: work_type 2 = on, work_type 1 = off, and the
0-10 level acts as brightness. This platform exposes such a port as a dimmable
light, scaling the 0-10 device level onto Home Assistant's 0-255 brightness.
"""
from __future__ import annotations

import math
from time import monotonic
from typing import Any

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_MODEL, DOMAIN, PORT_KIND_LIGHT, PORT_LEVEL_MAX
from .const import WRITE_COALESCE_SECONDS
from .controller import MultiPortController
from .coordinator import ACInfinityDataUpdateCoordinator
from .models import ACInfinityData, PortConfig


def _level_to_brightness(level: int) -> int:
    return min(255, round(level / PORT_LEVEL_MAX * 255))


def _brightness_to_level(brightness: int) -> int:
    return max(1, min(PORT_LEVEL_MAX, math.ceil(brightness / 255 * PORT_LEVEL_MAX)))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC Infinity light platform."""
    data: ACInfinityData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ACInfinityGrowLight(data.coordinator, data.device, entry.title, port)
        for port in data.ports
        if port.kind == PORT_KIND_LIGHT
    )


class ACInfinityGrowLight(
    PassiveBluetoothCoordinatorEntity[ACInfinityDataUpdateCoordinator], LightEntity
):
    """A grow light bound to a fixed UIS port on a multi-port controller."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: ACInfinityDataUpdateCoordinator,
        device: MultiPortController,
        name: str,
        port: PortConfig,
    ) -> None:
        """Initialize a per-port AC Infinity grow light."""
        super().__init__(coordinator)
        self._device = device
        self._port = port.port
        self._attr_name = port.name
        self._attr_unique_id = f"{device.address}_port{port.port}_light"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            model=DEVICE_MODEL.get(device.state.type),
            manufacturer="AC Infinity",
            sw_version=str(device.state.version),
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
        )
        self._last_write_signature: tuple[int, int] | None = None
        self._last_write_at = 0.0
        self._async_update_attrs()

    def _port_state(self):
        return self._device.port_states.get(self._port)

    def _is_duplicate_write(self, work_type: int, level: int) -> bool:
        """Return True if an identical command was written within the window."""
        return (
            self._last_write_signature == (work_type, level)
            and monotonic() - self._last_write_at <= WRITE_COALESCE_SECONDS
        )

    def _record_write(self, work_type: int, level: int) -> None:
        """Record a successful write so rapid duplicates are coalesced."""
        self._last_write_signature = (work_type, level)
        self._last_write_at = monotonic()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the grow light, optionally at a brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            level = _brightness_to_level(kwargs[ATTR_BRIGHTNESS])
        else:
            state = self._port_state()
            level = (state.level_on if state else None) or PORT_LEVEL_MAX
        if self._is_duplicate_write(2, level):
            return
        await self._device.set_port_level(self._port, 2, level)
        self._record_write(2, level)
        self._async_update_attrs()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the grow light."""
        if self._is_duplicate_write(1, 0):
            return
        await self._device.set_port_level(self._port, 1, 0)
        self._record_write(1, 0)
        self._async_update_attrs()
        self.async_write_ha_state()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        state = self._port_state()
        if state is None or state.work_type is None:
            # Port never polled or commanded (MultiPortController seeds an
            # empty PortState per port): unknown, not off/0 brightness.
            self._attr_is_on = None
            self._attr_brightness = None
            return
        self._attr_is_on = state.is_on
        level = state.level
        self._attr_brightness = _level_to_brightness(level) if level > 0 else 0

    @callback
    def _handle_coordinator_update(self, *args: Any) -> None:
        """Handle data update."""
        self._async_update_attrs()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            self._device.register_callback(self._handle_coordinator_update)
        )
        return await super().async_added_to_hass()
