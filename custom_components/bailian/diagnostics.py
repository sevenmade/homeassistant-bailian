"""Diagnostics for the Alibaba Cloud Bailian integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import BailianConfigEntry
from .const import CONF_WORKSPACE_ID

TO_REDACT = {CONF_API_KEY, CONF_WORKSPACE_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BailianConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "region": entry.runtime_data.client.region,
        "platforms": [platform.value for platform in entry.runtime_data.platforms],
    }
