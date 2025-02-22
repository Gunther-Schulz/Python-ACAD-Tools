# Component Boundaries

## Overview
This document outlines the strict rules and guidelines for maintaining clear boundaries between components in the Python ACAD Tools project.

## Related Documents
- [Code Quality Guidelines](CODE_QUALITY.md) - General code quality standards
- [Testing Guidelines](TESTING.md) - Testing requirements
- [Logging Guidelines](LOGGING.md) - Logging standards
- [INDEX](../INDEX.md) - Documentation index

## Version Applicability
- Python Version: 3.12+
- Last Updated: 2024-02-22
- Status: Draft

## Dependencies
- Static type checkers (mypy, pyright)
- Runtime type validation (beartype)
- Component dependency management
- Testing frameworks

## Core Principles

1. **Type Safety**
   - Strict static type checking with mypy and pyright
   - Runtime type validation with beartype
   - Protocol-based interfaces with runtime checks
   - No implicit type conversions
   - Type annotations for all public APIs
   - Clear interface contracts
   - Runtime type validation at boundaries

2. **Component Independence**
   - Components are independently testable
   - Components have clear interfaces
   - Components are loosely coupled
   - Components are highly cohesive
   - Maximum complexity of 10 (McCabe)
   - No circular dependencies
   - Clear contract boundaries

3. **Dependency Direction**
   - Dependencies flow inward toward core
   - No circular dependencies
   - No cross-component dependencies
   - Clear dependency boundaries
   - All dependencies through dependency injection
   - No direct service instantiation

## Import Rules

### Component Boundary Rules
- Each component is a sealed boundary
- No imports from internal component structure
- Only import from component's public types
- No reaching into other components' implementation details
- Components communicate only through their public interfaces

### Component Import Structure
```
src/
├── core/           # Core component
│   ├── types/     # Public types (importable)
│   ├── internal/  # Internal implementation (not importable)
│   └── ...
├── geometry/       # Geometry component
│   ├── types/     # Public types (importable)
│   ├── internal/  # Internal implementation (not importable)
│   └── ...
└── export/        # Export component
    ├── types/     # Public types (importable)
    ├── internal/  # Internal implementation (not importable)
    └── ...
```

### Configuration Maintenance
When adding new modules to the project:

1. **Update Type Checking Configuration**
   - Add new module paths to mypy configuration in `pyproject.toml`
   - Configure appropriate type checking strictness level
   - Ensure proper import rules are enforced
   - Add any necessary type checking overrides
   - Configure runtime type evaluation for base classes
   - Set up strict type checking mode

2. **Import Linting Rules**
   - Update import-linter contracts for new modules
   - Configure module boundaries and dependencies
   - Ensure proper layering is maintained
   - Add any necessary import exceptions
   - Ban relative imports project-wide
   - Enforce component isolation

Example configuration update for a new module:
```toml
# Type checking configuration
[[tool.mypy.overrides]]
module = "src.new_module.types.*"
disallow_any_explicit = false
implicit_reexport = true

# Runtime type evaluation
[tool.ruff.lint.flake8-type-checking]
strict = true
runtime-evaluated-base-classes = [
    "BaseModel",
    "Protocol",
    "TypedDict",
    "BaseConfigManager",
    "BaseGeometryManager",
    "BaseExportManager"
]

# Import rules
[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.importlinter]
[[tool.importlinter.contracts]]
name = "new-module"
type = "independence"
modules = ["src.new_module"]
```

### Allowed Imports
```python
# Required in all files
from __future__ import annotations

# Standard library imports
from typing import Any
from pathlib import Path

# Third-party imports through dependencies
from src.core.dependencies import numpy, shapely

# Core types through core.types
from src.core.types import CoreType

# Component types through component types
from src.geometry.types import GeometryType

# Implementations through dependencies
from src.geometry.dependencies import get_geometry_manager

# CORRECT: Import from component's public types
from src.geometry.types import Layer
from src.export.types import Exporter
```

### Forbidden Imports
```python
# NO relative imports
from . import module  # FORBIDDEN

# NO direct implementation imports
from src.geometry.implementations.manager import GeometryManager  # FORBIDDEN

# NO cross-component implementation imports
from src.export.implementations import ExportManager  # FORBIDDEN

# NO internal module imports
from src.geometry.internal import internal_function  # FORBIDDEN

# NO direct service/repository access
from src.services.geometry import GeometryService  # FORBIDDEN

# NO deep imports into other components
from src.geometry.pipeline.processor import GeometryProcessor  # FORBIDDEN
from src.export.formats.dxf.style import DXFStyle  # FORBIDDEN
from src.config.validators.schema import SchemaValidator  # FORBIDDEN

# NO imports from implementation details
from src.geometry.internal.utils import geometry_helper  # FORBIDDEN
from src.export.internal.converters import format_converter  # FORBIDDEN
```

