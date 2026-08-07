"""The ac_infinity sensor platform."""
from __future__ import annotations
from typing import Any

from ac_infinity_ble import ACInfinityController

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.const import UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_MODEL, DOMAIN
from .coordinator import ACInfinityDataUpdateCoordinator
from .models import ACInfinityData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC Infinity sensor platform."""
    data: ACInfinityData = hass.data[DOMAIN][entry.entry_id]
    entities = [
        TemperatureSensor(data.coordinator, data.device, entry.title),
        HumiditySensor(data.coordinator, data.device, entry.title),
        BLELastRSSISensor(data.coordinator, data.device, entry.title),
        BLELastSeenSensor(data.coordinator, data.device, entry.title),
        BLELastErrorSensor(data.coordinator, data.device, entry.title),
        BLEPollFailuresSensor(data.coordinator, data.device, entry.title),
    ]
    if data.device.state.version >= 3 and data.device.state.type in [7, 9, 11, 12]:
        entities.append(VpdSensor(data.coordinator, data.device, entry.title))
    async_add_entities(entities)


class ACInfinitySensor(
    PassiveBluetoothCoordinatorEntity[ACInfinityDataUpdateCoordinator], SensorEntity
):
    """Representation of AC Infinity sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ACInfinityDataUpdateCoordinator,
        device: ACInfinityController,
        name: str,
    ) -> None:
        """Initialize an AC Infinity sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = DeviceInfo(
            name=device.name,
            model=DEVICE_MODEL.get(device.state.type),
            manufacturer="AC Infinity",
            sw_version=str(device.state.version),
            # identifiers pin our entities to our own device record even if
            # another integration (e.g. august cloud) claims this MAC as a
            # connection on its device; connections-only DeviceInfo re-homed
            # entities onto a lock device on 2026-08-01 (see SPEC.md).
            identifiers={(DOMAIN, device.address)},
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
        )
        self._async_update_attrs()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        raise NotImplementedError("Not yet implemented.")

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


class TemperatureSensor(ACInfinitySensor):
    _attr_name = "Temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return f"{self._device.address}_tmp"

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        self._attr_native_value = self._device.state.tmp


class HumiditySensor(ACInfinitySensor):
    _attr_name = "Humidity"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return f"{self._device.address}_hum"

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        self._attr_native_value = self._device.state.hum


class VpdSensor(ACInfinitySensor):
    _attr_name = "VPD"
    _attr_native_unit_of_measurement = UnitOfPressure.KPA
    _attr_device_class = SensorDeviceClass.ATMOSPHERIC_PRESSURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return f"{self._device.address}_vpd"

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        self._attr_native_value = self._device.state.vpd


class BLELastRSSISensor(ACInfinitySensor):
    _attr_name = "BLE Last RSSI"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth"

    @property
    def unique_id(self) -> str:
        return f"{self._device.address}_ble_last_rssi"

    @callback
    def _async_update_attrs(self) -> None:
        self._attr_native_value = self.coordinator.ble_manager.stats(
            self._device.address
        ).last_rssi


class BLELastSeenSensor(ACInfinitySensor):
    _attr_name = "BLE Last Seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._device.address}_ble_last_seen"

    @callback
    def _async_update_attrs(self) -> None:
        last_seen = self.coordinator.ble_manager.stats(self._device.address).last_seen
        self._attr_native_value = last_seen


class BLELastErrorSensor(ACInfinitySensor):
    _attr_name = "BLE Last Error"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._device.address}_ble_last_error"

    @callback
    def _async_update_attrs(self) -> None:
        self._attr_native_value = self.coordinator.ble_manager.stats(
            self._device.address
        ).last_error


class BLEPollFailuresSensor(ACInfinitySensor):
    _attr_name = "BLE Poll Failures"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    @property
    def unique_id(self) -> str:
        return f"{self._device.address}_ble_poll_failures"

    @callback
    def _async_update_attrs(self) -> None:
        self._attr_native_value = self.coordinator.ble_manager.stats(
            self._device.address
        ).poll_failures
