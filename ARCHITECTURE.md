# Project Architecture

## Overview

This document outlines the architecture for the Python ACAD Tools project, which consists of three main components:

1. Configuration Management
2. Geometry Processing
3. DXF Export

## Development Environment

The project uses a modern Python development setup:

1. **Environment Management**
   - Conda for environment and package management
   - Python 3.12 as the base interpreter
   - Centralized dependency management via `environment.yml`

2. **Code Quality Tools**
   - Centralized tool configuration in `pyproject.toml`
   - Black for code formatting
   - Flake8 for style checking
   - MyPy for strict type checking
   - Pylint for static analysis
   - isort for import organization
   - Pre-commit hooks for automated checks

3. **IDE Integration**
   - Cursor IDE with integrated linting and formatting
   - Real-time type checking and error detection
   - Automated code formatting on save

## Legacy Code Integration

The project will maintain compatibility with existing DXF manipulation code from the original implementation (`src_old/`), particularly for ezdxf-specific patterns and optimizations.

### Component Mapping:
Old Component -> New Component
- src_old/dxf/ -> src/export/dxf/
- src_old/layer_processor/ -> src/geometry/layers/
- src_old/operations/ -> src/geometry/operations/
- src_old/geo/ -> src/geometry/types/
- src_old/preprocessors/ -> src/config/
- src_old/dxf_utils/ -> src/export/utils/
- src_old/dxf_exporter/ -> src/export/

### Key Areas to Reference:
1. **DXF Manipulation**
   - Reference `src_old/dxf/` for ezdxf-specific patterns
   - Maintain existing DXF entity creation methods
   - Keep optimized DXF writing strategies

2. **Layer Processing**
   - Study `src_old/layer_processor/` for layer handling patterns
   - Preserve efficient layer update mechanisms
   - Keep compatibility with existing layer styles

3. **Export Optimizations**
   - Reference `src_old/dxf_exporter/` for optimized export patterns
   - Maintain batch processing strategies
   - Keep memory optimization techniques

### Integration Strategy:
1. **Review and Document**
   - Document existing DXF manipulation patterns
   - Identify critical optimizations
   - Map dependencies and requirements

2. **Refactor and Integrate**
   - Extract core functionality
   - Modernize code structure
   - Maintain performance optimizations

3. **Test and Validate**
   - Ensure compatibility with existing files
   - Verify performance characteristics
   - Maintain optimization levels

### Implementation Status
- Core Components ✓
  - [x] Type definitions
  - [x] Project coordinator
  - [x] Style manager
  - [x] Utilities
  - [x] Basic error handling
  - [x] Development environment setup
  - [x] Tool configuration integration
- Configuration Management (Complete)
  - [x] Basic config loading
  - [x] Schema validation
  - [x] Style configuration
  - [x] Project configuration
  - [x] Geometry layer configuration
  - [x] Color configuration and ACI colors
  - [x] Specialized configurations (viewport, legend, etc.)
  - [x] Type validation and checking
  - [ ] Complete test coverage
- Geometry Processing (In Progress)
  - [x] Base geometry types
  - [x] Basic geometry manager
  - [x] Operations framework implementation
      - [x] Operation base classes (Unary, Binary, Multi)
      - [x] Operation context and results
      - [x] Parameter validation framework
      - [x] Error handling and propagation
      - [x] Type safety improvements
  - [ ] Individual operations
      - [x] Buffer operation
          - [x] Operation implementation
          - [x] Parameter validation
          - [x] Unit tests
          - [x] Integration tests
          - [x] Type safety
      - [ ] Intersection/Union/Difference
      - [ ] Dissolve/Merge
      - [ ] Filter operations
      - [ ] Clean/Repair operations
  - [x] Layer management
      - [x] Layer validation
      - [x] Layer processing
      - [x] Dependency handling
      - [x] Type safety
- Export System (In Progress)
  - [x] Basic export manager
  - [x] Interface definitions
  - [ ] DXF export implementation
  - [ ] Shapefile export implementation
  - [ ] Style application
  - [ ] Layer management

## Implementation Strategy

The project will be implemented following these principles:

1. **Test-Driven Development**
   - Write tests first for each component
   - Implement minimal functionality to make tests pass
   - Refactor and improve implementation
   - Maintain high test coverage (target: >90%)

2. **Component Independence**
   - Each component should be independently testable
   - Clear boundaries between components
   - Well-defined APIs for inter-component communication
   - Minimal dependencies between components

3. **Implementation Order**
   ```
   1. Core Components (DONE)
      ✓ Type definitions
      ✓ Utility functions
      ✓ Project coordinator
      ✓ Basic tests

   2. Configuration Management
      - Schema definitions
      - YAML loading and validation
      - Configuration objects
      - Tests for each config type

   3. Geometry Processing
      - Base geometry types
      - Operation framework
      - Individual operations
      - Layer management
      - Tests for each operation

   4. Export System
      - Style management
      - Layer management
      - DXF export
      - Tests for each export feature
   ```

