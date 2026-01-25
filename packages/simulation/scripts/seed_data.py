#!/usr/bin/env python3
"""Seed Atlas Town with realistic business data.

This script creates:
1. User accounts and organizations via signup (one per business)
2. Chart of accounts for each organization
3. Customers specific to each business type
4. Vendors for supplies and services
5. Opening balances via journal entries
6. Initial transactions to bootstrap the simulation

Usage:
    cd packages/simulation
    source .venv/bin/activate
    python scripts/seed_data.py
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from atlas_town.tools.atlas_api import AtlasAPIClient, AtlasAPIError

# ============================================================================
# BUSINESS DEFINITIONS
# ============================================================================

# Default password for all simulation accounts (meets Atlas requirements)
DEFAULT_PASSWORD = "AtlasTown2024!"

# The 5 Atlas Town businesses with owner credentials
BUSINESSES = {
    "craig": {
        "name": "Craig's Landscaping",
        "industry": "Landscaping Services",
        "owner": "Craig Miller",
        "description": "Full-service landscaping and lawn care",
        "email": "craig@atlasdev.com",
        "first_name": "Craig",
        "last_name": "Miller",
    },
    "tony": {
        "name": "Tony's Pizzeria",
        "industry": "Food & Beverage",
        "owner": "Tony Romano",
        "description": "Family-owned Italian restaurant",
        "email": "tony@atlasdev.com",
        "first_name": "Tony",
        "last_name": "Romano",
    },
    "maya": {
        "name": "Nexus Tech Consulting",
        "industry": "Technology Consulting",
        "owner": "Maya Patel",
        "description": "IT consulting and software development",
        "email": "maya@atlasdev.com",
        "first_name": "Maya",
        "last_name": "Patel",
    },
    "chen": {
        "name": "Main Street Dental",
        "industry": "Healthcare - Dental",
        "owner": "Dr. David Chen",
        "description": "Family dental practice",
        "email": "chen@atlasdev.com",
        "first_name": "David",
        "last_name": "Chen",
    },
    "marcus": {
        "name": "Harbor Realty",
        "industry": "Real Estate",
        "owner": "Marcus Thompson",
        "description": "Residential and commercial real estate",
        "email": "marcus@atlasdev.com",
        "first_name": "Marcus",
        "last_name": "Thompson",
    },
}

# ============================================================================
# CUSTOMERS BY BUSINESS
# ============================================================================

CUSTOMERS = {
    "craig": [
        {"display_name": "Riverside Apartments", "email": "manager@riversideapts.com", "payment_terms": "net_30"},
        {"display_name": "Oak Street HOA", "email": "board@oakstreethoa.com", "payment_terms": "net_15"},
        {"display_name": "Johnson Family", "email": "mike.johnson@email.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Sunrise Senior Living", "email": "facilities@sunrisesenior.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Town Municipality", "email": "parks@atlastown.gov", "payment_terms": "net_60"},
        {"display_name": "Tony's Pizzeria", "email": "tony@tonyspizza.com", "payment_terms": "net_15"},
        {"display_name": "Harbor Realty", "email": "marcus@harborrealty.com", "payment_terms": "net_15"},
    ],
    "tony": [
        {"display_name": "Atlas Elementary School", "email": "cafeteria@atlaselem.edu", "payment_terms": "net_30"},
        {"display_name": "Friday Night Football", "email": "events@fnfl.org", "payment_terms": "net_15"},
        {"display_name": "Birthday Party Catering", "email": "catering@tonyspizza.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Office Lunch Orders", "email": "corporate@tonyspizza.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Nexus Tech", "email": "office@nexustech.io", "payment_terms": "net_15"},
    ],
    "maya": [
        {"display_name": "Craig's Landscaping", "email": "craig@craigslandscaping.com", "payment_terms": "net_30"},
        {"display_name": "Tony's Pizzeria", "email": "tony@tonyspizza.com", "payment_terms": "net_30"},
        {"display_name": "Main Street Dental", "email": "office@mainstreetdental.com", "payment_terms": "net_30"},
        {"display_name": "Harbor Realty", "email": "marcus@harborrealty.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Fitness Center", "email": "manager@atlasfitness.com", "payment_terms": "net_30"},
        {"display_name": "Bloom Flower Shop", "email": "orders@bloomflowers.com", "payment_terms": "net_30"},
        {"display_name": "Coastal Insurance", "email": "it@coastalinsurance.com", "payment_terms": "net_60"},
    ],
    "chen": [
        {"display_name": "Smith Family", "email": "smith.family@email.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Garcia Family", "email": "garcia.family@email.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Williams, Robert", "email": "rwilliams@email.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Thompson, Sarah", "email": "sthompson@email.com", "payment_terms": "due_on_receipt"},
        {"display_name": "BlueCross Insurance", "email": "claims@bluecross.com", "payment_terms": "net_60"},
        {"display_name": "Delta Dental PPO", "email": "claims@deltadental.com", "payment_terms": "net_60"},
        {"display_name": "Atlas Town Employees", "email": "benefits@atlastown.gov", "payment_terms": "net_30"},
    ],
    "marcus": [
        {"display_name": "First-Time Buyers", "email": "ftb@harborrealty.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Estate of Johnson", "email": "legal@johnsonestate.com", "payment_terms": "net_30"},
        {"display_name": "Relocation Services", "email": "agents@relocateservices.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Development Corp", "email": "sales@atlasdevcorp.com", "payment_terms": "net_15"},
        {"display_name": "Private Seller Mitchell", "email": "jmitchell@email.com", "payment_terms": "due_on_receipt"},
    ],
}

# ============================================================================
# VENDORS BY BUSINESS
# ============================================================================

VENDORS = {
    "craig": [
        {"display_name": "Green Valley Nursery", "email": "orders@greenvalley.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Equipment Rental", "email": "rental@atlasequip.com", "payment_terms": "net_15"},
        {"display_name": "Shell Gas Station", "email": "fleet@shellgas.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Home Depot Pro", "email": "pro@homedepotpro.com", "payment_terms": "net_30"},
        {"display_name": "Irrigation Supply Co", "email": "sales@irrigationsupply.com", "payment_terms": "net_30"},
        {"display_name": "Workers Comp Insurance", "email": "billing@workerscomp.com", "payment_terms": "net_30"},
        {"display_name": "Equipment Yard Lease", "email": "billing@equipmentyardlease.com", "payment_terms": "net_30"},
        {"display_name": "City Utilities", "email": "billing@cityutilities.com", "payment_terms": "net_30"},
        {"display_name": "Jobber Software", "email": "billing@jobber.com", "payment_terms": "net_30"},
        {"display_name": "Smith Insurance Agency", "email": "billing@smithinsurance.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Payroll Services", "email": "payroll@atlaspayroll.com", "payment_terms": "net_15"},
        {"display_name": "IRS Payroll Taxes", "email": "payroll@irs.gov", "payment_terms": "net_15"},
    ],
    "tony": [
        {"display_name": "Sysco Food Services", "email": "orders@syscofood.com", "payment_terms": "net_15"},
        {"display_name": "Roma Cheese Imports", "email": "sales@romacheese.com", "payment_terms": "net_30"},
        {"display_name": "Coca-Cola Bottling", "email": "delivery@cocacolabottling.com", "payment_terms": "net_15"},
        {"display_name": "Restaurant Depot", "email": "orders@restaurantdepot.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Atlas Gas Electric", "email": "business@atlasge.com", "payment_terms": "net_30"},
        {"display_name": "Downtown Properties LLC", "email": "billing@downtownproperties.com", "payment_terms": "net_30"},
        {"display_name": "City Utilities", "email": "billing@cityutilities.com", "payment_terms": "net_30"},
        {"display_name": "POS Systems Inc", "email": "support@possystems.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Payroll Services", "email": "payroll@atlaspayroll.com", "payment_terms": "net_15"},
        {"display_name": "IRS Payroll Taxes", "email": "payroll@irs.gov", "payment_terms": "net_15"},
    ],
    "maya": [
        {"display_name": "Amazon Web Services", "email": "billing@awscloud.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Microsoft 365", "email": "billing@microsoft365.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Slack Technologies", "email": "billing@slacktech.com", "payment_terms": "due_on_receipt"},
        {"display_name": "GitHub Enterprise", "email": "billing@githubenterprise.com", "payment_terms": "due_on_receipt"},
        {"display_name": "WeWork Office Space", "email": "billing@weworkspace.com", "payment_terms": "net_30"},
        {"display_name": "Coworking Space LLC", "email": "billing@coworkingspace.com", "payment_terms": "net_30"},
        {"display_name": "City Utilities", "email": "billing@cityutilities.com", "payment_terms": "net_30"},
        {"display_name": "JetBrains Software", "email": "billing@jetbrains.com", "payment_terms": "net_30"},
        {"display_name": "E&O Insurance", "email": "billing@eoinsurance.com", "payment_terms": "net_30"},
        {"display_name": "Nexus Payroll Services", "email": "payroll@nexuspayroll.com", "payment_terms": "net_15"},
        {"display_name": "IRS Payroll Taxes", "email": "payroll@irs.gov", "payment_terms": "net_15"},
    ],
    "chen": [
        {"display_name": "Henry Schein Dental", "email": "orders@henryschein.com", "payment_terms": "net_30"},
        {"display_name": "Patterson Dental", "email": "orders@pattersondental.com", "payment_terms": "net_30"},
        {"display_name": "Atlas Dental Lab", "email": "orders@atlasdentallab.com", "payment_terms": "net_15"},
        {"display_name": "Sterilization Services", "email": "service@sterilize.com", "payment_terms": "net_30"},
        {"display_name": "Medical Waste Solutions", "email": "pickup@medwaste.com", "payment_terms": "net_30"},
        {"display_name": "Medical Plaza Properties", "email": "billing@medicalplaza.com", "payment_terms": "net_30"},
        {"display_name": "City Utilities", "email": "billing@cityutilities.com", "payment_terms": "net_30"},
        {"display_name": "Practice Management Software", "email": "billing@practicemanagement.com", "payment_terms": "net_30"},
        {"display_name": "Medical Equipment Leasing", "email": "billing@medicalequipmentleasing.com", "payment_terms": "net_30"},
        {"display_name": "Dental Malpractice Ins", "email": "billing@dentalmalpractice.com", "payment_terms": "net_30"},
        {"display_name": "Dental Payroll Co", "email": "payroll@dentalpayroll.com", "payment_terms": "net_15"},
        {"display_name": "IRS Payroll Taxes", "email": "payroll@irs.gov", "payment_terms": "net_15"},
    ],
    "marcus": [
        {"display_name": "MLS Listing Service", "email": "billing@mlslisting.com", "payment_terms": "due_on_receipt"},
        {"display_name": "MLS Subscription Service", "email": "billing@mlssubscription.com", "payment_terms": "net_30"},
        {"display_name": "Zillow Premier Agent", "email": "billing@zillowpremier.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Signs Now", "email": "orders@signsnow.com", "payment_terms": "net_15"},
        {"display_name": "Professional Photos", "email": "booking@prophotos.com", "payment_terms": "due_on_receipt"},
        {"display_name": "Atlas Title Company", "email": "closings@atlastitle.com", "payment_terms": "net_30"},
        {"display_name": "Office Space Partners", "email": "billing@officespacepartners.com", "payment_terms": "net_30"},
        {"display_name": "E&O Insurance Brokers", "email": "billing@eobrokers.com", "payment_terms": "net_30"},
        {"display_name": "Harbor Payroll Services", "email": "payroll@harborpayroll.com", "payment_terms": "net_15"},
        {"display_name": "IRS Payroll Taxes", "email": "payroll@irs.gov", "payment_terms": "net_15"},
    ],
}

# ============================================================================
# OPENING BALANCES (Starting financial position)
# ============================================================================

# These represent realistic starting positions for small businesses
OPENING_BALANCES = {
    "craig": {
        "cash": Decimal("15000.00"),
        "accounts_receivable": Decimal("4500.00"),
        "equipment": Decimal("35000.00"),
        "vehicle": Decimal("28000.00"),
        "accounts_payable": Decimal("2200.00"),
        "vehicle_loan": Decimal("18000.00"),
        "owner_equity": Decimal("62300.00"),
    },
    "tony": {
        "cash": Decimal("8000.00"),
        "inventory": Decimal("6500.00"),
        "equipment": Decimal("45000.00"),
        "leasehold_improvements": Decimal("25000.00"),
        "accounts_payable": Decimal("4800.00"),
        "equipment_loan": Decimal("20000.00"),
        "owner_equity": Decimal("59700.00"),
    },
    "maya": {
        "cash": Decimal("25000.00"),
        "accounts_receivable": Decimal("12000.00"),
        "computers_equipment": Decimal("8000.00"),
        "accounts_payable": Decimal("1500.00"),
        "owner_equity": Decimal("43500.00"),
    },
    "chen": {
        "cash": Decimal("20000.00"),
        "accounts_receivable": Decimal("35000.00"),  # Insurance claims pending
        "dental_equipment": Decimal("180000.00"),
        "leasehold_improvements": Decimal("45000.00"),
        "accounts_payable": Decimal("8000.00"),
        "equipment_loan": Decimal("120000.00"),
        "owner_equity": Decimal("152000.00"),
    },
    "marcus": {
        "cash": Decimal("12000.00"),
        "accounts_receivable": Decimal("8500.00"),  # Pending commissions
        "office_equipment": Decimal("5000.00"),
        "accounts_payable": Decimal("1200.00"),
        "owner_equity": Decimal("24300.00"),
    },
}

# ============================================================================
# SIGNUP & AUTHENTICATION
# ============================================================================


async def signup_business(
    api_url: str,
    business_key: str,
    business: dict[str, str],
) -> dict[str, Any] | None:
    """Create a user account and organization via signup.

    Returns signup response with tokens, or None if already exists.
    """
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        signup_data = {
            "email": business["email"],
            "password": DEFAULT_PASSWORD,
            "first_name": business["first_name"],
            "last_name": business["last_name"],
            "organization_name": business["name"],
        }

        try:
            response = await client.post("/api/v1/auth/signup", json=signup_data)

            if response.status_code == 201:
                data = response.json()
                print(f"  ✓ Created: {business['name']} ({business['email']})")
                return data
            elif response.status_code == 400:
                error = response.json()
                if "already registered" in error.get("detail", "").lower():
                    print(f"  ℹ Already exists: {business['email']}")
                    return None
                else:
                    print(f"  ✗ Signup failed: {error.get('detail', 'Unknown error')}")
                    return None
            else:
                error = response.json() if response.content else {}
                print(f"  ✗ Signup failed: HTTP {response.status_code} - {error}")
                return None
        except Exception as e:
            print(f"  ✗ Signup error: {e}")
            return None


async def login_business(
    api_url: str,
    email: str,
) -> dict[str, Any] | None:
    """Login to get fresh tokens for an existing account."""
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        try:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": DEFAULT_PASSWORD},
            )

            if response.status_code == 200:
                return response.json()
            else:
                error = response.json() if response.content else {}
                print(f"  ✗ Login failed for {email}: HTTP {response.status_code} - {error}")
                return None
        except Exception as e:
            print(f"  ✗ Login error: {e}")
            return None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def setup_chart_of_accounts(client: AtlasAPIClient) -> dict[str, UUID]:
    """Set up chart of accounts and return account name -> ID mapping."""
    # First check if accounts already exist
    existing_accounts = await client.list_accounts(limit=10)
    if existing_accounts:
        print(f"    ℹ Chart of accounts already exists ({len(existing_accounts)}+ accounts)")
    else:
        # Only try to set up COA if no accounts exist
        try:
            await client.post(
                "/api/v1/accounts/setup-coa",
                json={"template_name": "us_gaap", "industry": "general"},
            )
            print("    ✓ Chart of accounts created")
        except AtlasAPIError as e:
            error_str = str(e.details).lower() if e.details else ""
            if "already" in error_str or "exists" in error_str or e.status_code == 500:
                # 500 often means COA already exists (backend bug)
                print("    ℹ Chart of accounts already exists (or setup failed)")
            else:
                print(f"    ✗ COA setup error: {e.details}")
                raise

    # Get all accounts and build mapping
    accounts = await client.list_accounts(limit=200)
    account_map = {}
    for acc in accounts:
        # Map by both name and account_number for flexibility
        account_map[acc["name"].lower()] = UUID(acc["id"])
        if acc.get("account_number"):
            account_map[acc["account_number"]] = UUID(acc["id"])

    return account_map


async def create_customers(client: AtlasAPIClient, business_key: str) -> list[dict]:
    """Create customers for a business."""
    created = []
    for cust_data in CUSTOMERS.get(business_key, []):
        try:
            customer = await client.create_customer(cust_data)
            created.append(customer)
            print(f"    ✓ Customer: {cust_data['display_name']}")
        except AtlasAPIError as e:
            if "already exists" in str(e.details).lower() or e.status_code == 409:
                print(f"    ℹ Customer exists: {cust_data['display_name']}")
            else:
                print(f"    ✗ Customer failed: {cust_data['display_name']} - {e}")
    return created


async def create_vendors(client: AtlasAPIClient, business_key: str) -> list[dict]:
    """Create vendors for a business."""
    created = []
    for vendor_data in VENDORS.get(business_key, []):
        try:
            vendor = await client.create_vendor(vendor_data)
            created.append(vendor)
            print(f"    ✓ Vendor: {vendor_data['display_name']}")
        except AtlasAPIError as e:
            if "already exists" in str(e.details).lower() or e.status_code == 409:
                print(f"    ℹ Vendor exists: {vendor_data['display_name']}")
            else:
                print(f"    ✗ Vendor failed: {vendor_data['display_name']} - {e}")
    return created


async def create_opening_balances(
    client: AtlasAPIClient,
    business_key: str,
    account_map: dict[str, UUID],
) -> None:
    """Create opening balance journal entry."""
    balances = OPENING_BALANCES.get(business_key, {})
    if not balances:
        return

    # Build journal entry lines
    # Map balance keys to account names (must match US GAAP template names)
    account_name_map = {
        "cash": "cash - operating account",  # More specific than parent "cash"
        "accounts_receivable": "accounts receivable",
        "inventory": "inventory",
        "equipment": "property & equipment",  # Parent account for equipment
        "vehicle": "vehicles",
        "computers_equipment": "office equipment",
        "dental_equipment": "office equipment",  # Use office equipment for dental
        "office_equipment": "office equipment",
        "leasehold_improvements": "furniture & fixtures",  # No leasehold, use furniture
        "accounts_payable": "accounts payable",
        "vehicle_loan": "long-term notes payable",
        "equipment_loan": "long-term notes payable",
        "owner_equity": "owner's equity",
    }

    lines = []
    for balance_key, amount in balances.items():
        account_name = account_name_map.get(balance_key, balance_key)
        account_id = account_map.get(account_name)

        if not account_id:
            print(f"    ⚠ Account not found: {account_name}")
            continue

        # Determine debit/credit based on account type
        is_credit_account = balance_key in ["accounts_payable", "vehicle_loan", "equipment_loan", "owner_equity"]

        lines.append({
            "account_id": str(account_id),
            "entry_type": "credit" if is_credit_account else "debit",
            "amount": str(amount),
            "description": f"Opening balance - {balance_key.replace('_', ' ').title()}",
        })

    if lines:
        try:
            je_data = {
                "entry_date": (date.today() - timedelta(days=30)).isoformat(),
                "description": "Opening balances for business startup",
                "entry_type": "manual",
                "lines": lines,
            }
            await client.create_journal_entry(je_data)
            print(f"    ✓ Opening balances recorded ({len(lines)} accounts)")
        except AtlasAPIError as e:
            print(f"    ✗ Opening balances failed: {e.details}")


def _find_cash_gl_account(account_map: dict[str, UUID]) -> UUID | None:
    preferred = (
        "cash - operating account",
        "operating cash",
        "cash",
        "checking",
        "bank",
    )
    for name in preferred:
        account_id = account_map.get(name)
        if account_id:
            return account_id
    for key, value in account_map.items():
        if not isinstance(key, str) or key.isdigit():
            continue
        lowered = key.lower()
        if "cash" in lowered or "checking" in lowered or "bank" in lowered:
            return value
    return None


async def create_bank_feed_account(
    client: AtlasAPIClient,
    business_key: str,
    account_map: dict[str, UUID],
) -> None:
    """Create a linked bank account for bank feed transactions."""
    gl_account_id = _find_cash_gl_account(account_map)
    if not gl_account_id:
        print("    ⚠ Cash/Bank GL account not found - skipping bank feed account")
        return

    try:
        existing_accounts = await client.list_bank_accounts()
        for account in existing_accounts:
            if str(account.get("gl_account_id")) == str(gl_account_id):
                print("    ℹ Bank feed account exists")
                return
    except AtlasAPIError as e:
        print(f"    ⚠ Bank accounts lookup failed: {e}")

    profiles = {
        "craig": {
            "account_name": "Operating Checking - Landscaping",
            "bank_name": "Atlas Community Bank",
            "last4": "1001",
            "opening_balance": "2500",
        },
        "tony": {
            "account_name": "Operating Checking - Pizzeria",
            "bank_name": "Atlas Community Bank",
            "last4": "1002",
            "opening_balance": "4200",
        },
        "maya": {
            "account_name": "Operating Checking - Consulting",
            "bank_name": "Atlas Community Bank",
            "last4": "1003",
            "opening_balance": "8000",
        },
        "chen": {
            "account_name": "Operating Checking - Dental",
            "bank_name": "Atlas Community Bank",
            "last4": "1004",
            "opening_balance": "6500",
        },
        "marcus": {
            "account_name": "Operating Checking - Realty",
            "bank_name": "Atlas Community Bank",
            "last4": "1005",
            "opening_balance": "5000",
        },
    }
    profile = profiles.get(
        business_key,
        {
            "account_name": "Operating Checking",
            "bank_name": "Atlas Community Bank",
            "last4": "1000",
            "opening_balance": "0",
        },
    )

    try:
        await client.create_bank_account(
            {
                "gl_account_id": str(gl_account_id),
                "account_name": profile["account_name"],
                "bank_name": profile["bank_name"],
                "account_number_last4": profile["last4"],
                "account_type": "checking",
                "opening_balance": profile["opening_balance"],
                "currency": "USD",
            }
        )
        print("    ✓ Bank feed account created")
    except AtlasAPIError as e:
        if "already exists" in str(e.details).lower() or e.status_code == 409:
            print("    ℹ Bank feed account exists")
        else:
            print(f"    ✗ Bank feed account failed: {e.details}")


async def create_sample_transactions(
    client: AtlasAPIClient,
    business_key: str,
    account_map: dict[str, UUID],
) -> None:
    """Create a few sample transactions to bootstrap the simulation."""
    # Get customers and vendors
    customers = await client.list_customers()
    vendors = await client.list_vendors()

    if not customers or not vendors:
        print("    ⚠ No customers/vendors to create transactions")
        return

    # Find revenue account (required for invoices)
    revenue_account_id = (
        account_map.get("service revenue") or
        account_map.get("sales revenue") or
        account_map.get("4100") or  # Service Revenue
        account_map.get("4000")  # Sales Revenue
    )

    # Find expense account (required for bills)
    expense_account_id = (
        account_map.get("supplies expense") or
        account_map.get("cost of goods sold") or
        account_map.get("office supplies") or
        account_map.get("5100") or  # Cost of Goods Sold
        account_map.get("5200")  # Operating Expenses
    )

    if not revenue_account_id:
        print("    ⚠ Revenue account not found - skipping invoices")
    if not expense_account_id:
        print("    ⚠ Expense account not found - skipping bills")

    # Create 2-3 sample invoices
    sample_invoices = {
        "craig": [
            {"desc": "Monthly lawn maintenance", "amount": "450.00"},
            {"desc": "Spring cleanup and mulching", "amount": "875.00"},
        ],
        "tony": [
            {"desc": "Catering - Office lunch", "amount": "285.00"},
            {"desc": "Weekly pizza order", "amount": "156.00"},
        ],
        "maya": [
            {"desc": "IT consulting - January", "amount": "2400.00"},
            {"desc": "Website maintenance", "amount": "500.00"},
        ],
        "chen": [
            {"desc": "Dental cleaning and exam", "amount": "250.00"},
            {"desc": "Cavity filling", "amount": "380.00"},
        ],
        "marcus": [
            {"desc": "Commission - 123 Oak Street sale", "amount": "8500.00"},
        ],
    }

    if revenue_account_id:
        for i, inv in enumerate(sample_invoices.get(business_key, [])):
            if i >= len(customers):
                break
            try:
                invoice_data = {
                    "customer_id": customers[i]["id"],
                    "invoice_date": (date.today() - timedelta(days=15 - i * 5)).isoformat(),
                    "due_date": (date.today() + timedelta(days=15 + i * 5)).isoformat(),
                    "lines": [{
                        "description": inv["desc"],
                        "quantity": "1",
                        "unit_price": inv["amount"],
                        "revenue_account_id": str(revenue_account_id),
                    }],
                }
                await client.create_invoice(invoice_data)
                print(f"    ✓ Invoice: {inv['desc'][:40]}...")
            except AtlasAPIError as e:
                print(f"    ✗ Invoice failed: {e.details}")

    # Create 1-2 sample bills
    sample_bills = {
        "craig": [{"desc": "Mulch and plants", "amount": "340.00"}],
        "tony": [{"desc": "Weekly food supplies", "amount": "890.00"}],
        "maya": [{"desc": "AWS monthly", "amount": "127.00"}],
        "chen": [{"desc": "Dental supplies", "amount": "456.00"}],
        "marcus": [{"desc": "MLS monthly fee", "amount": "299.00"}],
    }

    if expense_account_id:
        for i, bill in enumerate(sample_bills.get(business_key, [])):
            if i >= len(vendors):
                break
            try:
                bill_data = {
                    "vendor_id": vendors[i]["id"],
                    "bill_date": (date.today() - timedelta(days=10)).isoformat(),
                    "due_date": (date.today() + timedelta(days=20)).isoformat(),
                    "vendor_bill_number": f"BILL-{business_key.upper()}-00{i+1}",
                    "lines": [{
                        "description": bill["desc"],
                        "quantity": "1",
                        "unit_price": bill["amount"],
                        "expense_account_id": str(expense_account_id),
                    }],
                }
                await client.create_bill(bill_data)
                print(f"    ✓ Bill: {bill['desc'][:40]}...")
            except AtlasAPIError as e:
                print(f"    ✗ Bill failed: {e.details}")


# ============================================================================
# MAIN SEEDING FUNCTION
# ============================================================================


async def seed_organization(client: AtlasAPIClient, org: dict, business_key: str) -> None:
    """Seed a single organization with all data."""
    org_id = UUID(org["id"])
    org_name = org["name"]

    print(f"\n{'='*60}")
    print(f"Seeding: {org_name}")
    print(f"{'='*60}")

    # Switch to this organization
    await client.switch_organization(org_id)

    # 1. Set up chart of accounts
    print("\n  [Chart of Accounts]")
    account_map = await setup_chart_of_accounts(client)

    # 2. Create customers
    print("\n  [Customers]")
    await create_customers(client, business_key)

    # 3. Create vendors
    print("\n  [Vendors]")
    await create_vendors(client, business_key)

    # 4. Create bank feed account
    print("\n  [Bank Feed Account]")
    await create_bank_feed_account(client, business_key, account_map)

    # 4. Create opening balances
    print("\n  [Opening Balances]")
    await create_opening_balances(client, business_key, account_map)

    # 5. Create sample transactions
    print("\n  [Sample Transactions]")
    await create_sample_transactions(client, business_key, account_map)

    print(f"\n  ✓ {org_name} seeding complete!")


async def main():
    """Main entry point."""
    # Load environment
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

    api_url = os.environ.get("ATLAS_API_URL", "http://localhost:8000")

    print("=" * 60)
    print("Atlas Town - Database Seeding")
    print("=" * 60)
    print(f"\nAPI URL: {api_url}")

    # Step 1: Create all business accounts via signup
    print("\n" + "-" * 60)
    print("Step 1: Creating Business Accounts")
    print("-" * 60)

    business_credentials: dict[str, dict[str, Any]] = {}

    for key, biz in BUSINESSES.items():
        # Try signup first
        signup_result = await signup_business(api_url, key, biz)

        if signup_result:
            # New account created, prefer a fresh login token for switch-org
            login_result = await login_business(api_url, biz["email"])
            if login_result and login_result.get("organizations"):
                org = login_result["organizations"][0]
                business_credentials[key] = {
                    "access_token": login_result["tokens"]["access_token"],
                    "refresh_token": login_result["tokens"]["refresh_token"],
                    "organization": org,
                    "user": login_result["user"],
                }
            else:
                business_credentials[key] = {
                    "access_token": signup_result["tokens"]["access_token"],
                    "refresh_token": signup_result["tokens"]["refresh_token"],
                    "organization": signup_result["organization"],
                    "user": signup_result["user"],
                }
        else:
            # Account exists, login to get tokens
            login_result = await login_business(api_url, biz["email"])
            if login_result:
                # Use first organization (should be the one we created)
                org = login_result["organizations"][0] if login_result["organizations"] else None
                if org:
                    business_credentials[key] = {
                        "access_token": login_result["tokens"]["access_token"],
                        "refresh_token": login_result["tokens"]["refresh_token"],
                        "organization": org,
                        "user": login_result["user"],
                    }
                else:
                    print(f"  ✗ No organization found for {biz['email']}")

    if not business_credentials:
        print("\n✗ Could not create or login to any business accounts!")
        return

    print(f"\n✓ {len(business_credentials)} business account(s) ready")

    # Step 2: Seed each business
    print("\n" + "-" * 60)
    print("Step 2: Seeding Business Data")
    print("-" * 60)

    for key, creds in business_credentials.items():
        biz = BUSINESSES[key]
        org = creds["organization"]

        # Create client with the business's credentials
        client = AtlasAPIClient(
            access_token=creds["access_token"],
            refresh_token=creds["refresh_token"],
        )

        try:
            # Override the organization info from login
            client._organizations = [org]
            client._current_org_id = UUID(org["id"])

            await seed_organization(client, org, key)
        finally:
            await client.close()

    # Save credentials for simulation use
    print("\n" + "-" * 60)
    print("Step 3: Saving Simulation Configuration")
    print("-" * 60)

    # Update .env with first business credentials (for backward compatibility)
    env_file = env_path
    env_content = env_file.read_text() if env_file.exists() else ""
    env_lines = env_content.splitlines()

    # Remove old simulation credentials
    env_lines = [
        line for line in env_lines
        if not line.startswith("ATLAS_USERNAME=")
        and not line.startswith("ATLAS_PASSWORD=")
    ]

    # Add new credentials
    first_biz_key = list(business_credentials.keys())[0]
    first_biz = BUSINESSES[first_biz_key]
    env_lines.append(f"ATLAS_USERNAME={first_biz['email']}")
    env_lines.append(f"ATLAS_PASSWORD={DEFAULT_PASSWORD}")

    # Write back
    env_file.write_text("\n".join(env_lines) + "\n")
    print(f"  ✓ Updated .env with simulation credentials")

    # Also save all business credentials to a JSON file for multi-org simulation
    import json
    creds_file = Path(__file__).parent.parent / "business_credentials.json"
    creds_data = {
        key: {
            "email": BUSINESSES[key]["email"],
            "password": DEFAULT_PASSWORD,
            "organization_id": str(creds["organization"]["id"]),
            "organization_name": creds["organization"]["name"],
        }
        for key, creds in business_credentials.items()
    }
    creds_file.write_text(json.dumps(creds_data, indent=2))
    print(f"  ✓ Saved business credentials to business_credentials.json")

    print("\n" + "=" * 60)
    print("SEEDING COMPLETE!")
    print("=" * 60)
    print(f"\nCreated {len(business_credentials)} businesses:")
    for key, creds in business_credentials.items():
        print(f"  - {creds['organization']['name']}: {BUSINESSES[key]['email']}")
    print(f"\nDefault password: {DEFAULT_PASSWORD}")
    print("\nYou can now run the simulation:")
    print("  python -m atlas_town.orchestrator --run 30")


if __name__ == "__main__":
    asyncio.run(main())
