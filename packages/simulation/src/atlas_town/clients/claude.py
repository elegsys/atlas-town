"""Claude (Anthropic) LLM client with function calling support."""

from dataclasses import dataclass
from typing import Any

import anthropic
import structlog

from atlas_town.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ClaudeResponse:
    """Response from Claude API."""

    content: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, int]


class ClaudeClient:
    """Client for Anthropic's Claude API with tool use support."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        settings = get_settings()
        self._api_key = api_key or settings.anthropic_api_key.get_secret_value()
        self._model = model or settings.claude_model
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._temperature = temperature or settings.llm_temperature

        self._client = anthropic.Anthropic(api_key=self._api_key)
        self._logger = logger.bind(client="claude", model=self._model)

    def _convert_tools_to_anthropic_format(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert our tool format to Anthropic's expected format.

        Our format uses 'input_schema', Anthropic uses 'input_schema' too,
        but we need to ensure the structure is correct.
        """
        anthropic_tools = []
        for tool in tools:
            anthropic_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            })
        return anthropic_tools

    def _convert_messages_to_anthropic_format(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert conversation history to Anthropic's message format."""
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": msg["content"],
                })
            elif msg["role"] == "assistant":
                # Build content blocks for assistant message
                content_blocks = []

                # Add text content if present
                if msg.get("content"):
                    content_blocks.append({
                        "type": "text",
                        "text": msg["content"],
                    })

                # Add tool use blocks if present
                for tool_call in msg.get("tool_calls", []):
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["name"],
                        "input": tool_call["arguments"],
                    })

                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else msg.get("content", ""),
                })
            elif msg["role"] == "tool_result":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg["tool_call_id"],
                            "content": msg["content"],
                        }
                    ],
                })

        return anthropic_messages

    def _parse_response(self, response: anthropic.types.Message) -> ClaudeResponse:
        """Parse Anthropic response into our format."""
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return ClaudeResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ClaudeResponse:
        """Generate a response from Claude.

        Args:
            system_prompt: The system prompt defining agent behavior.
            messages: Conversation history as list of message dicts.
            tools: Optional list of tool definitions for function calling.

        Returns:
            ClaudeResponse with content, tool calls, and usage info.
        """
        self._logger.debug(
            "generating_response",
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
        )

        # Convert messages to Anthropic format
        anthropic_messages = self._convert_messages_to_anthropic_format(messages)

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system_prompt,
            "messages": anthropic_messages,
        }

        # Only add temperature if not using tools (tool use works better with default)
        if not tools:
            kwargs["temperature"] = self._temperature

        # Add tools if provided
        if tools:
            kwargs["tools"] = self._convert_tools_to_anthropic_format(tools)

        # Make the API call (synchronous, but we wrap in async interface)
        try:
            response = self._client.messages.create(**kwargs)

            parsed = self._parse_response(response)

            self._logger.info(
                "response_generated",
                stop_reason=parsed.stop_reason,
                tool_calls=len(parsed.tool_calls),
                input_tokens=parsed.usage["input_tokens"],
                output_tokens=parsed.usage["output_tokens"],
            )

            return parsed

        except anthropic.APIError as e:
            self._logger.error("api_error", error=str(e))
            raise

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation. For exact counts, use the API.
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
