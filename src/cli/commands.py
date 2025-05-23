"""Command pattern implementation for CLI operations."""
from abc import ABC, abstractmethod
from typing import Any, Dict

from ..interfaces.project_orchestrator_interface import IProjectOrchestrator
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import ApplicationBaseException


class BaseCommand(ABC):
    """Base class for CLI commands following command pattern."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize command with injected logger service."""
        self._logger = logger_service.get_logger(__name__)

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the command with given arguments."""
        ...


class ProcessProjectCommand(BaseCommand):
    """Command to process a project using the orchestrator service."""

    def __init__(
        self,
        logger_service: ILoggingService,
        project_orchestrator: IProjectOrchestrator
    ):
        """Initialize with injected dependencies."""
        super().__init__(logger_service)
        self._project_orchestrator = project_orchestrator

    def execute(self, project_name: str) -> None:
        """Execute project processing command."""
        try:
            self._logger.info(f"Executing process project command for: {project_name}")
            self._project_orchestrator.process_project(project_name)
            self._logger.info(f"Successfully completed project processing: {project_name}")
        except Exception as e:
            self._logger.error(f"Failed to process project {project_name}: {e}", exc_info=True)
            raise ApplicationBaseException(f"Project processing failed: {e}") from e


class CommandRegistry:
    """Registry for CLI commands following dependency injection pattern."""

    def __init__(self):
        """Initialize empty command registry."""
        self._commands: Dict[str, BaseCommand] = {}

    def register_command(self, name: str, command: BaseCommand) -> None:
        """Register a command with the given name."""
        self._commands[name] = command

    def get_command(self, name: str) -> BaseCommand:
        """Get command by name."""
        if name not in self._commands:
            raise ApplicationBaseException(f"Unknown command: {name}")
        return self._commands[name]

    def execute_command(self, name: str, **kwargs) -> Any:
        """Execute command by name with given arguments."""
        command = self.get_command(name)
        return command.execute(**kwargs)
