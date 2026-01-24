"""Tests for B2B paired transactions."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from atlas_town.b2b import B2BCoordinator, B2BPlannedPair
from atlas_town.orchestrator import Orchestrator, OrganizationContext


def _make_org(owner_key: str, name: str) -> OrganizationContext:
    return OrganizationContext(
        id=uuid4(),
        name=name,
        industry="general",
        owner_key=owner_key,
    )


class TestB2BCoordinator:
    def test_plans_pair_from_customers(self):
        seller = _make_org("craig", "Craig's Landscaping")
        buyer = _make_org("tony", "Tony's Pizzeria")
        orgs = {"craig": seller, "tony": buyer}

        coordinator = B2BCoordinator(orgs_by_key=orgs, configs={}, org_reference={})
        customers = {
            "craig": [{"id": str(uuid4()), "display_name": "Tony's Pizzeria"}],
            "tony": [],
        }

        sim_date = date(2025, 1, 10)
        planned = coordinator.plan_pairs(sim_date, customers)

        assert len(planned) == 1
        pair = planned[0]
        assert pair.seller_key == "craig"
        assert pair.buyer_key == "tony"
        assert pair.amount > 0
        assert pair.due_date == date(2025, 2, 9)

    def test_dedupe_after_mark_seen(self):
        seller = _make_org("craig", "Craig's Landscaping")
        buyer = _make_org("tony", "Tony's Pizzeria")
        orgs = {"craig": seller, "tony": buyer}

        coordinator = B2BCoordinator(orgs_by_key=orgs, configs={}, org_reference={})
        customers = {
            "craig": [{"id": str(uuid4()), "display_name": "Tony's Pizzeria"}],
            "tony": [],
        }

        sim_date = date(2025, 1, 10)
        planned = coordinator.plan_pairs(sim_date, customers)
        assert planned
        coordinator.mark_pair_seen(planned[0].pair_id)

        planned_again = coordinator.plan_pairs(sim_date, customers)
        assert planned_again == []


class TestOrchestratorB2B:
    @pytest.mark.asyncio
    async def test_process_b2b_creates_records(self):
        orch = Orchestrator(start_websocket=False)
        orch._event_publisher = MagicMock()

        seller_ctx = OrganizationContext(
            id=uuid4(),
            name="Craig's Landscaping",
            industry="landscaping",
            owner_key="craig",
        )
        buyer_ctx = OrganizationContext(
            id=uuid4(),
            name="Tony's Pizzeria",
            industry="restaurant",
            owner_key="tony",
        )
        orch._organizations = {seller_ctx.id: seller_ctx, buyer_ctx.id: buyer_ctx}
        orch._org_by_owner = {"craig": seller_ctx.id, "tony": buyer_ctx.id}

        api = AsyncMock()
        api.switch_organization = AsyncMock()
        api.list_customers = AsyncMock(
            side_effect=[
                [{"id": str(uuid4()), "display_name": "Tony's Pizzeria"}],
                [{"id": str(uuid4()), "display_name": "Craig's Landscaping"}],
            ]
        )
        api.list_vendors = AsyncMock(
            side_effect=[
                [{"id": str(uuid4()), "display_name": "Some Vendor"}],
                [{"id": str(uuid4()), "display_name": "Craig's Landscaping"}],
            ]
        )
        api.list_invoices = AsyncMock(return_value=[])
        api.list_bills = AsyncMock(return_value=[])
        api.create_invoice = AsyncMock(return_value={"id": str(uuid4())})
        api.create_bill = AsyncMock(return_value={"id": str(uuid4())})
        api.create_bill_payment = AsyncMock(return_value={"id": str(uuid4())})
        api.create_payment = AsyncMock(return_value={"id": str(uuid4())})
        api.apply_payment_to_invoice = AsyncMock()
        rev_id = str(uuid4())
        exp_id = str(uuid4())
        ar_id = str(uuid4())
        bank_id = str(uuid4())
        api.list_accounts = AsyncMock(
            return_value=[
                {"id": rev_id, "name": "Service Revenue", "account_type": "revenue"},
                {"id": exp_id, "name": "Office Supplies", "account_type": "expense"},
                {"id": ar_id, "name": "Accounts Receivable", "account_type": "accounts_receivable"},
                {"id": bank_id, "name": "Checking", "account_type": "bank"},
            ]
        )

        orch._api_client = api

        pair = B2BPlannedPair(
            pair_id="pair-1",
            seller_key="craig",
            buyer_key="tony",
            seller_org_id=seller_ctx.id,
            buyer_org_id=buyer_ctx.id,
            seller_name=seller_ctx.name,
            buyer_name=buyer_ctx.name,
            amount=Decimal("500.00"),
            description="B2B test",
            due_date=date(2025, 1, 20),
            payment_flow="same_day",
        )

        orch._b2b_coordinator = MagicMock()
        orch._b2b_coordinator.plan_pairs.return_value = [pair]

        sim_date = date(2025, 1, 10)
        results = await orch._process_b2b_transactions(sim_date)

        assert results
        api.create_invoice.assert_called_once()
        api.create_bill.assert_called_once()
        api.create_bill_payment.assert_called_once()
        api.create_payment.assert_called_once()