### Component Access Rules
1. **Public Interface**
   - Components expose public types through `types/` directory
   - Components expose public protocols in `types/`
   - All inter-component communication through public interfaces
   - No access to internal implementation details

2. **Implementation Privacy**
   - Implementation details in `internal/` directory
   - Internal utilities not exposed outside component
   - Internal types not exposed outside component
   - Implementation details not importable from outside

3. **Dependency Management**
   - Dependencies declared in component's `dependencies.py`
   - Services accessed through dependency injection
   - Implementations accessed through factories
   - No direct instantiation of internal types

4. **Type Safety**
   - Public interfaces use protocol types
   - Implementation details hidden behind interfaces
   - Type checking enforced at boundaries
   - No leaking of implementation types

## Component Structure

### Core Component
```
src/core/
├── types/           # Core type definitions and protocols
│   ├── base.py     # Base protocols
│   ├── style.py    # Style protocols
│   ├── geometry.py # Geometry protocols
│   └── export.py   # Export protocols
├── protocols/       # Core interfaces
├── errors/         # Error definitions
└── utils/          # Core utilities
```

**Rules**:
- Core types imported through `core.types`
- Core utilities imported through `core.utils`
- No business logic in core
- No external dependencies in core types
- Protocols define clear boundaries
- Type safety enforced at boundaries
- Maximum complexity of 10
- Google-style docstrings required
- No implicit string concatenation
- Double quotes for strings

### Style System
```
src/style/
├── types/           # Style type definitions
├── manager/         # Style management
│   ├── registry.py # Style registry
│   └── provider.py # Style provider
├── converters/      # Format converters
└── validators/      # Style validators
```

**Rules**:
- Styles are immutable
- Style conversion happens in exporters
- No direct style manipulation
- Clear style inheritance chain
- Format-specific conversion isolated
- All services through dependency injection
- Type annotations for all public methods
- Runtime type validation

### Geometry Processing
```
src/geometry/
├── types/           # Geometry types
├── pipeline/        # Processing pipeline
│   ├── processor.py # Geometry processor
│   ├── validator.py # Geometry validator
│   └── optimizer.py # Geometry optimizer
├── operations/      # Geometry operations
└── context/        # Processing context
```

**Rules**:
- Processing happens through pipeline
- Operations are registered
- Validation before and after processing
- Optimization is format-aware
- Clear processing context
- No direct access to implementations
- Services accessed through dependency injection
- Type safety at component boundaries

### Component System
```
src/drawing/
├── types/           # Component types
├── factory/         # Component factories
├── registry/        # Component registry
└── lifecycle/      # Component lifecycle
```

**Rules**:
- Components created through factories
- Registry manages lifecycle
- Dependencies clearly declared
- Resources properly managed
- Format-specific rendering isolated
- No direct instantiation
- Clear dependency declaration
- Type-safe interfaces

### Export System
```
src/export/
├── types/           # Export types
├── manager/         # Export management
├── optimizers/      # Format optimizers
├── validators/      # Format validators
└── formats/        # Format implementations
```

**Rules**:
- Export happens through manager
- Format-specific code isolated
- Pre/post validation required
- Optimization is optional
- Clear error boundaries
- Type-safe interfaces
- No direct format access
- Services through dependency injection

## Dependency Management

### The Role of dependencies.py
```python
# Example dependencies.py structure
"""Component dependencies module.

This module serves as the single source of truth for all external dependencies
and implementation details of a component. It provides:
1. Access to implementations through factory functions
2. Registration of dependencies for dependency injection
3. Configuration of component services
4. Export of public interfaces
"""

from typing import Any
from dependency_injector import containers, providers

# Import implementations (only place allowed to do so)
from src.geometry.internal.layer import LayerImpl
from src.geometry.internal.processor import ProcessorImpl

# Import public interfaces
from src.geometry.types import Layer, Processor

class GeometryContainer(containers.DeclarativeContainer):
    """Geometry component dependency container."""

    # Configure external dependencies
    config = providers.Configuration()

    # Register implementations
    layer_factory = providers.Factory(LayerImpl)
    processor_factory = providers.Factory(ProcessorImpl)

    # Register services
    geometry_service = providers.Singleton(
        GeometryServiceImpl,
        layer_factory=layer_factory,
        processor_factory=processor_factory
    )

# Public factory functions
def get_layer_provider() -> Provider[Layer]:
    """Get layer provider."""
    return container.layer_factory

def get_processor() -> Processor:
    """Get geometry processor instance."""
    return container.processor_factory()

def get_geometry_service() -> GeometryService:
    """Get geometry service instance."""
    return container.geometry_service()
```

