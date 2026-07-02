"""Options flow for AC Infinity BLE integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_COMMAND_RETRY_COUNT,
    CONF_MIN_CONNECT_GAP_SECONDS,
    CONF_PASSIVE_ONLY,
    CONF_POLL_INTERVAL_SECONDS,
    DEFAULT_COMMAND_RETRY_COUNT,
    DEFAULT_MIN_CONNECT_GAP_SECONDS,
    DEFAULT_PASSIVE_ONLY,
    DEFAULT_POLL_INTERVAL_SECONDS,
)


class ACInfinityOptionsFlow(config_entries.OptionsFlow):
    """Handle AC Infinity BLE options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show and process options form."""
        if user_input is not None:
            # Merge over existing options instead of replacing them wholesale,
            # so keys not on this form (e.g. a manually-added CONF_PORTS list)
            # survive an options save.
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL_SECONDS,
                    default=self._option(
                        CONF_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=900)),
                vol.Required(
                    CONF_PASSIVE_ONLY,
                    default=self._option(CONF_PASSIVE_ONLY, DEFAULT_PASSIVE_ONLY),
                ): bool,
                vol.Required(
                    CONF_MIN_CONNECT_GAP_SECONDS,
                    default=self._option(
                        CONF_MIN_CONNECT_GAP_SECONDS, DEFAULT_MIN_CONNECT_GAP_SECONDS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                vol.Required(
                    CONF_COMMAND_RETRY_COUNT,
                    default=self._option(
                        CONF_COMMAND_RETRY_COUNT, DEFAULT_COMMAND_RETRY_COUNT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    def _option(self, key: str, default: Any) -> Any:
        if key in self._config_entry.options:
            return self._config_entry.options[key]
        return self._config_entry.data.get(key, default)
