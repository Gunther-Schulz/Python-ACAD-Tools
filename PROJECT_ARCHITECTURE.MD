# Project Architecture: Python-ACAD-Tools (Implemented)

**Version:** 2.0
**Date:** December 2024
**Status:** Production Ready

## 1. Introduction

This document outlines the implemented architectural design for the refactored `src/` directory of the Python-ACAD-Tools project. The architecture has been fully modernized with enterprise-grade patterns including Dependency Injection, Command Pattern, Factory Pattern, and Adapter Pattern.

The refactoring effort successfully eliminated technical debt and created a robust, maintainable foundation with strict boundaries, comprehensive interfaces, and production-ready patterns.

## 2. Guiding Principles & Standards Compliance

This architecture fully adheres to the principles outlined in `PROJECT_STANDARDS.MD`:

*   **✅ Clear Boundaries & Separation of Concerns:** All modules have well-defined responsibilities with no circular dependencies.
*   **✅ Domain Models as Single Source of Truth:** All data structures use Pydantic V2 models in the `src.domain` module.
*   **✅ Pydantic V2 Mandate:** All data validation, serialization, and configuration uses Pydantic V2.
*   **✅ Protocol-Based Interfaces:** All major components use `typing.Protocol` for loose coupling.
*   **✅ Dependency Injection (DI):** Comprehensive DI container manages all object creation and wiring.
*   **✅ Upfront Configuration:** Application configuration loaded into Pydantic V2 `AppConfig` at startup.
*   **✅ Stateless Utilities:** Pure functions in dedicated utility modules.
*   **✅ Enterprise Patterns:** Command, Factory, and Adapter patterns implemented.

## 3. Implemented Module Structure (src/)

### Core Architecture Modules

*   **`src.domain`**:
    *   **Responsibility:** Pydantic V2 models for all data structures, enums, constants, and exceptions.
    *   **Key Files:**
        *   `config_models.py` - Application configuration models
        *   `project_models.py` - Project and layer configuration models
        *   `style_models.py` - CAD styling and rendering models
        *   `geometry_models.py` - Geometric data structures
        *   `exceptions.py` - Complete exception hierarchy
        *   `config_validation.py` - Configuration validation schemas and services
    *   **Dependencies:** None (domain is dependency-free)

*   **`src.interfaces`**:
    *   **Responsibility:** Protocol definitions for all major services and components.
    *   **Key Interfaces:**
        *   `ILoggingService` - Logging abstraction
        *   `IConfigLoader` - Configuration loading
        *   `IDataSourceService` - Data source management
        *   `IGeometryProcessor` - Geometry operations
        *   `IStyleApplicator` - Style application
        *   `IDataExporter` - Data export operations
        *   `IResourceManager` - Resource lifecycle management
        *   `IConfigValidation` - Configuration validation
        *   `IOperationRegistry` - Operation registry management
        *   `IDXFAdapter` - DXF library adapter abstraction
    *   **Dependencies:** Only `src.domain` for type hints

*   **`src.core`**:
    *   **Responsibility:** Application orchestration, DI container, and core infrastructure.
    *   **Key Components:**
        *   `container.py` - Dependency injection container using `dependency-injector`
        *   `factories.py` - Factory pattern implementations with validation
    *   **Dependencies:** All service interfaces and implementations

### Service Layer

*   **`src.services`**:
    *   **Responsibility:** Business logic implementations of all interfaces.
    *   **Sub-packages:**
        *   `operations/` - Geometry operation handlers and registry
    *   **Key Services:**
        *   `LoggingService` - Implements `ILoggingService`
        *   `ConfigLoaderService` - Implements `IConfigLoader`
        *   `DataSourceService` - Implements `IDataSourceService`
        *   `GeometryProcessorService` - Implements `IGeometryProcessor`
        *   `StyleApplicatorService` - Implements `IStyleApplicator`
        *   `DataExporterService` - Implements `IDataExporter`
        *   `ProjectOrchestratorService` - Main workflow orchestration
        *   `ResourceManagerService` - Implements `IResourceManager`
    *   **Dependencies:** `src.interfaces`, `src.domain`, `src.utils`

### Infrastructure Layer

*   **`src.adapters`**:
    *   **Responsibility:** External library integration with proper abstraction.
    *   **Key Adapters:**
        *   `EzdxfAdapter` - Implements `IDXFAdapter` for ezdxf library
    *   **Dependencies:** `src.interfaces`, external libraries

*   **`src.cli`**:
    *   **Responsibility:** Command-line interface using Command Pattern.
    *   **Key Components:**
        *   `commands.py` - Command pattern implementations
        *   `main_cli.py` - CLI entry point with DI integration
    *   **Dependencies:** `src.core`, `src.interfaces`

*   **`src.config`**:
    *   **Responsibility:** Application configuration management.
    *   **Dependencies:** `src.domain` models

*   **`src.utils`**:
    *   **Responsibility:** Stateless utility functions.
    *   **Dependencies:** Minimal, primarily `src.domain` for types

## 4. Dependency Injection Architecture

### DI Container (`src.core.container.ApplicationContainer`)

```python
# Singleton Services
logging_service = providers.Singleton(LoggingService)
resource_manager = providers.Singleton(ResourceManagerService, logger_service=logging_service)
config_validation = providers.Singleton(ConfigValidationService)

# Factories and Registries
service_factory = providers.Singleton(ServiceFactory, logger_service=logging_service)
handler_factory = providers.Singleton(HandlerFactory, logger_service=logging_service)
factory_registry = providers.Singleton(FactoryRegistry, logger_service=logging_service)

# Adapters
dxf_adapter = providers.Singleton(EzdxfAdapter, logger_service=logging_service)

# Business Services with Dependency Injection
config_loader = providers.Singleton(ConfigLoaderService, logger_service=logging_service, app_config=config.app_config)
data_source = providers.Singleton(DataSourceService, logger_service=logging_service)
operation_registry = providers.Singleton(OperationRegistry, logger_service=logging_service, data_source_service=data_source)
```

