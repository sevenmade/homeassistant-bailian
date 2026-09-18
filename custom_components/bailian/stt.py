"""Speech-to-text support for Alibaba Cloud Bailian."""

from __future__ import annotations

from collections.abc import AsyncIterable
import io
import wave

from homeassistant.components import stt
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BailianConfigEntry
from .client import BailianError
from .const import (
    CONF_STT_MODEL,
    CONF_STT_PROMPT,
    DEFAULT_STT_NAME,
    DOMAIN,
    LOGGER,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_STT_PROMPT,
    STT_LANGUAGES,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BailianConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Bailian STT entity."""
    async_add_entities([BailianSTTEntity(config_entry)])


class BailianSTTEntity(stt.SpeechToTextEntity):
    """Bailian speech-to-text entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "stt"

    def __init__(self, entry: BailianConfigEntry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}-stt"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_STT_NAME,
            manufacturer="Alibaba Cloud",
            model="Bailian",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages."""
        return list(STT_LANGUAGES)

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Return supported audio formats."""
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Return supported codecs."""
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Return supported bit rates."""
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Return supported sample rates."""
        return [
            stt.AudioSampleRates.SAMPLERATE_8000,
            stt.AudioSampleRates.SAMPLERATE_16000,
            stt.AudioSampleRates.SAMPLERATE_22000,
            stt.AudioSampleRates.SAMPLERATE_44100,
            stt.AudioSampleRates.SAMPLERATE_48000,
        ]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Return supported channels."""
        return [stt.AudioChannels.CHANNEL_MONO, stt.AudioChannels.CHANNEL_STEREO]

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Send captured audio to Qwen-ASR."""
        audio_bytes = bytearray()
        async for chunk in stream:
            audio_bytes.extend(chunk)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(metadata.channel.value)
            wav_file.setsampwidth(metadata.bit_rate.value // 8)
            wav_file.setframerate(metadata.sample_rate.value)
            wav_file.writeframes(bytes(audio_bytes))
        audio_data = wav_buffer.getvalue()

        options = self.entry.options
        try:
            text = await self.entry.runtime_data.client.async_transcribe(
                audio=audio_data,
                mime_type="audio/wav",
                model=options.get(CONF_STT_MODEL, RECOMMENDED_STT_MODEL),
                language=metadata.language,
                context=options.get(CONF_STT_PROMPT, RECOMMENDED_STT_PROMPT),
            )
        except BailianError:
            LOGGER.exception("Error during Bailian STT")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        if not text:
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)
