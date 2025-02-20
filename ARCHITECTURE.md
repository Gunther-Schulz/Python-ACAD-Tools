# Project Architecture

## Overview

This document outlines the architecture for the Python ACAD Tools project, which consists of three main components:

1. Configuration Management
2. Geometry Processing
3. DXF Export

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
- Configuration Management (Complete)
  - [x] Basic config loading
  - [x] Schema validation
  - [x] Style configuration
  - [x] Project configuration
  - [x] Geometry layer configuration
  - [x] Color configuration and ACI colors
  - [x] Specialized configurations (viewport, legend, etc.)
  - [ ] Complete test coverage
- Geometry Processing (In Progress)
  - [x] Base geometry types
  - [x] Basic geometry manager
  - [x] Operations framework implementation
      - [x] Operation base classes (Unary, Binary, Multi)
      - [x] Operation context and results
      - [x] Parameter validation framework
      - [x] Error handling and propagation
  - [ ] Individual operations
      - [x] Buffer operation
          - [x] Operation implementation
          - [x] Parameter validation
          - [x] Unit tests
          - [x] Integration tests
      - [ ] Intersection/Union/Difference
      - [ ] Dissolve/Merge
      - [ ] Filter operations
      - [ ] Clean/Repair operations
  - [x] Layer management
      - [x] Layer validation
      - [x] Layer processing
      - [x] Dependency handling
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

### 1. Core Types (Shared Interfaces)

Located in `src/core/types.py`:

```python
from dataclasses import dataclass
from typing import Dict, Any, List, Protocol, Union, BinaryIO
from shapely.geometry import base

class GeometrySource(Protocol):
    """Interface for geometry data sources"""
    def read(self) -> 'GeometryData': ...
    def get_metadata(self) -> Dict[str, Any]: ...

class ShapefileReader(GeometrySource):
    """Interface for shapefile reading"""
    def read(self) -> 'GeometryData': ...
    def get_crs(self) -> str: ...

@dataclass
class GeometryData:
    """Data transfer object for geometry data"""
    id: str
    geom: Geometry
    metadata: Dict[str, Any]
    source_type: str  # e.g., 'shapefile', 'manual', etc.
    source_crs: str   # Coordinate reference system of source
```

### 2. Geometry Processing

Pure geometry processing with no knowledge of export or DXF:

```python
from dataclasses import dataclass
from shapely.geometry import base
from typing import Dict, Any, List

@dataclass
class GeometryLayer:
    """Pure geometry layer representation"""
    name: str
    geometry: base.BaseGeometry
    attributes: Dict[str, Any]
    operations_log: List[str]

class GeometryCollection:
    """Container for multiple geometry layers"""
    def __init__(self):
        self.layers: Dict[str, GeometryLayer] = {}
```

2. **Operations** (`geometry/operations/`)
   - Pure geometric operations
   - Input: geometry
   - Output: modified geometry
   - No side effects

```python
class GeometryOperation:
    """Base class for geometry operations"""
    def execute(self, geometry: base.BaseGeometry, **kwargs) -> base.BaseGeometry:
        """Execute the operation on the geometry"""
        raise NotImplementedError
```

3. **Layer Management** (`geometry/layers/`)
   - Manages geometric layer operations
   - Handles layer attributes
   - No export-specific logic

### 3. Export System

Handles conversion to DXF with no geometry processing:

```python
class DXFConverter:
    """Pure DXF conversion"""
    
    def convert(self, geom: Geometry) -> Any:  # Returns ezdxf entity
        """Convert geometry to DXF entity"""
        pass

class StyleApplicator:
    """Pure style application"""
    
    def apply(self, entity: Any, style_id: str) -> None:
        """Apply style to DXF entity"""
        pass

class ExportManager:
    """Coordinates export process"""
    
    def __init__(self, converter: DXFConverter, style: StyleApplicator):
        self.converter = converter
        self.style = style
    
    def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
        """Export using clean interfaces"""
        pass
```

### 4. Input System

The input system handles reading geometry from various sources (shapefiles, etc.) without knowledge of processing or export.

#### Key Components:

1. **Shapefile Import** (`input/shapefile/`)
   - Pure shapefile reading
   - CRS handling
   - Attribute reading

```python
class ShapefileImporter:
    """Pure shapefile import functionality"""
    
    def __init__(self, crs_transformer: Optional[CRSTransformer] = None):
        self.crs_transformer = crs_transformer
    
    def read(self, path: Union[str, Path]) -> GeometryData:
        """Read shapefile to geometry data"""
        pass

class CRSTransformer:
    """Handle coordinate reference system transformations"""
    
    def transform(self, geom: Geometry, from_crs: str, to_crs: str) -> Geometry:
        """Transform geometry between CRS"""
        pass
```

2. **Input Coordination** (`input/`)
   - Source type detection
   - Reader selection
   - Error handling

```python
class InputManager:
    """Coordinates geometry input from various sources"""
    
    def __init__(self, config: InputConfig):
        self.config = config
        self.readers: Dict[str, GeometrySource] = {}
    
    def register_reader(self, source_type: str, reader: GeometrySource) -> None:
        """Register a geometry source reader"""
        pass
    
    def read_geometry(self, source_id: str) -> GeometryData:
        """Read geometry from configured source"""
        pass
```

## Data Flow and Boundaries

### 1. Component Communication

Components communicate only through interface types:
```
GeometrySource ──► GeometryData ──► ProcessedGeometry ──► ExportData
      │                 │                    │                 │
      v                 v                    v                 v
  Shapefile ──► Geometry Interface ──► Operations ──► DXF/Export
   Reader          (Core Types)        Interface      Interface
```

### 2. Strict Boundaries

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

### 3. Dependency Rules

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

### 4. Testing Boundaries

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