## Directory Structure

```
.
├── src/                          # New implementation
│   ├── config/                   # Configuration management
│   │   ├── schemas/             # JSON schemas for validation
│   │   ├── config_manager.py    # Main configuration manager
│   │   ├── project_config.py    # Project configuration
│   │   ├── style_config.py      # Style configuration
│   │   ├── color_config.py      # Color configuration
│   │   ├── aci_colors.yaml      # AutoCAD color definitions
│   │   ├── geometry_layer_config.py  # Geometry layer config
│   │   ├── block_insert_config.py    # Block insertion config
│   │   ├── legend_config.py          # Legend configuration
│   │   ├── path_array_config.py      # Path array config
│   │   ├── position_config.py        # Position config
│   │   ├── text_insert_config.py     # Text insertion config
│   │   ├── viewport_config.py        # Viewport config
│   │   └── web_service_config.py     # Web service config
│   ├── geometry/                 # Geometry processing
│   │   ├── operations/          # Geometric operations
│   │   ├── layers/              # Layer management
│   │   ├── types/              # Geometry type definitions
│   │   ├── geometry_manager.py  # Geometry processing coordinator
│   │   └── __init__.py
│   ├── export/                   # Export functionality
│   │   ├── interfaces/         # Export interfaces
│   │   ├── dxf/               # DXF-specific functionality
│   │   ├── shapefile/         # Shapefile export
│   │   ├── utils/             # Export utilities
│   │   ├── manager.py         # Export coordination
│   │   ├── style_manager.py   # Style application
│   │   └── layer_manager.py   # Export layer management
│   ├── core/                     # Core functionality
│   │   ├── project.py         # Project coordinator
│   │   ├── types.py          # Type definitions
│   │   ├── utils.py          # Utilities
│   │   ├── style_manager.py  # Style management
│   │   └── __init__.py
│   └── __init__.py
├── src_old/                      # Legacy implementation (for reference)
│   ├── core/
│   ├── dxf_exporter/
│   ├── dxf_utils/
│   ├── layer_processor/
│   ├── operations/
│   ├── geo/
│   ├── preprocessors/
│   ├── dxf/
│   └── main.py
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── conftest.py              # pytest configuration
│   ├── test_config/            # Configuration tests
│   ├── test_geometry/          # Geometry processing tests
│   └── test_export/            # Export functionality tests
├── examples/                      # Example projects and usage
│   ├── simple_project/
│   └── complex_project/
├── docs/                         # Documentation
│   ├── api/
│   ├── guides/
│   └── examples/
├── requirements.txt              # Project dependencies
├── setup.py                     # Package installation
├── README.md                    # Project documentation
└── ARCHITECTURE.md              # This file
```

## Migration Strategy

The migration process is designed to be incremental and continuous, with testing integrated at every step. Each component can be developed, tested, and validated independently due to the modular architecture.

### Phase 1: Core Infrastructure (Continuous)
- Set up new project structure ✓
- Implement basic configuration system
- Create geometry type system
- **Testing Focus:**
  - Unit tests for each core component
  - Integration tests between core components
  - API stability tests

### Phase 2: Component Migration (Parallel Development)
Each component can be developed and tested independently:

1. **Configuration System**
   - Implement new config loading
   - Add validation
   - Test against existing configs
   - Validate backwards compatibility

2. **Geometry Processing**
   - Implement new geometry types
   - Port operations one by one
   - Test each operation independently
   - Compare results with old implementation

3. **Export System**
   - Create new DXF export system
   - Port optimizations
   - Test export functionality
   - Validate output consistency

**Continuous Testing Throughout:**
- Unit tests for new components
- Integration tests with existing components
- Performance benchmarks
- Compatibility validation
- API consistency checks

### Phase 3: Legacy Code Retirement (Gradual)
As new components are validated:
- Mark old components as deprecated
- Update documentation
- Remove unused code
- Maintain backwards compatibility where needed

## Error Handling Strategy

### Error Categories
- Configuration Errors
- Geometry Processing Errors
- Export Errors
- Validation Errors

### Error Propagation
- Component-level error handling
- Error aggregation
- User-friendly error messages

## Component APIs

### 1. Core Components

The core module provides the foundation of the application:

#### Key Components:
1. **Project Coordinator** (`core/project.py`)
   - Application central coordinator
   - Component initialization and management
   - Workflow orchestration
   - Error handling and logging

2. **Type System** (`core/types.py`)
   - Core data structures and protocols
   - Type hints and runtime checking
   - Interface definitions
   - Data transfer objects

3. **Style Manager** (`core/style_manager.py`)
   - Style configuration management
   - Style validation
   - Style application coordination
   - Style transformation

4. **Utilities** (`core/utils.py`)
   - Logging setup
   - Directory management
   - Path resolution
   - Error utilities

### 2. Configuration Management

The configuration system handles loading and validation of all YAML configuration files:

