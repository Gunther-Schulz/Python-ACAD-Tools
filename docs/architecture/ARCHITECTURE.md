# Project Architecture

## Overview

This document outlines the architecture for the Python ACAD Tools project, which consists of three main components:

1. Configuration Management
2. Geometry Processing
3. Export System

## Core Design Principles

1. **Clear Separation of Concerns**
   - Each component has a single responsibility
   - Clean boundaries between components
   - Dependencies flow in one direction
   - No circular dependencies

2. **Type Safety**
   - Strong typing throughout the codebase
   - Clear data structures and interfaces
   - Runtime type checking where needed
   - Explicit error types

3. **Component Independence**
   - Components are independently testable
   - Well-defined APIs between components
   - Minimal cross-component dependencies
   - Clear contract boundaries

## Component Architecture

### 1. Core Component (`src/core/`)

Core provides the foundation and shared interfaces:

1. **Type System** (`core/types.py`)
   - Core data structures and protocols
   - Interface definitions
   - Base classes
   - Shared type definitions
   ```python
   # Core protocols
   class StyleProvider(Protocol):
       """Central style provider protocol."""
       def get_style(self, style_id: StyleID) -> dict[str, Any]: ...
       def get_default_style(self) -> dict[str, Any]: ...
       def validate_style(self, style_id: StyleID) -> bool: ...

   class GeometryProcessor(Protocol):
       """Enhanced geometry processing protocol."""
       def get_dependencies(self) -> set[str]: ...
       def validate_input(self, geometry: GeometryData) -> bool: ...
       def process(self, geometry: GeometryData, context: ProcessingContext) -> GeometryData: ...
       def can_process(self, geometry_type: GeometryType) -> bool: ...
       def get_output_type(self) -> GeometryType: ...

   class ComponentFactory(Protocol):
       """Factory for creating drawing components."""
       def create_component(
           self,
           config: ComponentConfig,
           geometry_provider: GeometryProvider,
           style_provider: StyleProvider
       ) -> DrawingComponent: ...
       def validate_config(self, config: ComponentConfig) -> bool: ...
       def get_required_geometry(self, config: ComponentConfig) -> set[str]: ...
   ```

2. **Project Coordinator** (`core/project.py`)
   - Application central coordinator
   - Component initialization
   - Workflow orchestration
   - Error handling and logging
   - Resource lifecycle management

3. **Utilities** (`core/utils.py`)
   - Logging setup
   - Path resolution
   - Error utilities
   - Common functions
   - Performance monitoring utilities

### 2. Configuration Management (`src/config/`)

Handles all configuration loading and validation:

1. **Config Manager** (`config/config_manager.py`)
   - YAML configuration loading
   - Schema validation
   - Type conversion
   - Path resolution

2. **Configuration Types**
   - Project Configuration
   - Style Configuration
     - Colors (ACI color system)
     - Line weights
     - Line types
     - Layer properties
     - Style references used by:
       - Geometry layers
       - Drawing components
       - Export formats
   - Layer Configuration
   - Specialized Configurations (viewports, legends, etc.)

3. **Style System**
   ```
   [Style Config] ───────► [Style Manager]
         │                       │
         v                       v
    Define styles          Style Registry ──────────┐
    Define inheritance     (Immutable styles)       │
    Define converters            │                  v
                                │            [Format Converters]
                                │                   │
                                v                   v
                          Style Provider     Format-specific
                         (Runtime access)      conversion
   ```
   - Enhanced style management:
     ```python
     @dataclass
     class Style:
         """Immutable style definition."""
         id: StyleID
         properties: dict[str, Any]
         parent: StyleID | None = None

     class StyleManager:
         """Manages styles with inheritance and validation."""
         def register_style(self, style: Style) -> None: ...
         def register_converter(self, format: str, converter: StyleConverter) -> None: ...
         def get_converted_style(self, style_id: StyleID, format: str) -> Any: ...
     ```
   - Style inheritance and validation:
     ```yaml
     styles:
       base_style:
         layer:
           color: "7"
           lineweight: 25

       parcel_style:
         parent: base_style  # Inherits from base_style
         layer:
           color: "1"  # Overrides base color
     ```
   - Format-specific conversion:
     ```python
     class DXFStyleConverter(StyleConverter[DXFStyle]):
         """Converts styles to DXF format."""
         def convert_style(self, style: dict[str, Any]) -> DXFStyle: ...
         def get_format_defaults(self) -> DXFStyle: ...
     ```
   - Runtime style access through StyleProvider
   - Style validation at configuration load and runtime
   - Immutable style definitions prevent runtime modifications

