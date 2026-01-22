"""Ollama LLM client with function calling support for local models."""

import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from atlas_town.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class OllamaResponse:
    """Response from Ollama API."""

    content: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, int]


class OllamaClient:
    """Client for Ollama's local LLM API with tool use support.

    Ollama provides OpenAI-compatible tool calling via the /api/chat endpoint.
    This allows local models like qwen3:30b to function as drop-in replacements
    for cloud APIs.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._temperature = temperature or settings.llm_temperature

        self._client = httpx.AsyncClient(timeout=120.0)  # Local models can be slow
        self._logger = logger.bind(client="ollama", model=self._model)

    def _convert_tools_to_ollama_format(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert our tool format to Ollama's expected format.

        Ollama uses OpenAI-compatible tool format:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}  # JSON Schema
            }
        }
        """
        ollama_tools = []
        for tool in tools:
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            })
        return ollama_tools

    def _convert_messages_to_ollama_format(
        self, system_prompt: str, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert conversation history to Ollama's message format."""
        ollama_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            if msg["role"] == "user":
                ollama_messages.append({
                    "role": "user",
                    "content": msg["content"],
                })
            elif msg["role"] == "assistant":
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    # Ollama requires content to always be present
                    "content": msg.get("content") or "",
                }

                # Add tool calls if present
                if msg.get("tool_calls"):
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                # Ollama expects arguments as a dict, not JSON string
                                "arguments": tc["arguments"] if isinstance(tc["arguments"], dict) else json.loads(tc["arguments"]),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]

                ollama_messages.append(assistant_msg)
            elif msg["role"] == "tool_result":
                ollama_messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                })

        return ollama_messages

    def _parse_response(self, response_data: dict[str, Any]) -> OllamaResponse:
        """Parse Ollama response into our format."""
        message = response_data.get("message", {})
        content = message.get("content", "")
        tool_calls = []

        # Parse tool calls if present
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                arguments = func.get("arguments", {})

                # Arguments might be a string or dict
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                tool_calls.append({
                    "id": tc.get("id", f"call_{len(tool_calls)}"),
                    "name": func.get("name", ""),
                    "arguments": arguments,
                })

        # Determine stop reason
        done_reason = response_data.get("done_reason", "")
        if tool_calls:
            stop_reason = "tool_use"
        elif done_reason == "stop":
            stop_reason = "end_turn"
        elif done_reason == "length":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"

        # Extract usage from response
        usage = {
            "input_tokens": response_data.get("prompt_eval_count", 0),
            "output_tokens": response_data.get("eval_count", 0),
        }

        return OllamaResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> OllamaResponse:
        """Generate a response from the local Ollama model.

        Args:
            system_prompt: The system prompt defining agent behavior.
            messages: Conversation history as list of message dicts.
            tools: Optional list of tool definitions for function calling.

        Returns:
            OllamaResponse with content, tool calls, and usage info.
        """
        self._logger.debug(
            "generating_response",
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
        )

        # Convert messages to Ollama format
        ollama_messages = self._convert_messages_to_ollama_format(system_prompt, messages)

        # Build request payload
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": self._max_tokens,
                "temperature": self._temperature,
            },
        }

        # Add tools if provided
        if tools:
            payload["tools"] = self._convert_tools_to_ollama_format(tools)

        # Make the API call
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            response_data = response.json()

            parsed = self._parse_response(response_data)

            self._logger.info(
                "response_generated",
                stop_reason=parsed.stop_reason,
                tool_calls=len(parsed.tool_calls),
                input_tokens=parsed.usage["input_tokens"],
                output_tokens=parsed.usage["output_tokens"],
            )

            return parsed

        except httpx.HTTPStatusError as e:
            # Try to get error details from response body
            try:
                error_body = e.response.json()
                self._logger.error(
                    "api_error",
                    status=e.response.status_code,
                    error=str(e),
                    error_body=error_body,
                )
            except Exception:
                self._logger.error("api_error", status=e.response.status_code, error=str(e))
            raise
        except httpx.RequestError as e:
            self._logger.error("connection_error", error=str(e))
            raise

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation. Local models may tokenize differently.
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
