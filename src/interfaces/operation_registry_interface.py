"""Interface for operation registry services."""
from typing import Protocol, Optional, List, Dict, Any

from ..domain.exceptions import GeometryError


class IOperationRegistry(Protocol):
    """Interface for services that manage and execute geometry operations."""

    def get_handler(self, operation_type: str) -> Optional[Any]:
        """
        Get handler for the specified operation type.

        Args:
            operation_type: The type of operation to get handler for.

        Returns:
            The operation handler if found, None otherwise.
        """
        ...

    def has_handler(self, operation_type: str) -> bool:
        """
        Check if handler exists for the operation type.

        Args:
            operation_type: The type of operation to check.

        Returns:
            True if handler exists, False otherwise.
        """
        ...

    def get_supported_operations(self) -> List[str]:
        """
        Get list of all supported operation types.

        Returns:
            List of supported operation type names.
        """
        ...

    def execute_operation(
        self,
        operation_type: str,
        params: Any,
        source_layers: Dict[str, Any]
    ) -> Any:
        """
        Execute an operation using the appropriate handler.

        Args:
            operation_type: The type of operation to execute.
            params: Parameters for the operation.
            source_layers: Dictionary of source layers for the operation.

        Returns:
            Result of the operation execution.

        Raises:
            GeometryError: If operation execution fails or handler not found.
        """
        ...
