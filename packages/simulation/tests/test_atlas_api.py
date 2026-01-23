"""Tests for Atlas API client."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from atlas_town.tools.atlas_api import (
    AtlasAPIClient,
    AtlasAPIError,
    AuthenticationError,
)


@pytest.fixture
def client():
    """Create an AtlasAPIClient instance."""
    return AtlasAPIClient(
        base_url="http://localhost:8000",
        username="test@example.com",
        password="testpassword",
    )


class TestAtlasAPIClientInit:
    """Tests for AtlasAPIClient initialization."""

    def test_init_with_explicit_params(self):
        """Test initialization with explicit parameters."""
        client = AtlasAPIClient(
            base_url="http://custom:9000",
            username="custom@example.com",
            password="custompass",
        )

        assert client.base_url == "http://custom:9000"
        assert client._username == "custom@example.com"
        assert client._password == "custompass"

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = AtlasAPIClient(
            base_url="http://localhost:8000/",
            username="test@example.com",
            password="test",
        )

        assert client.base_url == "http://localhost:8000"


class TestAuthentication:
    """Tests for authentication methods."""

    @pytest.mark.asyncio
    async def test_login_success(self, client, mock_login_response):
        """Test successful login."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_login_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_http

            result = await client.login()

            assert result["user"]["email"] == "test@example.com"
            assert client._access_token == "access-token-123"
            assert client._refresh_token == "refresh-token-123"
            assert len(client._organizations) == 2

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_http

            with pytest.raises(AuthenticationError) as exc_info:
                await client.login()

            assert "Invalid credentials" in str(exc_info.value)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_context_manager_logs_in(self, client, mock_login_response):
        """Test that context manager calls login."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_login_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.aclose = AsyncMock()
            mock_get.return_value = mock_http

            async with client as c:
                assert c._access_token == "access-token-123"


class TestAPIRequests:
    """Tests for API request methods."""

    @pytest.mark.asyncio
    async def test_list_customers(self, client, mock_customers_response):
        """Test listing customers."""
        # Set up authenticated state
        client._access_token = "test-token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_customers_response
        mock_response.content = b"content"

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_http

            result = await client.list_customers()

            assert len(result) == 2
            assert result[0]["name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_create_invoice(self, client, mock_invoice_response):
        """Test creating an invoice."""
        client._access_token = "test-token"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = mock_invoice_response
        mock_response.content = b"content"

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_http

            result = await client.create_invoice({
                "customer_id": "cust-123",
                "invoice_date": "2024-01-15",
                "lines": [
                    {
                        "description": "Consulting",
                        "quantity": 10,
                        "unit_price": "100.00",
                    }
                ],
            })

            assert result["invoice_number"] == "INV-0001"
            assert result["total_amount"] == "1000.00"

    @pytest.mark.asyncio
    async def test_handles_api_error(self, client):
        """Test handling of API errors."""
        client._access_token = "test-token"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid data"}
        mock_response.content = b"content"

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_http

            with pytest.raises(AtlasAPIError) as exc_info:
                await client.list_customers()

            assert exc_info.value.status_code == 400


class TestOrganizationSwitching:
    """Tests for organization context switching."""

    @pytest.mark.asyncio
    async def test_switch_organization(self, client):
        """Test switching organization context."""
        client._access_token = "test-token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tokens": {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
            }
        }
        mock_response.content = b"content"

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_http

            org_id = UUID("12345678-1234-1234-1234-123456789012")
            await client.switch_organization(org_id)

            assert client._access_token == "new-access-token"
            assert client._current_org_id == org_id


class TestToolDefinitions:
    """Tests for tool definitions."""

    def test_accountant_tools_count(self):
        """Test that accountant has expected number of tools."""
        from atlas_town.tools.definitions import ACCOUNTANT_TOOLS

        # Should have 30+ tools for full accounting operations
        assert len(ACCOUNTANT_TOOLS) >= 30

    def test_owner_tools_are_read_only(self):
        """Test that owner tools are primarily read-only."""
        from atlas_town.tools.definitions import OWNER_TOOLS

        # Owner tools should not include create/update operations
        write_tools = ["create_", "update_", "void_", "approve_", "send_"]

        for tool in OWNER_TOOLS:
            for write_op in write_tools:
                assert not tool["name"].startswith(write_op), (
                    f"Owner should not have write tool: {tool['name']}"
                )

    def test_tool_schemas_are_valid(self):
        """Test that all tool schemas have required fields."""
        from atlas_town.tools.definitions import ALL_TOOLS

        for tool in ALL_TOOLS:
            assert "name" in tool, "Tool must have a name"
            assert "description" in tool, "Tool must have a description"
            assert "input_schema" in tool, "Tool must have input_schema"
            assert tool["input_schema"]["type"] == "object"
