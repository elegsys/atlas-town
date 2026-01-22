"""OpenAI GPT client with function calling support."""

import json
from dataclasses import dataclass
from typing import Any

import openai
import structlog

from atlas_town.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class OpenAIResponse:
    """Response from OpenAI API."""

    content: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, int]


class OpenAIClient:
    """Client for OpenAI's GPT API with tool use support.

    Also supports OpenAI-compatible APIs like LM Studio via custom base_url.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key.get_secret_value()
        self._base_url = base_url  # None means use OpenAI's default
        self._model = model or settings.gpt_model
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._temperature = temperature or settings.llm_temperature

        # Create client with optional custom base_url (for LM Studio, etc.)
        client_kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        self._client = openai.OpenAI(**client_kwargs)
        client_name = "lm_studio" if self._base_url else "openai"
        self._logger = logger.bind(client=client_name, model=self._model)

    def _convert_tools_to_openai_format(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert our tool format to OpenAI's expected format.

        OpenAI expects:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}  # JSON Schema
            }
        }
        """
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            })
        return openai_tools

    def _convert_messages_to_openai_format(
        self, system_prompt: str, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert conversation history to OpenAI's message format."""
        openai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            if msg["role"] == "user":
                openai_messages.append({
                    "role": "user",
                    "content": msg["content"],
                })
            elif msg["role"] == "assistant":
                assistant_msg: dict[str, Any] = {"role": "assistant"}

                # Add content if present
                if msg.get("content"):
                    assistant_msg["content"] = msg["content"]

                # Add tool calls if present
                if msg.get("tool_calls"):
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"]),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]

                openai_messages.append(assistant_msg)
            elif msg["role"] == "tool_result":
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                })

        return openai_messages

    def _parse_response(
        self, response: openai.types.chat.ChatCompletion
    ) -> OpenAIResponse:
        """Parse OpenAI response into our format."""
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        # Map OpenAI finish reasons to our format
        finish_reason = response.choices[0].finish_reason
        stop_reason_map = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "content_filter": "content_filter",
        }
        stop_reason = stop_reason_map.get(finish_reason or "stop", "end_turn")

        return OpenAIResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> OpenAIResponse:
        """Generate a response from GPT.

        Args:
            system_prompt: The system prompt defining agent behavior.
            messages: Conversation history as list of message dicts.
            tools: Optional list of tool definitions for function calling.

        Returns:
            OpenAIResponse with content, tool calls, and usage info.
        """
        self._logger.debug(
            "generating_response",
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
        )

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages_to_openai_format(system_prompt, messages)

        # Build request kwargs
        # Note: GPT-5+ models use max_completion_tokens instead of max_tokens
        # and gpt-5-nano only supports default temperature (1)
        is_gpt5_plus = self._model.startswith("gpt-5") or self._model.startswith("o3")
        is_nano = "nano" in self._model
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
        }
        # Only set temperature if model supports it
        if not is_nano:
            kwargs["temperature"] = self._temperature
        # GPT-5+ uses max_completion_tokens
        if is_gpt5_plus:
            kwargs["max_completion_tokens"] = self._max_tokens
        else:
            kwargs["max_tokens"] = self._max_tokens

        # Add tools if provided
        if tools:
            kwargs["tools"] = self._convert_tools_to_openai_format(tools)
            kwargs["tool_choice"] = "auto"

        # Make the API call (synchronous client, but we wrap in async interface)
        try:
            response = self._client.chat.completions.create(**kwargs)

            parsed = self._parse_response(response)

            self._logger.info(
                "response_generated",
                stop_reason=parsed.stop_reason,
                tool_calls=len(parsed.tool_calls),
                input_tokens=parsed.usage["input_tokens"],
                output_tokens=parsed.usage["output_tokens"],
            )

            return parsed

        except openai.APIError as e:
            self._logger.error("api_error", error=str(e))
            raise

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation. For exact counts, use tiktoken.
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
