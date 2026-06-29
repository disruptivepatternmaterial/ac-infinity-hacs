"""Tests for the coordinator poll-gating lifecycle (the headline review fix).

Exercises the REAL ACInfinityDataUpdateCoordinator._needs_poll / _async_update
against a REAL ACInfinityBLEManager, with HA internals stubbed by conftest.
Instances are built with object.__new__ to bypass HA's __init__.
"""
from __future__ import annotations

import asyncio
import logging
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.components import bluetooth

from custom_components.ac_infinity_ble.ble_manager import ACInfinityBLEManager
from custom_components.ac_infinity_ble.coordinator import (
    ACInfinityDataUpdateCoordinator,
)

ADDR = "AA:BB:CC:DD:EE:FF"


@pytest.fixture(autouse=True)
def _event_loop():
    """Ensure a current event loop so asyncio.Lock() can be constructed.

    On Python 3.9 a prior asyncio.run() leaves no current loop, which breaks
    ACInfinityBLEManager()'s lock creation. HA runs on 3.12+ where this is moot.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    asyncio.set_event_loop(None)
    loop.close()


@pytest.fixture(autouse=True)
def _connectable():
    """Default: a connectable device exists (truthy)."""
    bluetooth.async_ble_device_from_address.return_value = object()
    yield
    bluetooth.async_ble_device_from_address.reset_mock(return_value=True)


def _coord(passive_only=False, was_unavailable=False, interval=120):
    c = object.__new__(ACInfinityDataUpdateCoordinator)
    c.hass = SimpleNamespace(state="running")
    c.address = ADDR
    c.logger = logging.getLogger("test.coordinator")
    c.passive_only = passive_only
    c._was_unavailable = was_unavailable
    c.poll_interval_seconds = interval
    mgr = ACInfinityBLEManager()
    mgr.configure_address(ADDR, min_connect_gap_seconds=0, poll_interval_seconds=interval)
    c.ble_manager = mgr
    c.controller = MagicMock()
    return c


def _svc():
    return SimpleNamespace(device=SimpleNamespace(address=ADDR))


class TestNeedsPoll:
    def test_forces_poll_on_recovery_or_first_run(self):
        c = _coord(was_unavailable=True)
        assert c._needs_poll(_svc(), None) is True

    def test_passive_only_blocks_even_on_recovery(self):
        c = _coord(passive_only=True, was_unavailable=True)
        assert c._needs_poll(_svc(), None) is False

    def test_not_connectable_returns_false(self):
        bluetooth.async_ble_device_from_address.return_value = None
        c = _coord(was_unavailable=True)
        assert c._needs_poll(_svc(), None) is False

    def test_steady_state_gates_on_interval(self):
        c = _coord(was_unavailable=False)
        # First call initializes the schedule and declines to poll.
        assert c._needs_poll(_svc(), None) is False
        # Once due passes, it polls.
        c.ble_manager.stats(ADDR).next_poll_due_monotonic = monotonic() - 1
        assert c._needs_poll(_svc(), None) is True


class TestAsyncUpdate:
    def test_success_clears_flag_and_schedules_interval(self):
        c = _coord(was_unavailable=True)
        c.controller.update = AsyncMock(return_value=None)
        asyncio.run(c._async_update(_svc()))
        assert c._was_unavailable is False
        due = c.ble_manager.stats(ADDR).next_poll_due_monotonic
        assert due is not None and due > monotonic()

    def test_failure_clears_flag_backs_off_and_reraises(self):
        c = _coord(was_unavailable=True)
        c.controller.update = AsyncMock(side_effect=RuntimeError("ble fail"))
        with pytest.raises(RuntimeError):
            asyncio.run(c._async_update(_svc()))
        stats = c.ble_manager.stats(ADDR)
        assert c._was_unavailable is False
        assert stats.poll_failures == 1
        assert stats.next_poll_due_monotonic is not None

    def test_failed_poll_then_advert_does_not_immediately_repoll(self):
        """Regression guard for the storm interaction: after a failed poll the
        recovery flag is cleared and back-off keeps the next poll un-due."""
        c = _coord(was_unavailable=True)
        c.controller.update = AsyncMock(side_effect=RuntimeError("x"))
        with pytest.raises(RuntimeError):
            asyncio.run(c._async_update(_svc()))
        # Next advertisement: flag cleared, back-off in force -> no poll.
        assert c._needs_poll(_svc(), None) is False


class TestAsyncWaitReady:
    def test_returns_immediately_when_state_restored(self):
        """Cached/restored state (controller.name set) must not block startup."""
        c = _coord()
        c.controller.name = "Office 69 Pro"
        c._ready_event = asyncio.Event()  # never set
        assert asyncio.run(c.async_wait_ready()) is True

    def test_returns_true_when_event_already_set(self):
        c = _coord()
        c.controller.name = None

        async def _run():
            c._ready_event = asyncio.Event()
            c._ready_event.set()
            return await c.async_wait_ready()

        assert asyncio.run(_run()) is True
