# AC Infinity BLE (local) integration — specification

Status of this document: describes what this fork **does**, verified against a
live Home Assistant install controlling a UIS Controller 69 Pro over Bluetooth
on 2026-06-15. Where something is not yet implemented it is called out under
"Known limitations". Do not add claims here that are not verified on a real
device.

## 2026-06-21 code updates (repo verification)

The following behaviors were added in this repository on 2026-06-21 and are
verified at code level only (not yet production-verified):

- `ble_manager.py` now provides a global BLE lock with configurable
  `min_connect_gap_seconds` (default `3`) and deterministic stagger offsets for
  first active poll scheduling.
- Active polling is passive-first: coordinator polls only when advertisements
  are stale/unavailable, controlled by `poll_interval_seconds` (default `120`)
  and `passive_only`.
- Multi-port controllers now poll one port per active poll cycle in
  round-robin order.
- Options flow now exposes `poll_interval_seconds`, `passive_only`,
  `min_connect_gap_seconds`, and `command_retry_count`.
- New diagnostic sensors are added per controller:
  `ble_last_rssi`, `ble_last_seen`, `ble_last_error`, `ble_poll_failures`.
- Setup now restores entities from cached `CONF_SERVICE_DATA` when device is
  not connectable at boot, then hydrates on later advertisements.
- Fan/light duplicate writes to the same target state are coalesced for 5s.

Verification notes (executed in repo):
- `python3 -m compileall custom_components/ac_infinity_ble` -> pass
- `python3 -m pytest` -> no tests collected

## Purpose

Local Bluetooth (BLE) control of AC Infinity UIS controllers from Home
Assistant, with no cloud dependency. It is an alternative to the cloud
integration (`dalinicus/homeassistant-acinfinity`, domain `ac_infinity`).

## Domain and coexistence

- Domain: **`ac_infinity_ble`** (renamed from upstream `ac_infinity`).
- Rationale: Home Assistant loads exactly one integration per domain. The cloud
  integration already occupies `ac_infinity`. The rename lets both run at once
  so controllers can be migrated cloud -> local one at a time.
- Verify: `manifest.json` `"domain": "ac_infinity_ble"`, `const.py`
  `DOMAIN = "ac_infinity_ble"`, directory `custom_components/ac_infinity_ble/`.

## Hardware prerequisite: BLE vs Wi-Fi are mutually exclusive

On the Controller 69 Pro, configuring Wi-Fi **disables Bluetooth**, and vice
versa (AC Infinity Controller 69 Pro manual; confirmed empirically — a
controller on Wi-Fi emits zero BLE advertisements). To use this integration a
controller must be switched to Bluetooth mode: hold its port button ~5s until
the Bluetooth icon flashes. That disables Wi-Fi/cloud for that controller.

## Supported devices

`const.DEVICE_MODEL`: type 1 = Controller 67, 7 = Controller 69, 11 =
Controller 69 Pro, 6 = Airtap T4. Device type comes from BLE manufacturer data
(manufacturer id 2306).

## Entities (per config entry / controller)

Single-port (default, no port map configured):
- `fan.<name>_fan` — speed 1–10 mapped to 0–100%, plus on/off.
- `sensor.<name>_temperature`, `sensor.<name>_humidity`.
- `sensor.<name>_vpd` — only when `state.version >= 3` and type in {7,9,11,12}.

Multi-port (when the entry carries a port map — see "Multi-port control"):
- one `fan.<port name>` per `kind: fan` port, bound to a fixed port index.
- one `light.<port name>` per `kind: light` port (brightness = level 1–10
  scaled onto 0–255).
- the same controller-level temp/humidity/vpd sensors.

## Port addressing (the important fix)

The upstream `ac-infinity-ble==0.4.3` library hardcodes the UIS port index to
`0` in `set_level(...)` (commands) and `get_model_data(...)` (reads). UIS
controllers have multiple ports; the fan is often **not** on port 0, so
commands were acknowledged by the controller but changed nothing.

`controller.py::PortAwareController` overrides `update`, `turn_on`, `turn_off`,
and `set_speed` to use the controller's currently selected port
(`state.choose_port`, populated from every advertisement) instead of `0`.

Verified on a Controller 69 Pro (choose_port = 1):
- Before fix: `fan.set_percentage 50` -> command byte port `00`, advertised
  fan stays `0`.
- After fix: command byte port `01`, advertised `fan 0 -> 5`, `fan_state 0 -> 2`.
- `fan.turn_off` -> advertised `fan_state -> 1`, `fan` -> the port's configured
  off-speed (not necessarily 0; `set_percentage 0` gives a true stop).

## State updates (passive vs poll)

- The coordinator registers with `connectable=False` so it receives **every**
  advertisement (the controller's full state — temp/hum/vpd/fan/fan_state —
  is in the manufacturer data). This matters because the controller is often
  only heard via a non-connectable proxy; a `connectable=True` registration
  ignored those and the UI froze between polls.
- Commands (`set_speed`/`turn_on`/`turn_off`) and the 30s poll still need a
  connectable link, established on demand via `bleak_retry_connector`.
- `fan` on/off (`is_on`) derives from `work_type`, which is **not** in
  advertisements (only set by commands and polls). So on/off is correct
  immediately after a command (optimistic write) and refreshed each poll;
  fan **speed/percentage** tracks every advertisement.

## Multi-port control (office: 2 fans + grow light)

