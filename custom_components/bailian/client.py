"""Async Alibaba Cloud Bailian / DashScope client.

This module talks to Bailian over HTTP with aiohttp only. Keep it free of Home
Assistant imports so it can later move into a standalone PyPI package.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp
from yarl import URL

from .const import (
    ASR_LANGUAGE_CODES,
    DASHSCOPE_HOSTS,
    LOGGER,
    RECOMMENDED_TTS_MODEL,
    REGION_BEIJING,
    REGIONS_REQUIRING_WORKSPACE,
    REQUEST_TIMEOUT,
    TTS_VOICES,
    WORKSPACE_HOSTS,
)


class BailianError(Exception):
    """Base error for Bailian API calls."""


class BailianAuthError(BailianError):
    """Raised when the API key is rejected."""


class BailianConnectionError(BailianError):
    """Raised when the service cannot be reached."""


def build_base_url(region: str, workspace_id: str | None = None) -> str:
    """Return the DashScope / workspace base URL for a region."""
    workspace = (workspace_id or "").strip()
    if workspace:
        template = WORKSPACE_HOSTS.get(region)
        if template is None:
            raise BailianError(f"Unsupported region: {region}")
        return template.format(workspace=workspace)
    if region in REGIONS_REQUIRING_WORKSPACE:
        raise BailianError(
            f"Region {region} requires a workspace ID for the dedicated endpoint"
        )
    host = DASHSCOPE_HOSTS.get(region)
    if host is None:
        raise BailianError(f"Unsupported region: {region}")
    return host


def compatible_base_url(region: str, workspace_id: str | None = None) -> str:
    """Return the OpenAI-compatible chat base URL."""
    return f"{build_base_url(region, workspace_id)}/compatible-mode/v1"


def native_base_url(region: str, workspace_id: str | None = None) -> str:
    """Return the DashScope native API base URL."""
    return f"{build_base_url(region, workspace_id)}/api/v1"


@dataclass(slots=True)
class ChatMessage:
    """A chat completions message."""

    role: str
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    name: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the OpenAI-compatible payload."""
        payload: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            payload["content"] = self.content
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        if self.name is not None:
            payload["name"] = self.name
        return payload


@dataclass(slots=True)
class ChatResult:
    """Parsed chat completion result."""

    content: str | None
    tool_calls: list[dict[str, Any]]
    raw: dict[str, Any]


@dataclass(slots=True)
class CustomVoice:
    """A user-enrolled or designed TTS voice from Bailian."""

    voice_id: str
    label: str
    target_model: str | None = None
    source: str = "custom"


@dataclass(slots=True)
class AuthorizedModel:
    """A model the current API key is allowed to call."""

    model_id: str
    name: str | None = None

    @property
    def label(self) -> str:
        """Dropdown label with a human-readable name when Bailian provides one."""
        if self.name and self.name != self.model_id:
            return f"{self.name} ({self.model_id})"
        return self.model_id


