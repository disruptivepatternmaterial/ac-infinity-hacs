"""Constants for the ac_infinity integration."""
from bleak.exc import BleakError

DOMAIN = "ac_infinity_ble"

DEVICE_TIMEOUT = 30
UPDATE_SECONDS = 15

BLEAK_EXCEPTIONS = (AttributeError, BleakError, TimeoutError)

DEVICE_MODEL = {1: "Controller 67", 7: "Controller 69", 11: "Controller 69 Pro", 6: "Airtap T4"}

# Per-port control (multi-port controllers, e.g. the office 69 Pro).
# When an entry's data/options carries CONF_PORTS, the integration creates one
# entity per listed port instead of a single choose_port fan.
CONF_PORTS = "ports"
PORT_KIND_FAN = "fan"
PORT_KIND_LIGHT = "light"

# UIS levels are 0-10; grow-light brightness scales onto 0-255.
PORT_LEVEL_MAX = 10
