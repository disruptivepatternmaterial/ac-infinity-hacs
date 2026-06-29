"""AC Infinity Coordinator."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from ac_infinity_ble import ACInfinityController
import async_timeout
from bleak.backends.device import BLEDevice

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import CoreState, HomeAssistant, callback

from .ble_manager import ACInfinityBLEManager
from .const import DEFAULT_POLL_INTERVAL_SECONDS


DEVICE_STARTUP_TIMEOUT = 30


class ACInfinityDataUpdateCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Coordinator that polls and consumes advertisements for one controller."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        ble_device: BLEDevice,
        controller: ACInfinityController,
        ble_manager: ACInfinityBLEManager,
        *,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        passive_only: bool = False,
    ) -> None:
        """Initialize the AC Infinity data updater."""
        super().__init__(
            hass=hass,
            logger=logger,
            address=ble_device.address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            # Listen to ALL advertisements, including non-connectable ones. The
            # controller's full state (temp/hum/vpd/fan/fan_state) lives in the
            # advertisement manufacturer data, so passive updates keep entities
            # fresh even when the only nearby proxy is non-connectable. Commands
            # and polls still establish their own connectable link on demand.
            connectable=False,
        )
        self.ble_device = ble_device
        self.controller = controller
        self.ble_manager = ble_manager
        self.poll_interval_seconds = max(1, poll_interval_seconds)
        self.passive_only = passive_only
        self._ready_event = asyncio.Event()
        self._was_unavailable = True

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        if self.hass.state != CoreState.running:
            return False
        if self.passive_only:
            return False
        connectable_ble_device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        if not bool(connectable_ble_device):
            return False
        # Force a poll on first setup and on recovery from "unavailable" so the
        # fields that never appear in advertisements (work_type / per-port
        # state) refresh promptly. The flag is cleared in _async_update so this
        # only fires once per episode.
        if self._was_unavailable:
            return True
        # Otherwise poll on the configured interval, tracked from the last
        # successful poll (not from advertisement recency, which would suppress
        # polling entirely while the controller is advertising and leave
        # multi-port / on-off state frozen).
        return self.ble_manager.should_poll_now(
            service_info.device.address,
            poll_interval_seconds=self.poll_interval_seconds,
        )

    async def _async_update(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Poll the device."""
        # Clear the recovery flag before polling so the forced poll is attempted
        # exactly once; subsequent scheduling falls back to interval/back-off.
        self._was_unavailable = False
        try:
            await self.controller.update()
        except Exception as err:
            self.ble_manager.note_poll_failure(service_info.device.address, err)
            raise
        else:
            self.ble_manager.note_poll_success(service_info.device.address)

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Handle the device going unavailable."""
        super()._async_handle_unavailable(service_info)
        self._was_unavailable = True

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a Bluetooth event."""
        self.ble_device = service_info.device
        self.controller.set_ble_device_and_advertisement_data(
            service_info.device, service_info.advertisement
        )
        self.ble_manager.note_advertisement(service_info.device.address, service_info.rssi)
        if self.controller.name:
            self._ready_event.set()
        self.logger.debug(
            "%s: AC Infinity data: %s", self.ble_device.address, self.controller.state
        )
        # NOTE: do not clear self._was_unavailable here. It is cleared in
        # _async_update so the recovery poll is actually scheduled by
        # _needs_poll (which super() invokes on this advertisement).
        super()._async_handle_bluetooth_event(service_info, change)

    async def async_wait_ready(self) -> bool:
        """Wait for the device to be ready."""
        with contextlib.suppress(asyncio.TimeoutError):
            async with async_timeout.timeout(DEVICE_STARTUP_TIMEOUT):
                await self._ready_event.wait()
                return True
        return False
