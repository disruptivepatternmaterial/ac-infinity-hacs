"""The ac_infinity fan platform."""
from __future__ import annotations

import math
from time import monotonic
from typing import Any

from ac_infinity_ble import ACInfinityController

from homeassistant.components.fan import FanEntity, FanEntityFeature

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    int_states_in_range,
    ranged_value_to_percentage,
    percentage_to_ranged_value,
)

from .const import DEVICE_MODEL, DOMAIN, PORT_KIND_FAN, WRITE_COALESCE_SECONDS
from .controller import MultiPortController
from .coordinator import ACInfinityDataUpdateCoordinator
from .models import ACInfinityData, PortConfig

SPEED_RANGE = (1, 10)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC Infinity fan platform."""
    data: ACInfinityData = hass.data[DOMAIN][entry.entry_id]
    if data.ports:
        async_add_entities(
            ACInfinityPortFan(data.coordinator, data.device, entry.title, port)
            for port in data.ports
            if port.kind == PORT_KIND_FAN
        )
        return
    async_add_entities([ACInfinityFan(data.coordinator, data.device, entry.title)])


class ACInfinityFan(
    PassiveBluetoothCoordinatorEntity[ACInfinityDataUpdateCoordinator], FanEntity
):
    """Representation of AC Infinity sensor."""

    _attr_has_entity_name = True
    _attr_name = "Fan"
    _attr_speed_count = int_states_in_range(SPEED_RANGE)
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: ACInfinityDataUpdateCoordinator,
        device: ACInfinityController,
        name: str,
    ) -> None:
        """Initialize an AC Infinity sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{self._device.address}_fan"
        self._attr_device_info = DeviceInfo(
            name=device.name,
            model=DEVICE_MODEL.get(device.state.type),
            manufacturer="AC Infinity",
            sw_version=str(device.state.version),
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
        )
        self._last_write_speed: int | None = None
        self._last_write_at = 0.0
        self._async_update_attrs()

    def _is_duplicate_write(self, speed: int) -> bool:
        """Return True if an identical speed was written within the window."""
        return (
            self._last_write_speed == speed
            and monotonic() - self._last_write_at <= WRITE_COALESCE_SECONDS
        )

    def _record_write(self, speed: int) -> None:
        """Record a successful write so rapid duplicates are coalesced."""
        self._last_write_speed = speed
        self._last_write_at = monotonic()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        speed = 0
        if percentage > 0:
            speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))

        if self._is_duplicate_write(speed):
            return
        await self._device.set_speed(speed)
        self._record_write(speed)
        self._async_update_attrs()
        self.async_write_ha_state()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        speed = None
        if percentage is not None:
            speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
            if self._is_duplicate_write(speed):
                return
        await self._device.turn_on(speed)
        if speed is not None:
            self._record_write(speed)
        self._async_update_attrs()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        if self._is_duplicate_write(0):
            return
        await self._device.turn_off()
        self._record_write(0)
        self._async_update_attrs()
        self.async_write_ha_state()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        self._attr_is_on = self._device.is_on
        fan_speed = self._device.state.fan
        self._attr_percentage = (
            ranged_value_to_percentage(SPEED_RANGE, fan_speed)
            if fan_speed is not None and fan_speed > 0
            else 0
        )

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


class ACInfinityPortFan(
    PassiveBluetoothCoordinatorEntity[ACInfinityDataUpdateCoordinator], FanEntity
):
    """A fan bound to a fixed UIS port on a multi-port controller."""

    _attr_has_entity_name = True
    _attr_speed_count = int_states_in_range(SPEED_RANGE)
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: ACInfinityDataUpdateCoordinator,
        device: MultiPortController,
        name: str,
        port: PortConfig,
    ) -> None:
        """Initialize a per-port AC Infinity fan."""
        super().__init__(coordinator)
        self._device = device
        self._port = port.port
        self._attr_name = port.name
        self._attr_unique_id = f"{device.address}_port{port.port}_fan"
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

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of this port, as a percentage."""
        if percentage <= 0:
            if self._is_duplicate_write(1, 0):
                return
            await self._device.set_port_level(self._port, 1, 0)
            self._record_write(1, 0)
        else:
            speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
            if self._is_duplicate_write(2, speed):
                return
            await self._device.set_port_level(self._port, 2, speed)
            self._record_write(2, speed)
        self._async_update_attrs()
        self.async_write_ha_state()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on this port."""
        if percentage is not None and percentage > 0:
            speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        else:
            state = self._port_state()
            speed = (state.level_on if state else None) or 10
        if self._is_duplicate_write(2, speed):
            return
        await self._device.set_port_level(self._port, 2, speed)
        self._record_write(2, speed)
        self._async_update_attrs()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off this port."""
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
        self._attr_is_on = bool(state and state.is_on)
        level = state.level if state else 0
        self._attr_percentage = (
            ranged_value_to_percentage(SPEED_RANGE, level) if level > 0 else 0
        )

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
