"""The ac_infinity integration."""
from __future__ import annotations

import logging

from ac_infinity_ble import DeviceInfo
from bleak.backends.device import BLEDevice

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_SERVICE_DATA,
    Platform,
)
from homeassistant.core import HomeAssistant

from .ble_manager import ACInfinityBLEManager
from .const import CONF_PORTS, DOMAIN, PORT_KIND_LIGHT
from .const import (
    CONF_COMMAND_RETRY_COUNT,
    CONF_MIN_CONNECT_GAP_SECONDS,
    CONF_PASSIVE_ONLY,
    CONF_POLL_INTERVAL_SECONDS,
    DEFAULT_COMMAND_RETRY_COUNT,
    DEFAULT_MIN_CONNECT_GAP_SECONDS,
    DEFAULT_PASSIVE_ONLY,
    DEFAULT_POLL_INTERVAL_SECONDS,
)
from .controller import MultiPortController, PortAwareController
from .coordinator import ACInfinityDataUpdateCoordinator
from .models import ACInfinityData, PortConfig

_LOGGER = logging.getLogger(__name__)


def _read_ports(entry: ConfigEntry) -> list[PortConfig]:
    """Read the per-port map from an entry's options or data, if present."""
    raw = entry.options.get(CONF_PORTS) or entry.data.get(CONF_PORTS) or []
    return [PortConfig(**p) for p in raw]


def _read_entry_option(entry: ConfigEntry, key: str, default):
    """Read option value from options first, then data, then default."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ac_infinity from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), True)

    device_info: DeviceInfo | dict = entry.data[CONF_SERVICE_DATA]
    if type(device_info) is dict:
        device_info = DeviceInfo(**entry.data[CONF_SERVICE_DATA])
    if not ble_device:
        # Keep setup resilient across HA restarts: create entities from cached
        # service data even when the controller is not connectable at boot.
        ble_device = BLEDevice(
            address=address.upper(),
            name=device_info.name,
            details={},
            rssi=-127,
        )

    ports = _read_ports(entry)
    command_retry_count = int(
        _read_entry_option(entry, CONF_COMMAND_RETRY_COUNT, DEFAULT_COMMAND_RETRY_COUNT)
    )
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

    ble_manager: ACInfinityBLEManager = hass.data.setdefault(DOMAIN, {}).setdefault(
        "ble_manager", ACInfinityBLEManager()
    )
    min_connect_gap_seconds = int(
        _read_entry_option(
            entry, CONF_MIN_CONNECT_GAP_SECONDS, DEFAULT_MIN_CONNECT_GAP_SECONDS
        )
    )
    poll_interval_seconds = int(
        _read_entry_option(entry, CONF_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS)
    )
    passive_only = bool(_read_entry_option(entry, CONF_PASSIVE_ONLY, DEFAULT_PASSIVE_ONLY))
    ble_manager.configure_address(
        address,
        min_connect_gap_seconds=min_connect_gap_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    controller.set_ble_manager(ble_manager, command_retry_count=command_retry_count)
    coordinator = ACInfinityDataUpdateCoordinator(
        hass,
        _LOGGER,
        ble_device,
        controller,
        ble_manager,
        poll_interval_seconds=poll_interval_seconds,
        passive_only=passive_only,
    )

    hass.data[DOMAIN][entry.entry_id] = ACInfinityData(
        entry.title, controller, coordinator, ports
    )

    entry.async_on_unload(coordinator.async_start())
    if not await coordinator.async_wait_ready():
        _LOGGER.warning(
            "%s not advertising at setup; entities restored and will refresh on advertisements",
            address,
        )

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
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = _entry_platforms(entry)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        ble_manager: ACInfinityBLEManager = hass.data[DOMAIN]["ble_manager"]
        ble_manager.clear_address(entry.data[CONF_ADDRESS])
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