### Purpose and Rules
1. **Single Source of Truth**
   - Only place allowed to import implementations
   - Only place allowed to instantiate services
   - Only place allowed to configure dependencies
   - Only place allowed to wire up dependency injection

2. **Implementation Hiding**
   - Hides implementation details from consumers
   - Exposes only public interfaces
   - Manages component lifecycle
   - Handles dependency configuration

3. **Dependency Injection**
   - Configures dependency injection container
   - Registers component services
   - Manages service lifecycle
   - Handles dependency resolution

4. **Factory Functions**
   - Provides factory functions for public types
   - Returns interface types only
   - Handles implementation instantiation
   - Manages dependency injection

### Usage Examples
```python
# CORRECT: Access through dependencies.py
from src.geometry.dependencies import get_layer_provider
from src.geometry.dependencies import get_geometry_service

# Get implementations through factories
layer_provider = get_layer_provider()
layer = layer_provider()  # Returns Layer protocol type

# Get services through dependency injection
geometry_service = get_geometry_service()  # Returns GeometryService protocol type
```

### Benefits
1. **Encapsulation**
   - Implementation details hidden
   - Dependencies centralized
   - Configuration isolated
   - Service lifecycle managed

2. **Testability**
   - Easy to mock dependencies
   - Clear dependency boundaries
   - Isolated testing possible
   - Configuration injectable

3. **Maintainability**
   - Single place for changes
   - Clear dependency graph
   - Easy to update implementations
   - Easy to add new dependencies

4. **Type Safety**
   - Interface types enforced
   - Implementation details hidden
   - Dependency injection typed
   - Factory functions typed

## Code Quality Requirements

### Documentation
- Google-style docstrings required
- Type hints in docstrings
- Maximum line length of 100 characters
- Clear parameter documentation
- Return type documentation
- Error documentation
- Example usage in docstrings

### Type Safety
- Runtime type checking with beartype
- Static type checking with mypy/pyright
- Protocol-based interfaces
- No implicit conversions
- Clear type exports
- Type validation at boundaries

### Code Style
- Maximum complexity of 10
- No relative imports
- Double quotes for strings
- Clear error handling
- Proper logging format
- No print statements
- Proper path handling
- Clear naming conventions

### Testing
- Unit tests for components
- Integration tests for boundaries
- Type checking in tests
- Mock external dependencies
- Clear test documentation
- Test isolation
- Coverage requirements

## Error Handling

### Error Types
- Define component-specific errors
- Inherit from core errors
- Clear error hierarchies
- Meaningful error messages
- Type-safe error handling
- Error context preservation

### Error Boundaries
- Handle errors at component boundaries
- Convert internal errors
- Maintain error context
- Log boundary errors
- Type-safe error conversion
- Clear error documentation

## Implementation Guidelines

### Type Definitions
```python
# In src/geometry/types/layer.py
from src.core.types import Protocol

class Layer(Protocol):
    """Layer interface.

    Attributes:
        name: Layer name
        geometry: Layer geometry
    """
    def get_geometry(self) -> GeometryData:
        """Get layer geometry.

        Returns:
            Layer geometry data

        Raises:
            GeometryError: If geometry is invalid
        """
        ...
```

### Dependency Registration
```python
# In src/geometry/dependencies.py
from src.core.types import Provider
from src.geometry.types import Layer
from src.geometry.implementations.layer import LayerImpl

def get_layer_provider() -> Provider[Layer]:
    """Get layer provider.

    Returns:
        Layer provider instance
    """
    return Provider(LayerImpl)
```

## Quality Gates

### Static Analysis
- Ruff linting passes
- Mypy type checking passes
- Pyright type checking passes
- Pylint validation passes
- Import order validation
- Complexity checks
- Dead code detection

### Runtime Checks
- Beartype type validation
- Protocol runtime checks
- Dependency validation
- Resource cleanup
- Memory management
- Performance monitoring

### Documentation
- Docstring coverage >80%
- Google style validation
- Type hint validation
- Example validation
- API documentation
- Clear usage guides

## Type Management

