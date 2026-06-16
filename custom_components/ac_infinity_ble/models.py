"""The led ble integration models."""
from __future__ import annotations

from dataclasses import dataclass, field

from ac_infinity_ble import ACInfinityController

from .coordinator import ACInfinityDataUpdateCoordinator


@dataclass
class PortConfig:
    """Static configuration for one UIS port on a multi-port controller.

    ``port`` is the one-based BLE port index passed to the protocol
    (``get_model_data``/``set_level``); it matches the port number printed on
    the controller and used by the AC Infinity cloud (cloud "Port 1" -> BLE
    byte ``ff01``). Verified live against G-622UC on 2026-06-15: bytes
    ``ff01``/``ff02``/``ff03`` each return that port's data (see SPEC.md).

    ``name`` is the role-only entity name (e.g. "Fan 1", "Bathroom Grow
    Light"); Home Assistant prepends the device name via ``has_entity_name``.
    """

    port: int
    kind: str  # "fan" or "light"
    name: str


@dataclass
class PortState:
    """Live state for one UIS port, read via get_model_data(type, port)."""

    work_type: int | None = None  # 1 = off, 2 = on
    level_on: int | None = None
    level_off: int | None = None

    @property
    def level(self) -> int:
        """Effective current level (0-10) for this port."""
        if self.work_type == 2:
            return self.level_on or 0
        return self.level_off or 0

    @property
    def is_on(self) -> bool:
        """Whether this port is currently driven on."""
        return self.work_type == 2 and bool(self.level_on)


@dataclass
class ACInfinityData:
    """Data for the AC Infinity integration."""

    title: str
    device: ACInfinityController
    coordinator: ACInfinityDataUpdateCoordinator
    ports: list[PortConfig] = field(default_factory=list)
