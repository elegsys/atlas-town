"""Tests for orchestrator inflation notifications."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from atlas_town.agents.vendor import VENDOR_ARCHETYPES
from atlas_town.economics import InflationModel
from atlas_town.orchestrator import Orchestrator, OrganizationContext


def test_vendor_price_increase_notifications_published():
    orch = Orchestrator(start_websocket=False)
    orch._event_publisher = MagicMock()
    orch._inflation = InflationModel(
        annual_rate=Decimal("1.0"),
        start_date=date(2023, 1, 1),
    )
    orch._vendor_price_increase_sent = set()

    ctx = OrganizationContext(
        id=uuid4(),
        name="Craig's Landscaping",
        industry="landscaping",
        owner_key="craig",
    )
    orch._organizations = {ctx.id: ctx}

    orch._maybe_publish_vendor_price_increases(date(2024, 1, 1))

    expected = len(VENDOR_ARCHETYPES["landscaping"])
    assert orch._event_publisher.publish.call_count == expected
