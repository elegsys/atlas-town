"""Tests for the Orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from atlas_town.orchestrator import Orchestrator, OrganizationContext


class TestOrganizationContext:
    """Tests for OrganizationContext dataclass."""

    def test_organization_context_creation(self):
        """Test organization context creation."""
        org_id = uuid4()
        ctx = OrganizationContext(
            id=org_id,
            name="Test Corp",
            industry="consulting",
            owner_key="maya",
        )

        assert ctx.id == org_id
        assert ctx.name == "Test Corp"
        assert ctx.industry == "consulting"
        assert ctx.owner_key == "maya"
        assert ctx.owner is None
        assert ctx.customers == []
        assert ctx.vendors == []


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_orchestrator_initial_state(self):
        """Test orchestrator starts with correct initial state."""
        with patch("atlas_town.orchestrator.get_publisher") as mock_publisher:
            mock_publisher.return_value = MagicMock()
            orch = Orchestrator(start_websocket=False)

            assert orch._api_client is None
            assert orch._accountant is None
            assert orch._is_initialized is False
            assert orch._organizations == {}

    def test_scheduler_property(self):
        """Test scheduler property returns scheduler."""
        with patch("atlas_town.orchestrator.get_publisher") as mock_publisher:
            mock_publisher.return_value = MagicMock()
            orch = Orchestrator(start_websocket=False)

            scheduler = orch.scheduler
            assert scheduler is not None
            assert scheduler.current_time.day == 1

    def test_organizations_property_returns_list(self):
        """Test organizations property returns list."""
        with patch("atlas_town.orchestrator.get_publisher") as mock_publisher:
            mock_publisher.return_value = MagicMock()
            orch = Orchestrator(start_websocket=False)

            org_id = uuid4()
            orch._organizations = {
                org_id: OrganizationContext(
                    id=org_id,
                    name="Test",
                    industry="consulting",
                    owner_key="maya",
                )
            }

            orgs = orch.organizations
            assert len(orgs) == 1
            assert orgs[0].name == "Test"

    def test_current_org_returns_none_when_not_set(self):
        """Test current_org returns None when not set."""
        with patch("atlas_town.orchestrator.get_publisher") as mock_publisher:
            mock_publisher.return_value = MagicMock()
            orch = Orchestrator(start_websocket=False)

            assert orch.current_org is None

    def test_current_org_returns_context_when_set(self):
        """Test current_org returns context when set."""
        with patch("atlas_town.orchestrator.get_publisher") as mock_publisher:
            mock_publisher.return_value = MagicMock()
            orch = Orchestrator(start_websocket=False)

            org_id = uuid4()
            ctx = OrganizationContext(
                id=org_id,
                name="Test",
                industry="consulting",
                owner_key="maya",
            )
            orch._organizations = {org_id: ctx}
            orch._current_org_id = org_id

            assert orch.current_org == ctx

    @pytest.mark.asyncio
    async def test_initialize_creates_components(self, monkeypatch: pytest.MonkeyPatch):
        """Test that initialize creates API client and agents."""
        monkeypatch.setenv("SIM_MULTI_ORG", "0")
        mock_publisher = MagicMock()
        mock_publisher.is_running = False
        mock_publisher.start = AsyncMock()

        with patch(
            "atlas_town.orchestrator.get_publisher", return_value=mock_publisher
        ), patch("atlas_town.orchestrator.AtlasAPIClient") as MockClient, patch(
            "atlas_town.orchestrator.load_persona_payroll_configs", return_value={}
        ), patch(
            "atlas_town.orchestrator.load_persona_tax_configs", return_value={}
        ):
            mock_client = AsyncMock()
            mock_client.login = AsyncMock(return_value={})
            mock_client.organizations = [
                {"id": str(uuid4()), "name": "Test Org", "industry": "consulting"}
            ]
            mock_client.switch_organization = AsyncMock()
            MockClient.return_value = mock_client

            orch = Orchestrator(start_websocket=False)
            await orch.initialize()

            assert orch._api_client is not None
            assert orch._tool_executor is not None
            assert orch._accountant is not None
            assert orch._is_initialized is True
            mock_client.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self):
        """Test that shutdown closes API client."""
        mock_publisher = MagicMock()
        mock_publisher.is_running = False

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            orch._api_client = mock_client
            orch._is_initialized = True

            await orch.shutdown()

            mock_client.close.assert_called_once()
            assert orch._is_initialized is False

    @pytest.mark.asyncio
    async def test_context_manager(self, monkeypatch: pytest.MonkeyPatch):
        """Test orchestrator as async context manager."""
        monkeypatch.setenv("SIM_MULTI_ORG", "0")
        mock_publisher = MagicMock()
        mock_publisher.is_running = False
        mock_publisher.start = AsyncMock()
        mock_publisher.stop = AsyncMock()

        with patch(
            "atlas_town.orchestrator.get_publisher", return_value=mock_publisher
        ), patch("atlas_town.orchestrator.AtlasAPIClient") as MockClient, patch(
            "atlas_town.orchestrator.load_persona_payroll_configs", return_value={}
        ), patch(
            "atlas_town.orchestrator.load_persona_tax_configs", return_value={}
        ):
            mock_client = AsyncMock()
            mock_client.login = AsyncMock(return_value={})
            mock_client.organizations = []
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            async with Orchestrator(start_websocket=False) as orch:
                assert orch._api_client is not None

            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_organization(self):
        """Test switching organization context."""
        mock_publisher = MagicMock()
        mock_publisher.publish = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            # Set up mock client
            mock_client = AsyncMock()
            mock_client.switch_organization = AsyncMock()
            orch._api_client = mock_client

            # Set up organizations
            org_id = uuid4()
            orch._organizations = {
                org_id: OrganizationContext(
                    id=org_id,
                    name="Test Org",
                    industry="consulting",
                    owner_key="maya",
                )
            }

            # Set up mock accountant
            mock_accountant = MagicMock()
            mock_accountant.id = uuid4()
            mock_accountant.name = "Sarah Chen"
            orch._accountant = mock_accountant

            await orch.switch_organization(org_id)

            mock_client.switch_organization.assert_called_once_with(org_id)
            mock_accountant.set_organization.assert_called_once_with(org_id)
            assert orch._current_org_id == org_id

    @pytest.mark.asyncio
    async def test_switch_organization_invalid_id_raises(self):
        """Test that switching to invalid org raises ValueError."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)
            orch._organizations = {}

            with pytest.raises(ValueError, match="Unknown organization"):
                await orch.switch_organization(uuid4())

    def test_find_expense_account_prefers_payroll_names(self):
        """Payroll hints should map to payroll-specific expense accounts."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)
            accounts = [
                {"id": "1", "name": "Office Supplies", "account_type": "expense"},
                {"id": "2", "name": "Wages and Salaries", "account_type": "expense"},
                {"id": "3", "name": "Payroll Taxes", "account_type": "expense"},
            ]

            payroll_account = orch._find_expense_account(accounts, hint="payroll")
            assert payroll_account is not None
            assert payroll_account["name"] == "Wages and Salaries"

            tax_account = orch._find_expense_account(accounts, hint="payroll tax")
            assert tax_account is not None
            assert tax_account["name"] == "Payroll Taxes"

    @pytest.mark.asyncio
    async def test_ensure_payroll_vendors_creates_missing(self):
        """Payroll vendors should be auto-created when missing."""
        mock_publisher = MagicMock()
        payroll_config = {
            "tony": {
                "payroll_vendor": "Atlas Payroll Services",
                "tax_authority": "IRS Payroll Taxes",
            }
        }

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher), patch(
            "atlas_town.orchestrator.load_persona_payroll_configs", return_value=payroll_config
        ):
            orch = Orchestrator(start_websocket=False)
            org_id = uuid4()
            orch._organizations = {
                org_id: OrganizationContext(
                    id=org_id,
                    name="Test Org",
                    industry="restaurant",
                    owner_key="tony",
                )
            }

            mock_client = AsyncMock()
            mock_client.switch_organization = AsyncMock()
            mock_client.list_vendors = AsyncMock(return_value=[])
            mock_client.create_vendor = AsyncMock(
                side_effect=[
                    {"id": str(uuid4()), "display_name": "Atlas Payroll Services"},
                    {"id": str(uuid4()), "display_name": "IRS Payroll Taxes"},
                ]
            )
            orch._api_client = mock_client

            await orch._ensure_payroll_vendors()

            assert mock_client.create_vendor.call_count == 2
            created_names = [
                call.args[0]["display_name"]
                for call in mock_client.create_vendor.call_args_list
            ]
            assert "Atlas Payroll Services" in created_names
            assert "IRS Payroll Taxes" in created_names

    @pytest.mark.asyncio
    async def test_ensure_tax_vendors_creates_missing(self):
        """Quarterly tax vendors should be auto-created when missing."""
        mock_publisher = MagicMock()
        tax_config = {
            "maya": {
                "tax_vendor": "IRS Estimated Taxes",
            }
        }

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher), patch(
            "atlas_town.orchestrator.load_persona_tax_configs", return_value=tax_config
        ):
            orch = Orchestrator(start_websocket=False)
            org_id = uuid4()
            orch._organizations = {
                org_id: OrganizationContext(
                    id=org_id,
                    name="Test Org",
                    industry="consulting",
                    owner_key="maya",
                )
            }

            mock_client = AsyncMock()
            mock_client.switch_organization = AsyncMock()
            mock_client.list_vendors = AsyncMock(return_value=[])
            mock_client.create_vendor = AsyncMock(
                return_value={"id": str(uuid4()), "display_name": "IRS Estimated Taxes"}
            )
            orch._api_client = mock_client

            await orch._ensure_tax_vendors()

            mock_client.create_vendor.assert_called_once()
            created_name = mock_client.create_vendor.call_args[0][0]["display_name"]
            assert created_name == "IRS Estimated Taxes"

    @pytest.mark.asyncio
    async def test_run_single_task_without_initialization_raises(self):
        """Test that run_single_task raises if not initialized."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            with pytest.raises(RuntimeError, match="not initialized"):
                await orch.run_single_task("Do something")

    @pytest.mark.asyncio
    async def test_run_single_task_calls_accountant(self):
        """Test that run_single_task delegates to accountant."""
        mock_publisher = MagicMock()
        mock_publisher.publish = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            mock_accountant = MagicMock()
            mock_accountant.id = uuid4()
            mock_accountant.name = "Sarah Chen"
            mock_accountant.run_task = AsyncMock(return_value="Task completed")
            orch._accountant = mock_accountant

            result = await orch.run_single_task("Create an invoice")

            mock_accountant.run_task.assert_called_once_with("Create an invoice")
            assert result == "Task completed"

            # Should publish events
            assert mock_publisher.publish.call_count >= 2

    @pytest.mark.asyncio
    async def test_run_daily_cycle_without_initialization_raises(self):
        """Test that run_daily_cycle raises if not initialized."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            with pytest.raises(RuntimeError, match="not initialized"):
                await orch.run_daily_cycle()

    def test_pause_pauses_scheduler(self):
        """Test that pause pauses the scheduler."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            orch.pause()
            assert orch._scheduler.is_paused is True

    def test_resume_resumes_scheduler(self):
        """Test that resume resumes the scheduler."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            orch.pause()
            orch.resume()
            assert orch._scheduler.is_paused is False

    def test_stop_stops_scheduler(self):
        """Test that stop stops the scheduler."""
        mock_publisher = MagicMock()
        mock_publisher.publish = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)
            orch._scheduler._is_running = True

            orch.stop()
            assert orch._scheduler.is_running is False

    def test_get_status_returns_dict(self):
        """Test that get_status returns status dictionary."""
        mock_publisher = MagicMock()
        mock_publisher.get_status = MagicMock(return_value={"is_running": False})

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            status = orch.get_status()

            assert "is_initialized" in status
            assert "scheduler" in status
            assert "publisher" in status
            assert "organizations" in status
            assert "current_org" in status

    def test_owners_property_returns_copy(self):
        """Test that owners property returns a copy."""
        mock_publisher = MagicMock()

        with patch("atlas_town.orchestrator.get_publisher", return_value=mock_publisher):
            orch = Orchestrator(start_websocket=False)

            # Add a mock owner
            mock_owner = MagicMock()
            orch._owners = {"craig": mock_owner}

            owners = orch.owners
            assert "craig" in owners

            # Modifying returned dict shouldn't affect internal
            owners.clear()
            assert "craig" in orch._owners