class BailianClient:
    """Async client for Bailian chat, STT and TTS APIs."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        region: str = REGION_BEIJING,
        workspace_id: str | None = None,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self._region = region
        self._workspace_id = workspace_id or None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._compatible_url = compatible_base_url(region, workspace_id)
        self._native_url = native_base_url(region, workspace_id)

    @property
    def region(self) -> str:
        """Configured region."""
        return self._region

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_data: dict[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request and return JSON."""
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(extra_headers),
                json=json_data,
                params=params,
                timeout=self._timeout,
            ) as response:
                payload: dict[str, Any]
                try:
                    payload = await response.json(content_type=None)
                except aiohttp.ContentTypeError as err:
                    text = await response.text()
                    raise BailianError(
                        f"Unexpected response ({response.status}): {text[:200]}"
                    ) from err

                if response.status in (401, 403):
                    raise BailianAuthError(
                        _extract_error_message(payload) or "Invalid API key"
                    )
                if response.status >= 400:
                    raise BailianError(
                        _extract_error_message(payload)
                        or f"HTTP {response.status}"
                    )
                if isinstance(payload, dict) and payload.get("code") not in (
                    None,
                    "",
                    "Success",
                ):
                    # DashScope sometimes returns HTTP 200 with a business error.
                    code = str(payload.get("code"))
                    if code.upper() in {"UNAUTHORIZED", "INVALIDAPIKEY", "INVALID_API_KEY"}:
                        raise BailianAuthError(_extract_error_message(payload))
                    raise BailianError(_extract_error_message(payload) or code)
                return payload
        except asyncio.TimeoutError as err:
            raise BailianConnectionError("Timeout talking to Bailian") from err
        except aiohttp.ClientError as err:
            raise BailianConnectionError(str(err)) from err

    async def async_validate(self) -> None:
        """Validate credentials by listing compatible-mode models."""
        await self.async_list_chat_models()

    async def async_list_chat_models(self) -> list[str]:
        """Return chat-capable model IDs from the compatible-mode API."""
        return [
            item.model_id
            for item in await self._async_list_compatible_models()
            if is_chat_model(item.model_id)
        ]

    async def async_list_authorized_models(self) -> list[AuthorizedModel]:
        """Return models this API key is authorized to call.

        Prefer the workspace permissions API (already-authorized inference).
        Fall back to the compatible-mode catalog if permissions are unavailable.
        """
        try:
            return await self._async_list_permission_models()
        except BailianError as err:
            LOGGER.debug(
                "Could not list Bailian model permissions, falling back to catalog: %s",
                err,
            )
            return await self._async_list_compatible_models()

    async def _async_list_permission_models(self) -> list[AuthorizedModel]:
        """Page through GET /api/v1/models/permissions?authorization_scope=AUTHORIZED."""
        models: list[AuthorizedModel] = []
        seen: set[str] = set()
        page_no = 1
        while page_no <= _PERMISSION_MAX_PAGES:
            payload = await self._request(
                "GET",
                f"{self._native_url}/models/permissions",
                params={
                    "authorization_scope": "AUTHORIZED",
                    "action": "INFERENCE",
                    "page_no": page_no,
                    "page_size": _PERMISSION_PAGE_SIZE,
                },
            )
            if isinstance(payload, dict) and payload.get("success") is False:
                raise BailianError(
                    _extract_error_message(payload) or "Failed to list model permissions"
                )
            output = payload.get("output") if isinstance(payload, dict) else None
            if not isinstance(output, dict):
                break
            permissions = output.get("permissions") or []
            if not isinstance(permissions, list) or not permissions:
                break
            for item in permissions:
                parsed = _parse_authorized_model(item)
                if parsed is None or parsed.model_id in seen:
                    continue
                seen.add(parsed.model_id)
                models.append(parsed)
            total = output.get("total")
            if isinstance(total, int) and len(models) >= total:
                break
            if len(permissions) < _PERMISSION_PAGE_SIZE:
                break
            page_no += 1
        LOGGER.debug("Listed %s authorized Bailian models", len(models))
        return models

    async def _async_list_compatible_models(self) -> list[AuthorizedModel]:
        """Return the OpenAI-compatible model catalog."""
        payload = await self._request("GET", f"{self._compatible_url}/models")
        models: list[AuthorizedModel] = []
        seen: set[str] = set()
        for item in payload.get("data") or []:
            model_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(model_id, str) or model_id in seen:
                continue
            seen.add(model_id)
            models.append(AuthorizedModel(model_id=model_id))
        return models

    async def async_list_custom_voices(self) -> list[CustomVoice]:
        """Return enrolled / designed TTS voices for this API key.

        CosyVoice clone/design and Qwen clone/design use the same customization
        endpoint with different model + action pairs. One catalog failing must
        not hide the others.
        """
        voices: list[CustomVoice] = []
        seen: set[str] = set()
        catalogs = (
            ("voice-enrollment", "list_voice"),
            ("qwen-voice-enrollment", "list"),
            ("qwen-voice-design", "list"),
        )
        for model, action in catalogs:
            try:
                found = await self._async_list_enrollment_voices(model, action)
            except BailianError as err:
                LOGGER.debug("Could not list %s voices: %s", model, err)
                continue
            for voice in found:
                if voice.voice_id in seen:
                    continue
                seen.add(voice.voice_id)
                voices.append(voice)
        LOGGER.debug("Listed %s custom Bailian TTS voices", len(voices))
        return voices

    async def _async_list_enrollment_voices(
        self, model: str, action: str
    ) -> list[CustomVoice]:
        """Page through one voice-enrollment catalog."""
        voices: list[CustomVoice] = []
        page_index = 0
        while page_index < _VOICE_LIST_MAX_PAGES:
            payload = await self._request(
                "POST",
                f"{self._native_url}/services/audio/tts/customization",
                json_data={
                    "model": model,
                    "input": {
                        "action": action,
                        "page_index": page_index,
                        "page_size": _VOICE_LIST_PAGE_SIZE,
                    },
                },
            )
            output = payload.get("output") if isinstance(payload, dict) else None
            if not isinstance(output, dict):
                break
            voice_list = output.get("voice_list") or []
            if not isinstance(voice_list, list) or not voice_list:
                break
            for item in voice_list:
                parsed = _parse_custom_voice(item, source=model)
                if parsed is not None:
                    voices.append(parsed)
            total_count = output.get("total_count")
            if isinstance(total_count, int) and len(voices) >= total_count:
                break
            if len(voice_list) < _VOICE_LIST_PAGE_SIZE:
                break
            page_index += 1
        return voices

    async def async_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool = False,
    ) -> ChatResult:
        """Call OpenAI-compatible chat completions."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "enable_thinking": enable_thinking,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        payload = await self._request(
            "POST",
            f"{self._compatible_url}/chat/completions",
            json_data=body,
        )
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as err:
            raise BailianError(f"Malformed chat response: {payload}") from err

        tool_calls = message.get("tool_calls") or []
        content = _normalize_chat_text(message.get("content"))
        if not content:
            content = _normalize_chat_text(message.get("reasoning_content"))
        return ChatResult(content=content, tool_calls=tool_calls, raw=payload)

    async def async_transcribe(
        self,
        *,
        audio: bytes,
        mime_type: str = "audio/wav",
        model: str,
        language: str | None = None,
        context: str | None = None,
    ) -> str:
        """Transcribe audio with Qwen-ASR (Base64, synchronous)."""
        data_uri = f"data:{mime_type};base64,{base64.b64encode(audio).decode()}"
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": [{"text": context or ""}]},
            {"role": "user", "content": [{"audio": data_uri}]},
        ]
        asr_options: dict[str, Any] = {"enable_itn": False}
        lang_code = None
        if language:
            lang_code = ASR_LANGUAGE_CODES.get(language.split("-")[0].lower())
        if lang_code in {"zh", "en"}:
            asr_options["enable_itn"] = True
        if lang_code:
            asr_options["language"] = lang_code

        payload = await self._request(
            "POST",
            f"{self._native_url}/services/aigc/multimodal-generation/generation",
            json_data={
                "model": model,
                "input": {"messages": messages},
                "parameters": {
                    "asr_options": asr_options,
                    "result_format": "message",
                },
            },
        )
        text = _extract_multimodal_text(payload)
        if not text:
            raise BailianError("Empty transcription result")
        return text

    async def async_synthesize(
        self,
        *,
        text: str,
        model: str,
        voice: str,
        language_type: str = "Chinese",
        audio_format: str = "wav",
    ) -> tuple[str, bytes]:
        """Synthesize speech and return (extension, audio bytes)."""
        if _is_speech_synthesizer_model(model):
            payload = await self._request(
                "POST",
                f"{self._native_url}/services/audio/tts/SpeechSynthesizer",
                json_data={
                    "model": model,
                    "input": {
                        "text": text,
                        "voice": voice,
                    },
                    "parameters": {
                        "text_type": "PlainText",
                        "format": audio_format,
                        "sample_rate": 22050,
                    },
                },
            )
        else:
            payload = await self._request(
                "POST",
                f"{self._native_url}/services/aigc/multimodal-generation/generation",
                json_data={
                    "model": model,
                    "input": {
                        "text": text,
                        "voice": voice,
                        "language_type": language_type,
                    },
                },
            )

        audio_bytes, extension = _extract_audio_payload(payload)
        if audio_bytes:
            return extension or audio_format, audio_bytes

        audio_url = _extract_audio_url(payload)
        if not audio_url:
            raise BailianError("TTS response did not include audio")

        audio_bytes = await self._async_download_audio(audio_url)
        LOGGER.debug("Downloaded %s bytes of TTS audio", len(audio_bytes))
        return _audio_extension(audio_url, audio_format), audio_bytes

    async def _async_download_audio(self, audio_url: str) -> bytes:
        """Download a pre-signed TTS URL without re-encoding the query string."""
        candidates = [audio_url]
        if audio_url.startswith("http://"):
            candidates.append("https://" + audio_url[len("http://") :])

        last_error: BailianError | None = None
        for candidate in candidates:
            try:
                return await self._async_download_signed_url(candidate)
            except (BailianError, BailianConnectionError) as err:
                last_error = err if isinstance(err, BailianError) else BailianError(str(err))
                LOGGER.debug("TTS audio download failed for %s: %s", candidate, err)
        raise last_error or BailianError("Failed to download TTS audio")

    async def _async_download_signed_url(self, audio_url: str) -> bytes:
        """Follow OSS redirects manually so signatures stay intact."""
        current = audio_url
        last_status = 0
        for _ in range(6):
            try:
                request_url: str | URL = URL(current, encoded=True)
            except ValueError:
                request_url = current
            try:
                async with self._session.get(
                    request_url,
                    timeout=self._timeout,
                    allow_redirects=False,
                    headers={"Accept": "*/*"},
                ) as response:
                    last_status = response.status
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise BailianError(
                                f"Failed to download TTS audio ({response.status})"
                            )
                        if location.startswith(("http://", "https://")):
                            current = location
                        else:
                            current = str(
                                URL(current, encoded=True).join(
                                    URL(location, encoded=True)
                                )
                            )
                        continue
                    if response.status >= 400:
                        raise BailianError(
                            f"Failed to download TTS audio ({response.status})"
                        )
                    audio_bytes = await response.read()
            except asyncio.TimeoutError as err:
                raise BailianConnectionError(
                    "Timeout downloading TTS audio"
                ) from err
            except aiohttp.ClientError as err:
                raise BailianConnectionError(str(err)) from err
            if not audio_bytes:
                raise BailianError("Downloaded TTS audio was empty")
            return audio_bytes
        raise BailianError(
            f"Failed to download TTS audio ({last_status or 'redirect loop'})"
        )


def _normalize_chat_text(value: Any) -> str | None:
    """Flatten chat completion content into a plain string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        text = "".join(parts).strip()
        return text or None
    text = str(value).strip()
    return text or None


