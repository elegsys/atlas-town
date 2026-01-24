"""Atlas API client with JWT authentication and automatic token refresh."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import httpx
import structlog

from atlas_town.config import get_settings

logger = structlog.get_logger(__name__)


class AtlasAPIError(Exception):
    """Base exception for Atlas API errors."""

    def __init__(self, message: str, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AuthenticationError(AtlasAPIError):
    """Authentication failed."""

    pass


class RateLimitError(AtlasAPIError):
    """Rate limit exceeded."""

    pass


class AtlasAPIClient:
    """Async client for Atlas API with JWT authentication."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.atlas_api_url).rstrip("/")
        self._username = username or settings.atlas_username
        self._password = password or settings.atlas_password.get_secret_value()
        self._timeout = settings.atlas_timeout
        self._max_retries = settings.atlas_max_retries

        # Allow pre-populated tokens (from signup/login)
        self._access_token: str | None = access_token
        self._refresh_token: str | None = refresh_token
        self._token_expires_at: datetime | None = None
        if access_token:
            # Assume token is fresh, set expiry to 55 minutes from now
            self._token_expires_at = datetime.now(UTC) + timedelta(minutes=55)

        self._current_org_id: UUID | None = None
        self._current_company_id: UUID | None = None
        self._organizations: list[dict[str, Any]] = []

        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AtlasAPIClient":
        await self.login()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # === Authentication ===

    async def login(self) -> dict[str, Any]:
        """Authenticate and get JWT tokens."""
        client = await self._get_client()

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": self._username, "password": self._password},
        )

        if response.status_code == 401:
            raise AuthenticationError("Invalid credentials", status_code=401)
        response.raise_for_status()

        data_raw = response.json()
        if not isinstance(data_raw, dict):
            raise AtlasAPIError("Invalid switch-org response format")
        data = cast(dict[str, Any], data_raw)
        if not isinstance(data, dict):
            raise AtlasAPIError("Invalid login response format")
        self._access_token = data["tokens"]["access_token"]
        self._refresh_token = data["tokens"]["refresh_token"]
        self._organizations = data.get("organizations", [])

        # Set default org if available
        if self._organizations and not self._current_org_id:
            self._current_org_id = UUID(self._organizations[0]["id"])

        # Estimate token expiry (Atlas uses 60min access tokens, refresh at 55min)
        self._token_expires_at = datetime.now(UTC) + timedelta(minutes=55)

        logger.info(
            "logged_in",
            user=data["user"]["email"],
            org_count=len(self._organizations),
        )

        # Fetch default company for the organization
        await self._fetch_default_company()

        return data

    async def refresh_tokens(self) -> None:
        """Refresh the access token."""
        if not self._refresh_token:
            raise AuthenticationError("No refresh token available")

        client = await self._get_client()
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": self._refresh_token},
        )

        if response.status_code == 401:
            # Refresh token expired, need full re-login
            await self.login()
            return

        response.raise_for_status()
        data_raw = response.json()
        if not isinstance(data_raw, dict):
            raise AtlasAPIError("Invalid switch-org response format")
        data = cast(dict[str, Any], data_raw)
        if not isinstance(data, dict):
            raise AtlasAPIError("Invalid switch-org response format")
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._token_expires_at = datetime.now(UTC) + timedelta(minutes=55)
        logger.debug("tokens_refreshed")

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid access token."""
        async with self._lock:
            if not self._access_token:
                await self.login()
            elif self._token_expires_at and datetime.now(UTC) >= self._token_expires_at:
                await self.refresh_tokens()

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with auth token."""
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def switch_organization(self, org_id: UUID) -> dict[str, Any]:
        """Switch to a different organization context."""
        if self._current_org_id == org_id and self._current_company_id:
            logger.info("organization_already_selected", org_id=str(org_id))
            return {
                "access_token": self._access_token or "",
                "organization": {"id": str(org_id)},
            }

        await self._ensure_authenticated()
        client = await self._get_client()

        response = await client.post(
            "/api/v1/auth/switch-org",
            json={"org_id": str(org_id)},
            headers=self._get_headers(),
        )
        response.raise_for_status()

        data_raw = response.json()
        if not isinstance(data_raw, dict):
            raise AtlasAPIError("Invalid switch-org response format")
        data = cast(dict[str, Any], data_raw)
        # switch-org returns flat access_token, not nested under "tokens"
        self._access_token = data.get("access_token") or data.get("tokens", {}).get("access_token")
        # switch-org doesn't return refresh_token, keep the existing one
        self._current_org_id = org_id
        if self._access_token:
            self._token_expires_at = datetime.now(UTC) + timedelta(minutes=55)

        # Fetch default company for the new organization
        await self._fetch_default_company()

        logger.info("switched_organization", org_id=str(org_id))
        return data

    @property
    def current_org_id(self) -> UUID | None:
        """Get current organization ID."""
        return self._current_org_id

    @property
    def current_company_id(self) -> UUID | None:
        """Get current company ID."""
        return self._current_company_id

    @property
    def organizations(self) -> list[dict[str, Any]]:
        """Get list of available organizations."""
        return self._organizations

    async def get_organization(self, org_id: UUID) -> dict[str, Any]:
        """Get organization details by ID."""
        for org in self._organizations:
            if org.get("id") == str(org_id):
                return org

        result = await self.get(f"/api/v1/organizations/{org_id}")
        return result if isinstance(result, dict) else {}

    async def _fetch_default_company(self) -> None:
        """Fetch and set the default company for the current organization."""
        try:
            # Use _request_raw to bypass company_id injection (we don't have it yet)
            await self._ensure_authenticated()
            client = await self._get_client()
            response = await client.get(
                "/api/v1/companies/",
                headers=self._get_headers(),
            )

            # Handle 401 by refreshing and retrying once
            if response.status_code == 401:
                await self.refresh_tokens()
                response = await client.get(
                    "/api/v1/companies/",
                    headers=self._get_headers(),
                )

            if response.status_code == 200:
                companies_raw = response.json()
                companies = self._extract_items(companies_raw)
                if companies:
                    self._current_company_id = UUID(companies[0]["id"])
                    logger.info("company_set", company_id=str(self._current_company_id))
                else:
                    logger.warning("no_companies_found", org_id=str(self._current_org_id))
            else:
                logger.warning(
                    "fetch_company_failed",
                    status_code=response.status_code,
                    org_id=str(self._current_org_id),
                )
        except Exception as e:
            logger.warning("fetch_company_error", error=str(e))

    # === Generic Request Methods ===

    # Paths that require company_id parameter
    _COMPANY_SCOPED_PATHS = (
        "/api/v1/customers",
        "/api/v1/vendors",
        "/api/v1/invoices",
        "/api/v1/bills",
        "/api/v1/payments",
        "/api/v1/accounts",
        "/api/v1/journal-entries",
        "/api/v1/bank-transactions",
        "/api/v1/reports",
    )

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make an authenticated API request with retry logic."""
        await self._ensure_authenticated()
        client = await self._get_client()

        # Auto-inject company_id for scoped endpoints
        if self._current_company_id and any(path.startswith(p) for p in self._COMPANY_SCOPED_PATHS):
            params = params or {}
            if "company_id" not in params:
                params["company_id"] = str(self._current_company_id)

        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                json=json,
                headers=self._get_headers(),
            )

            if response.status_code == 401 and retry_count < 1:
                # Token expired during request, refresh and retry
                await self.refresh_tokens()
                return await self._request(method, path, params, json, retry_count + 1)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise RateLimitError(
                    f"Rate limited, retry after {retry_after}s",
                    status_code=429,
                    details={"retry_after": retry_after},
                )

            if response.status_code >= 400:
                try:
                    error_detail = response.json() if response.content else {}
                except Exception:
                    error_detail = {
                        "raw": response.text[:500]
                        if response.text
                        else "empty response"
                    }
                raise AtlasAPIError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code,
                    details=error_detail,
                )

            return response.json() if response.content else {}

        except httpx.RequestError as e:
            if retry_count < self._max_retries:
                await asyncio.sleep(2**retry_count)  # Exponential backoff
                return await self._request(method, path, params, json, retry_count + 1)
            raise AtlasAPIError(f"Request failed: {e}") from e

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make GET request."""
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make POST request."""
        return await self._request("POST", path, params=params, json=json)

    async def put(
        self, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make PUT request."""
        return await self._request("PUT", path, json=json)

    async def patch(
        self, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make PATCH request."""
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Make DELETE request."""
        return await self._request("DELETE", path)

    # === Customer Endpoints ===

    @staticmethod
    def _clamp_limit(limit: int) -> int:
        return min(max(limit, 1), 500)

    @staticmethod
    def _extract_items(result: Any) -> list[dict[str, Any]]:
        """Return list of items from a list or paged response."""
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            items = result.get("items")
            if isinstance(items, list):
                return items
        return []

    async def list_customers(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List customers for current organization."""
        result = await self.get(
            "/api/v1/customers/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def get_customer(self, customer_id: UUID) -> dict[str, Any]:
        """Get customer by ID."""
        result = await self.get(f"/api/v1/customers/{customer_id}")
        return result if isinstance(result, dict) else {}

    async def create_customer(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new customer."""
        result = await self.post("/api/v1/customers/", json=data)
        return result if isinstance(result, dict) else {}

    async def update_customer(
        self, customer_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a customer."""
        result = await self.patch(f"/api/v1/customers/{customer_id}", json=data)
        return result if isinstance(result, dict) else {}

    # === Vendor Endpoints ===

    async def list_vendors(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List vendors for current organization."""
        result = await self.get(
            "/api/v1/vendors/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def get_vendor(self, vendor_id: UUID) -> dict[str, Any]:
        """Get vendor by ID."""
        result = await self.get(f"/api/v1/vendors/{vendor_id}")
        return result if isinstance(result, dict) else {}

    async def create_vendor(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new vendor."""
        result = await self.post("/api/v1/vendors/", json=data)
        return result if isinstance(result, dict) else {}

    # === Invoice Endpoints ===

    async def list_invoices(
        self, offset: int = 0, limit: int = 100, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List invoices for current organization."""
        params: dict[str, Any] = {"offset": offset, "limit": self._clamp_limit(limit)}
        if status:
            params["status"] = status
        result = await self.get("/api/v1/invoices/", params=params)
        return self._extract_items(result)

    async def get_invoice(self, invoice_id: UUID) -> dict[str, Any]:
        """Get invoice by ID."""
        result = await self.get(f"/api/v1/invoices/{invoice_id}")
        return result if isinstance(result, dict) else {}

    async def create_invoice(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new invoice."""
        result = await self.post("/api/v1/invoices/", json=data)
        return result if isinstance(result, dict) else {}

    async def send_invoice(
        self, invoice_id: UUID, ar_account_id: UUID
    ) -> dict[str, Any]:
        """Mark invoice as sent and create AR journal entry."""
        result = await self.post(
            f"/api/v1/invoices/{invoice_id}/send",
            params={"ar_account_id": str(ar_account_id)},
        )
        return result if isinstance(result, dict) else {}

    async def void_invoice(self, invoice_id: UUID, reason: str) -> dict[str, Any]:
        """Void an invoice."""
        result = await self.post(
            f"/api/v1/invoices/{invoice_id}/void", json={"reason": reason}
        )
        return result if isinstance(result, dict) else {}

    # === Bill Endpoints ===

    async def list_bills(
        self, offset: int = 0, limit: int = 100, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List bills for current organization."""
        params: dict[str, Any] = {"offset": offset, "limit": self._clamp_limit(limit)}
        if status:
            params["status"] = status
        result = await self.get("/api/v1/bills/", params=params)
        return self._extract_items(result)

    async def get_bill(self, bill_id: UUID) -> dict[str, Any]:
        """Get bill by ID."""
        result = await self.get(f"/api/v1/bills/{bill_id}")
        return result if isinstance(result, dict) else {}

    async def create_bill(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new bill."""
        result = await self.post("/api/v1/bills/", json=data)
        return result if isinstance(result, dict) else {}

    async def approve_bill(self, bill_id: UUID) -> dict[str, Any]:
        """Approve a bill for payment."""
        result = await self.post(f"/api/v1/bills/{bill_id}/approve")
        return result if isinstance(result, dict) else {}

    # === Payment Endpoints ===

    async def list_payments(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List payments for current organization."""
        result = await self.get(
            "/api/v1/payments/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def create_payment(
        self, data: dict[str, Any], ar_account_id: UUID
    ) -> dict[str, Any]:
        """Create a payment (receive money from customer)."""
        result = await self.post(
            "/api/v1/payments/",
            json=data,
            params={"ar_account_id": str(ar_account_id)},
        )
        return result if isinstance(result, dict) else {}

    async def apply_payment_to_invoice(
        self, payment_id: UUID, invoice_id: UUID, amount: str
    ) -> dict[str, Any]:
        """Apply payment to an invoice."""
        result = await self.post(
            f"/api/v1/payments/{payment_id}/apply",
            json={"invoice_id": str(invoice_id), "amount": amount},
        )
        return result if isinstance(result, dict) else {}

    # === Bill Payment Endpoints ===

    async def list_bill_payments(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List bill payments for current organization."""
        result = await self.get(
            "/api/v1/bill-payments/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def create_bill_payment(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a bill payment (pay vendor)."""
        result = await self.post("/api/v1/bill-payments/", json=data)
        return result if isinstance(result, dict) else {}

    # === Account Endpoints ===

    async def list_accounts(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List chart of accounts."""
        result = await self.get(
            "/api/v1/accounts/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def get_account(self, account_id: UUID) -> dict[str, Any]:
        """Get account by ID."""
        result = await self.get(f"/api/v1/accounts/{account_id}")
        return result if isinstance(result, dict) else {}

    async def get_account_balance(self, account_id: UUID) -> dict[str, Any]:
        """Get account balance."""
        result = await self.get(f"/api/v1/accounts/{account_id}/balance")
        return result if isinstance(result, dict) else {}

    # === Journal Entry Endpoints ===

    async def list_journal_entries(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List journal entries."""
        result = await self.get(
            "/api/v1/journal-entries/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def create_journal_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a journal entry."""
        result = await self.post("/api/v1/journal-entries/", json=data)
        return result if isinstance(result, dict) else {}

    # === Report Endpoints ===

    async def get_trial_balance(
        self, as_of_date: str | None = None
    ) -> dict[str, Any]:
        """Get trial balance report."""
        params = {"as_of_date": as_of_date} if as_of_date else {}
        result = await self.get("/api/v1/reports/trial-balance", params=params)
        return result if isinstance(result, dict) else {}

    async def get_profit_loss(
        self, period_start: str, period_end: str
    ) -> dict[str, Any]:
        """Get profit and loss report."""
        result = await self.get(
            "/api/v1/reports/profit-loss",
            params={"period_start": period_start, "period_end": period_end},
        )
        return result if isinstance(result, dict) else {}

    async def get_balance_sheet(self, as_of_date: str) -> dict[str, Any]:
        """Get balance sheet report."""
        result = await self.get(
            "/api/v1/reports/balance-sheet", params={"as_of_date": as_of_date}
        )
        return result if isinstance(result, dict) else {}

    async def get_ar_aging(self) -> dict[str, Any]:
        """Get accounts receivable aging report."""
        result = await self.get("/api/v1/reports/ar-aging")
        return result if isinstance(result, dict) else {}

    async def get_ap_aging(self) -> dict[str, Any]:
        """Get accounts payable aging report."""
        result = await self.get("/api/v1/reports/ap-aging")
        return result if isinstance(result, dict) else {}

    # === Tax Form Endpoints ===

    async def list_tax_years(
        self,
        company_id: UUID,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List tax years for a company."""
        params: dict[str, Any] = {"company_id": str(company_id)}
        if status_filter:
            params["status_filter"] = status_filter
        result = await self.get("/api/v1/tax-forms/tax-years/", params=params)
        return self._extract_items(result)

    async def create_tax_year(
        self,
        company_id: UUID,
        year: int,
        threshold_override: str | None = None,
    ) -> dict[str, Any]:
        """Create a tax year for a company."""
        payload: dict[str, Any] = {"company_id": str(company_id), "year": year}
        if threshold_override is not None:
            payload["threshold_override"] = threshold_override
        result = await self.post("/api/v1/tax-forms/tax-years/", json=payload)
        return result if isinstance(result, dict) else {}

    async def get_tax_year(self, tax_year_id: UUID) -> dict[str, Any]:
        """Get tax year details by ID."""
        result = await self.get(f"/api/v1/tax-forms/tax-years/{tax_year_id}")
        return result if isinstance(result, dict) else {}

    async def list_quarterly_estimates(
        self,
        tax_year_id: UUID,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List quarterly estimates for a tax year."""
        params: dict[str, Any] = {"tax_year_id": str(tax_year_id)}
        if status_filter:
            params["status_filter"] = status_filter
        result = await self.get(
            "/api/v1/tax-forms/quarterly-estimates/",
            params=params,
        )
        return self._extract_items(result)

    async def create_quarterly_estimate(
        self,
        tax_year_id: UUID,
        quarter: int,
        estimated_income: str,
        prior_year_tax: str | None = None,
        prior_year_agi: str | None = None,
    ) -> dict[str, Any]:
        """Create a quarterly estimate for a tax year."""
        payload: dict[str, Any] = {
            "tax_year_id": str(tax_year_id),
            "quarter": quarter,
            "estimated_income": estimated_income,
        }
        if prior_year_tax is not None:
            payload["prior_year_tax"] = prior_year_tax
        if prior_year_agi is not None:
            payload["prior_year_agi"] = prior_year_agi
        result = await self.post(
            "/api/v1/tax-forms/quarterly-estimates/calculate",
            json=payload,
        )
        return result if isinstance(result, dict) else {}

    async def update_quarterly_estimate(
        self,
        estimate_id: UUID,
        estimated_income: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update a quarterly estimate."""
        payload: dict[str, Any] = {}
        if estimated_income is not None:
            payload["estimated_income"] = estimated_income
        if status is not None:
            payload["status"] = status
        result = await self.put(
            f"/api/v1/tax-forms/quarterly-estimates/{estimate_id}",
            json=payload,
        )
        return result if isinstance(result, dict) else {}

    async def record_quarterly_estimate_payment(
        self,
        estimate_id: UUID,
        amount: str,
        payment_date: date,
        payment_method: str | None = None,
    ) -> dict[str, Any]:
        """Record a quarterly estimate payment."""
        payload: dict[str, Any] = {
            "amount": amount,
            "payment_date": payment_date.isoformat(),
        }
        if payment_method is not None:
            payload["payment_method"] = payment_method
        result = await self.post(
            f"/api/v1/tax-forms/quarterly-estimates/{estimate_id}/pay",
            json=payload,
        )
        return result if isinstance(result, dict) else {}

    # === Bank Transaction Endpoints ===

    async def list_bank_transactions(
        self, offset: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List bank transactions."""
        result = await self.get(
            "/api/v1/bank-transactions/",
            params={"offset": offset, "limit": self._clamp_limit(limit)},
        )
        return self._extract_items(result)

    async def categorize_bank_transaction(
        self, transaction_id: UUID, account_id: UUID
    ) -> dict[str, Any]:
        """Categorize a bank transaction."""
        result = await self.post(
            f"/api/v1/bank-transactions/{transaction_id}/categorize",
            json={"account_id": str(account_id)},
        )
        return result if isinstance(result, dict) else {}

    async def match_bank_transaction(
        self, transaction_id: UUID, match_id: UUID, match_type: str
    ) -> dict[str, Any]:
        """Match bank transaction to invoice/bill/payment."""
        result = await self.post(
            f"/api/v1/bank-transactions/{transaction_id}/match",
            json={"match_id": str(match_id), "match_type": match_type},
        )
        return result if isinstance(result, dict) else {}
