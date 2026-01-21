"""Tests for the Scheduler."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from atlas_town.scheduler import (
    DayPhase,
    PhaseConfig,
    ScheduledTask,
    Scheduler,
    SimulatedTime,
)


class TestSimulatedTime:
    """Tests for SimulatedTime class."""

    def test_default_initialization(self):
        """Test default time starts at day 1, 6:00."""
        time = SimulatedTime()

        assert time.day == 1
        assert time.hour == 6
        assert time.minute == 0

    def test_custom_initialization(self):
        """Test custom time initialization."""
        time = SimulatedTime(day=5, hour=14, minute=30)

        assert time.day == 5
        assert time.hour == 14
        assert time.minute == 30

    def test_advance_minutes(self):
        """Test advancing time by minutes."""
        time = SimulatedTime(day=1, hour=10, minute=30)
        time.advance(45)

        assert time.hour == 11
        assert time.minute == 15

    def test_advance_wraps_hour(self):
        """Test that advancing wraps hour correctly."""
        time = SimulatedTime(day=1, hour=23, minute=30)
        time.advance(60)

        assert time.day == 2
        assert time.hour == 0
        assert time.minute == 30

    def test_phase_detection_morning(self):
        """Test morning phase detection."""
        time = SimulatedTime(day=1, hour=9, minute=0)
        assert time.phase == DayPhase.MORNING

    def test_phase_detection_afternoon(self):
        """Test afternoon phase detection."""
        time = SimulatedTime(day=1, hour=15, minute=0)
        assert time.phase == DayPhase.AFTERNOON

    def test_phase_detection_evening(self):
        """Test evening phase detection."""
        time = SimulatedTime(day=1, hour=18, minute=0)
        assert time.phase == DayPhase.EVENING

    def test_phase_detection_night(self):
        """Test night phase detection (wraps around midnight)."""
        time = SimulatedTime(day=1, hour=22, minute=0)
        assert time.phase == DayPhase.NIGHT

        time2 = SimulatedTime(day=1, hour=3, minute=0)
        assert time2.phase == DayPhase.NIGHT

    def test_to_time_string(self):
        """Test time string formatting."""
        time = SimulatedTime(day=3, hour=14, minute=5)
        assert time.to_time_string() == "Day 3, 14:05"


class TestDayPhase:
    """Tests for DayPhase enum."""

    def test_phase_values(self):
        """Test all phase values exist."""
        assert DayPhase.EARLY_MORNING.value == "early_morning"
        assert DayPhase.MORNING.value == "morning"
        assert DayPhase.LUNCH.value == "lunch"
        assert DayPhase.AFTERNOON.value == "afternoon"
        assert DayPhase.EVENING.value == "evening"
        assert DayPhase.NIGHT.value == "night"


class TestScheduledTask:
    """Tests for ScheduledTask dataclass."""

    def test_task_creation(self):
        """Test creating a scheduled task."""
        handler = MagicMock()
        task = ScheduledTask(
            name="test_task",
            phase=DayPhase.MORNING,
            handler=handler,
            priority=1,
        )

        assert task.name == "test_task"
        assert task.phase == DayPhase.MORNING
        assert task.priority == 1
        assert task.enabled is True

    def test_task_with_org_id(self):
        """Test task with organization ID."""
        org_id = uuid4()
        task = ScheduledTask(
            name="org_task",
            phase=DayPhase.AFTERNOON,
            handler=MagicMock(),
            org_id=org_id,
        )

        assert task.org_id == org_id


class TestScheduler:
    """Tests for Scheduler class."""

    def test_scheduler_initialization(self):
        """Test scheduler initializes with defaults."""
        scheduler = Scheduler()

        assert scheduler.current_time.day == 1
        assert scheduler.current_time.hour == 6
        assert scheduler.is_running is False
        assert scheduler.is_paused is False

    def test_scheduler_with_custom_speed(self):
        """Test scheduler with custom speed."""
        scheduler = Scheduler(speed_multiplier=10.0)
        assert scheduler.speed == 10.0

    def test_set_speed(self):
        """Test setting speed."""
        scheduler = Scheduler()
        scheduler.speed = 5.0

        assert scheduler.speed == 5.0

    def test_set_invalid_speed_raises(self):
        """Test that invalid speed raises error."""
        scheduler = Scheduler()

        with pytest.raises(ValueError, match="positive"):
            scheduler.speed = 0

        with pytest.raises(ValueError, match="positive"):
            scheduler.speed = -1.0

    def test_register_phase_handler(self):
        """Test registering a phase handler."""
        scheduler = Scheduler()
        handler = MagicMock()

        scheduler.register_phase_handler(DayPhase.MORNING, handler)

        assert handler in scheduler._phase_handlers[DayPhase.MORNING]

    def test_schedule_task(self):
        """Test scheduling a task."""
        scheduler = Scheduler()
        task = ScheduledTask(
            name="test",
            phase=DayPhase.AFTERNOON,
            handler=MagicMock(),
        )

        scheduler.schedule_task(task)

        assert task in scheduler._tasks

    def test_remove_task(self):
        """Test removing a task."""
        scheduler = Scheduler()
        task = ScheduledTask(
            name="to_remove",
            phase=DayPhase.MORNING,
            handler=MagicMock(),
        )
        scheduler.schedule_task(task)

        result = scheduler.remove_task("to_remove")

        assert result is True
        assert task not in scheduler._tasks

    def test_remove_nonexistent_task(self):
        """Test removing nonexistent task returns False."""
        scheduler = Scheduler()

        result = scheduler.remove_task("nonexistent")

        assert result is False

    def test_get_tasks_for_phase(self):
        """Test getting tasks for a specific phase."""
        scheduler = Scheduler()

        morning_task = ScheduledTask("morning", DayPhase.MORNING, MagicMock())
        afternoon_task = ScheduledTask("afternoon", DayPhase.AFTERNOON, MagicMock())
        disabled_task = ScheduledTask("disabled", DayPhase.MORNING, MagicMock(), enabled=False)

        scheduler.schedule_task(morning_task)
        scheduler.schedule_task(afternoon_task)
        scheduler.schedule_task(disabled_task)

        morning_tasks = scheduler.get_tasks_for_phase(DayPhase.MORNING)

        assert len(morning_tasks) == 1
        assert morning_task in morning_tasks
        assert disabled_task not in morning_tasks

    def test_pause_resume(self):
        """Test pausing and resuming."""
        scheduler = Scheduler()

        scheduler.pause()
        assert scheduler.is_paused is True

        scheduler.resume()
        assert scheduler.is_paused is False

    def test_reset(self):
        """Test resetting scheduler."""
        scheduler = Scheduler()
        scheduler._time.advance(1000)  # Advance time
        scheduler._is_running = True

        scheduler.reset()

        assert scheduler.current_time.day == 1
        assert scheduler.current_time.hour == 6
        assert scheduler.is_running is False

    def test_stop(self):
        """Test stopping scheduler."""
        scheduler = Scheduler()
        scheduler._is_running = True
        scheduler._is_paused = True

        scheduler.stop()

        assert scheduler.is_running is False
        assert scheduler.is_paused is False

    def test_get_status(self):
        """Test getting scheduler status."""
        scheduler = Scheduler(speed_multiplier=2.0)
        scheduler.schedule_task(ScheduledTask("task", DayPhase.MORNING, MagicMock()))

        status = scheduler.get_status()

        assert status["is_running"] is False
        assert status["is_paused"] is False
        assert status["day"] == 1
        assert status["speed"] == 2.0
        assert status["scheduled_tasks"] == 1

    @pytest.mark.asyncio
    async def test_advance_to_phase(self):
        """Test advancing to a specific phase."""
        scheduler = Scheduler()
        initial_hour = scheduler.current_time.hour

        await scheduler.advance_to_phase(DayPhase.AFTERNOON)

        assert scheduler.current_phase == DayPhase.AFTERNOON
        assert scheduler.current_time.hour >= 13

    @pytest.mark.asyncio
    async def test_run_phase_executes_handlers(self):
        """Test that run_phase executes registered handlers."""
        scheduler = Scheduler()

        handler = AsyncMock(return_value="handler_result")
        scheduler.register_phase_handler(DayPhase.MORNING, handler)

        # Advance to morning
        await scheduler.advance_to_phase(DayPhase.MORNING)

        results = await scheduler.run_phase(DayPhase.MORNING)

        handler.assert_called_once()
        assert "handler_result" in results

    @pytest.mark.asyncio
    async def test_run_phase_executes_tasks(self):
        """Test that run_phase executes scheduled tasks."""
        scheduler = Scheduler()

        task_handler = AsyncMock(return_value="task_result")
        task = ScheduledTask("test_task", DayPhase.AFTERNOON, task_handler)
        scheduler.schedule_task(task)

        await scheduler.advance_to_phase(DayPhase.AFTERNOON)
        results = await scheduler.run_phase(DayPhase.AFTERNOON)

        task_handler.assert_called_once()
        assert any(r.get("task") == "test_task" for r in results if isinstance(r, dict))