#### Key Components:
1. **Config Manager** (`config/config_manager.py`)
   - Central configuration loading
   - Schema validation
   - Path resolution
   - Type conversion

2. **Configuration Types**
   - Project Configuration (`project_config.py`)
   - Style Configuration (`style_config.py`)
   - Color Configuration (`color_config.py`)
   - Geometry Layer Configuration (`geometry_layer_config.py`)
   - Specialized Configurations:
     - Block Insert (`block_insert_config.py`)
     - Legend (`legend_config.py`)
     - Path Array (`path_array_config.py`)
     - Position (`position_config.py`)
     - Text Insert (`text_insert_config.py`)
     - Viewport (`viewport_config.py`)
     - Web Service (`web_service_config.py`)

### 3. Export System

The export system handles conversion of geometry to various output formats:

#### Key Components:
1. **Export Manager** (`export/manager.py`)
   - Export format registration
   - Export coordination
   - Format-agnostic interface
   - Error handling

2. **Export Interfaces** (`export/interfaces/`)
   - Export protocol definitions
   - Common export types
   - Format-agnostic contracts

3. **DXF Export** (`export/dxf/`)
   - DXF-specific implementation
   - Entity conversion
   - Style application
   - Layer management

4. **Shapefile Export** (`export/shapefile/`)
   - Shapefile-specific implementation
   - Attribute handling
   - CRS management

5. **__init__.py** - Package Definition
   - Marks export directory as a Python package
   - Provides clean import boundaries
   - Enables proper module organization

### Export System Responsibilities

1. **Format Management**
   - Registration of export formats
   - Format-specific implementation isolation
   - Export format validation
   - Format-specific error handling

2. **Data Conversion**
   - Converting processed geometry to output format
   - Applying format-specific styles
   - Managing layers and attributes
   - Handling coordinate systems

3. **Style Application**
   - Format-specific style handling
   - Style validation and defaults
   - Style transformation and mapping
   - Consistent styling across exports

4. **Layer Management**
   - Layer organization and naming
   - Layer property application
   - Layer hierarchy maintenance
   - Format-specific layer handling

### Export System Flow

The export process follows this sequence:
```
ProcessedGeometry
       │
       v
   ExportData ──────► ExportManager
       │                   │
       │                   v
       │         Format-specific Exporter
       │            (DXF/Shapefile)
       │                   │
       v                   v
Style/Layer Info    Output Generation
```

### Export Boundaries

1. **Input Boundaries**
   - Accepts only `ProcessedGeometry` and `ExportData`
   - No direct geometry processing
   - No direct configuration management
   - Clean interface through `GeometryExporter` protocol

2. **Output Boundaries**
   - Format-specific output handling
   - No geometry modifications
   - No configuration changes
   - Clear error propagation

3. **Component Isolation**
   - Each format is self-contained
   - Shared code through interfaces only
   - No cross-format dependencies
   - Clean separation of concerns

### Export System Extension

To add a new export format:
1. Create new directory `export/new_format/`
2. Implement `GeometryExporter` protocol
3. Add format-specific handling
4. Register with `ExportManager`

Example:
```python
# export/new_format/exporter.py
class NewFormatExporter(GeometryExporter):
    def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
        # Format-specific implementation
        pass

# Usage
export_manager = ExportManager()
export_manager.register_exporter('new_format', NewFormatExporter())
```

## Component Boundaries

### 1. Import Rules

1. **No Deep Imports**
   - NEVER import from component internals
   - Only import from component root (`__init__.py`)
   - Example:
     ```python
     # WRONG - deep import
     from src.core.types import LayerName
     from src.config.config_manager import ConfigManager

     # CORRECT - import from component root
     from src.core import LayerName
     from src.config import ConfigManager
     ```

2. **Component Dependencies**
   - Each component MUST have a `dependencies.py` file
   - All imports from other components MUST go through `dependencies.py`
   - Only `dependencies.py` and `__init__.py` can import from other components
   - Example:
     ```python
     # WRONG - direct import from another component
     from src.core import setup_logger

     # CORRECT - import through dependencies.py
     from .dependencies import setup_logger
     ```

3. **Dependencies File Structure**
   ```python
   # src/config/dependencies.py
   """Config component dependencies.

   This module centralizes all imports from other components.
   All cross-component dependencies MUST go through this file.
   """
   from src.core import setup_logger, resolve_path

   __all__ = [
       "setup_logger",
       "resolve_path",
   ]
   ```

4. **Local Types**
   - Define component-specific types in the component
   - Export them through the component's public API
   - Example:
     ```python
     # src/config/types.py
     from typing import NewType
     LayerName = NewType("LayerName", str)

     # src/config/__init__.py
     from .types import LayerName
     __all__ = ["LayerName"]
     ```

5. **Enforcement**
   - Flake8 and Pylint are configured to enforce these rules
   - Deep imports will cause linting errors
   - Direct imports from other components (bypassing dependencies.py) will cause errors
   - Only dependencies.py and __init__.py are allowed to import from other components
   - CI/CD pipeline will fail on violations

