"""Shared BLE connection manager for AC Infinity controllers."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from .const import DEFAULT_MIN_CONNECT_GAP_SECONDS


@dataclass
class BLEDeviceStats:
    """Runtime BLE stats for one controller."""

    last_rssi: int | None = None
    last_seen: datetime | None = None
    last_error: str | None = None
    poll_failures: int = 0
    next_poll_due_monotonic: float | None = None


class ACInfinityBLEManager:
    """Global BLE manager shared across config entries."""

    def __init__(self) -> None:
        self._global_lock = asyncio.Lock()
        self._last_connect_started = 0.0
        self._min_gap_by_address: dict[str, float] = {}
        self._poll_interval_by_address: dict[str, int] = {}
        self._stats_by_address: dict[str, BLEDeviceStats] = {}

    def configure_address(
        self,
        address: str,
        *,
        min_connect_gap_seconds: int,
        poll_interval_seconds: int,
    ) -> None:
        """Apply options for one address."""
        normalized = address.upper()
        self._min_gap_by_address[normalized] = float(max(0, min_connect_gap_seconds))
        self._poll_interval_by_address[normalized] = max(1, poll_interval_seconds)

    def clear_address(self, address: str) -> None:
        """Drop all runtime state for an address."""
        normalized = address.upper()
        self._min_gap_by_address.pop(normalized, None)
        self._poll_interval_by_address.pop(normalized, None)
        self._stats_by_address.pop(normalized, None)

    @asynccontextmanager
    async def acquire(self, address: str) -> AsyncIterator[None]:
        """Acquire the global BLE session lock with minimum session spacing."""
        normalized = address.upper()
        min_gap = self._min_gap_by_address.get(
            normalized, float(DEFAULT_MIN_CONNECT_GAP_SECONDS)
        )
        async with self._global_lock:
            now = monotonic()
            wait_for = max(0.0, (self._last_connect_started + min_gap) - now)
            if wait_for:
                await asyncio.sleep(wait_for)
            self._last_connect_started = monotonic()
            yield

    def stats(self, address: str) -> BLEDeviceStats:
        """Return stats object for one address."""
        normalized = address.upper()
        return self._stats_by_address.setdefault(normalized, BLEDeviceStats())

    def note_advertisement(self, address: str, rssi: int | None) -> None:
        """Update passive diagnostics on advertisement reception."""
        entry = self.stats(address)
        entry.last_seen = datetime.now(UTC)
        entry.last_rssi = rssi

    def note_poll_success(self, address: str) -> None:
        """Update poll scheduling on successful poll."""
        normalized = address.upper()
        entry = self.stats(normalized)
        interval = self._poll_interval_by_address.get(normalized, 120)
        entry.next_poll_due_monotonic = monotonic() + interval

    def note_poll_failure(self, address: str, error: Exception) -> None:
        """Record poll failure diagnostics."""
        entry = self.stats(address)
        entry.poll_failures += 1
        entry.last_error = str(error) or error.__class__.__name__

    def note_command_failure(self, address: str, error: Exception) -> None:
        """Record command failure diagnostics."""
        entry = self.stats(address)
        entry.last_error = str(error) or error.__class__.__name__

    def should_poll_now(
        self,
        address: str,
        *,
        seconds_since_last_poll: float | None,
        poll_interval_seconds: int,
    ) -> bool:
        """Return True when this address should actively poll now."""
        normalized = address.upper()
        entry = self.stats(normalized)
        now = monotonic()
        if entry.next_poll_due_monotonic is None:
            stagger = self._stagger_offset_seconds(normalized, poll_interval_seconds)
            entry.next_poll_due_monotonic = now + stagger
            return False
        if seconds_since_last_poll is None:
            return now >= entry.next_poll_due_monotonic
        return now >= entry.next_poll_due_monotonic

    @staticmethod
    def _stagger_offset_seconds(address: str, interval_seconds: int) -> int:
        """Compute deterministic poll stagger for an address."""
        if interval_seconds <= 1:
            return 0
        return sum(address.encode("utf-8")) % interval_seconds
