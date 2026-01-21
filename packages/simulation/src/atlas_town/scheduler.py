"""Scheduler for managing daily simulation phases and agent coordination."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Callable
from uuid import UUID

import structlog

from atlas_town.config import get_settings

logger = structlog.get_logger(__name__)


class DayPhase(str, Enum):
    """Phases of a simulated business day."""

    EARLY_MORNING = "early_morning"   # 6:00 - 8:00: Prep, planning
    MORNING = "morning"               # 8:00 - 12:00: Business opens, activity
    LUNCH = "lunch"                   # 12:00 - 13:00: Mid-day lull
    AFTERNOON = "afternoon"           # 13:00 - 17:00: Peak business
    EVENING = "evening"               # 17:00 - 20:00: Wind down, accounting
    NIGHT = "night"                   # 20:00 - 6:00: Closed, processing


# Phase time boundaries (hour of day)
PHASE_TIMES: dict[DayPhase, tuple[int, int]] = {
    DayPhase.EARLY_MORNING: (6, 8),
    DayPhase.MORNING: (8, 12),
    DayPhase.LUNCH: (12, 13),
    DayPhase.AFTERNOON: (13, 17),
    DayPhase.EVENING: (17, 20),
    DayPhase.NIGHT: (20, 6),  # Wraps to next day
}


@dataclass
class SimulatedTime:
    """Represents the current simulated time."""

    day: int = 1
    hour: int = 6
    minute: int = 0

    def __post_init__(self) -> None:
        self._normalize()

    def _normalize(self) -> None:
        """Normalize time values (handle overflow)."""
        while self.minute >= 60:
            self.minute -= 60
            self.hour += 1
        while self.hour >= 24:
            self.hour -= 24
            self.day += 1

    def advance(self, minutes: int) -> None:
        """Advance time by the given number of minutes."""
        self.minute += minutes
        self._normalize()

    @property
    def phase(self) -> DayPhase:
        """Get the current phase based on hour."""
        for phase, (start, end) in PHASE_TIMES.items():
            if start <= end:
                if start <= self.hour < end:
                    return phase
            else:  # Wraps around midnight
                if self.hour >= start or self.hour < end:
                    return phase
        return DayPhase.NIGHT

    def to_time_string(self) -> str:
        """Get formatted time string."""
        return f"Day {self.day}, {self.hour:02d}:{self.minute:02d}"

    def to_datetime(self, base_date: datetime | None = None) -> datetime:
        """Convert to datetime object."""
        base = base_date or datetime(2024, 1, 1, tzinfo=timezone.utc)
        return base.replace(
            day=base.day + self.day - 1,
            hour=self.hour,
            minute=self.minute,
        )


@dataclass
class ScheduledTask:
    """A task scheduled to run at a specific phase."""

    name: str
    phase: DayPhase
    handler: Callable[..., Any]
    priority: int = 0  # Lower = higher priority
    org_id: UUID | None = None  # If task is org-specific
    enabled: bool = True


@dataclass
class PhaseConfig:
    """Configuration for a simulation phase."""

    phase: DayPhase
    duration_minutes: int  # Real-time duration at 1x speed
    description: str
    transaction_probability: float  # 0.0 to 1.0


# Default phase configurations
DEFAULT_PHASE_CONFIGS: dict[DayPhase, PhaseConfig] = {
    DayPhase.EARLY_MORNING: PhaseConfig(
        phase=DayPhase.EARLY_MORNING,
        duration_minutes=10,
        description="Business prep and planning",
        transaction_probability=0.1,
    ),
    DayPhase.MORNING: PhaseConfig(
        phase=DayPhase.MORNING,
        duration_minutes=20,
        description="Morning business activity",
        transaction_probability=0.6,
    ),
    DayPhase.LUNCH: PhaseConfig(
        phase=DayPhase.LUNCH,
        duration_minutes=5,
        description="Mid-day lull",
        transaction_probability=0.3,
    ),
    DayPhase.AFTERNOON: PhaseConfig(
        phase=DayPhase.AFTERNOON,
        duration_minutes=20,
        description="Peak afternoon activity",
        transaction_probability=0.8,
    ),
    DayPhase.EVENING: PhaseConfig(
        phase=DayPhase.EVENING,
        duration_minutes=15,
        description="Wind down and accounting",
        transaction_probability=0.2,
    ),
    DayPhase.NIGHT: PhaseConfig(
        phase=DayPhase.NIGHT,
        duration_minutes=5,
        description="End of day processing",
        transaction_probability=0.0,
    ),
}


class Scheduler:
    """Manages simulation timing and phase transitions.

    The scheduler:
    1. Tracks simulated time (day, hour, minute)
    2. Manages phase transitions
    3. Executes scheduled tasks at appropriate phases
    4. Handles speed multiplier for faster simulation
    """

    def __init__(
        self,
        speed_multiplier: float | None = None,
        phase_configs: dict[DayPhase, PhaseConfig] | None = None,
    ):
        settings = get_settings()
        self._speed = speed_multiplier or settings.simulation_speed
        self._phase_configs = phase_configs or DEFAULT_PHASE_CONFIGS

        self._time = SimulatedTime()
        self._tasks: list[ScheduledTask] = []
        self._is_running = False
        self._is_paused = False

        self._phase_handlers: dict[DayPhase, list[Callable[..., Any]]] = {
            phase: [] for phase in DayPhase
        }

        self._logger = logger.bind(component="scheduler")

    @property
    def current_time(self) -> SimulatedTime:
        """Get the current simulated time."""
        return self._time

    @property
    def current_phase(self) -> DayPhase:
        """Get the current phase."""
        return self._time.phase

    @property
    def speed(self) -> float:
        """Get the current speed multiplier."""
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        """Set the speed multiplier."""
        if value <= 0:
            raise ValueError("Speed must be positive")
        self._speed = value
        self._logger.info("speed_changed", speed=value)

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """Check if scheduler is paused."""
        return self._is_paused

    def register_phase_handler(
        self, phase: DayPhase, handler: Callable[..., Any]
    ) -> None:
        """Register a handler to be called when entering a phase.

        Args:
            phase: The phase to trigger on.
            handler: Async function to call when phase starts.
        """
        self._phase_handlers[phase].append(handler)
        self._logger.debug("handler_registered", phase=phase.value)

    def schedule_task(self, task: ScheduledTask) -> None:
        """Add a task to the schedule.

        Args:
            task: The task to schedule.
        """
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority)
        self._logger.debug("task_scheduled", task=task.name, phase=task.phase.value)

    def remove_task(self, task_name: str) -> bool:
        """Remove a task by name.

        Args:
            task_name: Name of the task to remove.

        Returns:
            True if task was found and removed.
        """
        original_len = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.name != task_name]
        return len(self._tasks) < original_len

    def get_tasks_for_phase(self, phase: DayPhase) -> list[ScheduledTask]:
        """Get all tasks scheduled for a specific phase.

        Args:
            phase: The phase to get tasks for.

        Returns:
            List of scheduled tasks.
        """
        return [t for t in self._tasks if t.phase == phase and t.enabled]

    def pause(self) -> None:
        """Pause the scheduler."""
        self._is_paused = True
        self._logger.info("scheduler_paused")

    def resume(self) -> None:
        """Resume the scheduler."""
        self._is_paused = False
        self._logger.info("scheduler_resumed")

    def reset(self) -> None:
        """Reset the scheduler to day 1."""
        self._time = SimulatedTime()
        self._is_running = False
        self._is_paused = False
        self._logger.info("scheduler_reset")

    async def advance_to_phase(self, target_phase: DayPhase) -> None:
        """Advance time until reaching the target phase.

        Args:
            target_phase: The phase to advance to.
        """
        while self._time.phase != target_phase:
            # Advance by 30 simulated minutes at a time
            self._time.advance(30)

        self._logger.info(
            "advanced_to_phase",
            phase=target_phase.value,
            time=self._time.to_time_string(),
        )

    async def run_phase(self, phase: DayPhase) -> list[Any]:
        """Run all tasks and handlers for a specific phase.

        Args:
            phase: The phase to run.

        Returns:
            List of results from handlers and tasks.
        """
        results = []
        config = self._phase_configs[phase]

        self._logger.info(
            "phase_starting",
            phase=phase.value,
            description=config.description,
            duration=config.duration_minutes,
        )

        # Run phase handlers
        for handler in self._phase_handlers[phase]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(self._time, phase)
                else:
                    result = handler(self._time, phase)
                results.append(result)
            except Exception as e:
                self._logger.error("handler_error", phase=phase.value, error=str(e))

        # Run scheduled tasks
        for task in self.get_tasks_for_phase(phase):
            try:
                if asyncio.iscoroutinefunction(task.handler):
                    result = await task.handler(self._time, phase, task.org_id)
                else:
                    result = task.handler(self._time, phase, task.org_id)
                results.append({"task": task.name, "result": result})
            except Exception as e:
                self._logger.error("task_error", task=task.name, error=str(e))

        self._logger.info("phase_completed", phase=phase.value, results=len(results))
        return results

    async def run_day(self) -> dict[DayPhase, list[Any]]:
        """Run a complete simulated day through all phases.

        Returns:
            Dictionary mapping phases to their results.
        """
        self._is_running = True
        day_results: dict[DayPhase, list[Any]] = {}

        self._logger.info("day_starting", day=self._time.day)

        # Run through each phase in order
        phase_order = [
            DayPhase.EARLY_MORNING,
            DayPhase.MORNING,
            DayPhase.LUNCH,
            DayPhase.AFTERNOON,
            DayPhase.EVENING,
            DayPhase.NIGHT,
        ]

        for phase in phase_order:
            if not self._is_running:
                break

            while self._is_paused:
                await asyncio.sleep(0.1)

            # Advance to this phase
            await self.advance_to_phase(phase)

            # Run the phase
            results = await self.run_phase(phase)
            day_results[phase] = results

            # Calculate real-time delay based on speed
            config = self._phase_configs[phase]
            real_delay = config.duration_minutes / self._speed

            # Wait (with check for pause/stop)
            elapsed = 0.0
            while elapsed < real_delay and self._is_running:
                while self._is_paused:
                    await asyncio.sleep(0.1)
                await asyncio.sleep(min(0.5, real_delay - elapsed))
                elapsed += 0.5

        # Advance to next day
        self._time = SimulatedTime(day=self._time.day + 1)
        self._is_running = False

        self._logger.info("day_completed", day=self._time.day - 1)
        return day_results

    async def run_continuous(self, max_days: int | None = None) -> None:
        """Run the simulation continuously.

        Args:
            max_days: Optional maximum number of days to run.
        """
        self._is_running = True
        days_run = 0

        self._logger.info("continuous_run_starting", max_days=max_days)

        while self._is_running:
            if max_days and days_run >= max_days:
                break

            await self.run_day()
            days_run += 1

            # run_day() sets _is_running to False at the end,
            # but we want to continue in continuous mode
            if max_days is None or days_run < max_days:
                self._is_running = True

            # Small delay between days
            await asyncio.sleep(0.1)

        self._logger.info("continuous_run_ended", days_run=days_run)

    def stop(self) -> None:
        """Stop the scheduler."""
        self._is_running = False
        self._is_paused = False
        self._logger.info("scheduler_stopped")

    def get_status(self) -> dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Status dictionary.
        """
        return {
            "is_running": self._is_running,
            "is_paused": self._is_paused,
            "current_time": self._time.to_time_string(),
            "current_phase": self._time.phase.value,
            "day": self._time.day,
            "speed": self._speed,
            "scheduled_tasks": len(self._tasks),
        }
