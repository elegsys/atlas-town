"""Tool definitions for LLM function calling with Atlas API.

These schemas define the tools available to AI agents for interacting with
the Atlas accounting system. Each tool maps to one or more Atlas API endpoints.
"""

from typing import Any

# === Customer Tools ===

LIST_CUSTOMERS_TOOL: dict[str, Any] = {
    "name": "list_customers",
    "description": "List all customers for the current organization. Returns customer names, contact info, and balances.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skip": {
                "type": "integer",
                "description": "Number of records to skip for pagination",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of records to return",
                "default": 100,
            },
        },
        "required": [],
    },
}

GET_CUSTOMER_TOOL: dict[str, Any] = {
    "name": "get_customer",
    "description": "Get detailed information about a specific customer by their ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "format": "uuid",
                "description": "The unique identifier of the customer",
            },
        },
        "required": ["customer_id"],
    },
}

CREATE_CUSTOMER_TOOL: dict[str, Any] = {
    "name": "create_customer",
    "description": "Create a new customer record. Customers are people or businesses that owe you money.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Customer's full name or business name",
            },
            "email": {
                "type": "string",
                "format": "email",
                "description": "Customer's email address",
            },
            "phone": {
                "type": "string",
                "description": "Customer's phone number",
            },
            "billing_address": {
                "type": "object",
                "description": "Customer's billing address",
                "properties": {
                    "line1": {"type": "string"},
                    "line2": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "postal_code": {"type": "string"},
                    "country": {"type": "string", "default": "US"},
                },
            },
        },
        "required": ["name"],
    },
}

# === Vendor Tools ===

LIST_VENDORS_TOOL: dict[str, Any] = {
    "name": "list_vendors",
    "description": "List all vendors for the current organization. Vendors are people or businesses you owe money to.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skip": {
                "type": "integer",
                "description": "Number of records to skip",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records to return",
                "default": 100,
            },
        },
        "required": [],
    },
}

GET_VENDOR_TOOL: dict[str, Any] = {
    "name": "get_vendor",
    "description": "Get detailed information about a specific vendor.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_id": {
                "type": "string",
                "format": "uuid",
                "description": "The unique identifier of the vendor",
            },
        },
        "required": ["vendor_id"],
    },
}

CREATE_VENDOR_TOOL: dict[str, Any] = {
    "name": "create_vendor",
    "description": "Create a new vendor record.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Vendor's name or business name",
            },
            "email": {
                "type": "string",
                "format": "email",
                "description": "Vendor's email address",
            },
            "phone": {
                "type": "string",
                "description": "Vendor's phone number",
            },
        },
        "required": ["name"],
    },
}

# === Invoice Tools ===

LIST_INVOICES_TOOL: dict[str, Any] = {
    "name": "list_invoices",
    "description": "List invoices for the current organization. Invoices represent money owed TO you by customers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["draft", "sent", "viewed", "partial", "paid", "overdue", "voided"],
                "description": "Filter by invoice status",
            },
            "skip": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 100},
        },
        "required": [],
    },
}

GET_INVOICE_TOOL: dict[str, Any] = {
    "name": "get_invoice",
    "description": "Get detailed information about a specific invoice including line items.",
    "input_schema": {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "string",
                "format": "uuid",
                "description": "The invoice ID",
            },
        },
        "required": ["invoice_id"],
    },
}

CREATE_INVOICE_TOOL: dict[str, Any] = {
    "name": "create_invoice",
    "description": "Create a new invoice for a customer. This records revenue and creates an accounts receivable entry.",
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "format": "uuid",
                "description": "The customer being invoiced",
            },
            "invoice_date": {
                "type": "string",
                "format": "date",
                "description": "Invoice date (YYYY-MM-DD)",
            },
            "due_date": {
                "type": "string",
                "format": "date",
                "description": "Payment due date (YYYY-MM-DD)",
            },
            "lines": {
                "type": "array",
                "description": "Invoice line items",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Description of the product or service",
                        },
                        "quantity": {
                            "type": "number",
                            "description": "Quantity",
                        },
                        "unit_price": {
                            "type": "string",
                            "description": "Price per unit as decimal string (e.g., '100.00')",
                        },
                        "account_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Revenue account ID",
                        },
                    },
                    "required": ["description", "quantity", "unit_price"],
                },
                "minItems": 1,
            },
            "notes": {
                "type": "string",
                "description": "Notes to include on the invoice",
            },
        },
        "required": ["customer_id", "invoice_date", "lines"],
    },
}

