"""Tests for Claude LLM client."""

from unittest.mock import MagicMock, patch

import pytest

from atlas_town.clients.claude import ClaudeClient, ClaudeResponse


class TestClaudeClient:
    """Tests for ClaudeClient."""

    def test_client_initialization_with_defaults(self):
        """Test client initializes with settings defaults."""
        client = ClaudeClient()

        assert client._model is not None
        assert client._max_tokens > 0

    def test_client_initialization_with_custom_params(self):
        """Test client accepts custom parameters."""
        client = ClaudeClient(
            api_key="test-key",
            model="claude-3-opus-20240229",
            max_tokens=2048,
            temperature=0.5,
        )

        assert client._api_key == "test-key"
        assert client._model == "claude-3-opus-20240229"
        assert client._max_tokens == 2048
        assert client._temperature == 0.5

    def test_convert_tools_to_anthropic_format(self):
        """Test tool format conversion."""
        client = ClaudeClient()
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

        converted = client._convert_tools_to_anthropic_format(tools)

        assert len(converted) == 1
        assert converted[0]["name"] == "test_tool"
        assert converted[0]["description"] == "A test tool"
        assert "input_schema" in converted[0]

    def test_convert_user_message_to_anthropic_format(self):
        """Test user message conversion."""
        client = ClaudeClient()
        messages = [{"role": "user", "content": "Hello"}]

        converted = client._convert_messages_to_anthropic_format(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"

    def test_convert_assistant_message_with_tool_calls(self):
        """Test assistant message with tool calls conversion."""
        client = ClaudeClient()
        messages = [
            {
                "role": "assistant",
                "content": "Let me check",
                "tool_calls": [
                    {"id": "call_123", "name": "list_customers", "arguments": {}},
                ],
            }
        ]

        converted = client._convert_messages_to_anthropic_format(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "assistant"

        # Content should be a list with text and tool_use blocks
        content = converted[0]["content"]
        assert isinstance(content, list)
        assert len(content) == 2

        text_block = content[0]
        assert text_block["type"] == "text"
        assert text_block["text"] == "Let me check"

        tool_block = content[1]
        assert tool_block["type"] == "tool_use"
        assert tool_block["id"] == "call_123"
        assert tool_block["name"] == "list_customers"

    def test_convert_tool_result_message(self):
        """Test tool result message conversion."""
        client = ClaudeClient()
        messages = [
            {
                "role": "tool_result",
                "content": '{"customers": []}',
                "tool_call_id": "call_123",
            }
        ]

        converted = client._convert_messages_to_anthropic_format(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "user"

        content = converted[0]["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "tool_result"
        assert content[0]["tool_use_id"] == "call_123"
        assert content[0]["content"] == '{"customers": []}'

    def test_parse_text_response(self):
        """Test parsing text-only response."""
        client = ClaudeClient()

        # Mock Anthropic response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Hello there")]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)

        parsed = client._parse_response(mock_response)

        assert parsed.content == "Hello there"
        assert parsed.tool_calls == []
        assert parsed.stop_reason == "end_turn"
        assert parsed.usage["input_tokens"] == 10
        assert parsed.usage["output_tokens"] == 5

    def test_parse_tool_use_response(self):
        """Test parsing response with tool calls."""
        client = ClaudeClient()

        # Mock tool use block
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "call_abc"
        tool_block.name = "list_customers"
        tool_block.input = {"limit": 10}

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.stop_reason = "tool_use"
        mock_response.usage = MagicMock(input_tokens=20, output_tokens=15)

        parsed = client._parse_response(mock_response)

        assert len(parsed.tool_calls) == 1
        assert parsed.tool_calls[0]["id"] == "call_abc"
        assert parsed.tool_calls[0]["name"] == "list_customers"
        assert parsed.tool_calls[0]["arguments"] == {"limit": 10}
        assert parsed.stop_reason == "tool_use"

    def test_count_tokens_approximation(self):
        """Test token counting approximation."""
        client = ClaudeClient()

        # ~4 chars per token for English
        text = "Hello world, this is a test."  # 28 chars
        count = client.count_tokens(text)

        assert count == 7  # 28 // 4


class TestClaudeResponse:
    """Tests for ClaudeResponse dataclass."""

    def test_response_creation(self):
        """Test ClaudeResponse creation."""
        response = ClaudeResponse(
            content="Hello",
            tool_calls=[{"id": "1", "name": "test", "arguments": {}}],
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

        assert response.content == "Hello"
        assert len(response.tool_calls) == 1
        assert response.stop_reason == "tool_use"
        assert response.usage["input_tokens"] == 10
