"""Config flow for the Alibaba Cloud Bailian integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    SOURCE_REAUTH,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import (
    BailianAuthError,
    BailianClient,
    BailianConnectionError,
    BailianError,
)
from .const import (
    CHAT_MODELS,
    CONF_CHAT_MODEL,
    CONF_ENABLE_STT,
    CONF_ENABLE_TTS,
    CONF_ENABLE_THINKING,
    CONF_MAX_TOKENS,
    CONF_REGION,
    CONF_STT_MODEL,
    CONF_STT_PROMPT,
    CONF_TEMPERATURE,
    CONF_TTS_MODEL,
    CONF_TTS_VOICE,
    CONF_WORKSPACE_ID,
    DEFAULT_NAME,
    DEFAULT_REGION,
    DOMAIN,
    LOGGER,
    REGION_LABELS,
    REGIONS_REQUIRING_WORKSPACE,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_ENABLE_STT,
    RECOMMENDED_ENABLE_TTS,
    RECOMMENDED_ENABLE_THINKING,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_OPTIONS,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_STT_PROMPT,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TTS_MODEL,
    RECOMMENDED_TTS_VOICE,
    STT_MODELS,
    TTS_MODELS,
    TTS_VOICES,
)


class WorkspaceRequiredError(Exception):
    """Raised when the selected region needs a workspace ID."""


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=DEFAULT_REGION): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=value, label=label)
                    for value, label in REGION_LABELS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_API_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_WORKSPACE_ID): selector.TextSelector(),
    }
)

STEP_ENGINES_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_ENABLE_STT, default=RECOMMENDED_ENABLE_STT
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_ENABLE_TTS, default=RECOMMENDED_ENABLE_TTS
        ): selector.BooleanSelector(),
    }
)


def _options_schema(hass: HomeAssistant, options: Mapping[str, Any] | None) -> vol.Schema:
    """Return the options schema with current values as suggested defaults."""
    current = {**RECOMMENDED_OPTIONS, **(options or {})}
    apis = [
        selector.SelectOptionDict(label=api.name, value=api.id)
        for api in llm.async_get_apis(hass)
    ]
    return vol.Schema(
        {
            vol.Required(
                CONF_ENABLE_STT,
                default=current.get(CONF_ENABLE_STT, RECOMMENDED_ENABLE_STT),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_ENABLE_TTS,
                default=current.get(CONF_ENABLE_TTS, RECOMMENDED_ENABLE_TTS),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_LLM_HASS_API,
                description={"suggested_value": current.get(CONF_LLM_HASS_API)},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=apis, multiple=True)
            ),
            vol.Optional(
                CONF_PROMPT,
                description={"suggested_value": current.get(CONF_PROMPT)},
            ): selector.TemplateSelector(),
            vol.Optional(
                CONF_CHAT_MODEL,
                default=current.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=CHAT_MODELS,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_ENABLE_THINKING,
                default=current.get(CONF_ENABLE_THINKING, RECOMMENDED_ENABLE_THINKING),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_TEMPERATURE,
                default=current.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2, step=0.1, mode=selector.NumberSelectorMode.SLIDER
                )
            ),
            vol.Optional(
                CONF_MAX_TOKENS,
                default=current.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=64, max=8192, step=64, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_STT_MODEL,
                default=current.get(CONF_STT_MODEL, RECOMMENDED_STT_MODEL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=STT_MODELS,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_STT_PROMPT,
                description={"suggested_value": current.get(CONF_STT_PROMPT, RECOMMENDED_STT_PROMPT)},
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(
                CONF_TTS_MODEL,
                default=current.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TTS_MODELS,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_TTS_VOICE,
                default=current.get(CONF_TTS_VOICE, RECOMMENDED_TTS_VOICE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TTS_VOICES,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


async def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> None:
    """Validate API credentials against Bailian."""
    region = user_input[CONF_REGION]
    workspace_id = (user_input.get(CONF_WORKSPACE_ID) or "").strip() or None
    if region in REGIONS_REQUIRING_WORKSPACE and not workspace_id:
        raise WorkspaceRequiredError

    client = BailianClient(
        session=async_get_clientsession(hass),
        api_key=user_input[CONF_API_KEY],
        region=region,
        workspace_id=workspace_id,
    )
    await client.async_validate()


class BailianConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bailian."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_WORKSPACE_ID] = (
                user_input.get(CONF_WORKSPACE_ID) or ""
            ).strip()
            if self.source != SOURCE_REAUTH:
                self._async_abort_entries_match(
                    {
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_REGION: user_input[CONF_REGION],
                        CONF_WORKSPACE_ID: user_input[CONF_WORKSPACE_ID],
                    }
                )
            try:
                await _validate_input(self.hass, user_input)
            except WorkspaceRequiredError:
                errors[CONF_WORKSPACE_ID] = "workspace_required"
            except BailianAuthError:
                errors["base"] = "invalid_auth"
            except BailianConnectionError:
                errors["base"] = "cannot_connect"
            except BailianError:
                LOGGER.exception("Unexpected Bailian error during setup")
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception during Bailian setup")
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data_updates=user_input,
                    )
                self._user_input = user_input
                return await self.async_step_engines()

        schema_input = user_input
        if schema_input is None and self.source == SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            schema_input = {
                CONF_REGION: reauth_entry.data.get(CONF_REGION, DEFAULT_REGION),
                CONF_WORKSPACE_ID: reauth_entry.data.get(CONF_WORKSPACE_ID, ""),
            }
        schema = self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, schema_input)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "docs_url": "https://docs.bailian.console.aliyun.com/zh/model-studio/get-api-key",
            },
        )

    async def async_step_engines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose optional speech engines. Conversation is always enabled."""
        if user_input is not None:
            options = dict(RECOMMENDED_OPTIONS)
            options[CONF_ENABLE_STT] = user_input[CONF_ENABLE_STT]
            options[CONF_ENABLE_TTS] = user_input[CONF_ENABLE_TTS]
            region = self._user_input[CONF_REGION]
            title = f"{DEFAULT_NAME} ({REGION_LABELS.get(region, region)})"
            return self.async_create_entry(
                title=title,
                data=self._user_input,
                options=options,
            )

        return self.async_show_form(
            step_id="engines",
            data_schema=STEP_ENGINES_SCHEMA,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return BailianOptionsFlow()


class BailianOptionsFlow(OptionsFlow):
    """Handle Bailian options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            if CONF_LLM_HASS_API in user_input and not user_input[CONF_LLM_HASS_API]:
                user_input.pop(CONF_LLM_HASS_API)
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(self.hass, self.config_entry.options),
                self.config_entry.options,
            ),
        )
