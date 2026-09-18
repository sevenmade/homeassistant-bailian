"""The Alibaba Cloud Bailian integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .client import BailianAuthError, BailianClient, BailianConnectionError, BailianError
from .const import (
    CONF_ENABLE_STT,
    CONF_ENABLE_TTS,
    CONF_REGION,
    CONF_WORKSPACE_ID,
    DOMAIN,
    LOGGER,
    RECOMMENDED_ENABLE_STT,
    RECOMMENDED_ENABLE_TTS,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class BailianData:
    """Runtime data for a Bailian config entry."""

    client: BailianClient
    platforms: tuple[Platform, ...]


type BailianConfigEntry = ConfigEntry[BailianData]


def enabled_platforms(entry: ConfigEntry) -> tuple[Platform, ...]:
    """Return platforms enabled in the config entry options."""
    platforms: list[Platform] = [Platform.CONVERSATION]
    if entry.options.get(CONF_ENABLE_STT, RECOMMENDED_ENABLE_STT):
        platforms.append(Platform.STT)
    if entry.options.get(CONF_ENABLE_TTS, RECOMMENDED_ENABLE_TTS):
        platforms.append(Platform.TTS)
    return tuple(platforms)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Bailian integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BailianConfigEntry) -> bool:
    """Set up Bailian from a config entry."""
    client = BailianClient(
        session=async_get_clientsession(hass),
        api_key=entry.data[CONF_API_KEY],
        region=entry.data[CONF_REGION],
        workspace_id=entry.data.get(CONF_WORKSPACE_ID),
    )

    try:
        await client.async_validate()
    except BailianAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (BailianConnectionError, BailianError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    platforms = enabled_platforms(entry)
    entry.runtime_data = BailianData(client=client, platforms=platforms)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    LOGGER.debug(
        "Bailian entry %s set up for region %s (platforms=%s)",
        entry.entry_id,
        client.region,
        platforms,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BailianConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(
        entry, entry.runtime_data.platforms
    )


async def async_reload_entry(hass: HomeAssistant, entry: BailianConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