6. **Component Structure**
   ```
   src/
   ├── component/
   │   ├── __init__.py        # Public API
   │   ├── dependencies.py    # External dependencies
   │   ├── types/            # Component types
   │   │   ├── __init__.py
   │   │   └── base.py
   │   ├── internal/         # Internal modules
   │   │   ├── __init__.py
   │   │   └── utils.py
   │   └── README.md         # Component docs
   ```

7. **Import Flow**
   ```
   External Code
        │
        ▼
   __init__.py ◄── dependencies.py
        │              │
        ▼              │
   Internal Code       │
        │              │
        └──────────────┘
   ```

8. **Dependencies Management**
   - Keep dependencies.py minimal
   - Document why each dependency is needed
   - Review dependencies regularly
   - Consider impact on testing
   - Example:
     ```python
     """Geometry component dependencies.

     Core:
     - setup_logger: Used for component-wide logging
     - GeometryType: Base type for geometry operations

     Config:
     - LayerConfig: Layer configuration and validation
     """
     from src.core import setup_logger, GeometryType
     from src.config import LayerConfig

     __all__ = [
         "setup_logger",
         "GeometryType",
         "LayerConfig",
     ]
     ```

### 2. Core Types (Shared Interfaces)

Located in `src/core/types.py`:

```python
from dataclasses import dataclass
from typing import Dict, Any, List, Protocol, Union, BinaryIO
from shapely.geometry import base

class GeometrySource(Protocol):
    """Interface for geometry data sources"""
    def read(self) -> 'GeometryData': ...
    def get_metadata(self) -> Dict[str, Any]: ...
```

### 3. Component Entry Points and Import Rules

Each component MUST follow these rules for clean boundaries and dependencies:

1. **Single Entry Point**
   - Each component MUST have a clear public API in its `__init__.py`
   - All external code MUST import only from the component root (e.g., `from src.config import X`)
   - The `__all__` list in `__init__.py` MUST explicitly declare the public API
   - Example of a proper component `__init__.py`:
     ```python
     """Component description and purpose."""

     from .submodule import PublicClass
     from .other import OtherPublic

     __all__ = ['PublicClass', 'OtherPublic']
     ```

2. **Import Organization**
   - External imports MUST be from component roots only
   - Internal imports within a component can be more detailed
   - Imports should be grouped and clearly commented:
     ```python
     # Standard library imports
     from typing import Dict, List

     # External component imports
     from src.config import ConfigClass

     # Internal imports
     from src.current_component.submodule import InternalClass
     ```

3. **Component Independence**
   - Components should be independently testable
   - Clear boundaries between components
   - Well-defined APIs for inter-component communication
   - Minimal dependencies between components

4. **Documentation Requirements**
   - Each component's `__init__.py` MUST include docstring explaining its purpose
   - Public API must be clearly documented
   - Internal modules should document their relationship to the public API

5. **Enforcing Component Boundaries**
   - Use static analysis tools to enforce import rules
   - Configure linters to check import patterns
   - Example flake8 configuration:
     ```ini
     [flake8]
     # Enforce absolute imports for external components
     import-order-style = google
     application-import-names = src
     # Warn about imports from internal modules of other components
     extend-ignore = I202
     ```
   - Example pylint configuration:
     ```ini
     [IMPORTS]
     # Only allow imports from component roots
     allow-any-import-level = src.config,src.geometry,src.export,src.core
     # Warn about relative imports crossing component boundaries
     allow-wildcard-with-all = no
     ```
   - Regular code reviews should verify compliance
   - Automated tests should verify public API stability

### 4. Component Communication

Components communicate only through interface types:
```
GeometrySource ──► GeometryData ──► ProcessedGeometry ──► ExportData
      │                 │                    │                 │
      v                 v                    v                 v
  Shapefile ──► Geometry Interface ──► Operations ──► DXF/Export
   Reader          (Core Types)        Interface      Interface
```

### 5. Strict Boundaries

1. **Input System**
   - Input: File paths, source configurations
   - Output: `GeometryData`
   - No knowledge of:
     - Geometry processing
     - Export formats
     - Business logic

2. **Geometry Processing**
   - Input: `GeometryData`
   - Output: `ProcessedGeometry`
   - No knowledge of:
     - DXF formats
     - Export styles
     - Layer naming

3. **Export System**
   - Input: `ProcessedGeometry` + `ExportData`
   - Output: DXF file
   - No knowledge of:
     - Geometry operations
     - Processing logic
     - Source data formats

4. **Configuration System**
   - Provides: Configuration objects
   - No knowledge of:
     - Implementation details
     - Processing logic
     - Export formats

### 6. Dependency Rules

1. All dependencies flow inward:
   ```
   Config ──► Core Types ◄── Export
                   ▲
                   │
              Processing
   ```