### 3. Geometry Processing (`src/geometry/`)

The geometry processing system consists of several key components:

1. **Processing Pipeline**
   ```
   [Geometry Layer Config] ─────► [Processing Pipeline]
           │                            │
           v                            v
    Define processors         Validate & Optimize ────┐
    Define operations         Process geometry        │
    Configure pipeline              │                 │
           │                        v                 v
           └─────────► [Processed Geometry] ──► [Component Access]
                      (Internal structure)        [Export System]
   ```

2. **Enhanced Processing System**
   ```python
   class ProcessingPipeline:
       """Manages geometry processing with validation and optimization."""
       def add_processor(self, name: str, processor: GeometryProcessor) -> None: ...
       def add_validator(self, name: str, validator: GeometryValidator) -> None: ...
       def add_optimizer(self, name: str, optimizer: GeometryOptimizer) -> None: ...

       def process(self, geometry: GeometryData, context: ProcessingContext) -> GeometryData:
           """Process geometry with validation and optimization."""
           # Validate input
           self._validate_input(geometry)

           # Determine processing order
           order = self._get_processing_order(geometry)

           # Process with optimization
           for step in order:
               geometry = self._processors[step].process(geometry, context)
               geometry = self._optimize(geometry)

           # Validate output
           self._validate_output(geometry)
           return geometry
   ```

3. **Processing Components**
   - Processors: Transform geometry
   - Validators: Ensure geometry validity
   - Optimizers: Improve geometry efficiency
   - Context providers: Supply processing context

4. **Processing Features**
   - Input validation before processing
   - Automatic dependency resolution
   - Intermediate result validation
   - Performance optimization
   - Type safety throughout pipeline
   - Processing context for shared state
   - Error handling and recovery
   - Progress tracking and logging

### 4. Drawing Components (`src/drawing/`)

Format-agnostic drawing enhancements and specialized elements:

1. **Component System**
   ```
   [Component Configs] ─────► [Component Registry]
           │                         │
           v                         v
    Define components     Component Factories ────┐
    Configure types       Create instances        │
    Set dependencies            │                 │
           │                    v                 v
           └────────► [Component Lifecycle] ─► [Export]
                     Initialize & validate    Format-specific
                     Process geometry        rendering
   ```

2. **Enhanced Component Management**
   ```python
   class ComponentRegistry:
       """Manages component lifecycle and dependencies."""
       def __init__(self) -> None:
           self._factories: dict[str, ComponentFactory] = {}
           self._components: dict[str, DrawingComponent] = {}
           self._dependencies: dict[str, set[str]] = {}

       def register_factory(self, type_name: str, factory: ComponentFactory) -> None: ...

       def create_component(
           self,
           config: ComponentConfig,
           geometry_provider: GeometryProvider,
           style_provider: StyleProvider
       ) -> DrawingComponent:
           """Create component with proper initialization."""
           factory = self._factories[config.type]
           component = factory.create_component(config, geometry_provider, style_provider)
           self._register_component(component)
           return component

       def get_processing_order(self) -> list[str]:
           """Get components in dependency order."""
           return self._resolve_dependencies()
   ```

3. **Component Features**
   - Factory-based component creation
   - Automatic dependency resolution
   - Lifecycle management
   - Resource cleanup
   - Validation at all stages
   - Access to processed geometry
   - Style application
   - Format-specific rendering

4. **Component Types**
   Example configuration:
   ```yaml
   path_arrays:
     - name: blocks_along_path
       type: path_array
       path_layer: path_a  # Geometry dependency
       style: path_style   # Style dependency
       block: my_block
       spacing: 10
       validation:
         min_spacing: 5
         max_spacing: 20
   ```

5. **Component Lifecycle**
   - Configuration validation
   - Factory selection
   - Instance creation
   - Dependency resolution
   - Geometry processing
   - Style application
   - Export preparation
   - Resource cleanup

