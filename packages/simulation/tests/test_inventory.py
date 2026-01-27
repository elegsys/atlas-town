"""Tests for inventory transaction generation."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import atlas_town.transactions as transactions


def test_consumption_tracking_updates_inventory_levels(monkeypatch):
    """Test that recording daily revenue decreases inventory levels."""

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,  # Monday
                "costing_method": "fifo",
                "consumption_driver": "revenue",
                "average_sale_price": 20.00,
                "average_visit_count": None,
                "items": [
                    {
                        "sku": "FLOUR-50LB",
                        "name": "Pizza Flour",
                        "unit_cost": 24.00,
                        "consumption_rate": 0.1,  # 0.1 units per sale
                        "reorder_level": 10,
                        "reorder_quantity": 20,
                        "vendor": "Test Supplier",
                        "category": "ingredients",
                    }
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)

    # Initial level should be reorder_level + reorder_quantity = 30
    # Record $200 revenue = 10 sales * 0.1 units = 1 unit consumed
    generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), Decimal("200")  # Tuesday
    )

    # Record another day of $400 revenue = 20 sales * 0.1 units = 2 units consumed
    generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 3), Decimal("400")  # Wednesday
    )

    # Access internal state to verify - 30 - 1 - 2 = 27
    state = generator._inventory_scheduler._inventory_levels.get(("testbiz", "FLOUR-50LB"))
    assert state is not None
    assert state.quantity == Decimal("27")


def test_replenishment_generated_at_reorder_level(monkeypatch):
    """Test that bills are generated when inventory hits reorder level on check day."""
    vendor_id = uuid4()

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,  # Monday
                "costing_method": "fifo",
                "consumption_driver": "revenue",
                "average_sale_price": 10.00,
                "average_visit_count": None,
                "items": [
                    {
                        "sku": "CHEESE-5LB",
                        "name": "Mozzarella Cheese",
                        "unit_cost": 18.50,
                        "consumption_rate": 0.5,  # 0.5 units per sale
                        "reorder_level": 20,
                        "reorder_quantity": 40,
                        "vendor": "Test Supplier",
                        "category": "ingredients",
                    }
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Test Supplier"}]

    # Initial level: 20 + 40 = 60 units
    # Consume heavily over several days to get below reorder level
    # $1000 revenue = 100 sales * 0.5 = 50 units consumed -> 10 remaining
    generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), Decimal("1000")  # Tuesday
    )

    # Check on non-Monday - should not generate transactions
    txs = generator.generate_inventory_transactions(
        "testbiz", date(2024, 1, 2), vendors  # Tuesday
    )
    assert txs == []

    # Check on Monday - should generate reorder
    txs = generator.generate_inventory_transactions(
        "testbiz", date(2024, 1, 8), vendors  # Monday
    )
    assert len(txs) == 1
    assert txs[0].transaction_type == transactions.TransactionType.BILL
    assert txs[0].description == "Inventory restock - Mozzarella Cheese"
    # Amount = 18.50 * 40 = 740.00
    assert txs[0].amount == Decimal("740.00")
    assert txs[0].vendor_id == vendor_id
    assert txs[0].metadata["inventory_sku"] == "CHEESE-5LB"
    assert txs[0].metadata["quantity"] == 40


def test_no_duplicate_orders_in_same_week(monkeypatch):
    """Test that the same item is not reordered twice in the same week."""
    vendor_id = uuid4()

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,  # Monday
                "costing_method": "fifo",
                "consumption_driver": "revenue",
                "average_sale_price": 10.00,
                "average_visit_count": None,
                "items": [
                    {
                        "sku": "SAUCE-GAL",
                        "name": "Tomato Sauce",
                        "unit_cost": 8.75,
                        "consumption_rate": 1.0,  # 1 unit per sale
                        "reorder_level": 15,
                        "reorder_quantity": 30,
                        "vendor": "Test Supplier",
                        "category": "ingredients",
                    }
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Test Supplier"}]

    # Deplete inventory: initial 45, consume 40 -> 5 remaining
    generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), Decimal("400")  # Tuesday, 40 units consumed
    )

    # First Monday check - should reorder
    txs = generator.generate_inventory_transactions(
        "testbiz", date(2024, 1, 8), vendors
    )
    assert len(txs) == 1

    # Simulate same Monday check again - should NOT reorder
    txs = generator.generate_inventory_transactions(
        "testbiz", date(2024, 1, 8), vendors
    )
    assert txs == []


def test_chen_appointment_based_consumption(monkeypatch):
    """Test appointment-based consumption driver for dental practice."""
    vendor_id = uuid4()

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,  # Monday
                "costing_method": "fifo",
                "consumption_driver": "appointments",
                "average_sale_price": None,
                "average_visit_count": 12,  # 12 appointments per day
                "items": [
                    {
                        "sku": "GLOVES-M",
                        "name": "Nitrile Gloves",
                        "unit_cost": 12.50,
                        "consumption_rate": 0.05,  # 0.05 boxes per appointment
                        "reorder_level": 20,
                        "reorder_quantity": 40,
                        "vendor": "Dental Supply Co",
                        "category": "disposables",
                    }
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Dental Supply Co"}]

    # Initial level: 20 + 40 = 60 units
    # Each day: 12 appointments * 0.05 = 0.6 units consumed
    # Record 5 business days (no revenue needed for appointments driver)
    for day in range(1, 6):  # Mon-Fri
        generator.record_daily_inventory_activity(
            "testbiz", date(2024, 1, day), None
        )

    # After 5 days: 60 - (5 * 0.6) = 57 units
    state = generator._inventory_scheduler._inventory_levels.get(("testbiz", "GLOVES-M"))
    assert state is not None
    assert state.quantity == Decimal("57")

    # Should not trigger reorder yet (57 > 20)
    txs = generator.generate_inventory_transactions(
        "testbiz", date(2024, 1, 8), vendors  # Monday
    )
    assert txs == []


def test_inventory_disabled_by_default(monkeypatch):
    """Test that businesses without inventory config don't generate transactions."""
    vendor_id = uuid4()

    def fake_inventory_configs():
        return {}  # No configs

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Test Supplier"}]

    # Should not raise errors, just return empty
    generator.record_daily_inventory_activity("nonexistent", date(2024, 1, 1), Decimal("1000"))
    txs = generator.generate_inventory_transactions("nonexistent", date(2024, 1, 8), vendors)
    assert txs == []