def _extract_error_message(payload: dict[str, Any]) -> str:
    """Best-effort error message from a DashScope / OpenAI-compatible body."""
    if not isinstance(payload, dict):
        return str(payload)
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    for key in ("message", "msg"):
        if payload.get(key):
            return str(payload[key])
    return ""


def _extract_multimodal_text(payload: dict[str, Any]) -> str:
    """Extract transcript text from a DashScope multimodal response."""
    output = payload.get("output") or payload
    if not isinstance(output, dict):
        return ""
    if isinstance(output.get("text"), str) and output["text"].strip():
        return output["text"].strip()
    choices = output.get("choices")
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return ""


def _extract_audio_url(payload: dict[str, Any]) -> str | None:
    """Extract a TTS audio URL from a DashScope response."""
    output = payload.get("output") or payload
    if not isinstance(output, dict):
        return None
    audio = output.get("audio")
    if isinstance(audio, str) and audio.startswith("http"):
        return audio
    if isinstance(audio, dict) and audio.get("url"):
        return str(audio["url"])
    if output.get("audio_url"):
        return str(output["audio_url"])
    return None


def _extract_audio_payload(payload: dict[str, Any]) -> tuple[bytes | None, str | None]:
    """Extract inline Base64 audio from a DashScope TTS response."""
    output = payload.get("output") or payload
    if not isinstance(output, dict):
        return None, None
    audio = output.get("audio")
    if not isinstance(audio, dict):
        return None, None
    data = audio.get("data")
    if not isinstance(data, str) or not data.strip():
        return None, None
    try:
        return base64.b64decode(data), None
    except ValueError:
        return None, None