### 5. Export System (`src/export/`)

Handles conversion of processed geometry to output formats:

1. **Enhanced Export Manager**
   ```python
   class EnhancedExportManager:
       """Enhanced export manager with optimization and validation."""
       def __init__(self) -> None:
           self._exporters: dict[str, GeometryExporter] = {}
           self._optimizers: dict[str, ExportOptimizer] = {}
           self._validators: dict[str, ExportValidator] = {}

       def export(self, geometry: ProcessedGeometry, export_data: ExportData) -> None:
           """Export with optimization and validation."""
           format = export_data.format

           # Pre-export validation
           self._validators[format].validate_pre_export(geometry)

           # Optimize for format
           optimized = self._optimizers[format].optimize(geometry)

           # Export
           self._exporters[format].export(optimized, export_data)

           # Post-export validation
           self._validators[format].validate_post_export(export_data.path)
   ```

2. **Export Pipeline**
   ```
   [Processed Geometry] ─────► [Export Pipeline]
           │                         │
           v                         v
    Format selection        Pre-export validation
    Style resolution              │
    Optimization                  v
           │               Format optimization
           │                      │
           v                      v
    [Format Exporter] ◄─── Export process
           │                      │
           v                      v
    Output generation      Post-export validation
   ```

3. **Format-Specific Components**
   - **DXF Export** (`export/dxf/`)
     ```python
     class DXFOptimizer(ExportOptimizer):
         """DXF-specific optimization."""
         def optimize(self, data: Any) -> Any:
             """Optimize geometry for DXF format."""
             return self._optimize_for_dxf(data)

     class DXFValidator(ExportValidator):
         """DXF-specific validation."""
         def validate_pre_export(self, geometry: ProcessedGeometry) -> bool:
             """Validate before DXF export."""
             return self._validate_dxf_compatibility(geometry)
     ```
   - **Shapefile Export** (`export/shapefile/`)
     ```python
     class ShapefileOptimizer(ExportOptimizer):
         """Shapefile-specific optimization."""
         def optimize(self, data: Any) -> Any:
             """Optimize geometry for shapefile format."""
             return self._optimize_for_shapefile(data)

     class ShapefileValidator(ExportValidator):
         """Shapefile-specific validation."""
         def validate_pre_export(self, geometry: ProcessedGeometry) -> bool:
             """Validate before shapefile export."""
             return self._validate_shapefile_compatibility(geometry)
     ```

4. **Export Features**
   - Format-specific optimization
   - Pre-export validation
   - Post-export validation
   - Style conversion
   - Resource management
   - Error handling
   - Progress tracking
   - Export metadata

5. **Export Configuration**
   ```yaml
   export:
     format: dxf
     version: R2018
     optimization:
       enabled: true
       level: aggressive
     validation:
       pre_export: true
       post_export: true
     metadata:
       author: "ACAD Tools"
       company: "Example Corp"
       project: "Project A"
   ```

## Directory Structure

```
src/
├── core/                     # Core functionality
│   ├── types.py            # Type definitions
│   ├── project.py          # Project coordinator
│   └── utils.py           # Utilities
├── config/                  # Configuration management
│   ├── config_manager.py   # Main config manager
│   └── schemas/           # JSON schemas
├── geometry/               # Geometry processing
│   ├── types/            # Geometry types
│   ├── operations/       # Geometry operations
│   └── layers/           # Layer management
├── drawing/               # Drawing components
│   ├── components/       # Component implementations
│   ├── processor.py      # Component processor
│   └── coordinator.py    # Component coordination
└── export/                 # Export functionality
    ├── dxf/              # DXF export
    ├── shapefile/        # Shapefile export
    └── manager.py        # Export coordination
```

## Related Documentation

- [Development Phases](../development/PHASES.md) - Detailed development and migration strategy
- [Code Quality Guidelines](../guidelines/CODE_QUALITY.md) - Coding standards and best practices
- [Component Boundaries](../guidelines/BOUNDARIES.md) - Rules for component separation and dependencies
- [Testing Strategy](../guidelines/TESTING.md) - Testing requirements and practices
- [Implementation Guidelines](../guidelines/IMPLEMENTATION.md) - Guidelines for implementing new features
