"""Port-aware AC Infinity BLE controller.

The upstream ``ac-infinity-ble`` library hardcodes the UIS port index to ``0``
in every command (``set_level(..., 0, sequence)``) and in its read
(``get_model_data(type, 0, sequence)``). On multi-port controllers such as the
UIS Controller 69 Pro the fan is frequently wired to a different port, so those
commands target an empty port and nothing moves even though the controller
acknowledges them.

This subclass targets the port the controller currently has selected
(``choose_port``), which the library populates from every BLE advertisement
(see ``set_ble_device_and_advertisement_data``). The command/read bodies are
otherwise identical to upstream (pinned ``ac-infinity-ble==0.4.3``); only the
port argument changes.
"""
from __future__ import annotations

import logging

from ac_infinity_ble import ACInfinityController, CallbackType
import async_timeout

from .ble_manager import ACInfinityBLEManager
from .const import (
    BLE_SESSION_TIMEOUT_SECONDS,
    DEFAULT_COMMAND_RETRY_COUNT,
    DISCONNECT_TIMEOUT_SECONDS,
)
from .models import PortState

_LOGGER = logging.getLogger(__name__)


class PortAwareController(ACInfinityController):
    """An ACInfinityController that addresses the selected UIS port."""

    _ble_manager: ACInfinityBLEManager | None = None
    _command_retry_count: int = DEFAULT_COMMAND_RETRY_COUNT

    @property
    def _port(self) -> int:
        """Return the controller's currently selected port index."""
        return self._state.choose_port or 0

    def set_ble_manager(
        self, ble_manager: ACInfinityBLEManager, *, command_retry_count: int
    ) -> None:
        """Attach the shared BLE manager and command retry policy."""
        self._ble_manager = ble_manager
        self._command_retry_count = max(1, command_retry_count)

    async def _run_with_retries(self, operation_name: str, command_coro) -> None:
        """Run one BLE operation under the global lock with retry."""
        if self._ble_manager is None:
            await command_coro()
            return
        last_error: Exception | None = None
        for attempt in range(1, self._command_retry_count + 1):
            try:
                async with self._ble_manager.acquire(self.address):
                    async with async_timeout.timeout(BLE_SESSION_TIMEOUT_SECONDS):
                        await command_coro()
                return
            except Exception as err:  # noqa: BLE001
                last_error = err
                self._ble_manager.note_command_failure(self.address, err)
                if attempt >= self._command_retry_count:
                    raise
                _LOGGER.debug(
                    "%s retrying %s after attempt %d/%d failed: %s",
                    self.address,
                    operation_name,
                    attempt,
                    self._command_retry_count,
                    err,
                )
        if last_error is not None:
            raise last_error

    async def _execute_disconnect(self) -> None:
        """Bound disconnect cleanup so a hung disconnect can't hold the lock.

        Disconnect runs in each command's ``finally``, which executes while the
        task is unwinding after the session timeout has fired. The session
        ``async_timeout`` no longer guards that unwind, so give disconnect its
        own ceiling and never let it raise (cleanup must always complete).
        """
        try:
            async with async_timeout.timeout(DISCONNECT_TIMEOUT_SECONDS):
                await super()._execute_disconnect()
        except Exception as err:  # noqa: BLE001 - cleanup must never propagate
            _LOGGER.debug(
                "%s: disconnect cleanup timed out/failed: %s", self.address, err
            )

    async def update(self) -> None:
        """Update the controller, reading the selected port."""
        async def _do_update() -> None:
            await self._ensure_connected()
            try:
                command = self._protocol.get_model_data(
                    self._state.type, self._port, self.sequence
                )
                data = await self._send_command(command)
                if data is not None and len(data) >= 19:
                    self._state.work_type = data[12]
                    self._state.level_off = data[15]
                    self._state.level_on = data[18]
                    if self._state.work_type == 1:
                        self._state.fan = self._state.level_off
                    if self._state.work_type == 2:
                        self._state.fan = self._state.level_on
                    self._fire_callbacks(CallbackType.UPDATE_RESPONSE)
                elif data is not None:
                    _LOGGER.debug(
                        "%s: short update response (%d bytes), skipping",
                        self.address,
                        len(data),
                    )
            finally:
                await self._execute_disconnect()

        await self._run_with_retries("update", _do_update)

    async def turn_on(self, speed: int | None = None) -> None:
        """Turn on the selected port."""
        async def _do_turn_on() -> None:
            await self._ensure_connected()
            try:
                self._state.work_type = 2
                if speed is not None:
                    self._state.fan = speed
                    self._state.level_on = speed
                else:
                    self._state.fan = self._state.level_on or 10
                    self._state.level_on = self._state.fan
                command = self._protocol.set_level(
                    self._state.type, 2, self._state.level_on, self._port, self.sequence
                )
                await self._send_command(command)
            finally:
                await self._execute_disconnect()

        await self._run_with_retries("turn_on", _do_turn_on)

    async def turn_off(self) -> None:
        """Turn off the selected port."""
        async def _do_turn_off() -> None:
            await self._ensure_connected()
            try:
                self._state.work_type = 1
                self._state.fan = self._state.level_off or 0
                self._state.level_off = self._state.fan
                command = self._protocol.set_level(
                    self._state.type, 1, self._state.level_off, self._port, self.sequence
                )
                await self._send_command(command)
            finally:
                await self._execute_disconnect()

        await self._run_with_retries("turn_off", _do_turn_off)

    async def set_speed(self, speed: int) -> None:
        """Set the speed of the selected port."""
        async def _do_set_speed() -> None:
            await self._ensure_connected()
            try:
                self._state.work_type = 2 if speed > 0 else 1
                self._state.fan = speed
                if self._state.work_type == 1:
                    self._state.level_off = speed
                else:
                    self._state.level_on = speed
                command = self._protocol.set_level(
                    self._state.type, self._state.work_type, speed, self._port, self.sequence
                )
                await self._send_command(command)
            finally:
                await self._execute_disconnect()

        await self._run_with_retries("set_speed", _do_set_speed)