def _audio_extension(audio_url: str, fallback: str) -> str:
    """Guess a file extension from a TTS audio URL."""
    path = urlparse(audio_url).path.lower()
    for ext in ("mp3", "wav", "ogg", "opus", "flac"):
        if path.endswith(f".{ext}"):
            return ext
    return fallback


def _is_speech_synthesizer_model(model: str) -> bool:
    """Return True for CosyVoice / Qwen-Audio-TTS synthesizer endpoints."""
    lowered = model.lower()
    return lowered.startswith("cosyvoice") or lowered.startswith("qwen-audio-")


_VOICE_LIST_PAGE_SIZE = 10
_VOICE_LIST_MAX_PAGES = 50
_PERMISSION_PAGE_SIZE = 200
_PERMISSION_MAX_PAGES = 20
_OK_VOICE_STATUSES = frozenset({"", "OK", "SUCCESS"})
_COSYVOICE_MODEL_PREFIXES = (
    "cosyvoice-v3.5-plus",
    "cosyvoice-v3.5-flash",
    "cosyvoice-v3-plus",
    "cosyvoice-v3-flash",
    "cosyvoice-v2",
)


def infer_cosyvoice_model(voice_id: str) -> str | None:
    """Infer the CosyVoice synthesis model from a cloned / designed voice ID."""
    lowered = voice_id.lower()
    for prefix in _COSYVOICE_MODEL_PREFIXES:
        if lowered.startswith(f"{prefix}-"):
            return prefix
    return None


