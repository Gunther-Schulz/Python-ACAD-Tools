"""Service management and dependency injection system."""
from typing import Any, Callable, Dict, Optional, Type
from src.core.utils import log_warning

class ServiceProvider:
    """Base class for service providers."""
    
    def provide(self, container: 'ServiceContainer') -> Any:
        """Provide an instance of the service."""
        raise NotImplementedError

class FactoryProvider(ServiceProvider):
    """Provider that uses a factory function to create the service."""
    
    def __init__(self, factory: Callable[['ServiceContainer'], Any]):
        self.factory = factory
        
    def provide(self, container: 'ServiceContainer') -> Any:
        return self.factory(container)

class SingletonProvider(ServiceProvider):
    """Provider that ensures only one instance of the service is created."""
    
    def __init__(self, factory: Callable[['ServiceContainer'], Any]):
        self.factory = factory
        self._instance = None
        
    def provide(self, container: 'ServiceContainer') -> Any:
        if self._instance is None:
            self._instance = self.factory(container)
        return self._instance

class ServiceContainer:
    """Enhanced service container with better dependency management."""
    
    def __init__(self):
        self._providers: Dict[str, ServiceProvider] = {}
        self._instances: Dict[str, Any] = {}
        
    def register(self, service_name: str, provider: ServiceProvider) -> None:
        """Register a service provider."""
        self._providers[service_name] = provider
        
    def register_factory(self, service_name: str, factory: Callable[['ServiceContainer'], Any], singleton: bool = True) -> None:
        """Register a factory function for creating a service."""
        provider = SingletonProvider(factory) if singleton else FactoryProvider(factory)
        self.register(service_name, provider)
        
    def register_instance(self, service_name: str, instance: Any) -> None:
        """Register an existing instance."""
        self._instances[service_name] = instance
        
    def get(self, service_name: str) -> Optional[Any]:
        """Get a service instance."""
        # First check for existing instances
        if service_name in self._instances:
            return self._instances[service_name]
            
        # Then try to create from provider
        if service_name in self._providers:
            instance = self._providers[service_name].provide(self)
            return instance
            
        return None

def create_default_container(project_loader) -> ServiceContainer:
    """Create a container with default service configuration."""
    from src.dxf_exporter.style_manager import StyleManager
    from src.dxf_exporter.layer_manager import LayerManager
    
    container = ServiceContainer()
    
    # Register project loader
    container.register_instance('project_loader', project_loader)
    
    # Register style manager factory
    def style_manager_factory(container):
        return StyleManager(container.get('project_loader'))
    container.register_factory('style_manager', style_manager_factory)
    
    # Register layer manager factory
    def layer_manager_factory(container):
        return LayerManager(
            container.get('project_loader'),
            container.get('style_manager')
        )
    container.register_factory('layer_manager', layer_manager_factory)
    
    return container 