SEND_INVOICE_TOOL: dict[str, Any] = {
    "name": "send_invoice",
    "description": "Mark an invoice as sent to the customer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "string",
                "format": "uuid",
                "description": "The invoice to send",
            },
        },
        "required": ["invoice_id"],
    },
}

VOID_INVOICE_TOOL: dict[str, Any] = {
    "name": "void_invoice",
    "description": "Void an invoice. This reverses the journal entry and marks the invoice as voided.",
    "input_schema": {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "string",
                "format": "uuid",
                "description": "The invoice to void",
            },
            "reason": {
                "type": "string",
                "description": "Reason for voiding the invoice",
            },
        },
        "required": ["invoice_id", "reason"],
    },
}

# === Bill Tools ===

LIST_BILLS_TOOL: dict[str, Any] = {
    "name": "list_bills",
    "description": "List bills for the current organization. Bills represent money YOU owe to vendors.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["draft", "pending", "approved", "partial", "paid", "overdue", "voided"],
                "description": "Filter by bill status",
            },
            "skip": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 100},
        },
        "required": [],
    },
}

GET_BILL_TOOL: dict[str, Any] = {
    "name": "get_bill",
    "description": "Get detailed information about a specific bill.",
    "input_schema": {
        "type": "object",
        "properties": {
            "bill_id": {
                "type": "string",
                "format": "uuid",
                "description": "The bill ID",
            },
        },
        "required": ["bill_id"],
    },
}

CREATE_BILL_TOOL: dict[str, Any] = {
    "name": "create_bill",
    "description": "Create a new bill from a vendor. This records an expense and creates an accounts payable entry.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_id": {
                "type": "string",
                "format": "uuid",
                "description": "The vendor this bill is from",
            },
            "bill_date": {
                "type": "string",
                "format": "date",
                "description": "Bill date (YYYY-MM-DD)",
            },
            "due_date": {
                "type": "string",
                "format": "date",
                "description": "Payment due date",
            },
            "bill_number": {
                "type": "string",
                "description": "Vendor's invoice/bill number",
            },
            "lines": {
                "type": "array",
                "description": "Bill line items",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": {"type": "string"},
                        "account_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Expense account ID",
                        },
                    },
                    "required": ["description", "quantity", "unit_price"],
                },
                "minItems": 1,
            },
        },
        "required": ["vendor_id", "bill_date", "lines"],
    },
}

APPROVE_BILL_TOOL: dict[str, Any] = {
    "name": "approve_bill",
    "description": "Approve a bill for payment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "bill_id": {
                "type": "string",
                "format": "uuid",
                "description": "The bill to approve",
            },
        },
        "required": ["bill_id"],
    },
}

# === Payment Tools ===

LIST_PAYMENTS_TOOL: dict[str, Any] = {
    "name": "list_payments",
    "description": "List customer payments received.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skip": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 100},
        },
        "required": [],
    },
}

CREATE_PAYMENT_TOOL: dict[str, Any] = {
    "name": "create_payment",
    "description": "Record a payment received from a customer. This increases cash and reduces accounts receivable.",
    "input_schema": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "format": "uuid",
                "description": "The customer making the payment",
            },
            "payment_date": {
                "type": "string",
                "format": "date",
                "description": "Date payment was received",
            },
            "amount": {
                "type": "string",
                "description": "Payment amount as decimal string",
            },
            "payment_method": {
                "type": "string",
                "enum": ["cash", "check", "credit_card", "bank_transfer", "other"],
                "description": "How the payment was made",
            },
            "reference_number": {
                "type": "string",
                "description": "Check number or transaction reference",
            },
            "deposit_account_id": {
                "type": "string",
                "format": "uuid",
                "description": "Bank account to deposit into",
            },
        },
        "required": ["customer_id", "payment_date", "amount"],
    },
}

APPLY_PAYMENT_TOOL: dict[str, Any] = {
    "name": "apply_payment_to_invoice",
    "description": "Apply a payment to a specific invoice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "payment_id": {
                "type": "string",
                "format": "uuid",
                "description": "The payment to apply",
            },
            "invoice_id": {
                "type": "string",
                "format": "uuid",
                "description": "The invoice to apply payment to",
            },
            "amount": {
                "type": "string",
                "description": "Amount to apply",
            },
        },
        "required": ["payment_id", "invoice_id", "amount"],
    },
}

# === Bill Payment Tools ===

