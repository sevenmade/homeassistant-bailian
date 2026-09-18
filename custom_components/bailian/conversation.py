"""Conversation agent for Alibaba Cloud Bailian."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import json
from typing import Any, Literal

from voluptuous_openapi import convert

from homeassistant.components import conversation
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BailianConfigEntry
from .client import BailianError
from .const import (
    CONF_CHAT_MODEL,
    CONF_ENABLE_THINKING,
    CONF_MAX_TOKENS,
    CONF_TEMPERATURE,
    DEFAULT_CONVERSATION_NAME,
    DOMAIN,
    LOGGER,
    MAX_TOOL_ITERATIONS,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_ENABLE_THINKING,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: BailianConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Bailian conversation entity."""
    async_add_entities([BailianConversationEntity(config_entry)])


def _format_tool(
    tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None
) -> dict[str, Any]:
    """Convert a Home Assistant LLM tool to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": convert(tool.parameters, custom_serializer=custom_serializer),
        },
    }


def _convert_content(content: Iterable[conversation.Content]) -> list[dict[str, Any]]:
    """Convert ChatLog messages to OpenAI-compatible messages."""
    messages: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, conversation.ToolResultContent):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.tool_call_id,
                    "content": json.dumps(item.tool_result, ensure_ascii=False),
                }
            )
            continue

        if isinstance(item, conversation.AssistantContent):
            message: dict[str, Any] = {
                "role": "assistant",
                "content": item.content or "",
            }
            if item.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.tool_name,
                            "arguments": json.dumps(
                                tool_call.tool_args, ensure_ascii=False
                            ),
                        },
                    }
                    for tool_call in item.tool_calls
                ]
            messages.append(message)
            continue

        messages.append({"role": item.role, "content": item.content or ""})
    return messages


def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> list[llm.ToolInput]:
    """Parse OpenAI-style tool calls into Home Assistant ToolInput objects."""
    parsed: list[llm.ToolInput] = []
    for call in raw_calls:
        function = call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                tool_args = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                LOGGER.warning("Invalid tool arguments from Bailian: %s", arguments)
                tool_args = {}
        elif isinstance(arguments, dict):
            tool_args = arguments
        else:
            tool_args = {}
        tool_input_kwargs: dict[str, Any] = {
            "tool_name": str(function.get("name") or ""),
            "tool_args": tool_args,
        }
        if call.get("id"):
            tool_input_kwargs["id"] = str(call["id"])
        parsed.append(llm.ToolInput(**tool_input_kwargs))
    return parsed


class BailianConversationEntity(
    conversation.ConversationEntity, conversation.AbstractConversationAgent
):
    """Bailian conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "conversation"
    _attr_supports_streaming = False

    def __init__(self, entry: BailianConfigEntry) -> None:
        """Initialize the agent."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}-conversation"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_CONVERSATION_NAME,
            manufacturer="Alibaba Cloud",
            model="Bailian",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        if entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """Register as a conversation agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the conversation agent."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Send the chat log to Bailian and execute any tool calls."""
        options = self.entry.options
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                options.get(CONF_LLM_HASS_API),
                options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log)
        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _async_handle_chat_log(self, chat_log: conversation.ChatLog) -> None:
        """Iterate chat completions until the model stops calling tools."""
        client = self.entry.runtime_data.client
        options = self.entry.options
        tools: list[dict[str, Any]] | None = None
        if chat_log.llm_api:
            tools = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]

        for _iteration in range(MAX_TOOL_ITERATIONS):
            try:
                result = await client.async_chat(
                    model=options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
                    messages=_convert_content(chat_log.content),
                    tools=tools,
                    temperature=float(
                        options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE)
                    ),
                    max_tokens=int(options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS)),
                    enable_thinking=bool(
                        options.get(CONF_ENABLE_THINKING, RECOMMENDED_ENABLE_THINKING)
                    ),
                )
            except BailianError as err:
                LOGGER.error("Bailian chat failed: %s", err)
                raise HomeAssistantError(f"Error talking to Bailian: {err}") from err

            if result.tool_calls:
                async for _tool_input in chat_log.async_add_assistant_content(
                    conversation.AssistantContent(
                        agent_id=self.entity_id,
                        content=result.content or None,
                        tool_calls=_parse_tool_calls(result.tool_calls),
                    )
                ):
                    pass
                continue

            chat_log.async_add_assistant_content_without_tools(
                conversation.AssistantContent(
                    agent_id=self.entity_id,
                    content=result.content or "",
                )
            )
            return

        LOGGER.warning("Reached maximum Bailian tool iterations")
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=self.entity_id,
                content="Sorry, I could not complete that request.",
            )
        )
