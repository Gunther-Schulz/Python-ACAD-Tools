"""Operation registry for managing geometry operation handlers."""
from typing import Dict, Type, Optional
import importlib
import inspect

from ...interfaces.logging_service_interface import ILoggingService
from ...interfaces.data_source_interface import IDataSource
from ...domain.exceptions import GeometryError
from .base_operation_handler import BaseOperationHandler


class OperationRegistry:
    """Registry for operation handlers following dependency injection pattern."""

    def __init__(self, logger_service: ILoggingService, data_source_service: IDataSource):
        """Initialize registry with injected dependencies."""
        self._logger = logger_service.get_logger(__name__)
        self._logger_service = logger_service
        self._data_source_service = data_source_service
        self._handlers: Dict[str, BaseOperationHandler] = {}
        self._handler_classes: Dict[str, Type[BaseOperationHandler]] = {}

        # Auto-discover and register handlers
        self._discover_handlers()

    def _discover_handlers(self) -> None:
        """Auto-discover operation handlers following existing pattern."""
        handler_modules = [
            'transformation_handlers',
            'spatial_analysis_handlers',
            'geometry_creation_handlers',
            'data_processing_handlers',
            'filtering_handlers',
            'advanced_handlers'
        ]

        for module_name in handler_modules:
            try:
                module = importlib.import_module(f"src.services.operations.{module_name}")

                # Find all handler classes in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseOperationHandler) and
                        obj != BaseOperationHandler and
                        hasattr(obj, 'operation_type')):

                        try:
                            # Create instance to get operation_type
                            handler_instance = obj(self._logger_service, self._data_source_service)
                            operation_type = handler_instance.operation_type

                            self._handlers[operation_type] = handler_instance
                            self._handler_classes[operation_type] = obj

                            self._logger.debug(f"Registered operation handler: {operation_type} -> {obj.__name__}")

                        except Exception as e:
                            self._logger.warning(f"Failed to instantiate handler {obj.__name__}: {e}")

            except ImportError as e:
                self._logger.debug(f"Could not import handler module {module_name}: {e}")
            except Exception as e:
                self._logger.warning(f"Error discovering handlers in module {module_name}: {e}")

    def get_handler(self, operation_type: str) -> Optional[BaseOperationHandler]:
        """Get handler for the specified operation type."""
        handler = self._handlers.get(operation_type)
        if not handler:
            self._logger.warning(f"No handler found for operation type: {operation_type}")
        return handler

    def has_handler(self, operation_type: str) -> bool:
        """Check if handler exists for the operation type."""
        return operation_type in self._handlers

    def get_supported_operations(self) -> list[str]:
        """Get list of all supported operation types."""
        return list(self._handlers.keys())

    def register_handler(self, handler: BaseOperationHandler) -> None:
        """Manually register an operation handler."""
        operation_type = handler.operation_type
        self._handlers[operation_type] = handler
        self._handler_classes[operation_type] = type(handler)
        self._logger.info(f"Manually registered operation handler: {operation_type}")

    def execute_operation(
        self,
        operation_type: str,
        params: any,
        source_layers: Dict[str, any]
    ) -> any:
        """Execute an operation using the appropriate handler."""
        handler = self.get_handler(operation_type)
        if not handler:
            raise GeometryError(f"No handler available for operation type: {operation_type}")

        try:
            return handler.handle(params, source_layers)
        except Exception as e:
            self._logger.error(f"Error executing {operation_type} operation: {e}", exc_info=True)
            raise GeometryError(f"Error executing {operation_type} operation: {e}") from e