Office 69 Pro is in **BLE mode** (G-622UC, `48:CA:43:81:9F:E6`). Verified
2026-06-15: with the per-port-reconnect read (below) the controller polls all
three ports with **0 poll failures**, and a `light.turn_off` write to port 3
fires with no BLE error. Physical per-port isolation (each entity moves only
its own load) is the remaining owner-confirmation step.

Design:
- A config entry gains per-port behaviour when its `data`/`options` carries a
  `ports` list (`const.CONF_PORTS`). Live office entry (`G-622UC`):
  ```json
  "ports": [
    {"port": 1, "kind": "fan",   "name": "Office Fan Port 1"},
    {"port": 2, "kind": "fan",   "name": "Office Fan Port 2"},
    {"port": 3, "kind": "light", "name": "Bathroom Grow Light"}
  ]
  ```
- `controller.py::MultiPortController` keeps a `port_states: dict[int,
  PortState]` and reads each configured port in **its own** connect/disconnect
  cycle (`get_model_data(type, port, seq)`, one command per connection). The
  controller answers only the first command per BLE connection, so batching all
  ports into one session times out every read after the first
  (`CancelledError`) and fails the whole poll — reconnect per port instead.
  Writes go to a single port via `set_port_level(port, work_type, level)`.
- `fan.py::ACInfinityPortFan` and `light.py::ACInfinityGrowLight` each bind to
  a fixed port index (not `choose_port`). `__init__.py` selects
  `MultiPortController` + the FAN/LIGHT/SENSOR platforms when a port map exists.

Office port map (read from the live cloud device registry, controller id
`1424979258063479287`): Port 1 = Office Fan Port 1, Port 2 = Office Fan Port 2,
Port 3 = Bathroom Grow Light, Port 4 = unused.

**BLE port index is one-based** (cloud "Port N" -> BLE byte N), confirmed: the
controller advertises `choose_port = 1`, and `get_model_data(type, 1, seq)`
returns valid data while the cloud registry calls the same load "Port 1". The
live map therefore uses indices 1/2/3.

Verification (live G-622UC, 2026-06-15, library logger at debug):
- ✅ Each poll connects, reads one port, disconnects, then repeats — the
  command byte (`ff <pp>`) cycles `ff01`, `ff02`, `ff03` and each gets a
  `Notification received` with distinct body (port 1 `120104` vs port 2
  `120109`). 0 poll failures.
  ```
  G-622UC: Sending command a5...1617ff01...  -> Notification ...120104...
  G-622UC: Sending command a5...1617ff02...  -> Notification ...120109...
  G-622UC: Sending command a5...1617ff03...  -> Notification ...120104...
  ```
- ✅ `light.turn_off` write to port 3 fires with no BLE error.
- ⏳ Owner to confirm physical isolation: `fan.set_percentage` on each fan
  entity changes only that fan; `light.turn_on`/brightness changes only the
  light.
- The grow-light on-device sunrise/sunset schedule is lost in BLE; it is driven
  from the Node-RED "Plant Light" flow against the new `light.*` entity.

## Known limitations

- The single-port (default) path targets the controller's *selected* port
  (`choose_port`); if the physical port selection is changed on the controller,
  commands follow it. Multi-port entries pin explicit indices and do not have
  this issue.
- Multi-port light scheduling depends on Node-RED/HA (the controller's
  on-device schedule does not run while in BLE mode).

## Verification commands

- Is a controller advertising BLE (mfr id 2306)? Subscribe to
  `bluetooth/subscribe_advertisements` over the HA websocket and look for the
  controller address / manufacturer id 2306. (A controller on Wi-Fi shows
  nothing.)
- Live fan state without connecting: parse the advertisement's manufacturer
  data with `ac_infinity_ble.protocol.parse_manufacturer_data` and read
  `fan`, `fan_state`, `choose_port`.
- Command port byte: set `ac_infinity_ble` logger to debug and read the
  `Sending command ...` hex line; the trailing `ff <pp>` is `ff` + port index.

## Operations (verified 2026-06-21)

These commands were run against the live BowmanMtn host and are safe to re-run.

- Baseline + scanner snapshot: run the command block recorded in `ops/acinf-ble-baseline-20260621.txt`.
- LR/Family visibility check:
  `ssh bowmanmtn "python3 -c \"import json; rs=json.load(open('/home/ntableman/docker/ha/config/.storage/bluetooth.remote_scanners'))['data']; targets=['80:65:99:AB:00:3E','3C:84:27:2D:BF:F6']; print({t:any(t in s.get('discovered_device_advertisement_datas',{}) for s in rs.values()) for t in targets})\""`
- Registry hygiene check:
  `ssh bowmanmtn "python3 -c \"import json; er=json.load(open('/home/ntableman/docker/ha/config/.storage/core.entity_registry'))['data']['entities']; orph=[e for e in er if e.get('platform')=='ac_infinity_ble' and not e.get('config_entry_id')]; cloud=[e for e in er if e.get('platform')=='ac_infinity']; print('orphan_ble',len(orph)); print('cloud_acinfinity',len(cloud))\""`

Physical recovery notes (current blockers):
- LR `80:65:99:AB:00:3E` is not advertising on any scanner, so HA re-adopt cannot proceed yet.
- Family `3C:84:27:2D:BF:F6` has a config entry/entity but is not advertising, so commands will stay unavailable until advertising resumes.

