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
from .client import BailianError, CustomVoice, resolve_tts_model
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
        self._custom_by_id: dict[str, CustomVoice] = {}

    async def async_added_to_hass(self) -> None:
        """Load enrolled / designed voices from Bailian."""
        await super().async_added_to_hass()
        await self._async_refresh_voices()

    async def _async_refresh_voices(self) -> None:
        """Merge custom voices ahead of the built-in system list."""
        custom: list[CustomVoice] = []
        try:
            custom = await self.entry.runtime_data.client.async_list_custom_voices()
        except BailianError as err:
            LOGGER.debug("Could not list Bailian custom voices: %s", err)
        self._custom_by_id = {item.voice_id: item for item in custom}
        voices = [Voice(item.voice_id, item.label) for item in custom]
        seen = set(self._custom_by_id)
        selected = self.entry.options.get(CONF_TTS_VOICE)
        if isinstance(selected, str) and selected not in seen and selected not in TTS_VOICES:
            voices.insert(0, Voice(selected, selected))
            seen.add(selected)
        for voice_id in TTS_VOICES:
            if voice_id not in seen:
                voices.append(Voice(voice_id, voice_id))
        self._voices = voices

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
        voice_id = str(voice)
        configured_model = self.entry.options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL)
        model = resolve_tts_model(
            voice_id, configured_model, self._custom_by_id.get(voice_id)
        )
        language_type = TTS_LANGUAGE_TYPES.get(language.split("-")[0], "Chinese")
        try:
            extension, audio = await self.entry.runtime_data.client.async_synthesize(
                text=message,
                model=str(model),
                voice=voice_id,
                language_type=language_type,
            )
        except BailianError as err:
            LOGGER.exception("Error during Bailian TTS")
            raise HomeAssistantError(str(err)) from err
        return extension, audio
