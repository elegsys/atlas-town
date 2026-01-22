"""Tests for Ollama LLM client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlas_town.clients.ollama import OllamaClient, OllamaResponse


class TestOllamaClient:
    """Tests for OllamaClient."""

    def test_client_initialization_with_defaults(self):
        """Test client initializes with settings defaults."""
        client = OllamaClient()

        assert client._base_url == "http://localhost:11434"
        assert client._model == "qwen3:30b"
        assert client._max_tokens > 0

    def test_client_initialization_with_custom_params(self):
        """Test client accepts custom parameters."""
        client = OllamaClient(
            base_url="http://localhost:9999",
            model="llama3:8b",
            max_tokens=2048,
            temperature=0.5,
        )

        assert client._base_url == "http://localhost:9999"
        assert client._model == "llama3:8b"
        assert client._max_tokens == 2048
        assert client._temperature == 0.5

    def test_base_url_trailing_slash_stripped(self):
        """Test trailing slash is stripped from base URL."""
        client = OllamaClient(base_url="http://localhost:11434/")

        assert client._base_url == "http://localhost:11434"

    def test_convert_tools_to_ollama_format(self):
        """Test tool format conversion to OpenAI-compatible format."""
        client = OllamaClient()
        tools = [
            {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"arg1": {"type": "string"}},
                },
            }
        ]

        converted = client._convert_tools_to_ollama_format(tools)

        assert len(converted) == 1
        assert converted[0]["type"] == "function"
        assert converted[0]["function"]["name"] == "test_tool"
        assert converted[0]["function"]["description"] == "A test tool"
        assert "parameters" in converted[0]["function"]

    def test_convert_user_message_to_ollama_format(self):
        """Test user message conversion."""
        client = OllamaClient()
        messages = [{"role": "user", "content": "Hello"}]

        converted = client._convert_messages_to_ollama_format("System prompt", messages)

        # First message should be system prompt
        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "System prompt"
        assert converted[1]["role"] == "user"
        assert converted[1]["content"] == "Hello"

    def test_convert_assistant_message_with_tool_calls(self):
        """Test assistant message with tool calls conversion."""
        client = OllamaClient()
        messages = [
            {
                "role": "assistant",
                "content": "Let me check",
                "tool_calls": [
                    {"id": "call_123", "name": "list_customers", "arguments": {"limit": 10}},
                ],
            }
        ]

        converted = client._convert_messages_to_ollama_format("System", messages)

        # Skip system message
        assert converted[1]["role"] == "assistant"
        assert converted[1]["content"] == "Let me check"

        tool_calls = converted[1]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "call_123"
        assert tool_calls[0]["type"] == "function"
        assert tool_calls[0]["function"]["name"] == "list_customers"
        # Arguments should be a dict for Ollama (not JSON string)
        assert tool_calls[0]["function"]["arguments"] == {"limit": 10}

    def test_convert_tool_result_message(self):
        """Test tool result message conversion."""
        client = OllamaClient()
        messages = [
            {
                "role": "tool_result",
                "content": '{"customers": []}',
                "tool_call_id": "call_123",
            }
        ]

        converted = client._convert_messages_to_ollama_format("System", messages)

        assert len(converted) == 2  # system + tool result
        assert converted[1]["role"] == "tool"
        assert converted[1]["tool_call_id"] == "call_123"
        assert converted[1]["content"] == '{"customers": []}'

    def test_parse_text_response(self):
        """Test parsing text-only response."""
        client = OllamaClient()

        response_data = {
            "message": {"content": "Hello there"},
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        parsed = client._parse_response(response_data)

        assert parsed.content == "Hello there"
        assert parsed.tool_calls == []
        assert parsed.stop_reason == "end_turn"
        assert parsed.usage["input_tokens"] == 10
        assert parsed.usage["output_tokens"] == 5

    def test_parse_tool_use_response(self):
        """Test parsing response with tool calls."""
        client = OllamaClient()

        response_data = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "function": {
                            "name": "list_customers",
                            "arguments": '{"limit": 10}',
                        },
                    }
                ],
            },
            "done_reason": "stop",
            "prompt_eval_count": 20,
            "eval_count": 15,
        }

        parsed = client._parse_response(response_data)

        assert len(parsed.tool_calls) == 1
        assert parsed.tool_calls[0]["id"] == "call_abc"
        assert parsed.tool_calls[0]["name"] == "list_customers"
        assert parsed.tool_calls[0]["arguments"] == {"limit": 10}
        assert parsed.stop_reason == "tool_use"

    def test_parse_tool_use_response_with_dict_arguments(self):
        """Test parsing tool calls where arguments are already a dict."""
        client = OllamaClient()

        response_data = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_xyz",
                        "function": {
                            "name": "get_customer",
                            "arguments": {"customer_id": "123"},  # Already a dict
                        },
                    }
                ],
            },
            "done_reason": "stop",
            "prompt_eval_count": 15,
            "eval_count": 10,
        }

        parsed = client._parse_response(response_data)

        assert parsed.tool_calls[0]["arguments"] == {"customer_id": "123"}

    def test_parse_response_with_length_stop(self):
        """Test parsing response that stopped due to max tokens."""
        client = OllamaClient()

        response_data = {
            "message": {"content": "Partial response..."},
            "done_reason": "length",
            "prompt_eval_count": 100,
            "eval_count": 4096,
        }

        parsed = client._parse_response(response_data)

        assert parsed.stop_reason == "max_tokens"

    def test_count_tokens_approximation(self):
        """Test token counting approximation."""
        client = OllamaClient()

        # ~4 chars per token for English
        text = "Hello world, this is a test."  # 28 chars
        count = client.count_tokens(text)

        assert count == 7  # 28 // 4

    @pytest.mark.asyncio
    async def test_generate_makes_correct_api_call(self):
        """Test generate method makes correct API call."""
        client = OllamaClient()

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Response from model"},
            "done_reason": "stop",
            "prompt_eval_count": 50,
            "eval_count": 20,
        }
        mock_response.raise_for_status = MagicMock()

        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.generate(
            system_prompt="You are a helpful assistant.",
            messages=[{"role": "user", "content": "Hello"}],
            tools=None,
        )

        # Verify the API was called
        client._client.post.assert_called_once()
        call_args = client._client.post.call_args

        assert call_args[0][0] == "http://localhost:11434/api/chat"
        payload = call_args[1]["json"]
        assert payload["model"] == "qwen3:30b"
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2  # system + user

        # Verify the result
        assert result.content == "Response from model"
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_generate_with_tools(self):
        """Test generate method includes tools in API call."""
        client = OllamaClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "test_tool", "arguments": "{}"},
                    }
                ],
            },
            "done_reason": "stop",
            "prompt_eval_count": 30,
            "eval_count": 10,
        }
        mock_response.raise_for_status = MagicMock()

        client._client.post = AsyncMock(return_value=mock_response)

        tools = [
            {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]

        result = await client.generate(
            system_prompt="System",
            messages=[{"role": "user", "content": "Use the tool"}],
            tools=tools,
        )

        call_args = client._client.post.call_args
        payload = call_args[1]["json"]

        assert "tools" in payload
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["function"]["name"] == "test_tool"

        assert len(result.tool_calls) == 1
        assert result.stop_reason == "tool_use"

    @pytest.mark.asyncio
    async def test_close_closes_client(self):
        """Test close method closes the HTTP client."""
        client = OllamaClient()
        client._client.aclose = AsyncMock()

        await client.close()

        client._client.aclose.assert_called_once()


class TestOllamaResponse:
    """Tests for OllamaResponse dataclass."""

    def test_response_creation(self):
        """Test OllamaResponse creation."""
        response = OllamaResponse(
            content="Hello",
            tool_calls=[{"id": "1", "name": "test", "arguments": {}}],
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

        assert response.content == "Hello"
        assert len(response.tool_calls) == 1
        assert response.stop_reason == "tool_use"
        assert response.usage["input_tokens"] == 10