CREATE_BILL_PAYMENT_TOOL: dict[str, Any] = {
    "name": "create_bill_payment",
    "description": "Record a payment made to a vendor. This decreases cash and reduces accounts payable.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_id": {
                "type": "string",
                "format": "uuid",
                "description": "The vendor being paid",
            },
            "payment_date": {
                "type": "string",
                "format": "date",
                "description": "Date payment was made",
            },
            "amount": {
                "type": "string",
                "description": "Payment amount",
            },
            "payment_method": {
                "type": "string",
                "enum": ["check", "bank_transfer", "credit_card", "other"],
            },
            "payment_account_id": {
                "type": "string",
                "format": "uuid",
                "description": "Bank account to pay from",
            },
            "bill_applications": {
                "type": "array",
                "description": "Bills to apply this payment to",
                "items": {
                    "type": "object",
                    "properties": {
                        "bill_id": {"type": "string", "format": "uuid"},
                        "amount": {"type": "string"},
                    },
                    "required": ["bill_id", "amount"],
                },
            },
        },
        "required": ["vendor_id", "payment_date", "amount"],
    },
}

# === Account Tools ===

LIST_ACCOUNTS_TOOL: dict[str, Any] = {
    "name": "list_accounts",
    "description": "List all accounts in the chart of accounts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skip": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 100},
        },
        "required": [],
    },
}

GET_ACCOUNT_BALANCE_TOOL: dict[str, Any] = {
    "name": "get_account_balance",
    "description": "Get the current balance of a specific account.",
    "input_schema": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "format": "uuid",
                "description": "The account ID",
            },
        },
        "required": ["account_id"],
    },
}

# === Journal Entry Tools ===

LIST_JOURNAL_ENTRIES_TOOL: dict[str, Any] = {
    "name": "list_journal_entries",
    "description": "List journal entries. Journal entries are the fundamental accounting records that affect account balances.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skip": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 100},
        },
        "required": [],
    },
}

CREATE_JOURNAL_ENTRY_TOOL: dict[str, Any] = {
    "name": "create_journal_entry",
    "description": "Create a manual journal entry. Debits must equal credits. Use for adjustments, corrections, or complex transactions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entry_date": {
                "type": "string",
                "format": "date",
                "description": "Date of the entry",
            },
            "memo": {
                "type": "string",
                "description": "Description of the journal entry",
            },
            "lines": {
                "type": "array",
                "description": "Debit and credit lines (must balance)",
                "items": {
                    "type": "object",
                    "properties": {
                        "account_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Account to affect",
                        },
                        "debit": {
                            "type": "string",
                            "description": "Debit amount (use either debit or credit, not both)",
                        },
                        "credit": {
                            "type": "string",
                            "description": "Credit amount",
                        },
                        "memo": {
                            "type": "string",
                            "description": "Line memo",
                        },
                    },
                    "required": ["account_id"],
                },
                "minItems": 2,
            },
        },
        "required": ["entry_date", "lines"],
    },
}

# === Report Tools ===

GET_TRIAL_BALANCE_TOOL: dict[str, Any] = {
    "name": "get_trial_balance",
    "description": "Get the trial balance report showing all account balances. Useful for verifying books are balanced.",
    "input_schema": {
        "type": "object",
        "properties": {
            "as_of_date": {
                "type": "string",
                "format": "date",
                "description": "Get balances as of this date (default: today)",
            },
        },
        "required": [],
    },
}

GET_PROFIT_LOSS_TOOL: dict[str, Any] = {
    "name": "get_profit_loss",
    "description": "Get the Profit & Loss (Income Statement) report for a date range.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "format": "date",
                "description": "Start of period",
            },
            "end_date": {
                "type": "string",
                "format": "date",
                "description": "End of period",
            },
        },
        "required": ["start_date", "end_date"],
    },
}

GET_BALANCE_SHEET_TOOL: dict[str, Any] = {
    "name": "get_balance_sheet",
    "description": "Get the Balance Sheet report showing assets, liabilities, and equity.",
    "input_schema": {
        "type": "object",
        "properties": {
            "as_of_date": {
                "type": "string",
                "format": "date",
                "description": "Get balance sheet as of this date",
            },
        },
        "required": ["as_of_date"],
    },
}

GET_AR_AGING_TOOL: dict[str, Any] = {
    "name": "get_ar_aging",
    "description": "Get the Accounts Receivable aging report showing who owes you money and how long overdue.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

GET_AP_AGING_TOOL: dict[str, Any] = {
    "name": "get_ap_aging",
    "description": "Get the Accounts Payable aging report showing who you owe money to and due dates.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

# === Bank Transaction Tools ===

LIST_BANK_TRANSACTIONS_TOOL: dict[str, Any] = {
    "name": "list_bank_transactions",
    "description": "List imported bank transactions that need categorization or matching.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skip": {"type": "integer", "default": 0},
            "limit": {"type": "integer", "default": 100},
        },
        "required": [],
    },
}