### Dependency Flow
1. **CLI** → **DI Container** → **Commands** → **Services** → **Adapters**
2. All dependencies injected at application startup
3. No manual service instantiation
4. Clear separation of concerns maintained

## 5. Implemented Design Patterns

### Command Pattern (`src.cli.commands`)

```python
# Abstract base command
class BaseCommand(ABC):
    @abstractmethod
    def execute(self) -> int: ...

# Concrete command implementations
class ProcessProjectCommand(BaseCommand):
    def __init__(self, project_orchestrator: IProjectOrchestrator, ...):
        # Dependencies injected via DI container

# Command registry for extensibility
class CommandRegistry:
    def register_command(self, name: str, command_class: Type[BaseCommand]): ...
    def get_command(self, name: str) -> BaseCommand: ...
```

### Factory Pattern (`src.core.factories`)

```python
# Factory protocol
class IFactory(Protocol):
    def create(self, component_type: str, **kwargs) -> Any: ...
    def register(self, component_type: str, component_class: Type) -> None: ...

# Concrete factory implementations
class ServiceFactory(BaseFactory): ...
class HandlerFactory(BaseFactory): ...

# Central factory registry
class FactoryRegistry:
    def register_factory(self, factory_type: str, factory: IFactory): ...
    def get_factory(self, factory_type: str) -> IFactory: ...
```

### Adapter Pattern (`src.adapters`)

```python
# Adapter interface
class IDXFAdapter(Protocol):
    def load_dxf_file(self, file_path: str) -> Optional[Any]: ...
    def extract_entities_from_layer(self, dxf_document: Any, layer_name: str, crs: str) -> Optional[gpd.GeoDataFrame]: ...
    def save_dxf_file(self, dxf_document: Any, file_path: str) -> None: ...

# Concrete adapter implementation
class EzdxfAdapter(IDXFAdapter):
    # Wraps ezdxf library with application-specific interface
```

## 6. Data Modeling with Pydantic V2

### Configuration Models (`src.domain.config_models`)
```python
class AppConfig(BaseSettings):
    model_config = ConfigDict(env_prefix="ACAD_")

class ProjectConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

class LayerConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
```

### Validation Strategy (`src.domain.config_validation`)
*   **ConfigValidationService** implements `IConfigValidation`
*   **ValidationRegistry** for common validation patterns
*   **ConfigValidators** for reusable validation functions
*   **CrossFieldValidator** for inter-field validation

## 7. Error Handling Strategy

### Exception Hierarchy (`src.domain.exceptions`)
```python
ApplicationBaseException (base)
├── ConfigError
│   └── ConfigValidationError
├── ProcessingError
│   ├── DXFProcessingError
│   ├── GeometryError
│   └── DataSourceError
```

### Error Handling Patterns
*   Services raise specific domain exceptions
*   Adapters translate external library exceptions
*   CLI commands handle exceptions and return appropriate exit codes
*   Comprehensive logging with error context

## 8. Dependencies and Requirements

### Core Dependencies
```txt
# Dependency Injection and Configuration
dependency-injector==4.41.0
pydantic==2.10.0
pydantic-settings==2.7.0

# Geometric and GIS Operations
geopandas==1.0.1
shapely==2.0.6
pyproj==3.6.1
fiona==1.10.1

# CAD/DXF Operations
ezdxf==1.3.3

# Data Processing
pandas==2.2.3
numpy==2.1.1

# CLI and Utilities
click==8.1.7
PyYAML==6.0.2
```

## 9. Module Interaction Diagram

```
CLI Layer:
  main_cli.py → commands.py → DI Container

Core Layer:
  container.py ↔ factories.py

Service Layer:
  All services implement interfaces and use DI
  ProjectOrchestratorService orchestrates workflows

Adapter Layer:
  EzdxfAdapter wraps external ezdxf library

Domain Layer:
  Models, exceptions, validation (dependency-free)
```

## 10. Key Architectural Achievements

### ✅ Dependency Injection
*   Central DI container manages all dependencies
*   No manual service instantiation
*   Testable and mockable components

### ✅ Interface Segregation
*   11 focused Protocol interfaces
*   Clear contracts between components
*   Loose coupling throughout

### ✅ Command Pattern
*   Extensible CLI command system
*   Clean separation of CLI from business logic
*   Dependency injection in commands

### ✅ Factory Pattern
*   Validated component creation
*   Registry pattern for extensibility
*   Centralized factory management

### ✅ Adapter Pattern
*   External library abstraction
*   Testable without external dependencies
*   Consistent error handling

### ✅ Exception Handling
*   Comprehensive exception hierarchy
*   Domain-specific error types
*   Consistent error reporting

## 11. Testing Strategy

*   **Unit Tests:** Mock interfaces for isolated testing
*   **Integration Tests:** Test service interactions via DI
*   **Contract Tests:** Validate interface implementations
*   **CLI Tests:** Test command execution and error handling

## 12. Future Extensibility

The architecture supports:
*   **New Operations:** Register handlers via HandlerFactory
*   **New Commands:** Register via CommandRegistry
*   **New Adapters:** Implement adapter interfaces
*   **New Services:** Register in DI container
*   **Configuration Extensions:** Add Pydantic models

## 13. Document Evolution

This document reflects the production-ready architecture as of December 2024. All critical architecture issues have been resolved, and the system is ready for production deployment with enterprise-grade patterns and practices.
