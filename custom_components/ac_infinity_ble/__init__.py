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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .ble_manager import ACInfinityBLEManager
from .const import CONF_PORTS, DOMAIN, PORT_CAPABLE_TYPES, PORT_KIND_LIGHT
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
from .debug_ndjson import agent_log
from .models import ACInfinityData, PortConfig

_LOGGER = logging.getLogger(__name__)


def _read_ports(entry: ConfigEntry) -> list[PortConfig]:
    """Read the per-port map from an entry's options or data, if present.

    Presence-based (options first, then data) so an explicit empty list in
    options clears a port map stored in data instead of falling through to it.
    """
    raw = _read_entry_option(entry, CONF_PORTS, []) or []
    return [PortConfig(**p) for p in raw]


def _read_entry_option(entry: ConfigEntry, key: str, default):
    """Read option value from options first, then data, then default."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _device_is_contaminated(device: dr.DeviceEntry, address: str) -> bool:
    """Return True if this registry device also belongs to another integration."""
    address = address.upper()
    if any(ident[0] != DOMAIN for ident in device.identifiers):
        return True
    return any(
        conn[0] == dr.CONNECTION_BLUETOOTH and conn[1].upper() != address
        for conn in device.connections
    )


@callback
def _async_detach_from_contaminated_device(
    hass: HomeAssistant, entry: ConfigEntry, address: str
) -> bool:
    """Strip our identity off a device shared with another integration.

    Connections-only DeviceInfo previously let HA merge the Library controller
    onto an August lock that already claimed a bluetooth connection. Once
    merged, even adding identifiers only updates the contaminated record.
    Detach first so entity DeviceInfo can create a clean AC Infinity device.
    """
    address = address.upper()
    dev_reg = dr.async_get(hass)
    # Check identifier and connection matches separately: a clean identifier
    # hit must not hide a still-contaminated connection on another device.
    candidates: list[dr.DeviceEntry] = []
    seen_ids: set[str] = set()
    for device in (
        dev_reg.async_get_device(identifiers={(DOMAIN, address)}),
        dev_reg.async_get_device(
            connections={(dr.CONNECTION_BLUETOOTH, address)}
        ),
    ):
        if device is not None and device.id not in seen_ids:
            seen_ids.add(device.id)
            candidates.append(device)

    detached = False
    for device in candidates:
        if not _device_is_contaminated(device, address):
            continue

        new_identifiers = {
            ident for ident in device.identifiers if ident[0] != DOMAIN
        }
        new_connections = {
            conn
            for conn in device.connections
            if not (
                conn[0] == dr.CONNECTION_BLUETOOTH and conn[1].upper() == address
            )
        }
        update_kwargs: dict = {
            "new_identifiers": new_identifiers,
            "new_connections": new_connections,
        }
        if entry.entry_id in device.config_entries:
            update_kwargs["remove_config_entry_id"] = entry.entry_id

        _LOGGER.warning(
            "%s: detaching from contaminated device %s (%s / %s); "
            "entities will rebind to a dedicated AC Infinity device",
            address,
            device.id,
            device.name_by_user or device.name,
            device.model,
        )
        # #region agent log
        agent_log(
            "H5",
            "__init__.py:_async_detach_from_contaminated_device",
            "detaching from contaminated device",
            {
                "address": address,
                "device_id": device.id,
                "device_name": device.name_by_user or device.name,
                "device_model": device.model,
                "old_identifiers": list(device.identifiers),
                "old_connections": list(device.connections),
                "new_identifiers": list(new_identifiers),
                "new_connections": list(new_connections),
                "removed_config_entry": entry.entry_id
                if entry.entry_id in device.config_entries
                else None,
            },
            run_id="post-fix",
        )
        # #endregion
        dev_reg.async_update_device(device.id, **update_kwargs)
        detached = True
    return detached


@callback
def _async_rebind_entry_entities(
    hass: HomeAssistant, entry: ConfigEntry, address: str
) -> int:
    """Move this entry's entities onto the dedicated AC Infinity device.

    Detaching identifiers/connections from a contaminated device is not always
    enough: the entity registry can keep the old device_id until explicitly
    updated.
    """
    address = address.upper()
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(
        identifiers={(DOMAIN, address)}
    ) or dev_reg.async_get_device(
        connections={(dr.CONNECTION_BLUETOOTH, address)}
    )
    if device is None or _device_is_contaminated(device, address):
        return 0

    ent_reg = er.async_get(hass)
    moved = 0
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.device_id == device.id:
            continue
        ent_reg.async_update_entity(ent.entity_id, device_id=device.id)
        moved += 1
    if moved:
        _LOGGER.info(
            "%s: rebound %s entities to device %s (%s)",
            address,
            moved,
            device.id,
            device.name_by_user or device.name,
        )
        # #region agent log
        agent_log(
            "H5",
            "__init__.py:_async_rebind_entry_entities",
            "rebound entities to clean device",
            {
                "address": address,
                "device_id": device.id,
                "device_name": device.name_by_user or device.name,
                "moved": moved,
            },
            run_id="post-fix",
        )
        # #endregion
    return moved


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
    if ports and device_info.type not in PORT_CAPABLE_TYPES:
        # The protocol drops the port byte for these types, so per-port
        # entities would all drive the same load. Refuse the map loudly.
        _LOGGER.warning(
            "%s: device type %s does not support per-port addressing; "
            "ignoring configured ports %s and using single-port control",
            address,
            device_info.type,
            [p.port for p in ports],
        )
        ports = []
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
        entry.title, controller, coordinator, ports, platforms
    )

    entry.async_on_unload(coordinator.async_start())
    if not await coordinator.async_wait_ready():
        _LOGGER.warning(
            "%s not advertising at setup; entities restored and will refresh on advertisements",
            address,
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    detached = _async_detach_from_contaminated_device(hass, entry, address)
    # #region agent log
    dev_reg = dr.async_get(hass)
    by_conn = dev_reg.async_get_device(
        connections={(dr.CONNECTION_BLUETOOTH, address.upper())}
    )
    by_ident = dev_reg.async_get_device(identifiers={(DOMAIN, address.upper())})
    agent_log(
        "H1",
        "__init__.py:async_setup_entry",
        "setup device registry lookup",
        {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "address": address.upper(),
            "device_name": getattr(device_info, "name", None),
            "device_type": getattr(device_info, "type", None),
            "detached_contaminated": detached,
            "by_conn_id": getattr(by_conn, "id", None),
            "by_conn_name": getattr(by_conn, "name_by_user", None)
            or getattr(by_conn, "name", None),
            "by_conn_model": getattr(by_conn, "model", None),
            "by_conn_mfr": getattr(by_conn, "manufacturer", None),
            "by_conn_identifiers": list(getattr(by_conn, "identifiers", []) or []),
            "by_conn_connections": list(getattr(by_conn, "connections", []) or []),
            "by_ident_id": getattr(by_ident, "id", None),
            "by_ident_name": getattr(by_ident, "name_by_user", None)
            or getattr(by_ident, "name", None),
            "by_ident_model": getattr(by_ident, "model", None),
            "by_ident_mfr": getattr(by_ident, "manufacturer", None),
            "same_device": bool(
                by_conn and by_ident and by_conn.id == by_ident.id
            ),
            "merged_with_foreign": bool(
                by_conn is not None and _device_is_contaminated(by_conn, address)
            ),
        },
        run_id="post-fix",
    )
    # #endregion
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    _async_rebind_entry_entities(hass, entry, address)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Use the platform list recorded at setup, not one recomputed from the
    # entry's current data/options, which may have changed since setup.
    data: ACInfinityData = hass.data[DOMAIN][entry.entry_id]
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, data.platforms
    ):
        ble_manager: ACInfinityBLEManager = hass.data[DOMAIN]["ble_manager"]
        ble_manager.clear_address(entry.data[CONF_ADDRESS])
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
