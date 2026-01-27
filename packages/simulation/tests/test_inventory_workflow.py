"""Tests for inventory workflow in AccountingWorkflow."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from atlas_town.accounting_workflow import (
    AccountingWorkflow,
    InventoryConfig,
    InventoryItemConfig,
    InventoryPolicy,
)
from atlas_town.transactions import GeneratedTransaction, TransactionType


@dataclass
class InventoryAPIStub:
    current_company_id: UUID
    accounts: list[dict[str, Any]] = field(default_factory=list)
    inventory_items: list[dict[str, Any]] = field(default_factory=list)
    low_stock: list[dict[str, Any]] = field(default_factory=list)
    created_items: list[dict[str, Any]] = field(default_factory=list)
    issued: list[dict[str, Any]] = field(default_factory=list)
    received: list[dict[str, Any]] = field(default_factory=list)
    bills: list[dict[str, Any]] = field(default_factory=list)
    purchase_orders: list[dict[str, Any]] = field(default_factory=list)
    journal_entries: list[dict[str, Any]] = field(default_factory=list)
    posted_journal_entries: list[dict[str, Any]] = field(default_factory=list)

    async def switch_organization(self, org_id: UUID) -> None:  # noqa: ARG002
        return None

    async def list_accounts(self, limit: int = 200) -> list[dict[str, Any]]:  # noqa: ARG002
        return self.accounts

    async def list_bank_accounts(self, include_inactive: bool = False) -> list[dict[str, Any]]:  # noqa: ARG002
        return []

    async def list_inventory_items(
        self,
        company_id: UUID | None = None,  # noqa: ARG002
        category: str | None = None,  # noqa: ARG002
        is_active: bool | None = True,  # noqa: ARG002
        offset: int = 0,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.inventory_items

    async def create_inventory_item(
        self, data: dict[str, Any], company_id: UUID | None = None  # noqa: ARG002
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid4()),
            "sku": data["sku"],
            "name": data["name"],
            "quantity_on_hand": "0",
            **data,
        }
        self.inventory_items.append(item)
        self.created_items.append(item)
        return item

    async def receive_inventory_goods(
        self, item_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        quantity = Decimal(str(data["quantity"]))
        for item in self.inventory_items:
            if str(item.get("id")) == str(item_id):
                on_hand = Decimal(str(item.get("quantity_on_hand", "0")))
                item["quantity_on_hand"] = str(on_hand + quantity)
                break
        self.received.append({"item_id": str(item_id), **data})
        return {"id": str(uuid4())}

    async def issue_inventory_goods(
        self, item_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        quantity = Decimal(str(data["quantity"]))
        for item in self.inventory_items:
            if str(item.get("id")) == str(item_id):
                on_hand = Decimal(str(item.get("quantity_on_hand", "0")))
                item["quantity_on_hand"] = str(on_hand - quantity)
                break
        self.issued.append({"item_id": str(item_id), **data})
        total_cost = (quantity * Decimal("10")).quantize(Decimal("0.01"))
        return {"total_cost": total_cost, "allocations": [], "transaction": {}}

    async def list_low_stock_items(
        self,
        company_id: UUID | None = None,  # noqa: ARG002
        offset: int = 0,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.low_stock

    async def create_bill(self, data: dict[str, Any]) -> dict[str, Any]:
        bill = {"id": str(uuid4()), **data}
        self.bills.append(bill)
        return bill

    async def create_purchase_order(
        self, data: dict[str, Any], company_id: UUID | None = None  # noqa: ARG002
    ) -> dict[str, Any]:
        po = {
            "id": str(uuid4()),
            "po_number": "PO-TEST-0001",
            "lines": [{"id": str(uuid4()), **data["lines"][0]}],
            **data,
        }
        self.purchase_orders.append(po)
        return po

    async def submit_purchase_order(self, po_id: UUID) -> dict[str, Any]:
        return {"id": str(po_id), "status": "submitted"}

    async def approve_purchase_order(self, po_id: UUID) -> dict[str, Any]:
        return {"id": str(po_id), "status": "approved"}

    async def list_journal_entries(
        self,
        company_id: UUID | None = None,  # noqa: ARG002
        offset: int = 0,  # noqa: ARG002
        limit: int = 100,  # noqa: ARG002
        status_filter: str | None = None,  # noqa: ARG002
        entry_type: str | None = None,  # noqa: ARG002
        start_date: str | None = None,  # noqa: ARG002
        end_date: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return self.journal_entries

    async def create_journal_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        entry = {"id": str(uuid4()), **data}
        self.journal_entries.append(entry)
        return entry

    async def post_journal_entry(self, entry_id: UUID) -> dict[str, Any]:
        entry = next(
            (item for item in self.journal_entries if str(item.get("id")) == str(entry_id)),
            None,
        )
        if entry is None:
            entry = {"id": str(entry_id)}
        posted = {**entry, "status": "posted"}
        self.posted_journal_entries.append(posted)
        return posted


def _inventory_config(cogs_ratio: str = "0.5") -> InventoryConfig:
    return InventoryConfig(
        items=(
            InventoryItemConfig(
                name="Test Item",
                sku="TEST-1",
                unit_cost=Decimal("10"),
                reorder_level=Decimal("2"),
                reorder_quantity=Decimal("10"),
                weekly_usage=Decimal("7"),
                unit_of_measure="each",
                costing_method="fifo",
                category=None,
                preferred_vendor=None,
            ),
        ),
        policy=InventoryPolicy(
            cogs_ratio=Decimal(cogs_ratio),
            usage_floor=Decimal("0"),
            usage_ceiling=Decimal("10"),
        ),
    )


def test_inventory_issue_scales_with_sales() -> None:
    org_id = UUID("11111111-1111-1111-1111-111111111111")
    api = InventoryAPIStub(
        current_company_id=UUID("22222222-2222-2222-2222-222222222222"),
        accounts=[
            {"id": str(uuid4()), "account_type": "asset", "name": "Inventory"},
            {"id": str(uuid4()), "account_type": "expense", "name": "Cost of Goods Sold"},
            {"id": str(uuid4()), "account_type": "expense", "name": "Supplies Expense"},
        ],
    )
    workflow = AccountingWorkflow(api_client=api)
    workflow._inventory_configs = {"tony": _inventory_config(cogs_ratio="0.5")}

    transactions = [
        GeneratedTransaction(
            transaction_type=TransactionType.CASH_SALE,
            description="Pizza sales",
            amount=Decimal("40"),
            customer_id=uuid4(),
        )
    ]

    result = asyncio.run(
        workflow.run_inventory_workflow(
            business_key="tony",
            org_id=org_id,
            current_date=date(2024, 1, 5),
            transactions=transactions,
            vendors=[],
        )
    )

    assert result["issued"] == 1
    assert api.issued
    assert Decimal(api.issued[0]["quantity"]) == Decimal("2.00")
    assert api.posted_journal_entries


def test_inventory_reorder_triggers_bill_and_receipt() -> None:
    org_id = UUID("33333333-3333-3333-3333-333333333333")
    api = InventoryAPIStub(
        current_company_id=UUID("44444444-4444-4444-4444-444444444444"),
        accounts=[
            {"id": str(uuid4()), "account_type": "asset", "name": "Inventory"},
            {"id": str(uuid4()), "account_type": "expense", "name": "Cost of Goods Sold"},
            {"id": str(uuid4()), "account_type": "expense", "name": "Supplies Expense"},
        ],
    )
    workflow = AccountingWorkflow(api_client=api)
    workflow._inventory_configs = {"chen": _inventory_config(cogs_ratio="0.1")}

    api.low_stock = [
        {
            "id": str(uuid4()),
            "sku": "TEST-1",
            "name": "Test Item",
            "quantity_on_hand": "1",
            "reorder_level": "2",
            "reorder_quantity": "10",
        }
    ]

    result = asyncio.run(
        workflow.run_inventory_workflow(
            business_key="chen",
            org_id=org_id,
            current_date=date(2024, 1, 6),
            transactions=[],
            vendors=[{"id": str(uuid4()), "name": "Test Vendor"}],
        )
    )

    assert result["replenished"] == 1
    assert api.purchase_orders
    assert api.bills
    assert api.received
    assert Decimal(api.received[-1]["quantity"]) == Decimal("10")