def test_multiple_items_reorder_independently(monkeypatch):
    """Test that multiple items can trigger reorders independently."""
    vendor_id = uuid4()

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,  # Monday
                "costing_method": "fifo",
                "consumption_driver": "revenue",
                "average_sale_price": 10.00,
                "average_visit_count": None,
                "items": [
                    {
                        "sku": "ITEM-A",
                        "name": "Item A (low stock)",
                        "unit_cost": 5.00,
                        "consumption_rate": 1.0,
                        "reorder_level": 10,
                        "reorder_quantity": 20,
                        "vendor": "Test Supplier",
                        "category": "test",
                    },
                    {
                        "sku": "ITEM-B",
                        "name": "Item B (sufficient stock)",
                        "unit_cost": 10.00,
                        "consumption_rate": 0.1,  # Much lower consumption
                        "reorder_level": 10,
                        "reorder_quantity": 20,
                        "vendor": "Test Supplier",
                        "category": "test",
                    },
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)
    vendors = [{"id": str(vendor_id), "display_name": "Test Supplier"}]

    # Initial: A=30, B=30
    # $200 revenue = 20 sales
    # A: 20 * 1.0 = 20 consumed -> 10 remaining (at reorder level)
    # B: 20 * 0.1 = 2 consumed -> 28 remaining (above reorder level)
    generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), Decimal("200")
    )

    txs = generator.generate_inventory_transactions(
        "testbiz", date(2024, 1, 8), vendors  # Monday
    )

    # Only Item A should be reordered
    assert len(txs) == 1
    assert txs[0].metadata["inventory_sku"] == "ITEM-A"
    assert txs[0].amount == Decimal("100.00")  # 5.00 * 20


def test_cogs_calculated_on_consumption(monkeypatch):
    """Test that COGS is calculated using FIFO (unit cost) when inventory is consumed."""

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,
                "costing_method": "fifo",
                "consumption_driver": "revenue",
                "average_sale_price": 20.00,
                "average_visit_count": None,
                "items": [
                    {
                        "sku": "FLOUR-50LB",
                        "name": "Pizza Flour",
                        "unit_cost": 24.00,
                        "consumption_rate": 0.1,  # 0.1 units per sale
                        "reorder_level": 10,
                        "reorder_quantity": 20,
                        "vendor": "Test Supplier",
                        "category": "ingredients",
                    },
                    {
                        "sku": "CHEESE-5LB",
                        "name": "Mozzarella",
                        "unit_cost": 18.50,
                        "consumption_rate": 0.25,  # 0.25 units per sale
                        "reorder_level": 10,
                        "reorder_quantity": 20,
                        "vendor": "Test Supplier",
                        "category": "ingredients",
                    },
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)

    # $200 revenue at $20/sale = 10 sales
    # Flour: 10 * 0.1 = 1 unit consumed * $24 = $24 COGS
    # Cheese: 10 * 0.25 = 2.5 units consumed * $18.50 = $46.25 COGS
    # Total COGS = $70.25
    cogs = generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), Decimal("200")
    )

    assert cogs is not None
    assert cogs.business_key == "testbiz"
    assert cogs.current_date == date(2024, 1, 2)
    assert cogs.total_cogs == Decimal("70.25")
    assert len(cogs.items) == 2

    # Check individual item COGS
    flour_cogs = next((item for item in cogs.items if item[0] == "FLOUR-50LB"), None)
    cheese_cogs = next((item for item in cogs.items if item[0] == "CHEESE-5LB"), None)

    assert flour_cogs is not None
    assert flour_cogs[2] == Decimal("24.00")  # 1 unit * $24

    assert cheese_cogs is not None
    assert cheese_cogs[2] == Decimal("46.25")  # 2.5 units * $18.50


def test_cogs_returns_none_when_no_consumption(monkeypatch):
    """Test that COGS returns None when there's no consumption."""

    def fake_inventory_configs():
        return {
            "testbiz": {
                "enabled": True,
                "check_day": 0,
                "costing_method": "fifo",
                "consumption_driver": "revenue",
                "average_sale_price": 20.00,
                "average_visit_count": None,
                "items": [
                    {
                        "sku": "FLOUR-50LB",
                        "name": "Pizza Flour",
                        "unit_cost": 24.00,
                        "consumption_rate": 0.1,
                        "reorder_level": 10,
                        "reorder_quantity": 20,
                        "vendor": "Test Supplier",
                        "category": "ingredients",
                    },
                ],
            }
        }

    monkeypatch.setattr(
        transactions, "load_persona_inventory_configs", fake_inventory_configs
    )

    generator = transactions.TransactionGenerator(seed=1)

    # No revenue = no consumption = no COGS
    cogs = generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), Decimal("0")
    )
    assert cogs is None

    # None revenue = no COGS
    cogs = generator.record_daily_inventory_activity(
        "testbiz", date(2024, 1, 2), None
    )
    assert cogs is None
