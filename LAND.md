# LAND — ac_infinity_ble (NET Fork) fixes to land

Source: multi-model adversarial review (Opus 4.8, GPT-5.3 Codex, Gemini 3.5, Sonnet 4.6, GPT-5.5)
Scope reviewed: `git diff 1655604..HEAD` (merge-base with upstream `hunterjm/ac-infinity-hacs`)
Status: ACT ON items #1-#5 LANDED 2026-06-29 (verified; tests green, 25 pytest cases).

Consensus column = how many of 5 reviewers independently flagged it.

---

## Land order

Fix #1 and #5 together (same root cause + they interact), then #2, #3, #4.

---

## ACT ON  — [LANDED 2026-06-29]

Implementation summary:
- #1/#5: `coordinator._needs_poll` now gates on last successful poll (drops the
  advertisement-age short-circuit), forces a poll on first-run/recovery, and
  clears `_was_unavailable` in `_async_update`; `ble_manager.note_poll_failure`
  backs off `min(FAILURE_BACKOFF_SECONDS=30, interval)`.
- #2: fan/light split `_is_duplicate_write` (read) from `_record_write` (stamp
  after success).
- #3: `DEVICE_MODEL.get(type)` in `sensor.py` + `fan.py`.
- #4: `async_timeout(BLE_SESSION_TIMEOUT_SECONDS=60)` around each BLE session in
  `controller._run_with_retries`.
- Tests: `tests/test_ble_manager.py`, `tests/test_coalesce.py`; conftest extended.

### 1. CRITICAL — Active polling never runs while the device advertises (multi-port state frozen)
- Consensus: 3/5 (Opus, Codex, Gemini) — verified
- Files: `custom_components/ac_infinity_ble/coordinator.py:85-89`, `:116-134`
- Cause: `_async_handle_bluetooth_event` sets `last_seen = now` (`note_advertisement`, line 127)
  and `self._was_unavailable = False` (line 133) **before** `super()` (line 134) evaluates
  `_needs_poll`. HA's `ActiveBluetoothDataUpdateCoordinator` only schedules polls from that
  callback (no independent timer), so the age check `age < poll_interval_seconds` is always true
  while advertising → polls never fire.
- Impact: `MultiPortController.port_states` only refreshes via `update()`/`set_port_level()`;
  multi-port fan/light entities sit at OFF/0% until a manual command and never reconcile.
  Single-port on/off (`work_type`, not in adverts) also goes stale.
- Fix: gate active polls on a separate "last successful poll" timestamp (monotonic), independent
  of advertisement recency. Do not mutate `_was_unavailable`/`last_seen` before calling `super()`
  if they are meant to influence `needs_poll`.

### 5. (lands with #1) — `_was_unavailable` recovery branch is dead code + failure backoff
- Consensus: 2/5 (Opus, Sonnet) for dead branch; Gemini for the storm risk
- Files: `coordinator.py:79-84`, `:133`; `ble_manager.py:87-91`
- Cause: `_was_unavailable` reset to `False` before `super()` triggers `_needs_poll`, so the
  "poll immediately on recovery" path never runs. Separately, `note_poll_failure` never sets
  `next_poll_due_monotonic`.
- Interaction: today the age-gate from #1 masks any poll storm. Once #1 is fixed, a failed poll
  with no backoff WILL storm the adapter. Add a backoff in `note_poll_failure`
  (e.g. `next_poll_due_monotonic = monotonic() + min(30, interval)`).

### 2. WARNING — Write coalescing drops failed/legitimate retries
- Consensus: 4/5 (Opus, Codex, Gemini, GPT-5.5) — verified
- Files: `fan.py:86-107`, `fan.py:198-248`, `light.py:93-124`
- Cause: `_should_skip_duplicate_write` records signature/timestamp **before** the awaited BLE
  write. If the write raises (default `command_retry_count=1` = no retry), an identical user retry
  within 5s is dropped though nothing changed.
- Fix: stamp the coalesce cache only after a successful write, or clear it in the `except` path.

### 3. WARNING — `DEVICE_MODEL[type]` KeyError crashes setup for types 9/12
- Consensus: 4/5 (Opus, Gemini, Sonnet, GPT-5.5) — verified
- Files: `const.py:22`, `sensor.py:68`, `fan.py:77` (vs `sensor.py:44`)
- Cause: `sensor.py:44` treats types `7,9,11,12` as VPD-capable, but `DEVICE_MODEL` only maps
  `{1,6,7,11}`. Direct indexing `DEVICE_MODEL[device.state.type]` raises `KeyError` on type 9/12.
- Fix: use `DEVICE_MODEL.get(type, "Unknown AC Infinity Controller")` everywhere (multi-port code
  already does).

### 4. WARNING — Global BLE lock: `asyncio.sleep` held inside lock, no timeout
- Consensus: 2/5 (Opus, Sonnet) — verified
- Files: `ble_manager.py:54-67`, used in `controller.py:47-72`
- Cause: `_global_lock` is held across the full BLE session and the connect-gap sleep happens
  inside the lock; no `async_timeout` around the guarded op. A hung connect/disconnect blocks
  every other device house-wide.
- Fix: perform the connect-gap sleep before acquiring (or release earlier); wrap the guarded
  operation in `async_timeout`.

---

## CONSIDER

- `CancelledError` bypasses retry/failure accounting — `except Exception` at `controller.py:58`,
  `coordinator.py:102` won't catch `BaseException`; diagnostics skipped. (Codex)
- 30s startup block when device offline despite cache restore — `coordinator.py:136-142`
  `async_wait_ready` waits full timeout even when state restored from `CONF_SERVICE_DATA`. (Gemini)
- `IndexError` on short BLE response — `data[12/15/18]` in `controller.py` update paths has no
  length guard. (Gemini)
- Options flow may drop `CONF_PORTS` — `options_flow.py:33`; safe only because `_read_ports`
  falls back to `entry.data` (ports must not live in `entry.options`). Low risk as configured.
  (GPT-5.5; Opus disagrees it's a live bug)

---

## NOTED (nits)

LANDED with the ACT ON pass:
- Redundant `should_poll_now` branch collapsed — `ble_manager.py`.
- Zero-based -> one-based `MultiPortController` docstring corrected — `controller.py`.
- Copy-paste docstrings fixed ("switchbot"/"LEDBLE") — `coordinator.py`, `sensor.py`, `models.py`.
- `self.state.fan` -> `self._state.fan` consistency — `controller.py`.
- Unused `self._name` removed — `sensor.py`.
- conftest const drift fixed (`DEFAULT_MIN_CONNECT_GAP_SECONDS` 2 -> 3) + thin-tests gap addressed.
- `datetime.UTC` -> `timezone.utc` for <3.11 portability (surfaced by tests) — `ble_manager.py`.

NOT changed (deliberate):
- VPD sensor `SensorDeviceClass.ATMOSPHERIC_PRESSURE` (`sensor.py`) — left as-is; changing
  device_class can reset long-term statistics on existing installs.
- Manifest `connectable: true` vs runtime `connectable=False` — manual add works; auto-discovery
  change deferred.

---

## DISMISSED (benign after verification)

- `self.state.fan = speed` "typo" in `set_speed` (`controller.py:140`) — `.state` is a property
  returning the same `_state` object; mutates the identical `DeviceInfo`. Style inconsistency only.

---

## Clean areas (per reviewers)

Sensor null/zero fidelity + its tests, domain-rename wiring (`ac_infinity_ble` consistent),
options-flow reload, `models.py` PortState/PortConfig, lock acquisition order (no deadlock).
