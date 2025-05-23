"""Factory patterns for component creation and validation."""
from typing import Dict, Type, Any, Protocol, runtime_checkable
from abc import ABC, abstractmethod

from ..interfaces.logging_service_interface import ILoggingService
from ..domain.exceptions import ApplicationBaseException


@runtime_checkable
class IFactory(Protocol):
    """Protocol for factory pattern implementations."""

    def create(self, component_type: str, **kwargs) -> Any:
        """Create a component of the specified type."""
        ...

    def register(self, component_type: str, component_class: Type) -> None:
        """Register a component class for the given type."""
        ...

    def supports(self, component_type: str) -> bool:
        """Check if factory supports the given component type."""
        ...


class BaseFactory(ABC):
    """Base factory implementation with registry pattern validation."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize factory with injected logger service."""
        self._logger = logger_service.get_logger(__name__)
        self._registry: Dict[str, Type] = {}

    def register(self, component_type: str, component_class: Type) -> None:
        """Register a component class for the given type."""
        if not isinstance(component_type, str) or not component_type.strip():
            raise ApplicationBaseException("Component type must be a non-empty string")

        if not isinstance(component_class, type):
            raise ApplicationBaseException("Component class must be a valid class type")

        self._registry[component_type] = component_class
        self._logger.debug(f"Registered component: {component_type} -> {component_class.__name__}")

    def supports(self, component_type: str) -> bool:
        """Check if factory supports the given component type."""
        return component_type in self._registry

    def create(self, component_type: str, **kwargs) -> Any:
        """Create a component of the specified type."""
        if not self.supports(component_type):
            raise ApplicationBaseException(f"No component registered for type: {component_type}")

        component_class = self._registry[component_type]

        try:
            # Validate component class meets requirements
            self._validate_component_class(component_class)

            # Create instance
            instance = component_class(**kwargs)
            self._logger.debug(f"Created component instance: {component_type}")
            return instance

        except Exception as e:
            error_msg = f"Failed to create component {component_type}: {e}"
            self._logger.error(error_msg, exc_info=True)
            raise ApplicationBaseException(error_msg) from e

    @abstractmethod
    def _validate_component_class(self, component_class: Type) -> None:
        """Validate that component class meets factory requirements."""
        ...

    def get_registered_types(self) -> list[str]:
        """Get list of all registered component types."""
        return list(self._registry.keys())

    def clear_registry(self) -> None:
        """Clear all registered components."""
        self._registry.clear()
        self._logger.debug("Cleared component registry")


class ServiceFactory(BaseFactory):
    """Factory for creating service instances with interface validation."""

    def _validate_component_class(self, component_class: Type) -> None:
        """Validate that component class is a proper service implementation."""
        # Check if class has required service patterns
        if not hasattr(component_class, '__init__'):
            raise ApplicationBaseException(f"Service class {component_class.__name__} must have __init__ method")

        # Additional service-specific validations can be added here
        self._logger.debug(f"Service class {component_class.__name__} passed validation")


class HandlerFactory(BaseFactory):
    """Factory for creating operation handler instances."""

    def _validate_component_class(self, component_class: Type) -> None:
        """Validate that component class is a proper handler implementation."""
        # Check for required handler attributes/methods
        required_attrs = ['operation_type', 'handle']

        for attr in required_attrs:
            if not hasattr(component_class, attr):
                raise ApplicationBaseException(
                    f"Handler class {component_class.__name__} must have {attr} attribute/method"
                )

        self._logger.debug(f"Handler class {component_class.__name__} passed validation")


class FactoryRegistry:
    """Central registry for all factories in the application."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize factory registry with injected logger service."""
        self._logger = logger_service.get_logger(__name__)
        self._factories: Dict[str, IFactory] = {}

    def register_factory(self, factory_type: str, factory: IFactory) -> None:
        """Register a factory for the given type."""
        if not isinstance(factory_type, str) or not factory_type.strip():
            raise ApplicationBaseException("Factory type must be a non-empty string")

        # Validate factory implements IFactory protocol
        if not isinstance(factory, IFactory):
            raise ApplicationBaseException(f"Factory must implement IFactory protocol")

        self._factories[factory_type] = factory
        self._logger.info(f"Registered factory: {factory_type}")

    def get_factory(self, factory_type: str) -> IFactory:
        """Get factory for the given type."""
        if factory_type not in self._factories:
            raise ApplicationBaseException(f"No factory registered for type: {factory_type}")

        return self._factories[factory_type]

    def has_factory(self, factory_type: str) -> bool:
        """Check if factory exists for the given type."""
        return factory_type in self._factories

    def get_supported_factory_types(self) -> list[str]:
        """Get list of all supported factory types."""
        return list(self._factories.keys())
