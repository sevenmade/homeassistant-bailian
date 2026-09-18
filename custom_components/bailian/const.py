"""Constants for the Alibaba Cloud Bailian integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN: Final = "bailian"
LOGGER = logging.getLogger(__package__)

CONF_REGION: Final = "region"
CONF_WORKSPACE_ID: Final = "workspace_id"
CONF_CHAT_MODEL: Final = "chat_model"
CONF_STT_MODEL: Final = "stt_model"
CONF_TTS_MODEL: Final = "tts_model"
CONF_TTS_VOICE: Final = "tts_voice"
CONF_ENABLE_STT: Final = "enable_stt"
CONF_ENABLE_TTS: Final = "enable_tts"
CONF_ENABLE_THINKING: Final = "enable_thinking"
CONF_TEMPERATURE: Final = "temperature"
CONF_MAX_TOKENS: Final = "max_tokens"
CONF_STT_PROMPT: Final = "stt_prompt"
CONF_REFRESH_MODELS: Final = "refresh_models"

DEFAULT_NAME: Final = "Alibaba Cloud Bailian"
DEFAULT_CONVERSATION_NAME: Final = "Bailian Conversation"
DEFAULT_STT_NAME: Final = "Bailian STT"
DEFAULT_TTS_NAME: Final = "Bailian TTS"

REGION_BEIJING: Final = "cn-beijing"
REGION_SINGAPORE: Final = "ap-southeast-1"
REGION_VIRGINIA: Final = "us-east-1"
REGION_HONGKONG: Final = "cn-hongkong"
REGION_TOKYO: Final = "ap-northeast-1"
REGION_FRANKFURT: Final = "eu-central-1"

DEFAULT_REGION: Final = REGION_BEIJING

RECOMMENDED_CHAT_MODEL: Final = "qwen3.8-flash"
RECOMMENDED_STT_MODEL: Final = "qwen3-asr-flash"
RECOMMENDED_TTS_MODEL: Final = "qwen3-tts-flash"
RECOMMENDED_TTS_VOICE: Final = "Cherry"
RECOMMENDED_ENABLE_STT: Final = True
RECOMMENDED_ENABLE_TTS: Final = True
RECOMMENDED_ENABLE_THINKING: Final = False
RECOMMENDED_TEMPERATURE: Final = 0.7
RECOMMENDED_MAX_TOKENS: Final = 2048
RECOMMENDED_STT_PROMPT: Final = (
    "The following conversation is a smart home user talking to Home Assistant."
)

CHAT_MODELS: Final = [
    "qwen3.8-flash",
    "qwen3.8-max",
    "qwen3.7-plus",
    "qwen3.7-flash",
    "qwen-plus",
    "qwen-flash",
    "qwen-turbo",
    "qwen-max",
]

STT_MODELS: Final = [
    "qwen3-asr-flash",
    "qwen3-asr-flash-2026-02-10",
    "qwen3-asr-flash-2025-09-08",
]

TTS_MODELS: Final = [
    "qwen3-tts-flash",
    "qwen3-tts-flash-2025-11-27",
    "qwen3-tts-instruct-flash",
    "qwen3-tts-vc-flash",
    "qwen-audio-3.0-tts-flash",
    "qwen-audio-3.0-tts-plus",
    "cosyvoice-v3-flash",
    "cosyvoice-v3-plus",
    "cosyvoice-v3.5-flash",
    "cosyvoice-v3.5-plus",
]

TTS_VOICES: Final = [
    "Cherry",
    "Serena",
    "Ethan",
    "Chelsie",
    "Momo",
    "Vivian",
    "Moon",
    "Maia",
    "Kai",
    "Nofish",
    "Bella",
    "Jennifer",
    "Ryan",
    "Katerina",
    "Aiden",
    "Eldric Sage",
    "Mia",
]

# Shared DashScope hostnames (no workspace id required).
DASHSCOPE_HOSTS: Final[dict[str, str]] = {
    REGION_BEIJING: "https://dashscope.aliyuncs.com",
    REGION_SINGAPORE: "https://dashscope-intl.aliyuncs.com",
    REGION_VIRGINIA: "https://dashscope-us.aliyuncs.com",
    REGION_HONGKONG: "https://cn-hongkong.dashscope.aliyuncs.com",
}

# Dedicated workspace host templates.
WORKSPACE_HOSTS: Final[dict[str, str]] = {
    REGION_BEIJING: "https://{workspace}.cn-beijing.maas.aliyuncs.com",
    REGION_SINGAPORE: "https://{workspace}.ap-southeast-1.maas.aliyuncs.com",
    REGION_VIRGINIA: "https://{workspace}.us-east-1.maas.aliyuncs.com",
    REGION_HONGKONG: "https://{workspace}.cn-hongkong.maas.aliyuncs.com",
    REGION_TOKYO: "https://{workspace}.ap-northeast-1.maas.aliyuncs.com",
    REGION_FRANKFURT: "https://{workspace}.eu-central-1.maas.aliyuncs.com",
}

REGIONS_REQUIRING_WORKSPACE: Final = frozenset({REGION_TOKYO, REGION_FRANKFURT})

REGION_LABELS: Final[dict[str, str]] = {
    REGION_BEIJING: "China (Beijing)",
    REGION_SINGAPORE: "Singapore",
    REGION_VIRGINIA: "US (Virginia)",
    REGION_HONGKONG: "China (Hong Kong)",
    REGION_TOKYO: "Japan (Tokyo)",
    REGION_FRANKFURT: "Germany (Frankfurt)",
}

TTS_LANGUAGE_TYPES: Final[dict[str, str]] = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
}

STT_LANGUAGES: Final = [
    "zh-CN",
    "en-US",
    "ja-JP",
    "ko-KR",
    "de-DE",
    "fr-FR",
    "ru-RU",
    "es-ES",
    "it-IT",
    "pt-PT",
    "ar-SA",
    "hi-IN",
    "id-ID",
    "th-TH",
    "tr-TR",
    "vi-VN",
]

TTS_LANGUAGES: Final = [
    "zh-CN",
    "en-US",
    "ja-JP",
    "ko-KR",
    "de-DE",
    "fr-FR",
    "ru-RU",
    "es-ES",
    "it-IT",
    "pt-PT",
]

RECOMMENDED_OPTIONS: Final[dict[str, object]] = {
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
    CONF_CHAT_MODEL: RECOMMENDED_CHAT_MODEL,
    CONF_STT_MODEL: RECOMMENDED_STT_MODEL,
    CONF_TTS_MODEL: RECOMMENDED_TTS_MODEL,
    CONF_TTS_VOICE: RECOMMENDED_TTS_VOICE,
    CONF_ENABLE_STT: RECOMMENDED_ENABLE_STT,
    CONF_ENABLE_TTS: RECOMMENDED_ENABLE_TTS,
    CONF_ENABLE_THINKING: RECOMMENDED_ENABLE_THINKING,
    CONF_TEMPERATURE: RECOMMENDED_TEMPERATURE,
    CONF_MAX_TOKENS: RECOMMENDED_MAX_TOKENS,
    CONF_STT_PROMPT: RECOMMENDED_STT_PROMPT,
}

MAX_TOOL_ITERATIONS: Final = 10
REQUEST_TIMEOUT: Final = 60
