"""Tests for sales tax configuration loading."""

from decimal import Decimal

from atlas_town.config.personas_loader import load_persona_sales_tax_configs


def test_sales_tax_config_loaded_for_tony():
    configs = load_persona_sales_tax_configs()
    assert "tony" in configs

    tony = configs["tony"]
    assert tony["enabled"] is True
    assert Decimal(str(tony["rate"])) == Decimal("0.0825")
    assert tony["jurisdiction"] == "NY"
    assert "pizza" in [item.lower() for item in tony["collect_on"]]