2. Shared interfaces live in core:
   - No circular dependencies
   - No implementation leakage
   - Clear contract boundaries

### 7. Testing Boundaries

Each component can be tested in isolation:

1. **Geometry Processing Tests**
   ```python
   def test_buffer_operation():
       # Uses only GeometryData and Geometry interface
       data = GeometryData(...)
       processor = GeometryProcessor()
       result = processor.process(data)
       assert isinstance(result, ProcessedGeometry)
   ```

2. **Export Tests**
   ```python
   def test_dxf_conversion():
       # Uses only ProcessedGeometry and ExportData
       geom = ProcessedGeometry(...)
       export_data = ExportData(...)
       exporter = ExportManager(...)
       exporter.export(geom, export_data)
   ```

## Code Style and Linting Configuration

### 1. Configuration Sources

The project uses two configuration files for code style and linting:

1. **pyproject.toml** - Primary configuration source for:
   - Black (code formatting)
   - isort (import sorting)
   - mypy (type checking)
   - pylint (static analysis)

2. **.flake8** - Dedicated configuration for flake8 because:
   - Flake8 doesn't support pyproject.toml configuration natively
   - Settings are aligned with other tools for consistency
   - Contains flake8-specific settings and plugins

### 2. Tool-Specific Configurations

1. **Black Configuration** (`pyproject.toml`)
   ```toml
   [tool.black]
   line-length = 100
   target-version = ['py38']
   skip-string-normalization = true  # Preserve quote styles
   ```

2. **isort Configuration** (`pyproject.toml`)
   ```toml
   [tool.isort]
   profile = "google"
   line_length = 100
   sections = ["FUTURE", "STDLIB", "THIRDPARTY", "FIRSTPARTY", "LOCALFOLDER"]
   import_heading_stdlib = "Standard library imports"
   import_heading_thirdparty = "Third party imports"
   import_heading_firstparty = "First party imports"
   ```

3. **Flake8 Configuration** (`.flake8`)
   ```ini
   [flake8]
   max-line-length = 100
   inline-quotes = "single"
   multiline-quotes = "single"
   docstring-quotes = "double"
   import-order-style = "google"
   extend-ignore = ["W503", "E203", "E501"]  # Compatibility with Black
   ```

4. **Pylint Configuration** (`pyproject.toml`)
   ```toml
   [tool.pylint]
   max-line-length = 100
   string-quote = "single"
   triple-quote = "double"
   docstring-quote = "double"
   ```

### 3. Quote Style Standards

- Single quotes (`'`) for regular strings
- Double quotes (`"`) for docstrings
- Consistent across all tools through configuration:
  - Black: `skip-string-normalization = true`
  - Flake8: `inline-quotes = "single", docstring-quotes = "double"`
  - Pylint: `string-quote = "single", docstring-quote = "double"`

### 4. Import Organization

1. **Import Groups** (enforced by isort and flake8-import-order)
   ```python
   # Standard library imports
   import os
   from typing import Dict, List

   # Third party imports
   import numpy as np
   from shapely.geometry import Point

   # First party imports
   from src.core import setup_logger

   # Local imports
   from .utils import validate_path
   ```

2. **Import Rules**
   - No star imports
   - Absolute imports for external components
   - Relative imports for internal modules
   - Imports grouped and sorted alphabetically
   - Component boundaries enforced through flake8's `banned-modules`

### 5. Line Length and Formatting

- Maximum line length: 100 characters
- Enforced consistently across all tools:
  - Black: `line-length = 100`
  - Flake8: `max-line-length = 100`
  - Pylint: `max-line-length = 100`
  - isort: `line_length = 100`

### 6. Integration with Editor

VS Code settings in `.vscode/settings.json`:
```json
{
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--config=pyproject.toml"],
    "editor.formatOnSave": true,
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.flake8Args": ["--config=.flake8"],
    "python.linting.pylintEnabled": true,
    "python.linting.pylintArgs": ["--rcfile=pyproject.toml"],
    "python.linting.mypyEnabled": true,
    "python.linting.mypyArgs": ["--config-file=pyproject.toml"]
}
```

### 7. Pre-commit Hooks

Configuration in `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.1
    hooks:
      - id: black
        args: ["--config=pyproject.toml"]

  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ["--config=.flake8"]

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ["--settings-path=pyproject.toml"]
```

### 8. Enforcement Strategy

1. **Editor Level**
   - Real-time linting feedback
   - Format on save with Black
   - Import organization with isort
   - Type checking with mypy

2. **Pre-commit Level**
   - Prevents commits with style violations
   - Automatic formatting
   - Import organization
   - Consistent quote styles

3. **CI/CD Level**
   - Full linting check on every PR
   - Type checking
   - Style verification
   - Import order validation

### 9. Component Boundaries

