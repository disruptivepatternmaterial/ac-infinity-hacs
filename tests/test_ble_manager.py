"""Tests for ACInfinityBLEManager poll scheduling and failure back-off.

conftest.py stubs the integration's .const module, so these exercise the real
ble_manager.py against known constant values (FAILURE_BACKOFF_SECONDS=30,
DEFAULT_POLL_INTERVAL_SECONDS=120).
"""
from __future__ import annotations

from time import monotonic

from custom_components.ac_infinity_ble.ble_manager import ACInfinityBLEManager

ADDR = "AA:BB:CC:DD:EE:FF"


def _manager(interval: int = 120, gap: int = 0) -> ACInfinityBLEManager:
    m = ACInfinityBLEManager()
    m.configure_address(ADDR, min_connect_gap_seconds=gap, poll_interval_seconds=interval)
    return m


class TestPollFailureBackoff:
    def test_failure_increments_and_records_error(self):
        m = _manager()
        m.note_poll_failure(ADDR, RuntimeError("boom"))
        stats = m.stats(ADDR)
        assert stats.poll_failures == 1
        assert stats.last_error == "boom"

    def test_failure_with_blank_message_uses_class_name(self):
        m = _manager()
        m.note_poll_failure(ADDR, TimeoutError())
        assert m.stats(ADDR).last_error == "TimeoutError"

    def test_failure_schedules_backoff_capped_by_interval(self):
        # interval (5) smaller than FAILURE_BACKOFF_SECONDS (30) -> capped at 5
        m = _manager(interval=5)
        before = monotonic()
        m.note_poll_failure(ADDR, RuntimeError("x"))
        due = m.stats(ADDR).next_poll_due_monotonic
        assert due is not None
        assert before + 5 - 0.5 <= due <= before + 5 + 0.5

    def test_failure_backoff_uses_30s_when_interval_large(self):
        m = _manager(interval=120)
        before = monotonic()
        m.note_poll_failure(ADDR, RuntimeError("x"))
        due = m.stats(ADDR).next_poll_due_monotonic
        assert due is not None
        assert before + 30 - 0.5 <= due <= before + 30 + 0.5

    def test_failure_then_advertisement_does_not_immediately_repoll(self):
        """After a failure the next poll must not be due right away (no storm)."""
        m = _manager(interval=120)
        m.note_poll_failure(ADDR, RuntimeError("x"))
        assert (
            m.should_poll_now(
                ADDR, seconds_since_last_poll=None, poll_interval_seconds=120
            )
            is False
        )


class TestShouldPollNow:
    def test_first_call_initializes_and_returns_false(self):
        m = _manager(interval=120)
        assert (
            m.should_poll_now(
                ADDR, seconds_since_last_poll=None, poll_interval_seconds=120
            )
            is False
        )
        assert m.stats(ADDR).next_poll_due_monotonic is not None

    def test_returns_true_once_due_passes(self):
        m = _manager(interval=120)
        m.should_poll_now(ADDR, seconds_since_last_poll=None, poll_interval_seconds=120)
        m.stats(ADDR).next_poll_due_monotonic = monotonic() - 1
        assert (
            m.should_poll_now(
                ADDR, seconds_since_last_poll=None, poll_interval_seconds=120
            )
            is True
        )

    def test_success_schedules_full_interval(self):
        m = _manager(interval=120)
        before = monotonic()
        m.note_poll_success(ADDR)
        due = m.stats(ADDR).next_poll_due_monotonic
        assert due is not None
        assert before + 120 - 0.5 <= due <= before + 120 + 0.5