CATEGORIZE_BANK_TRANSACTION_TOOL: dict[str, Any] = {
    "name": "categorize_bank_transaction",
    "description": "Categorize a bank transaction to an expense or income account.",
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {
                "type": "string",
                "format": "uuid",
                "description": "Bank transaction ID",
            },
            "account_id": {
                "type": "string",
                "format": "uuid",
                "description": "Account to categorize to",
            },
        },
        "required": ["transaction_id", "account_id"],
    },
}

MATCH_BANK_TRANSACTION_TOOL: dict[str, Any] = {
    "name": "match_bank_transaction",
    "description": "Match a bank transaction to an existing invoice, bill, or payment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {
                "type": "string",
                "format": "uuid",
                "description": "Bank transaction ID",
            },
            "match_id": {
                "type": "string",
                "format": "uuid",
                "description": "ID of invoice, bill, or payment to match",
            },
            "match_type": {
                "type": "string",
                "enum": ["invoice", "bill", "payment", "bill_payment"],
                "description": "Type of record to match",
            },
        },
        "required": ["transaction_id", "match_id", "match_type"],
    },
}

# === Organization Context Tool ===

SWITCH_ORGANIZATION_TOOL: dict[str, Any] = {
    "name": "switch_organization",
    "description": "Switch to a different organization context. Use this when you need to work on a different business's books.",
    "input_schema": {
        "type": "object",
        "properties": {
            "org_id": {
                "type": "string",
                "format": "uuid",
                "description": "Organization ID to switch to",
            },
        },
        "required": ["org_id"],
    },
}

# === Tool Collections ===

ACCOUNTANT_TOOLS: list[dict[str, Any]] = [
    # Organization
    SWITCH_ORGANIZATION_TOOL,
    # Customers & Vendors
    LIST_CUSTOMERS_TOOL,
    GET_CUSTOMER_TOOL,
    CREATE_CUSTOMER_TOOL,
    LIST_VENDORS_TOOL,
    GET_VENDOR_TOOL,
    CREATE_VENDOR_TOOL,
    # Invoices & Bills
    LIST_INVOICES_TOOL,
    GET_INVOICE_TOOL,
    CREATE_INVOICE_TOOL,
    SEND_INVOICE_TOOL,
    VOID_INVOICE_TOOL,
    LIST_BILLS_TOOL,
    GET_BILL_TOOL,
    CREATE_BILL_TOOL,
    APPROVE_BILL_TOOL,
    # Payments
    LIST_PAYMENTS_TOOL,
    CREATE_PAYMENT_TOOL,
    APPLY_PAYMENT_TOOL,
    CREATE_BILL_PAYMENT_TOOL,
    # Accounts & Journal Entries
    LIST_ACCOUNTS_TOOL,
    GET_ACCOUNT_BALANCE_TOOL,
    LIST_JOURNAL_ENTRIES_TOOL,
    CREATE_JOURNAL_ENTRY_TOOL,
    # Reports
    GET_TRIAL_BALANCE_TOOL,
    GET_PROFIT_LOSS_TOOL,
    GET_BALANCE_SHEET_TOOL,
    GET_AR_AGING_TOOL,
    GET_AP_AGING_TOOL,
    # Bank Transactions
    LIST_BANK_TRANSACTIONS_TOOL,
    CATEGORIZE_BANK_TRANSACTION_TOOL,
    MATCH_BANK_TRANSACTION_TOOL,
]

OWNER_TOOLS: list[dict[str, Any]] = [
    # Read-only access to their business
    LIST_CUSTOMERS_TOOL,
    GET_CUSTOMER_TOOL,
    LIST_VENDORS_TOOL,
    LIST_INVOICES_TOOL,
    GET_INVOICE_TOOL,
    LIST_BILLS_TOOL,
    GET_BILL_TOOL,
    LIST_PAYMENTS_TOOL,
    GET_TRIAL_BALANCE_TOOL,
    GET_PROFIT_LOSS_TOOL,
    GET_BALANCE_SHEET_TOOL,
    GET_AR_AGING_TOOL,
    GET_AP_AGING_TOOL,
]

# All available tools
ALL_TOOLS: list[dict[str, Any]] = ACCOUNTANT_TOOLS