Flake8 enforces strict component boundaries through `banned-modules`:
```ini
banned-modules =
    # Ban deep imports from components
    src.core.* = Import from src.core instead
    src.config.* = Import from src.config instead
    src.geometry.* = Import from src.geometry instead
    src.export.* = Import from src.export instead
    # Ban direct imports between components
    src.core = Import through dependencies.py
    src.config = Import through dependencies.py
    src.geometry = Import through dependencies.py
    src.export = Import through dependencies.py
```

This ensures:
- Components are only imported through their public API
- Cross-component dependencies go through `dependencies.py`
- Clean separation between components

## Type Organization Rules

The project follows strict rules for organizing and defining types across components. These rules ensure clean architecture, prevent duplication, and maintain clear boundaries between core and component-specific types.

### Type Categories

1. **Core Types** (`src/core/types.py`)
   Types that should be defined in core include:
   - Types used across multiple components
   - Interface definitions (Protocol classes)
   - Base classes for component-specific types
   - Error types
   - Manager base classes
   - Data transfer objects
   - Configuration base types
   - Type-related definitions
   - Operation results

2. **Component Types** (`src/<component>/types.py` or `__init__.py`)
   Types that should be defined within components:
   - Implementation classes specific to the component
   - Component-specific configurations
   - Types used only within the component
   - Internal data structures

### Type Organization Rules

1. **Location Rules**
   - Core types MUST be defined in `core/types.py`
   - Component types MUST be defined in the component's `types.py` or `__init__.py`
   - No type definitions allowed in other files
   - Each component should have its own types module

2. **Import Rules**
   - Components MUST import core types from `src.core.types`
   - No direct imports of types from other components
   - Type imports MUST go through `dependencies.py`
   - Proper imports through `__init__.py` required

3. **Type Placement**
   - Types used across components MUST be in core
   - Component-specific types MUST stay in their component
   - Base classes and protocols belong in core
   - Implementation classes belong in components

4. **Type Naming**
   - Core types should follow naming patterns:
     - `*Protocol` for interfaces
     - `*Base` for base classes
     - `*Error` for error types
     - `*Manager` for manager classes
     - `*Config` for configuration types
     - `*Type` for type definitions
     - `*Result` for operation results

### Type Checker

The project includes a type checker script (`scripts/check_duplicate_types.py`) that enforces these rules by:

1. **Cross-Component Usage Tracking**
   - Identifies types used in multiple components
   - Flags types that should be moved to core
   - Detects improper type locations

2. **Name Pattern Analysis**
   - Checks type names against core patterns
   - Ensures proper placement of core types
   - Validates component-specific types

3. **Component-Specific Checks**
   - Verifies type definition locations
   - Checks import patterns
   - Validates component boundaries

4. **Location Rules**
   - Enforces core types in `core/types.py`
   - Requires component types in proper files
   - Prevents scattered type definitions

### Example Type Organization

```python
# src/core/types.py
from typing import Protocol, TypeVar

class GeometryManagerProtocol(Protocol):
    """Interface for geometry managers."""
    def process(self) -> None: ...

class OperationBase:
    """Base class for all operations."""
    pass

# src/geometry/types.py
from src.core.types import OperationBase

class BufferOperation(OperationBase):
    """Component-specific implementation."""
    pass
```

### Type Validation

The type checker can be run to validate type organization:

```bash
python scripts/check_duplicate_types.py
```

This will:
1. Find duplicate type definitions
2. Check core type conflicts
3. Validate type placement rules
4. Ensure proper import patterns

## Testing Strategy

### 1. Unit Tests
- Test each component in isolation
- Mock dependencies
- Test edge cases and error conditions
- Maintain high coverage

### 2. Integration Tests
- Test component interactions
- Test complete workflows
- Test with real config files

### 3. Performance Tests
- Test with large datasets
- Monitor memory usage
- Check processing times

### 4. Test Data
- Create sample projects
- Include various geometry types
- Cover different configurations

## Development Workflow

1. **For Each Component**:
   ```
   a. Write tests first
   b. Implement minimal functionality
   c. Make tests pass
   d. Refactor and optimize
   e. Document API
   f. Review and update tests
   ```

2. **For Each Feature**:
   ```
   a. Define API
   b. Write interface tests
   c. Implement feature
   d. Add edge case tests
   e. Document usage
   ```

3. **For Each Release**:
   ```
   a. Run all tests
   b. Check coverage
   c. Update documentation
   d. Review API changes
   ```

### 4. Main Project Coordinator

