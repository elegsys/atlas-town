"""Google Gemini client with function calling support.

Uses the new google-genai SDK (v1.0+) for both text generation and image generation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import structlog
from google import genai
from google.genai import types

from atlas_town.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class GeminiResponse:
    """Response from Gemini API."""

    content: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, int]


class GeminiClient:
    """Client for Google's Gemini API with tool use support.

    Uses the new google-genai SDK which provides a unified interface for
    both Gemini text models and Imagen/Nano Banana image models.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        settings = get_settings()
        self._api_key = api_key or settings.google_api_key.get_secret_value()
        self._model_name = model or settings.gemini_model
        self._max_tokens = max_tokens or settings.llm_max_tokens
        self._temperature = temperature or settings.llm_temperature

        # Initialize the new SDK client
        self._client = genai.Client(api_key=self._api_key)

        self._logger = logger.bind(client="gemini", model=self._model_name)

    def _convert_json_schema_to_gemini(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Convert JSON Schema to Gemini's schema format.

        Gemini uses a subset of OpenAPI schema format.
        """
        gemini_schema: dict[str, Any] = {}

        if "type" in schema:
            # Map JSON Schema types to Gemini types
            type_map = {
                "string": "STRING",
                "integer": "INTEGER",
                "number": "NUMBER",
                "boolean": "BOOLEAN",
                "array": "ARRAY",
                "object": "OBJECT",
            }
            gemini_schema["type"] = type_map.get(schema["type"], "STRING")

        if "description" in schema:
            gemini_schema["description"] = schema["description"]

        if "enum" in schema:
            gemini_schema["enum"] = schema["enum"]

        if "properties" in schema:
            gemini_schema["properties"] = {
                k: self._convert_json_schema_to_gemini(v)
                for k, v in schema["properties"].items()
            }

        if "required" in schema:
            gemini_schema["required"] = schema["required"]

        if "items" in schema:
            gemini_schema["items"] = self._convert_json_schema_to_gemini(schema["items"])

        return gemini_schema

    def _convert_tools_to_gemini_format(
        self, tools: list[dict[str, Any]]
    ) -> list[types.Tool]:
        """Convert our tool format to Gemini's expected format."""
        function_declarations = []

        for tool in tools:
            # Convert the input schema
            parameters = types.Schema.model_validate(
                self._convert_json_schema_to_gemini(tool["input_schema"])
            )

            func_decl = types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=parameters,
            )
            function_declarations.append(func_decl)

        return [types.Tool(function_declarations=function_declarations)]

    def _convert_messages_to_gemini_format(
        self, messages: list[dict[str, Any]]
    ) -> list[types.Content]:
        """Convert conversation history to Gemini's content format."""
        gemini_contents = []

        for msg in messages:
            if msg["role"] == "user":
                gemini_contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=msg["content"])],
                    )
                )
            elif msg["role"] == "assistant":
                parts = []

                # Add text content if present
                if msg.get("content"):
                    parts.append(types.Part(text=msg["content"]))

                # Add function calls if present
                for tool_call in msg.get("tool_calls", []):
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                name=tool_call["name"],
                                args=tool_call["arguments"],
                            )
                        )
                    )

                gemini_contents.append(
                    types.Content(role="model", parts=parts)
                )
            elif msg["role"] == "tool_result":
                gemini_contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=msg.get("tool_name", "function"),
                                    response={"result": msg["content"]},
                                )
                            )
                        ],
                    )
                )

        return gemini_contents

    def _parse_response(self, response: Any) -> GeminiResponse:
        """Parse Gemini response into our format."""
        content = ""
        tool_calls: list[dict[str, Any]] = []

        # Get the first candidate's content
        if response.candidates:
            candidate = response.candidates[0]

            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    content = part.text
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append({
                        "id": f"call_{fc.name}_{len(tool_calls)}",
                        "name": fc.name,
                        "arguments": dict(fc.args) if fc.args else {},
                    })

            # Map finish reasons
            finish_reason = candidate.finish_reason
            # New SDK uses string enums
            stop_reason_map = {
                "STOP": "end_turn",
                "MAX_TOKENS": "max_tokens",
                "SAFETY": "content_filter",
                "RECITATION": "content_filter",
                "OTHER": "tool_use",
            }
            stop_reason = stop_reason_map.get(str(finish_reason), "end_turn")

            # If we have tool calls, override stop reason
            if tool_calls:
                stop_reason = "tool_use"

        # Get usage metadata if available
        usage = {"input_tokens": 0, "output_tokens": 0}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage["input_tokens"] = (
                getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            )
            usage["output_tokens"] = (
                getattr(response.usage_metadata, "candidates_token_count", 0) or 0
            )

        return GeminiResponse(
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
    ) -> GeminiResponse:
        """Generate a response from Gemini.

        Args:
            system_prompt: The system prompt defining agent behavior.
            messages: Conversation history as list of message dicts.
            tools: Optional list of tool definitions for function calling.

        Returns:
            GeminiResponse with content, tool calls, and usage info.
        """
        self._logger.debug(
            "generating_response",
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
        )

        # Build configuration
        config = types.GenerateContentConfig(
            max_output_tokens=self._max_tokens,
            temperature=self._temperature,
            system_instruction=system_prompt,
        )

        # Add tools if provided
        if tools:
            config.tools = cast(
                list[types.Tool | Callable[..., Any]],
                self._convert_tools_to_gemini_format(tools),
            )

        # Convert messages to Gemini format
        gemini_contents = self._convert_messages_to_gemini_format(messages)
        contents_payload = cast(list[Any], gemini_contents)

        try:
            # Generate response using new SDK
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=contents_payload,
                config=config,
            )

            parsed = self._parse_response(response)

            self._logger.info(
                "response_generated",
                stop_reason=parsed.stop_reason,
                tool_calls=len(parsed.tool_calls),
                input_tokens=parsed.usage["input_tokens"],
                output_tokens=parsed.usage["output_tokens"],
            )

            return parsed

        except Exception as e:
            self._logger.error("api_error", error=str(e))
            raise

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation.
        """
        # Rough approximation: ~4 characters per token
        return len(text) // 4
