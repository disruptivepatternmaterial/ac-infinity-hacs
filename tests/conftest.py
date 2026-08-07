"""Stub all external dependencies so tests run without HA or upstream libs installed."""
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _mod(name: str, **attrs) -> ModuleType:
    m = sys.modules.get(name) or ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# ---------------------------------------------------------------------------
# bleak (needed by ac_infinity_ble upstream and integration __init__)
# ---------------------------------------------------------------------------
_mod("bleak")
_mod("bleak.backends")
_mod("bleak.backends.device", BLEDevice=MagicMock)
_mod("bleak.backends.scanner", AdvertisementData=MagicMock)
_mod("bleak.backends.service", BleakGATTServiceCollection=MagicMock, BleakGATTCharacteristic=MagicMock)
_mod("bleak.exc", BleakDBusError=Exception, BleakError=Exception)
_mod("bleak_retry_connector",
     BleakClientWithServiceCache=MagicMock,
     BleakError=Exception,
     BleakNotFoundError=Exception,
     establish_connection=MagicMock,
     retry_bluetooth_connection_error=lambda *a, **k: (lambda f: f),
     BLEAK_RETRY_EXCEPTIONS=(Exception,),
)
import contextlib as _contextlib


@_contextlib.asynccontextmanager
async def _noop_timeout(_seconds):
    yield


_mod("async_timeout", timeout=_noop_timeout)

# ---------------------------------------------------------------------------
# upstream ac_infinity_ble library
# ---------------------------------------------------------------------------
class _FakeBaseController:
    """Stand-in for ac_infinity_ble.ACInfinityController.

    Real enough that the fork's PortAwareController/MultiPortController can be
    subclassed and unit-tested. _execute_disconnect delegates to an instance
    hook (_raw_disconnect) so tests can make disconnect raise/hang.
    """

    def __init__(self, *args, **kwargs):
        pass

    @property
    def state(self):
        return self._state

    async def _execute_disconnect(self):
        raw = getattr(self, "_raw_disconnect", None)
        if raw is not None:
            await raw()


_mod("ac_infinity_ble",
     ACInfinityController=_FakeBaseController,
     DeviceInfo=MagicMock,
     CallbackType=MagicMock(),
)

# ---------------------------------------------------------------------------
# Home Assistant
# ---------------------------------------------------------------------------
_mod("homeassistant", HomeAssistant=MagicMock)
_mod("homeassistant.config_entries", ConfigEntry=MagicMock, OptionsFlow=object)
_mod("homeassistant.data_entry_flow", FlowResult=dict)
_mod("homeassistant.const",
     CONF_ADDRESS="address", CONF_SERVICE_DATA="service_data",
     Platform=MagicMock(), PERCENTAGE="%", SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm",
     UnitOfTemperature=MagicMock(), UnitOfPressure=MagicMock(),
)
class _CoreState:
    running = "running"


_mod("homeassistant.core",
     HomeAssistant=MagicMock, callback=lambda f: f, CoreState=_CoreState)


# Minimal real implementations of the percentage helpers used by fan.py so the
# coalescing tests exercise the real speed conversion.
def _int_states_in_range(low_high):
    low, high = low_high
    return high - low + 1


def _ranged_value_to_percentage(low_high, value):
    low, high = low_high
    return value / (high - low + 1) * 100


def _percentage_to_ranged_value(low_high, percentage):
    low, high = low_high
    return (high - low + 1) * percentage / 100


_mod("homeassistant.util")
_mod("homeassistant.util.percentage",
     int_states_in_range=_int_states_in_range,
     ranged_value_to_percentage=_ranged_value_to_percentage,
     percentage_to_ranged_value=_percentage_to_ranged_value)
_mod("homeassistant.helpers")
_dr = _mod(
    "homeassistant.helpers.device_registry",
    CONNECTION_BLUETOOTH="bluetooth",
    async_get=MagicMock(),
    DeviceEntry=MagicMock,
)
_er = _mod(
    "homeassistant.helpers.entity_registry",
    async_get=MagicMock(),
    async_entries_for_config_entry=MagicMock(return_value=[]),
)
# Ensure `from homeassistant.helpers import device_registry` resolves.
sys.modules["homeassistant.helpers"].device_registry = _dr
sys.modules["homeassistant.helpers"].entity_registry = _er
_mod("homeassistant.helpers.entity", DeviceInfo=dict, EntityCategory=MagicMock())
_mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=MagicMock)
_mod("homeassistant.helpers.update_coordinator",
     CoordinatorEntity=object, DataUpdateCoordinator=object)
_mod("homeassistant.helpers.storage", Store=MagicMock)
_mod("homeassistant.components")
_mod("homeassistant.components.bluetooth",
     BluetoothServiceInfoBleak=MagicMock,
     BluetoothChange=MagicMock,
     BluetoothScanningMode=MagicMock(),
     async_ble_device_from_address=MagicMock(),
)
class _Generic:
    def __class_getitem__(cls, item):
        return cls

_mod("homeassistant.components.bluetooth.active_update_coordinator",
     ActiveBluetoothDataUpdateCoordinator=_Generic)
_mod("homeassistant.components.bluetooth.passive_update_coordinator",
     PassiveBluetoothCoordinatorEntity=_Generic)
_mod("homeassistant.components.sensor",
     SensorDeviceClass=MagicMock(), SensorEntity=object, SensorStateClass=MagicMock())
_mod("homeassistant.components.light",
     ATTR_BRIGHTNESS="brightness", ColorMode=MagicMock(), LightEntity=object)
_mod("homeassistant.components.fan",
     FanEntity=object, FanEntityFeature=MagicMock())
_mod("homeassistant.components.number")

# ---------------------------------------------------------------------------
# Stub internal integration modules so the package __init__ doesn't cascade
# ---------------------------------------------------------------------------
import os as _os
_mod("custom_components")
_pkg = _mod("custom_components.ac_infinity_ble")
# Point __path__ at the real directory so submodule .py files can be found
# without re-executing the package __init__ (which is already stubbed above).
_pkg.__path__ = [
    _os.path.join(_os.path.dirname(__file__), "..", "custom_components", "ac_infinity_ble")
]
_pkg.__package__ = "custom_components.ac_infinity_ble"

_mod("custom_components.ac_infinity_ble.const",
     DOMAIN="ac_infinity_ble", DEVICE_MODEL={}, CONF_PORTS="ports",
     PORT_KIND_FAN="fan", PORT_KIND_LIGHT="light", PORT_LEVEL_MAX=10,
     WRITE_COALESCE_SECONDS=5, CONF_COMMAND_RETRY_COUNT="retry_count",
     CONF_MIN_CONNECT_GAP_SECONDS="gap", CONF_PASSIVE_ONLY="passive",
     CONF_POLL_INTERVAL_SECONDS="poll", DEFAULT_COMMAND_RETRY_COUNT=1,
     DEFAULT_MIN_CONNECT_GAP_SECONDS=3, DEFAULT_PASSIVE_ONLY=False,
     DEFAULT_POLL_INTERVAL_SECONDS=120, FAILURE_BACKOFF_SECONDS=30,
     BLE_SESSION_TIMEOUT_SECONDS=60, DISCONNECT_TIMEOUT_SECONDS=10,
)
_mod("custom_components.ac_infinity_ble.number")
