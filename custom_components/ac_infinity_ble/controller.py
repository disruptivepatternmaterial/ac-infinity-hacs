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

from ac_infinity_ble import ACInfinityController, CallbackType

from .models import PortState


class PortAwareController(ACInfinityController):
    """An ACInfinityController that addresses the selected UIS port."""

    @property
    def _port(self) -> int:
        """Return the controller's currently selected port index."""
        return self._state.choose_port or 0

    async def update(self) -> None:
        """Update the controller, reading the selected port."""
        await self._ensure_connected()
        command = self._protocol.get_model_data(
            self._state.type, self._port, self.sequence
        )
        if data := await self._send_command(command):
            self._state.work_type = data[12]
            self._state.level_off = data[15]
            self._state.level_on = data[18]
            if self._state.work_type == 1:
                self._state.fan = self._state.level_off
            if self._state.work_type == 2:
                self._state.fan = self._state.level_on
            self._fire_callbacks(CallbackType.UPDATE_RESPONSE)
        await self._execute_disconnect()

    async def turn_on(self, speed: int | None = None) -> None:
        """Turn on the selected port."""
        await self._ensure_connected()
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
        await self._execute_disconnect()

    async def turn_off(self) -> None:
        """Turn off the selected port."""
        await self._ensure_connected()
        self._state.work_type = 1
        self._state.fan = self._state.level_off or 0
        self._state.level_off = self._state.fan
        command = self._protocol.set_level(
            self._state.type, 1, self._state.level_off, self._port, self.sequence
        )
        await self._send_command(command)
        await self._execute_disconnect()

    async def set_speed(self, speed: int) -> None:
        """Set the speed of the selected port."""
        await self._ensure_connected()
        self._state.work_type = 2 if speed > 0 else 1
        self.state.fan = speed
        if self._state.work_type == 1:
            self._state.level_off = speed
        else:
            self._state.level_on = speed
        command = self._protocol.set_level(
            self._state.type, self._state.work_type, speed, self._port, self.sequence
        )
        await self._send_command(command)
        await self._execute_disconnect()


class MultiPortController(PortAwareController):
    """Controller that reads and writes each UIS port independently.

    Used for controllers that drive several loads at once (e.g. the office
    69 Pro: two fans + a grow light). The upstream library models a single
    port in ``DeviceInfo``; this subclass keeps a per-port ``PortState`` cache
    and addresses each port explicitly via the protocol's port argument, all
    over a single shared BLE connection (the link is held open for
    ``DISCONNECT_DELAY`` between commands).

    NOTE: the BLE port index is assumed zero-based (cloud "Port N" -> index
    N-1). This must be verified against the live controller before trusting it.
    """

    def __init__(self, *args, ports: list[int], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._port_indices: list[int] = list(ports)
        self.port_states: dict[int, PortState] = {p: PortState() for p in ports}

    async def update(self) -> None:
        """Read every configured port in one connected session."""
        await self._ensure_connected()
        try:
            for port in self._port_indices:
                command = self._protocol.get_model_data(
                    self._state.type, port, self.sequence
                )
                if data := await self._send_command(command):
                    self.port_states[port] = PortState(
                        work_type=data[12],
                        level_off=data[15],
                        level_on=data[18],
                    )
            self._fire_callbacks(CallbackType.UPDATE_RESPONSE)
        finally:
            await self._execute_disconnect()

    async def set_port_level(self, port: int, work_type: int, level: int) -> None:
        """Set one port to a work_type (1=off, 2=on) and level (0-10)."""
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