class MultiPortController(PortAwareController):
    """Controller that reads and writes each UIS port independently.

    Used for controllers that drive several loads at once (e.g. the office
    69 Pro: two fans + a grow light). The upstream library models a single
    port in ``DeviceInfo``; this subclass keeps a per-port ``PortState`` cache
    and addresses each port explicitly via the protocol's port argument, all
    over a single shared BLE connection (the link is held open for
    ``DISCONNECT_DELAY`` between commands).

    NOTE: the BLE port index is one-based (cloud "Port N" -> BLE byte N),
    verified live on a Controller 69 Pro (see SPEC.md "Port addressing").
    """

    def __init__(self, *args, ports: list[int], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._port_indices: list[int] = list(ports)
        self.port_states: dict[int, PortState] = {p: PortState() for p in ports}
        self._next_poll_port_idx = 0

    async def update(self) -> None:
        """Read one configured port (round-robin) in a connected session.

        Round-robin keeps house-wide BLE usage lower on multi-port controllers
        by polling only one port each poll cycle.
        """
        if not self._port_indices:
            return
        port = self._port_indices[self._next_poll_port_idx]
        self._next_poll_port_idx = (self._next_poll_port_idx + 1) % len(self._port_indices)

        async def _do_update() -> None:
            await self._ensure_connected()
            try:
                command = self._protocol.get_model_data(
                    self._state.type, port, self.sequence
                )
                data = await self._send_command(command)
                if data is not None and len(data) >= 19:
                    self.port_states[port] = PortState(
                        work_type=data[12],
                        level_off=data[15],
                        level_on=data[18],
                    )
                elif data is not None:
                    _LOGGER.debug(
                        "%s: short port-%d response (%d bytes), skipping",
                        self.address,
                        port,
                        len(data),
                    )
            finally:
                await self._execute_disconnect()
        await self._run_with_retries(f"poll_port_{port}", _do_update)
        self._fire_callbacks(CallbackType.UPDATE_RESPONSE)

    async def set_port_level(self, port: int, work_type: int, level: int) -> None:
        """Set one port to a work_type (1=off, 2=on) and level (0-10)."""
        async def _do_set_port_level() -> None:
            await self._ensure_connected()
            try:
                command = self._protocol.set_level(
                    self._state.type, work_type, level, port, self.sequence
                )
                await self._send_command(command)
                state = self.port_states.get(port) or PortState()
                state.work_type = work_type
                if work_type == 2:
                    state.level_on = level
                else:
                    state.level_off = level
                self.port_states[port] = state
                self._fire_callbacks(CallbackType.UPDATE_RESPONSE)
            finally:
                await self._execute_disconnect()

        await self._run_with_retries(f"set_port_level_{port}", _do_set_port_level)