_VOICE_ID_SKIP_TOKENS = frozenset(
    {"qwen", "tts", "vc", "vd", "audio", "flash", "plus", "realtime"}
)


def _human_voice_name(
    item: dict[str, Any], voice_id: str, target_model: str | None
) -> str:
    """Prefer the user-facing name; never show the raw enrollment ID."""
    for key in ("name", "voice_name", "preferred_name", "prefix", "display_name"):
        value = item.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if (
                cleaned
                and cleaned.lower() != voice_id.lower()
                and cleaned.lower() != (target_model or "").lower()
            ):
                return cleaned

    remainder = voice_id
    prefixes: list[str] = []
    if target_model:
        prefixes.append(target_model)
    inferred = infer_cosyvoice_model(voice_id)
    if inferred:
        prefixes.append(inferred)
    prefixes.extend(_COSYVOICE_MODEL_PREFIXES)
    prefixes.extend(
        (
            "qwen-audio-3.0-tts-flash",
            "qwen-audio-3.0-tts-plus",
            "qwen3-tts-vc-flash",
            "qwen3-tts-vc-plus",
        )
    )
    lowered = voice_id.lower()
    for prefix in prefixes:
        token = f"{prefix.lower()}-"
        if lowered.startswith(token):
            remainder = voice_id[len(prefix) + 1 :]
            break

    if remainder.lower().startswith("vd-"):
        name = remainder[3:].split("-", 1)[0]
        if name:
            return name

    parts = remainder.split("-")
    if "voice" in parts:
        name_parts = [
            part
            for part in parts[: parts.index("voice")]
            if part.lower() not in _VOICE_ID_SKIP_TOKENS
        ]
        if name_parts:
            return "-".join(name_parts)

    name = parts[0] if parts else remainder
    return name or voice_id


