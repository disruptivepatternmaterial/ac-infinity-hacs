"""The ac_infinity integration."""
from __future__ import annotations

import logging

from ac_infinity_ble import DeviceInfo

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_SERVICE_DATA,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PORTS, DOMAIN, PORT_KIND_LIGHT
from .controller import MultiPortController, PortAwareController
from .coordinator import ACInfinityDataUpdateCoordinator
from .models import ACInfinityData, PortConfig

_LOGGER = logging.getLogger(__name__)


def _read_ports(entry: ConfigEntry) -> list[PortConfig]:
    """Read the per-port map from an entry's options or data, if present."""
    raw = entry.options.get(CONF_PORTS) or entry.data.get(CONF_PORTS) or []
    return [PortConfig(**p) for p in raw]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ac_infinity from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), True)
    if not ble_device:
        raise ConfigEntryNotReady(
            f"Could not find AC Infinity device with address {address}"
        )

    device_info: DeviceInfo | dict = entry.data[CONF_SERVICE_DATA]
    if type(device_info) is dict:
        device_info = DeviceInfo(**entry.data[CONF_SERVICE_DATA])

    ports = _read_ports(entry)
    if ports:
        controller = MultiPortController(
            ble_device, device_info, ports=[p.port for p in ports]
        )
        platforms = [Platform.FAN, Platform.SENSOR]
        if any(p.kind == PORT_KIND_LIGHT for p in ports):
            platforms.append(Platform.LIGHT)
    else:
        controller = PortAwareController(ble_device, device_info)
        platforms = [Platform.SENSOR, Platform.FAN]

    coordinator = ACInfinityDataUpdateCoordinator(hass, _LOGGER, ble_device, controller)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = ACInfinityData(
        entry.title, controller, coordinator, ports
    )

    entry.async_on_unload(coordinator.async_start())
    if not await coordinator.async_wait_ready():
        raise ConfigEntryNotReady(f"{address} is not advertising state")

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


def _entry_platforms(entry: ConfigEntry) -> list[Platform]:
    """Recompute the platform list an entry was set up with."""
    ports = _read_ports(entry)
    if not ports:
        return [Platform.SENSOR, Platform.FAN]
    platforms = [Platform.FAN, Platform.SENSOR]
    if any(p.kind == PORT_KIND_LIGHT for p in ports):
        platforms.append(Platform.LIGHT)
    return platforms


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    data: ACInfinityData = hass.data[DOMAIN][entry.entry_id]
    if entry.title != data.title:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = _entry_platforms(entry)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
