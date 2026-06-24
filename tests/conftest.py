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
_mod("async_timeout")

# ---------------------------------------------------------------------------
# upstream ac_infinity_ble library
# ---------------------------------------------------------------------------
_mod("ac_infinity_ble",
     ACInfinityController=MagicMock,
     DeviceInfo=MagicMock,
     CallbackType=MagicMock,
)

# ---------------------------------------------------------------------------
# Home Assistant
# ---------------------------------------------------------------------------
_mod("homeassistant", HomeAssistant=MagicMock)
_mod("homeassistant.config_entries", ConfigEntry=MagicMock)
_mod("homeassistant.const",
     CONF_ADDRESS="address", CONF_SERVICE_DATA="service_data",
     Platform=MagicMock(), PERCENTAGE="%", SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm",
     UnitOfTemperature=MagicMock(), UnitOfPressure=MagicMock(),
)
_mod("homeassistant.core", HomeAssistant=MagicMock, callback=lambda f: f)
_mod("homeassistant.helpers")
_mod("homeassistant.helpers.device_registry", CONNECTION_BLUETOOTH="bluetooth")
_mod("homeassistant.helpers.entity", DeviceInfo=dict, EntityCategory=MagicMock())
_mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=MagicMock)
_mod("homeassistant.helpers.update_coordinator",
     CoordinatorEntity=object, DataUpdateCoordinator=object)
_mod("homeassistant.helpers.storage", Store=MagicMock)
_mod("homeassistant.components")
_mod("homeassistant.components.bluetooth",
     BluetoothServiceInfoBleak=MagicMock,
     BluetoothChange=MagicMock,
     async_ble_device_from_address=MagicMock,
)
class _Generic:
    def __class_getitem__(cls, item):
        return cls

_mod("homeassistant.components.bluetooth.passive_update_coordinator",
     PassiveBluetoothCoordinatorEntity=_Generic)
_mod("homeassistant.components.sensor",
     SensorDeviceClass=MagicMock(), SensorEntity=object, SensorStateClass=MagicMock())
_mod("homeassistant.components.light")
_mod("homeassistant.components.fan")
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
     PORT_KIND_LIGHT="light", CONF_COMMAND_RETRY_COUNT="retry_count",
     CONF_MIN_CONNECT_GAP_SECONDS="gap", CONF_PASSIVE_ONLY="passive",
     CONF_POLL_INTERVAL_SECONDS="poll", DEFAULT_COMMAND_RETRY_COUNT=1,
     DEFAULT_MIN_CONNECT_GAP_SECONDS=2, DEFAULT_PASSIVE_ONLY=False,
     DEFAULT_POLL_INTERVAL_SECONDS=120,
)
_mod("custom_components.ac_infinity_ble.ble_manager", ACInfinityBLEManager=MagicMock)
_mod("custom_components.ac_infinity_ble.coordinator",
     ACInfinityDataUpdateCoordinator=MagicMock)
_mod("custom_components.ac_infinity_ble.models", ACInfinityData=MagicMock)
_mod("custom_components.ac_infinity_ble.controller",
     MultiPortController=MagicMock, PortAwareController=MagicMock)
_mod("custom_components.ac_infinity_ble.fan")
_mod("custom_components.ac_infinity_ble.light")
_mod("custom_components.ac_infinity_ble.number")
_mod("custom_components.ac_infinity_ble.options_flow")