```python
class Project:
    """Main project coordinator"""

    def __init__(self, project_name: str):
        self.project_name = project_name
        self._initialize_components()

    def _initialize_components(self) -> None:
        """Initialize all project components"""
        self.config_manager = ConfigManager(self.project_name)
        self.project_config = self.config_manager.load_project_config()

        # Initialize geometry processing
        self.geometry_manager = GeometryManager(
            self.config_manager.load_geometry_layers()
        )

        # Initialize export components
        style_configs = self.config_manager.load_styles()
        self.style_manager = StyleManager(style_configs)
        self.layer_manager = LayerManager()
        self.dxf_exporter = DXFExporter(
            self.style_manager,
            self.layer_manager
        )

    def process(self) -> None:
        """Process the entire project"""
        try:
            # Process each layer
            for layer_name in self.geometry_manager.get_layer_names():
                # Get processed geometry
                layer = self.geometry_manager.process_layer(layer_name)

                # Export to DXF if needed
                if layer.update_dxf:
                    style = self.style_manager.get_style(layer.style)
                    self.dxf_exporter.export_layer(layer, style)

            # Finalize export
            self.dxf_exporter.finalize_export()

        except Exception as e:
            self._handle_error(e)

    def _handle_error(self, error: Exception) -> None:
        """Handle project processing errors"""
        # Log error and cleanup if needed
        pass
```

## Key Improvements

### 1. Clear Separation of Concerns
- Each component has a single responsibility
- Dependencies flow in one direction
- Components communicate through well-defined interfaces
- Clear error boundaries and handling

### 2. Type Safety
- Strong typing for configurations using dataclasses
- Clear data structures for geometry and style information
- Explicit interfaces between components
- Type hints throughout the codebase

### 3. Modularity
- Each operation is its own module
- Easy to add new operations or styles
- Components can be tested independently
- Plugin architecture for operations

### 4. Error Handling
- Each layer can define its own error types
- Clear boundaries for error propagation
- Better error reporting capabilities
- Centralized error handling in Project class

### 5. Testing
- Dedicated test directory structure
- Test configurations and fixtures
- Component-specific test suites
- Integration test examples

### 6. Documentation
- API documentation
- Usage guides
- Example projects
- Architecture documentation

## Core Components

Located in `src/core/`, these components form the foundation of the application:

### Core Files

1. **project.py** - Main Project Coordinator
   - Acts as the application's central coordinator
   - Initializes and manages all major components (config, geometry, export)
   - Orchestrates the workflow from configuration to export
   - Handles high-level error management and logging
   - Ensures proper cleanup and resource management

2. **types.py** - Core Type Definitions
   - Defines fundamental data structures and protocols
   - Provides type hints and runtime type checking
   - Contains core interfaces (GeometryExporter, GeometrySource, etc.)
   - Defines data transfer objects (GeometryData, ProcessedGeometry, etc.)
   - Implements basic geometric types and bounds checking

3. **utils.py** - Core Utilities
   - Provides logging setup and configuration
   - Handles directory creation and validation
   - Contains shared utility functions
   - Manages common operations like path resolution
   - Implements error handling utilities

4. **__init__.py** - Package Definition
   - Marks the core directory as a Python package
   - Enables proper module imports
   - Maintains clean import boundaries

### Core Responsibilities

The core module has these key responsibilities:

1. **Type Safety**
   - Enforcing type checking across the application
   - Defining protocol interfaces for components
   - Ensuring data structure consistency

2. **Project Management**
   - Coordinating component initialization
   - Managing the processing workflow
   - Handling errors and logging
   - Ensuring proper resource cleanup

3. **Infrastructure**
   - Providing essential utilities
   - Managing logging and debugging
   - Handling file system operations
   - Supporting error handling

4. **Component Integration**
   - Maintaining clean interfaces between components
   - Managing component lifecycle
   - Coordinating data flow
   - Ensuring proper component initialization

## Layer Architecture

### Layer Types

1. **Geometry Layers** (`src/geometry/layers/`)
   - Pure geometry representation from YAML configuration (e.g., `geom_layers.yaml`)
   - No relationship to import/export formats
   - Holds raw geometry data in memory
   - Supports geometric operations (buffer, union, etc.)
   - Format-agnostic - can be exported to any format
   - Defined by:
     - Geometry data (points, lines, polygons)
     - Layer name and attributes
     - Operation definitions
     - No styling information

2. **DXF Layers** (`src/export/dxf/layer.py`)
   - Format-specific representation for DXF output
   - Created from geometry layers + style configurations
   - Handles DXF-specific properties (color, linetype, etc.)
   - Manages DXF layer hierarchy and properties
   - Styled according to `styles.yaml` configuration
   - Defined by:
     - DXF layer properties
     - Style information
     - Entity properties
     - DXF-specific attributes

### Layer Flow

```
Geometry Layer (Pure)     Style Config
       │                      │
       │                      │
       v                      v
    Operations  ────►  DXF Layer Manager
       │                      │
       v                      v
 Processed Geometry    Styled DXF Layer
       │                      │
       v                      v
  Export Manager        DXF Entities
```

### Implementation Strategy

1. **Geometry Layer Processing**
   ```python
   class GeometryLayer:
       """Pure geometry layer without format-specific details."""
       def __init__(self, name: str, geometry: Any):
           self.name = name
           self.geometry = geometry  # Raw geometry data
           self.operations = []      # List of operations to apply

   class GeometryManager:
       """Manages pure geometry layers and operations."""
       def process_layer(self, layer_name: str) -> ProcessedGeometry:
           # Process pure geometry without export knowledge
           pass
   ```