### Type Export Structure
```python
# src/geometry/types/__init__.py
"""Geometry component public types.

This module exports all public types for the geometry component.
ONLY export types that are part of the public interface.
"""
from __future__ import annotations

# Re-export public protocols and types
from .base import (
    GeometryProtocol,
    GeometryProvider,
    GeometryProcessor,
)
from .layer import (
    Layer,
    LayerProtocol,
    LayerProvider,
)
from .operation import (
    Operation,
    OperationProtocol,
    OperationContext,
)

# Export type aliases
from .types import (
    GeometryData,
    LayerName,
    OperationName,
)

__all__ = [
    # Protocols
    "GeometryProtocol",
    "GeometryProvider",
    "GeometryProcessor",
    "Layer",
    "LayerProtocol",
    "LayerProvider",
    "Operation",
    "OperationProtocol",
    "OperationContext",
    # Type aliases
    "GeometryData",
    "LayerName",
    "OperationName",
]
```

### Type Import Rules

1. **Core Types**
```python
# CORRECT: Import from core.types
from src.core.types import BaseProtocol, Result, Error

# FORBIDDEN: Direct import from core implementation
from src.core.internal.types import InternalType  # FORBIDDEN
```

2. **Component Types**
```python
# CORRECT: Import from component types package
from src.geometry.types import Layer, GeometryData
from src.export.types import Exporter, ExportFormat

# FORBIDDEN: Import from internal modules
from src.geometry.internal.types import InternalLayer  # FORBIDDEN
from src.geometry.pipeline.types import PipelineType  # FORBIDDEN
```

3. **Implementation Types**
```python
# CORRECT: Only in dependencies.py
from src.geometry.internal.layer import LayerImpl  # Only in dependencies.py

# FORBIDDEN: Anywhere else
from src.geometry.implementations import LayerImpl  # FORBIDDEN
```

### Type Boundary Rules

1. **Type Visibility**
   - Public types exported through `types/__init__.py`
   - Implementation types stay in `internal/`
   - No leaking of implementation types
   - Clear separation of public/private types

2. **Type Dependencies**
   - Core types have no external dependencies
   - Component types may depend on core types
   - No circular type dependencies
   - Clear type dependency direction

3. **Protocol Boundaries**
   ```python
   # In src/geometry/types/layer.py
   from src.core.types import Protocol, GeometryData

   class LayerProtocol(Protocol):
       """Public layer interface."""
       def get_geometry(self) -> GeometryData: ...
       def process(self) -> None: ...

   # Type alias for public use
   Layer = LayerProtocol  # More friendly name for public API
   ```

4. **Type Exports**
   ```python
   # In src/geometry/types/types.py
   """Public type definitions for geometry component."""
   from typing import NewType

   # Public type aliases
   LayerName = NewType("LayerName", str)
   OperationName = NewType("OperationName", str)

   # Public type definitions
   GeometryData = dict[str, Any]  # Public type
   ```

### Type Safety at Boundaries

1. **Interface Types**
   ```python
   # Public interface in types/
   class GeometryProcessor(Protocol):
       """Public geometry processor interface."""
       def process(self, data: GeometryData) -> Result: ...

   # Implementation in internal/
   class GeometryProcessorImpl:
       """Internal implementation."""
       def process(self, data: GeometryData) -> Result:
           # Implementation details
           ...
   ```

2. **Factory Functions**
   ```python
   # In dependencies.py
   def get_processor() -> GeometryProcessor:  # Return protocol type
       """Get geometry processor instance."""
       return GeometryProcessorImpl()  # Return implementation
   ```

3. **Type Conversion**
   ```python
   # At component boundaries
   def convert_to_public(internal: InternalType) -> PublicType:
       """Convert internal type to public interface."""
       return PublicType(
           id=internal.id,
           data=internal.get_public_data()
       )
   ```

### Type Documentation

1. **Public Types**
   ```python
   class LayerProtocol(Protocol):
       """Public layer interface.

       This protocol defines the public interface for geometry layers.
       All layer implementations must conform to this interface.

       Attributes:
           name: Layer name
           geometry: Layer geometry data
       """
       def get_geometry(self) -> GeometryData:
           """Get layer geometry.

           Returns:
               GeometryData: Layer geometry in standard format

           Raises:
               GeometryError: If geometry is invalid
           """
           ...
   ```

2. **Type Aliases**
   ```python
   # Clear documentation for type aliases
   LayerName = NewType("LayerName", str)
   """Type-safe layer name identifier.

   This type ensures layer names are not confused with other string types.
   Must be a valid identifier string matching [a-zA-Z][a-zA-Z0-9_]*.
   """
   ```

### Type Validation

1. **Runtime Checks**
   ```python
   # Validate types at runtime
   @beartype
   def process_layer(layer: Layer) -> Result:
       """Process layer with runtime type checking."""
       assert isinstance(layer, Layer), "Invalid layer type"
       return layer.process()
   ```

2. **Static Analysis**
   ```python
   # Enable strict type checking
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       # Type checking specific imports
       from src.geometry.types import StrictType
   ```
