# AC Infinity BLE (local) integration — specification

Status of this document: describes what this fork **does**, verified against a
live Home Assistant install controlling a UIS Controller 69 Pro over Bluetooth
on 2026-06-15. Where something is not yet implemented it is called out under
"Known limitations". Do not add claims here that are not verified on a real
device.

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

- `fan.<name>_fan` — speed 1–10 mapped to 0–100%, plus on/off.
- `sensor.<name>_temperature`, `sensor.<name>_humidity`.
- `sensor.<name>_vpd` — only when `state.version >= 3` and type in {7,9,11,12}.

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

## Known limitations

- **Single port per controller.** Each config entry exposes one fan and
  targets the controller's *selected* port. Controllers driving multiple
  devices (e.g. an Office controller with two fans and a grow light) are **not
  fully supported**: there is no per-port fan entity and no light entity yet.
  Migrating such a controller off cloud would lose independent control of the
  other ports. 🚧 NOT YET IMPLEMENTED: multi-port entities (per-port fan +
  light). Track in this fork's issues before relying on it.
- The selected-port approach assumes the controller display stays on the fan's
  port. If the physical port selection is changed on the controller, commands
  follow it. An explicit per-entry port option is not yet implemented.

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
