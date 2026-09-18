"""Text-to-speech support for Alibaba Cloud Bailian."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BailianConfigEntry
from .client import BailianError
from .const import (
    CONF_TTS_MODEL,
    CONF_TTS_VOICE,
    DEFAULT_TTS_NAME,
    DOMAIN,
    LOGGER,
    RECOMMENDED_TTS_MODEL,
    RECOMMENDED_TTS_VOICE,
    TTS_LANGUAGE_TYPES,
    TTS_LANGUAGES,
    TTS_VOICES,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BailianConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Bailian TTS entity."""
    async_add_entities([BailianTTSEntity(config_entry)])


class BailianTTSEntity(TextToSpeechEntity):
    """Bailian text-to-speech entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "tts"
    _attr_supported_languages = list(TTS_LANGUAGES)
    _attr_default_language = "zh-CN"
    _attr_supported_options = [ATTR_VOICE]

    def __init__(self, entry: BailianConfigEntry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}-tts"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_TTS_NAME,
            manufacturer="Alibaba Cloud",
            model="Bailian",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        self._voices = [Voice(voice, voice) for voice in TTS_VOICES]

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice]:
        """Return supported voices."""
        return self._voices

    @property
    def default_options(self) -> Mapping[str, Any]:
        """Return default TTS options."""
        return {
            ATTR_VOICE: self.entry.options.get(CONF_TTS_VOICE, RECOMMENDED_TTS_VOICE)
        }

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Generate speech audio from text."""
        voice = options.get(
            ATTR_VOICE,
            self.entry.options.get(CONF_TTS_VOICE, RECOMMENDED_TTS_VOICE),
        )
        language_type = TTS_LANGUAGE_TYPES.get(language.split("-")[0], "Chinese")
        try:
            extension, audio = await self.entry.runtime_data.client.async_synthesize(
                text=message,
                model=self.entry.options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL),
                voice=str(voice),
                language_type=language_type,
            )
        except BailianError as err:
            LOGGER.exception("Error during Bailian TTS")
            raise HomeAssistantError(str(err)) from err
        return extension, audio
