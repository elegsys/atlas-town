"""Pytest configuration and fixtures."""

import os
from unittest.mock import AsyncMock

import pytest

# Set test environment variables before importing settings
os.environ.setdefault("ATLAS_USERNAME", "test@example.com")
os.environ.setdefault("ATLAS_PASSWORD", "testpassword")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx AsyncClient."""
    client = AsyncMock()
    client.request = AsyncMock()
    client.post = AsyncMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def mock_login_response():
    """Mock successful login response."""
    return {
        "user": {
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
        },
        "organizations": [
            {"id": "22222222-2222-2222-2222-222222222222", "name": "Test Org"},
            {"id": "33333333-3333-3333-3333-333333333333", "name": "Second Org"},
        ],
        "tokens": {
            "access_token": "access-token-123",
            "refresh_token": "refresh-token-123",
        },
    }


@pytest.fixture
def mock_customers_response():
    """Mock customers list response."""
    return [
        {
            "id": "44444444-4444-4444-4444-444444444444",
            "name": "John Doe",
            "email": "john@example.com",
            "balance": "1000.00",
        },
        {
            "id": "55555555-5555-5555-5555-555555555555",
            "name": "Jane Smith",
            "email": "jane@example.com",
            "balance": "500.00",
        },
    ]


@pytest.fixture
def mock_invoice_response():
    """Mock invoice response."""
    return {
        "id": "66666666-6666-6666-6666-666666666666",
        "invoice_number": "INV-0001",
        "customer_id": "44444444-4444-4444-4444-444444444444",
        "invoice_date": "2024-01-15",
        "due_date": "2024-02-15",
        "subtotal": "1000.00",
        "tax_amount": "0.00",
        "total_amount": "1000.00",
        "amount_paid": "0.00",
        "amount_due": "1000.00",
        "status": "draft",
        "lines": [
            {
                "id": "77777777-7777-7777-7777-777777777777",
                "description": "Consulting services",
                "quantity": 10,
                "unit_price": "100.00",
                "amount": "1000.00",
            }
        ],
    }
