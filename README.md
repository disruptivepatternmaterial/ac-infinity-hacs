# AC Infinity BLE (NET Fork)

Local Bluetooth (BLE) control of AC Infinity UIS fan controllers in Home Assistant — no cloud dependency.

**This repo:** [disruptivepatternmaterial/ac-infinity-hacs](https://github.com/disruptivepatternmaterial/ac-infinity-hacs)  
**Current release:** [v1.3.2](https://github.com/disruptivepatternmaterial/ac-infinity-hacs/releases/tag/v1.3.2)  
**HACS name:** `AC Infinity BLE (NET Fork)`  
**Integration domain:** `ac_infinity_ble` (coexists with cloud `ac_infinity` / dalinicus)

Fork lineage: [@hunterjm/ac-infinity-hacs](https://github.com/hunterjm/ac-infinity-hacs) → [@way-lo/ac-infinity-hacs](https://github.com/way-lo/ac-infinity-hacs) → this fork.

Behavior details, verification commands, and known limitations: [SPEC.md](SPEC.md).

---

## Install (HACS)

1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add `https://github.com/disruptivepatternmaterial/ac-infinity-hacs` as type **Integration**
3. Search **AC Infinity BLE (NET Fork)** → **Download**
4. Restart Home Assistant
5. **Settings → Devices & services → Add integration** → **AC Infinity BLE (NET Fork)**

After adding the custom repo once, future updates: HACS → **AC Infinity BLE (NET Fork)** → **Update** (shows version e.g. `v1.2.1`, not a commit hash, once a [GitHub release](https://github.com/disruptivepatternmaterial/ac-infinity-hacs/releases) exists for that version).

### Manual install

Copy `custom_components/ac_infinity_ble/` to `/config/custom_components/` and restart HA.

---

## Deploy checklist (BowmanMtn)

| Step | Command / action |
|------|------------------|
| Pull latest | HACS → Update **AC Infinity BLE (NET Fork)** |
| Verify version | `/config/custom_components/ac_infinity_ble/manifest.json` → `"version": "1.3.2"` |
| Restart | Restart Home Assistant |
| Smoke test | Fan speed change; temp/humidity show `unknown` when device has not reported (not `0`) |

---

## What this fork adds (summary)

| Area | Behavior |
|------|----------|
| **Domain** | `ac_infinity_ble` — runs beside cloud `ac_infinity` |
| **Multi-port** | Office 69 Pro: separate `fan` / `light` entities per port map |
| **Port selection** | `PortAwareController` uses advertisement `choose_port` (upstream hardcoded port 0) |
| **Advertisements** | Coordinator `connectable=False` so proxy-only adverts update state |
| **BLE manager** | Global lock, connect gap, staggered polls, passive-first, round-robin multi-port |
| **Options** | `poll_interval_seconds`, `passive_only`, `min_connect_gap_seconds`, `command_retry_count` |
| **Diagnostics** | `ble_last_rssi`, `ble_last_seen`, `ble_last_error`, `ble_poll_failures` |
| **Sensor fidelity** | Temp/hum/VPD read raw `state.tmp/hum/vpd` — missing readings stay `unknown`, not fabricated `0` |
| **Write coalescing** | Duplicate fan/light commands within 5s skipped |
| **Device identity** | `identifiers={(domain, mac)}` + detach migration if HA merged us onto another integration’s device |

---

## Changelog (NET Fork)

### v1.3.2 — device registry re-home fix

- **Bug:** Library controller `G-SGR1J` entities could appear under an August
  smart lock after Home Assistant merged device-registry records that shared
  bluetooth identity metadata.
- **Fix:** Pin entities with `identifiers={(ac_infinity_ble, mac)}`, detach our
  identifier/connection/config entry from any contaminated shared device, then
  rebind entities onto the dedicated Controller device.
- **Docs/tests:** SPEC incident notes; detach-helper unit tests.

### v1.3.1 — fourth/fifth review-pass fixes

Fixes from a 2026-07-02 review pass plus a 4-model re-review panel (see `LAND.md`).

- **Diagnostics:** `ble_last_error` is truncated to 255 chars at the source (HA rejects longer states).
- **Poll integrity:** a `None` update response (unreachable with pinned ac-infinity-ble 0.4.3) now raises `InvalidResponseError` instead of counting as a successful poll.
- **Options:** saving the options form merges over existing options, so a manually-added `ports` map survives a save; an explicit `ports: []` in options now clears a map stored in data.
- **Unload:** teardown uses the platform list recorded at setup, not one recomputed from possibly-edited entry data.
- **Port guard:** a `ports` map on a device type without per-port protocol support (`type` not in 7/9/11/12) is refused at setup with a warning instead of silently driving one load from N entities.
- **Data fidelity:** fan percentage / light brightness / per-port `is_on` report `unknown` (`None`) when never observed, instead of a fabricated off/0%; a real 0 still reads 0.
- **Tests:** options-flow merge, `_read_ports` precedence, unload platforms, multi-port `None` response, entity attribute fidelity; suite now **70 cases**.

### v1.3.0 — multi-model review hardening

Fixes from three rounds of multi-model code review (see `LAND.md`). No new features; correctness, resilience, and test coverage.

- **Polling fix (headline):** active polls are scheduled from the last successful poll, not advertisement recency. Previously, because the coordinator stamped the advertisement timestamp before evaluating the poll gate, active polling never fired while the controller was advertising — leaving multi-port `port_states` and single-port on/off (`work_type`, which is not in advertisements) frozen. Now polls run on `poll_interval_seconds`, with a forced poll on setup and on recovery from "unavailable".
- **Poll failure back-off:** a failed poll backs off `min(30s, poll_interval_seconds)` instead of retrying on every advertisement.
- **Write coalescing fix:** the 5s duplicate-skip cache is recorded only after a successful BLE write, so a command that failed can be retried immediately (previously a failed write poisoned the cache for 5s).
- **No setup crash on controller types 9/12:** `DEVICE_MODEL` lookups use `.get()` instead of direct indexing.
- **Bounded BLE sessions:** each connect/command/disconnect runs under a 60s timeout, and disconnect cleanup has its own 10s ceiling, so one hung device can't hold the global BLE lock indefinitely.
- **Short/corrupt responses handled:** frames shorter than 19 bytes raise instead of `IndexError`, and are recorded as a poll failure (with back-off and `ble_last_error` / `ble_poll_failures` diagnostics) rather than silently counted as success.
- **Faster startup for offline devices:** setup no longer blocks up to 30s waiting for an advertisement when state was restored from cached service data.
- **Cleanup:** removed dead constants and an unused parameter; portability and stale-docstring fixes.
- **Tests:** added `test_ble_manager.py`, `test_coalesce.py`, `test_coordinator.py`, `test_controller.py`; suite now **44 cases** (was 12).

### v1.2.2

- **README:** full NET Fork install/deploy docs, changelog, tests, HACS naming

### v1.2.1

- **HACS/manifest name:** AC Infinity BLE (NET Fork)
- **Sensor data fidelity:** bypass upstream `ac-infinity-ble==0.4.3` properties that use `or 0` for missing tmp/hum/vpd; entities report `unknown` when the device has not sent a reading
- **Tests:** `tests/test_sensor.py` (12 tests)

### v1.2.0

- Global BLE session manager (`ble_manager.py`): house-level lock, `min_connect_gap_seconds` (default 3s), staggered poll offsets
- Passive-first polling: `poll_interval_seconds` (default 120), `passive_only`, multi-port round-robin (one port per poll cycle)
- Options flow: poll interval, passive-only, connect gap, command retry count
- Diagnostic sensors: BLE RSSI, last seen, last error, poll failures
- Resilient setup from cached `CONF_SERVICE_DATA` when device not connectable at boot
- Fan/light write coalescing (5s duplicate skip)

### v1.1.0

- Multi-port control (`MultiPortController`): one fan/light entity per configured port
- 🚧 Office 69 Pro BLE port indexing not production-verified until device is in Bluetooth mode (see SPEC.md)

### v1.0.7

- Config flow discovery with `connectable=False` (controllers visible via non-connectable proxy)

### v1.0.6

- Coordinator consumes non-connectable advertisements (fixes stale UI until poll)
- Optimistic fan entity state after BLE commands

### v1.0.5

- Domain rename `ac_infinity` → `ac_infinity_ble`
- `PortAwareController` for correct UIS port targeting
- `sw_version` cast to string in device info

### v1.0.4 and earlier

- Airtap T4 (type 6), HA 2026.3.4+ fan features, config flow hardening (see git history)

---

## Tests

```bash
cd ac-infinity-hacs
python3 -m pytest tests/ -v
```

Requires only `pytest` (HA/upstream libs stubbed in `tests/conftest.py`). **64 tests** cover sensor null/zero passthrough, BLE-manager poll scheduling and failure back-off, fan/light write coalescing (incl. retry-after-failure), the coordinator poll-gating lifecycle and startup-wait shortcut, the controller short/None-response guard and bounded disconnect, options-flow merge semantics, `_read_ports` precedence, unload platform bookkeeping, and entity unknown-vs-zero attribute fidelity.

Compile check:

```bash
python3 -m compileall custom_components/ac_infinity_ble
```

---

## Hardware notes

- UIS controllers must be in **Bluetooth mode** (Wi-Fi and BLE are mutually exclusive on 69 Pro).
- Airtap vent fans expose a humidity entity but have **no humidity sensor** — expect missing/null behavior, not a real 0% reading after v1.2.1.

---

## Credits

Original integration: [@hunterjm](https://github.com/hunterjm/ac-infinity-hacs).  
Intermediate fork: [@way-lo](https://github.com/way-lo/ac-infinity-hacs).  
NET Fork maintenance: [disruptivepatternmaterial](https://github.com/disruptivepatternmaterial/ac-infinity-hacs).
