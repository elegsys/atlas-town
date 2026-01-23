"""Tool executor that bridges LLM tool calls to Atlas API."""

from typing import Any
from uuid import UUID

import structlog

from atlas_town.tools.atlas_api import AtlasAPIClient, AtlasAPIError

logger = structlog.get_logger(__name__)


class ToolExecutionError(Exception):
    """Error during tool execution."""

    def __init__(self, tool_name: str, message: str, details: Any = None):
        super().__init__(f"Tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name
        self.details = details


class ToolExecutor:
    """Executes LLM tool calls against the Atlas API."""

    def __init__(self, client: AtlasAPIClient):
        self.client = client
        self._tool_handlers: dict[str, Any] = {
            # Organization
            "switch_organization": self._switch_organization,
            # Customers
            "list_customers": self._list_customers,
            "get_customer": self._get_customer,
            "create_customer": self._create_customer,
            # Vendors
            "list_vendors": self._list_vendors,
            "get_vendor": self._get_vendor,
            "create_vendor": self._create_vendor,
            # Invoices
            "list_invoices": self._list_invoices,
            "get_invoice": self._get_invoice,
            "create_invoice": self._create_invoice,
            "send_invoice": self._send_invoice,
            "void_invoice": self._void_invoice,
            # Bills
            "list_bills": self._list_bills,
            "get_bill": self._get_bill,
            "create_bill": self._create_bill,
            "approve_bill": self._approve_bill,
            # Payments
            "list_payments": self._list_payments,
            "create_payment": self._create_payment,
            "apply_payment_to_invoice": self._apply_payment_to_invoice,
            "create_bill_payment": self._create_bill_payment,
            # Accounts
            "list_accounts": self._list_accounts,
            "get_account_balance": self._get_account_balance,
            # Journal Entries
            "list_journal_entries": self._list_journal_entries,
            "create_journal_entry": self._create_journal_entry,
            # Reports
            "get_trial_balance": self._get_trial_balance,
            "get_profit_loss": self._get_profit_loss,
            "get_balance_sheet": self._get_balance_sheet,
            "get_ar_aging": self._get_ar_aging,
            "get_ap_aging": self._get_ap_aging,
            # Bank Transactions
            "list_bank_transactions": self._list_bank_transactions,
            "categorize_bank_transaction": self._categorize_bank_transaction,
            "match_bank_transaction": self._match_bank_transaction,
        }

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call and return the result."""
        handler = self._tool_handlers.get(tool_name)
        if not handler:
            raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

        logger.info("executing_tool", tool=tool_name, args=arguments)

        try:
            result = await handler(**arguments)
            logger.info("tool_executed", tool=tool_name, success=True)
            return {"success": True, "result": result}
        except AtlasAPIError as e:
            logger.warning(
                "tool_api_error",
                tool=tool_name,
                status=e.status_code,
                details=e.details,
            )
            return {
                "success": False,
                "error": str(e),
                "status_code": e.status_code,
                "details": e.details,
            }
        except Exception as e:
            logger.exception("tool_execution_error", tool=tool_name)
            return {"success": False, "error": str(e)}

    # === Organization Handlers ===

    async def _switch_organization(self, org_id: str) -> dict[str, Any]:
        return await self.client.switch_organization(UUID(org_id))

    # === Customer Handlers ===

    async def _list_customers(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.client.list_customers(offset=offset, limit=limit)

    async def _get_customer(self, customer_id: str) -> dict[str, Any]:
        return await self.client.get_customer(UUID(customer_id))

    async def _create_customer(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_customer(data)

    # === Vendor Handlers ===

    async def _list_vendors(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.client.list_vendors(offset=offset, limit=limit)

    async def _get_vendor(self, vendor_id: str) -> dict[str, Any]:
        return await self.client.get_vendor(UUID(vendor_id))

    async def _create_vendor(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_vendor(data)

    # === Invoice Handlers ===

    async def _list_invoices(
        self, offset: int = 0, limit: int = 100, status: str | None = None
    ) -> list[dict[str, Any]]:
        return await self.client.list_invoices(offset=offset, limit=limit, status=status)

    async def _get_invoice(self, invoice_id: str) -> dict[str, Any]:
        return await self.client.get_invoice(UUID(invoice_id))

    async def _create_invoice(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_invoice(data)

    async def _send_invoice(self, invoice_id: str) -> dict[str, Any]:
        return await self.client.send_invoice(UUID(invoice_id))

    async def _void_invoice(self, invoice_id: str, reason: str) -> dict[str, Any]:
        return await self.client.void_invoice(UUID(invoice_id), reason)

    # === Bill Handlers ===

    async def _list_bills(
        self, offset: int = 0, limit: int = 100, status: str | None = None
    ) -> list[dict[str, Any]]:
        return await self.client.list_bills(offset=offset, limit=limit, status=status)

    async def _get_bill(self, bill_id: str) -> dict[str, Any]:
        return await self.client.get_bill(UUID(bill_id))

    async def _create_bill(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_bill(data)

    async def _approve_bill(self, bill_id: str) -> dict[str, Any]:
        return await self.client.approve_bill(UUID(bill_id))

    # === Payment Handlers ===

    async def _list_payments(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.client.list_payments(offset=offset, limit=limit)

    async def _create_payment(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_payment(data)

    async def _apply_payment_to_invoice(
        self, payment_id: str, invoice_id: str, amount: str
    ) -> dict[str, Any]:
        return await self.client.apply_payment_to_invoice(
            UUID(payment_id), UUID(invoice_id), amount
        )

    async def _create_bill_payment(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_bill_payment(data)

    # === Account Handlers ===

    async def _list_accounts(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.client.list_accounts(offset=offset, limit=limit)

    async def _get_account_balance(self, account_id: str) -> dict[str, Any]:
        return await self.client.get_account_balance(UUID(account_id))

    # === Journal Entry Handlers ===

    async def _list_journal_entries(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.client.list_journal_entries(offset=offset, limit=limit)

    async def _create_journal_entry(self, **data: Any) -> dict[str, Any]:
        return await self.client.create_journal_entry(data)

    # === Report Handlers ===

    async def _get_trial_balance(
        self, as_of_date: str | None = None
    ) -> dict[str, Any]:
        return await self.client.get_trial_balance(as_of_date)

    async def _get_profit_loss(
        self, period_start: str, period_end: str
    ) -> dict[str, Any]:
        return await self.client.get_profit_loss(period_start, period_end)

    async def _get_balance_sheet(self, as_of_date: str) -> dict[str, Any]:
        return await self.client.get_balance_sheet(as_of_date)

    async def _get_ar_aging(self) -> dict[str, Any]:
        return await self.client.get_ar_aging()

    async def _get_ap_aging(self) -> dict[str, Any]:
        return await self.client.get_ap_aging()

    # === Bank Transaction Handlers ===

    async def _list_bank_transactions(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self.client.list_bank_transactions(offset=offset, limit=limit)

    async def _categorize_bank_transaction(
        self, transaction_id: str, account_id: str
    ) -> dict[str, Any]:
        return await self.client.categorize_bank_transaction(
            UUID(transaction_id), UUID(account_id)
        )

    async def _match_bank_transaction(
        self, transaction_id: str, match_id: str, match_type: str
    ) -> dict[str, Any]:
        return await self.client.match_bank_transaction(
            UUID(transaction_id), UUID(match_id), match_type
        )