def _custom_voice_label(name: str) -> str:
    """Dropdown label for a custom voice."""
    return name


def http_synthesis_model(model: str) -> str:
    """Map realtime-only voice models onto an HTTP-capable equivalent."""
    lowered = model.lower()
    if "realtime" in lowered and "qwen3-tts-vc" in lowered:
        return "qwen3-tts-vc-flash"
    return model


def resolve_tts_model(
    voice: str,
    configured_model: str,
    custom: CustomVoice | None = None,
) -> str:
    """Pick the synthesis model that matches a (possibly custom) voice."""
    if custom and custom.target_model:
        return http_synthesis_model(custom.target_model)
    inferred = infer_cosyvoice_model(voice)
    if inferred:
        return inferred
    # Cherry / Serena / ... belong to Qwen3-TTS, not CosyVoice or Qwen-Audio.
    if voice in TTS_VOICES and _is_speech_synthesizer_model(configured_model):
        return RECOMMENDED_TTS_MODEL
    return configured_model


def _parse_custom_voice(item: Any, *, source: str) -> CustomVoice | None:
    """Parse one enrollment / design catalog item."""
    if not isinstance(item, dict):
        return None
    voice_id = item.get("voice_id") or item.get("voice")
    if not isinstance(voice_id, str) or not voice_id.strip():
        return None
    voice_id = voice_id.strip()
    status = item.get("status")
    if isinstance(status, str) and status.upper() not in _OK_VOICE_STATUSES:
        return None
    target_model = item.get("target_model")
    if not isinstance(target_model, str) or not target_model.strip():
        target_model = infer_cosyvoice_model(voice_id)
    else:
        target_model = target_model.strip()
    label = _custom_voice_label(_human_voice_name(item, voice_id, target_model))
    return CustomVoice(
        voice_id=voice_id,
        label=label,
        target_model=target_model,
        source=source,
    )


_NON_CHAT_MARKERS = (
    "tts",
    "asr",
    "wan2",
    "wanx",
    "image",
    "embedding",
    "rerank",
    "speech",
    "omni",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "qwen-audio",
    "qwen2-audio",
    "paraformer",
    "cosyvoice",
    "sambert",
    "fun-asr",
    "gummy",
    "qwen-mt",
)


def is_chat_model(model_id: str) -> bool:
    """Return True if a model ID looks like a text chat model."""
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MARKERS)


def is_stt_model(model_id: str) -> bool:
    """Return True if a model ID looks like a speech-to-text model."""
    lowered = model_id.lower()
    return any(marker in lowered for marker in ("asr", "paraformer", "fun-asr", "gummy"))


def is_tts_model(model_id: str) -> bool:
    """Return True if a model ID looks like a text-to-speech model."""
    lowered = model_id.lower()
    return (
        "tts" in lowered
        or lowered.startswith("cosyvoice")
        or lowered.startswith("sambert")
    )


def _parse_authorized_model(item: Any) -> AuthorizedModel | None:
    """Parse one item from the model permissions API."""
    if not isinstance(item, dict):
        return None
    model_id = item.get("model") or item.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    permissions = item.get("permissions")
    if isinstance(permissions, dict) and permissions.get("inference") is False:
        return None
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        name = None
    else:
        name = name.strip()
    return AuthorizedModel(model_id=model_id.strip(), name=name)