2. **DXF Layer Creation**
   ```python
   class DXFLayerManager:
       """Manages DXF-specific layer creation and styling."""
       def create_layer(self, geometry_layer: GeometryLayer, style: StyleConfig) -> None:
           # Create DXF layer with styling
           pass
   ```

3. **Export Flow**
   ```python
   class DXFExporter:
       """Handles DXF-specific export."""
       def export(self, geometry: ProcessedGeometry, style: StyleConfig) -> None:
           # Create and style DXF layer
           layer = self.layer_manager.create_layer(geometry, style)
           # Convert geometry to DXF entities
           entities = self.converter.convert(geometry)
           # Apply style to entities
           self.style_applicator.apply(entities, style)
   ```

### Key Distinctions

1. **Geometry Layer Responsibilities**
   - Hold raw geometry data
   - Define geometric operations
   - Maintain geometry attributes
   - Format-agnostic processing
   - No styling or export logic

2. **DXF Layer Responsibilities**
   - Apply DXF-specific styling
   - Manage DXF layer properties
   - Handle DXF entity creation
   - Maintain DXF hierarchy
   - Format-specific concerns

3. **Shapefile Export**
   - Direct export of geometry without styling
   - No layer management needed
   - Pure geometry conversion
   - Attribute mapping only

## Geometry Operations Architecture

### Operation Types

The geometry operations system is designed to be extensible and modular, supporting various types of geometric transformations:

1. **Basic Operations**
   - Buffer operations (with configurable distance)
   - Intersection/Union/Difference
   - Dissolve/Merge
   - Filter (by area, type, etc.)
   - Clean/Repair

2. **Advanced Operations**
   - Smoothing and simplification
   - Vertex snapping and alignment
   - Angle blunting
   - Label placement and association

### Operation Implementation

Each operation follows a consistent pattern:

```python
@dataclass
class GeometryOperation:
    """Configuration for a geometry operation."""
    type: str
    layers: Optional[Union[str, List[Union[str, Dict[str, List[str]]]]]] = None
    distance: Optional[float] = None
    params: Optional[Dict[str, Any]] = None

    def execute(self, geometry: Geometry) -> Geometry:
        """Execute the operation on the geometry."""
        pass
```

### Operation Flow

```
Input Geometry ──► Operation Config ──► Operation Handler ──► Processed Geometry
      │                  │                      │                    │
      v                  v                      v                    v
  Validation     Parameter Check        Operation Execution     Validation
```

### Key Components

1. **Operation Registry**
   - Central registry of available operations
   - Dynamic operation loading
   - Operation validation and verification
   - Parameter validation

2. **Operation Handler**
   ```python
   class GeometryHandler:
       """Handles geometry operations."""
       def __init__(self, layer_processor):
           self.layer_processor = layer_processor

       def execute_operation(self, operation: GeometryOperation, geometry: Geometry) -> Geometry:
           """Execute a geometry operation."""
           # Validate operation
           # Execute operation
           # Validate result
           pass
   ```

3. **Operation Configuration**
   - YAML-based operation definition
   - Parameter validation
   - Operation chaining support
   - Error handling

### Example Operation Configuration

```yaml
operations:
  - type: intersection
    layers:
      - Geltungsbereich
  - type: dissolve
  - type: filterGeometry
    geometryTypes:
      - polygon
    minArea: 1
```

### Operation Categories

1. **Transformation Operations**
   - Buffer
   - Smooth
   - Simplify
   - Snap to grid

2. **Boolean Operations**
   - Intersection
   - Union
   - Difference
   - Symmetric difference

3. **Cleanup Operations**
   - Filter by area
   - Filter by type
   - Remove invalid geometries
   - Fix self-intersections

4. **Analysis Operations**
   - Calculate area
   - Calculate length
   - Find centroids
   - Detect overlaps

### Operation Implementation Guidelines

1. **Input Validation**
   - Validate geometry type
   - Check parameter values
   - Verify layer references
   - Handle edge cases

2. **Error Handling**
   - Graceful failure modes
   - Informative error messages
   - Operation logging
   - Result validation

3. **Performance Considerations**
   - Optimize for large geometries
   - Use spatial indexing where appropriate
   - Implement early validation
   - Cache intermediate results

4. **Testing Requirements**
   - Unit tests for each operation
   - Integration tests for operation chains
   - Edge case coverage
   - Performance benchmarks

### Operation Extension

To add a new operation:

1. Create operation class implementing `GeometryOperation` protocol
2. Register operation in the operation registry
3. Add configuration schema validation
4. Implement operation handler
5. Add tests and documentation

Example:
```python
class CustomOperation(GeometryOperation):
    """Custom geometry operation."""
    def execute(self, geometry: Geometry) -> Geometry:
        # Implementation
        pass

# Registration
operation_registry.register("custom", CustomOperation)
```
