# ac-infinity-hacs
Custom Integration to test AC Infinity Controllers

All credit to @hunterjm's integration https://github.com/hunterjm/ac-infinity-hacs to which this is a fork of.
This fork is maintained at https://github.com/disruptivepatternmaterial/ac-infinity-hacs and is a fork of @way-lo's fork.

See [SPEC.md](SPEC.md) for the current behavior, deployed state, and known limitations.

1.2.0 (disruptivepatternmaterial)

Added phased BLE management updates in `ac_infinity_ble`:
- global BLE session manager (`ble_manager.py`) with one house-level lock, configurable minimum connect gap (`min_connect_gap_seconds`, default `3`), and deterministic staggered initial poll offsets.
- passive-first polling with configurable `poll_interval_seconds` (default `120`), `passive_only`, and office multi-port round-robin polling (one port per poll cycle).
- options flow (`options_flow.py`) exposing `poll_interval_seconds`, `passive_only`, `min_connect_gap_seconds`, and `command_retry_count`.
- diagnostic sensors: `ble_last_rssi`, `ble_last_seen`, `ble_last_error`, `ble_poll_failures`.
- resilient setup path: entries/platforms restore from cached `CONF_SERVICE_DATA` even when the controller is not connectable at boot, then refresh on later advertisements.
- write coalescing for fan/light commands: duplicate writes with identical target state within `5s` are skipped.

Verification notes for this release (repository-only):
- `python3 -m compileall custom_components/ac_infinity_ble` (pass)
- `python3 -m pytest` (runs, no tests collected in this repository)

1.1.0 (disruptivepatternmaterial)

Added multi-port control for controllers driving several loads at once (the office 69 Pro: two fans + a grow light). When a config entry carries a `ports` map (`const.CONF_PORTS`), the integration uses `controller.MultiPortController` (per-port state cache, reads every configured port in one connected BLE session, writes a single port via `set_port_level`) and creates one `fan` per `kind: fan` port plus one `light` per `kind: light` port (`light.py`), each bound to a fixed port index instead of `choose_port`. Without a port map the single-port behaviour is unchanged.

🚧 NOT YET VERIFIED on the live office controller: the office is still on Wi-Fi/cloud and cannot advertise BLE until switched to Bluetooth mode. The BLE port index is assumed zero-based (cloud "Port N" -> index N-1); this and per-port isolation must be probed on the live device before relying on it. See SPEC.md "Multi-port control".

1.0.7 (disruptivepatternmaterial)

Config flow now discovers with `connectable=False`. Controllers heard only via a non-connectable Bluetooth proxy were invisible to the add flow (`no_devices_found`) unless a brief connectable window happened to coincide; this makes them reliably listable. The connectable link for the connection test / setup is still established on demand.

1.0.6 (disruptivepatternmaterial)

Fixed the Home Assistant UI showing stale fan/sensor state. The controller's advertisements often arrive only via a non-connectable Bluetooth proxy, but the coordinator was registered with `connectable=True` and therefore ignored them, so entities only refreshed on the 30s poll (which does not re-read temperature). Changed the coordinator to `connectable=False` so it consumes all advertisements (full state lives in the manufacturer data); commands and polls still establish their own connectable link on demand. Verified: with `connectable=False`, `fan`/`temperature`/`humidity`/`vpd` track live advertisements.

Made `fan` commands optimistic: `set_percentage`/`turn_on`/`turn_off` now write entity state immediately after the BLE command instead of waiting for the next advertisement/poll, so the card reflects the change instantly.

1.0.5 (disruptivepatternmaterial)

Renamed integration domain from `ac_infinity` to `ac_infinity_ble` (directory, manifest, const.DOMAIN). This lets the local-BLE integration coexist with the cloud `ac_infinity` integration (dalinicus) on the same Home Assistant instance, so controllers can be migrated from cloud to local one at a time.

Added `controller.py` with `PortAwareController`, used in place of the upstream `ACInfinityController`. The upstream `ac-infinity-ble==0.4.3` library hardcodes the UIS port index to `0` in every command and read. On multi-port controllers (e.g. Controller 69 Pro) the fan is often on a different port, so commands were acknowledged by the controller but moved nothing. `PortAwareController` targets the controller's currently selected port (`choose_port`, populated from each advertisement). Verified live on a Controller 69 Pro: `fan.set_percentage` now changes the fan (0 -> 5, fan_state 0 -> 2) and `fan.turn_off` returns it to the configured off-speed. (See SPEC.md "Known limitations" for the single-port caveat.)

Cast `sw_version` to `str` in fan.py and sensor.py device info (upstream passed an int, which Home Assistant warns will stop working in 2026.12.0).

1.0.4

Added Airtap T4 (device type ID 6) to DEVICE_MODEL in const.py

Added FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF to _attr_supported_features in fan.py (fixes "does not support action fan.turn_off" error in HA 2026.3.4+)

Fixed _async_update_attrs in fan.py to guard against None or zero fan speed when computing percentage

Fixed config_flow.py to skip non-AC-Infinity Bluetooth devices during discovery (fixes "500 Internal Server Error" when loading config flow)

Fixed config_flow.py to abort with "no_devices_found" if no AC Infinity devices are visible in BT scan, instead of showing an empty/broken address form

Fixed config_flow.py to safely handle missing address in _discovered_devices on form submit

Added not_supported and device_not_found error strings to strings.json and translations/en.json

Note:
For the Airtap vent fans, humidity is provided as an entity but these devices have no humidity sensor.
