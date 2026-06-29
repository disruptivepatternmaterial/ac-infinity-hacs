"""Tests for PortAwareController / MultiPortController response handling.

Exercises the REAL controller classes (conftest provides a fake upstream base)
via object.__new__, covering the short-response guard and the bounded
disconnect override. The session/disconnect async_timeout is a no-op stub in
conftest, so the timing ceiling itself is not asserted here — only the parse and
error-handling branches.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ac_infinity_ble.controller import (
    InvalidResponseError,
    MultiPortController,
    PortAwareController,
)
from custom_components.ac_infinity_ble.models import PortState


def _valid_frame():
    frame = bytearray(19)
    frame[12] = 2  # work_type = on
    frame[15] = 3  # level_off
    frame[18] = 7  # level_on
    return frame


def _make_single():
    c = object.__new__(PortAwareController)
    c._ble_manager = None
    c._command_retry_count = 1
    c.address = "AA:BB:CC:DD:EE:FF"
    c._state = SimpleNamespace(
        type=11, choose_port=1, work_type=None, level_off=None, level_on=None, fan=None
    )
    c._protocol = MagicMock()
    c.sequence = 0
    c._ensure_connected = AsyncMock()
    c._send_command = AsyncMock()
    c._raw_disconnect = AsyncMock()
    c._fire_callbacks = MagicMock()
    return c


def _make_multi():
    c = object.__new__(MultiPortController)
    c._ble_manager = None
    c._command_retry_count = 1
    c.address = "AA:BB:CC:DD:EE:FF"
    c._state = SimpleNamespace(type=11, choose_port=1)
    c._protocol = MagicMock()
    c.sequence = 0
    c._ensure_connected = AsyncMock()
    c._send_command = AsyncMock()
    c._raw_disconnect = AsyncMock()
    c._fire_callbacks = MagicMock()
    c._port_indices = [1]
    c.port_states = {1: PortState()}
    c._next_poll_port_idx = 0
    return c


class TestSinglePortUpdate:
    def test_valid_frame_sets_state_and_disconnects(self):
        c = _make_single()
        c._send_command = AsyncMock(return_value=_valid_frame())
        asyncio.run(c.update())
        assert c._state.work_type == 2
        assert c._state.level_off == 3
        assert c._state.level_on == 7
        assert c._state.fan == 7  # work_type 2 -> fan tracks level_on
        c._fire_callbacks.assert_called_once()
        c._raw_disconnect.assert_awaited()

    def test_short_frame_raises_and_keeps_state(self):
        c = _make_single()
        c._send_command = AsyncMock(return_value=bytes(10))
        with pytest.raises(InvalidResponseError):
            asyncio.run(c.update())
        assert c._state.work_type is None
        c._fire_callbacks.assert_not_called()
        c._raw_disconnect.assert_awaited()  # finally still disconnects

    def test_none_response_is_noop(self):
        c = _make_single()
        c._send_command = AsyncMock(return_value=None)
        asyncio.run(c.update())
        assert c._state.work_type is None
        c._fire_callbacks.assert_not_called()


class TestMultiPortUpdate:
    def test_valid_frame_updates_port_state(self):
        c = _make_multi()
        c._send_command = AsyncMock(return_value=_valid_frame())
        asyncio.run(c.update())
        ps = c.port_states[1]
        assert ps.work_type == 2
        assert ps.level_off == 3
        assert ps.level_on == 7
        c._fire_callbacks.assert_called_once()

    def test_short_frame_raises(self):
        c = _make_multi()
        c._send_command = AsyncMock(return_value=bytes(5))
        with pytest.raises(InvalidResponseError):
            asyncio.run(c.update())
        c._fire_callbacks.assert_not_called()
        assert c.port_states[1].work_type is None


class TestExecuteDisconnect:
    def test_swallows_disconnect_error(self):
        c = _make_single()
        c._raw_disconnect = AsyncMock(side_effect=RuntimeError("boom"))
        # Must not raise — cleanup errors are logged and swallowed.
        asyncio.run(c._execute_disconnect())

    def test_propagates_cancelled_error(self):
        c = _make_single()
        c._raw_disconnect = AsyncMock(side_effect=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(c._execute_disconnect())
