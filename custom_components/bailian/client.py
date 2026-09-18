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

import aiohttp

from .const import (
    DASHSCOPE_HOSTS,
    LOGGER,
    REGION_BEIJING,
    REGIONS_REQUIRING_WORKSPACE,
    REQUEST_TIMEOUT,
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
    ) -> dict[str, Any]:
        """Perform an HTTP request and return JSON."""
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(extra_headers),
                json=json_data,
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
        await self._request("GET", f"{self._compatible_url}/models")

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
        content = message.get("content")
        if not content:
            content = message.get("reasoning_content")
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
        messages: list[dict[str, Any]] = []
        if context:
            messages.append(
                {"role": "system", "content": [{"text": context}]}
            )
        messages.append(
            {"role": "user", "content": [{"audio": data_uri}]}
        )
        asr_options: dict[str, Any] = {"enable_itn": True}
        if language:
            asr_options["language"] = language.split("-")[0]

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
                        "format": audio_format,
                        "sample_rate": 24000,
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

        audio_url = _extract_audio_url(payload)
        if not audio_url:
            raise BailianError("TTS response did not include an audio URL")

        try:
            async with self._session.get(
                audio_url, timeout=self._timeout
            ) as response:
                if response.status >= 400:
                    raise BailianError(
                        f"Failed to download TTS audio ({response.status})"
                    )
                audio_bytes = await response.read()
        except asyncio.TimeoutError as err:
            raise BailianConnectionError("Timeout downloading TTS audio") from err
        except aiohttp.ClientError as err:
            raise BailianConnectionError(str(err)) from err

        LOGGER.debug("Downloaded %s bytes of TTS audio", len(audio_bytes))
        return audio_format, audio_bytes


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
    choices = output.get("choices") if isinstance(output, dict) else None
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
    if isinstance(audio, dict) and audio.get("url"):
        return str(audio["url"])
    if output.get("audio_url"):
        return str(output["audio_url"])
    return None


def _is_speech_synthesizer_model(model: str) -> bool:
    """Return True for CosyVoice / Qwen-Audio-TTS synthesizer endpoints."""
    lowered = model.lower()
    return lowered.startswith("cosyvoice") or lowered.startswith("qwen-audio-")
