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
- Configuration Management (Mostly Complete)
  - [x] Basic config loading
  - [x] Schema validation
  - [x] Style configuration
  - [x] Project configuration
  - [x] Geometry layer configuration
  - [x] Specialized configurations (viewport, legend, etc.)
  - [ ] Complete test coverage
- Geometry Processing (Early Stages)
  - [x] Base geometry types
  - [x] Basic geometry manager
  - [ ] Operations framework implementation
  - [ ] Individual operations
  - [ ] Layer management
- Export System (Pending)
  - [ ] DXF export coordination
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
│   ├── export/                   # DXF export functionality
│   │   ├── dxf/                # DXF-specific functionality
│   │   ├── utils/              # Export utilities
│   │   ├── exporter.py         # Main export coordinator
│   │   ├── style_manager.py    # Style application
│   │   └── layer_manager.py    # Export layer management
│   ├── core/                     # Core functionality
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

### 1. Configuration Management

The configuration system handles loading and validation of all YAML configuration files.

#### Key Components:
1. **Config Manager**
   - Central configuration loading and validation
   - Schema validation
   - Deprecated field checking
   - Path resolution
   - Type conversion

2. **Configuration Types**
   - Project Configuration
   - Style Configuration
   - Geometry Layer Configuration
   - Specialized Configurations:
     - Legend Configuration
     - Viewport Configuration
     - Block Insert Configuration
     - Text Insert Configuration
     - Path Array Configuration
     - Web Service Configuration

Example implementation:

```python
from typing import Dict, Any, Optional, Type, TypeVar, List
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ProjectConfig:
    """Project configuration."""
    crs: str
    dxf_filename: str
    template_dxf: Optional[str]
    export_format: str
    dxf_version: str
    shapefile_output_dir: Optional[str]

    @classmethod
    def from_dict(cls, data: dict, folder_prefix: Optional[str] = None) -> 'ProjectConfig':
        """Create ProjectConfig from dictionary."""
        return cls(
            crs=data['crs'],
            dxf_filename=resolve_path(data['dxfFilename'], folder_prefix),
            template_dxf=resolve_path(data.get('template'), folder_prefix),
            export_format=data['exportFormat'],
            dxf_version=data['dxfVersion'],
            shapefile_output_dir=resolve_path(data.get('shapefileOutputDir'), folder_prefix)
        )

class ConfigManager:
    """Manages loading and validation of all configuration files."""
    
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self._initialize_schemas()
    
    def load_project_config(self) -> ProjectConfig:
        """Load and validate project configuration."""
        data = self._load_and_validate('project.yaml', project_schema, 'project')
        return self._convert_config(data, ProjectConfig)
    
    def load_geometry_layers(self) -> List[GeometryLayerConfig]:
        """Load and validate geometry layer configurations."""
        data = self._load_and_validate('geom_layers.yaml', geometry_layers_schema, 'geometry layers')
        return [self._convert_config(layer, GeometryLayerConfig) for layer in data['layers']]
    
    def load_styles(self) -> Dict[str, StyleConfig]:
        """Load and validate style configurations."""
        data = self._load_and_validate('styles.yaml', styles_schema, 'styles')
        return {name: self._convert_config(style, StyleConfig) 
                for name, style in data['styles'].items()}

### 2. Geometry Processing

The geometry system handles all geometric operations and transformations, working purely with in-memory geometric representations.

#### Key Components:

1. **Geometry Types** (`geometry/types/`)
   - Pure geometric representations
   - No export-specific attributes
   - Based on shapely geometries

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

The export system handles the conversion of pure geometric objects into various output formats (DXF, Shapefile).

#### Key Components:

1. **Export Interfaces** (`export/interfaces/`)
   ```python
   class GeometryExporter(Protocol):
       """Interface for geometry exporters"""
       def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None: ...
   ```

2. **DXF Export** (`export/dxf/`)
   ```python
   class DXFExporter(GeometryExporter):
       """DXF-specific export implementation"""
       def __init__(self, converter: DXFConverter, style: StyleApplicator):
           self.converter = converter
           self.style = style
       
       def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
           """Export to DXF format"""
           pass
   ```

3. **Shapefile Export** (`export/shapefile/`)
   ```python
   class ShapefileExporter(GeometryExporter):
       """Shapefile export implementation"""
       def __init__(self, crs_handler: CRSTransformer):
           self.crs_handler = crs_handler
       
       def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
           """Export to Shapefile format"""
           pass
   ```

4. **Export Manager** (`export/`)
   ```python
   class ExportManager:
       """Coordinates export process"""
       def __init__(self):
           self.exporters: Dict[str, GeometryExporter] = {}
       
       def register_exporter(self, format_type: str, exporter: GeometryExporter) -> None:
           """Register an exporter for a specific format"""
           self.exporters[format_type] = exporter
       
       def export(self, geom: ProcessedGeometry, export_data: ExportData) -> None:
           """Export using registered exporter"""
           exporter = self.exporters[export_data.format_type]
           exporter.export(geom, export_data)
   ```

#### Directory Structure Update:
```
src/
└── export/
    ├── interfaces/           # Export interfaces
    │   └── exporter.py      # GeometryExporter protocol
    ├── dxf/                 # DXF export implementation
    │   ├── converter.py     # DXF conversion
    │   └── style.py        # DXF styling
    ├── shapefile/          # Shapefile export implementation
    │   ├── exporter.py     # Shapefile export
    │   └── crs.py         # CRS handling for export
    └── manager.py          # Export coordination
```

#### Data Types Update:
```python
@dataclass
class ExportData:
    """Export configuration data"""
    id: str
    format_type: str  # 'dxf' or 'shapefile'
    style_id: Optional[str]  # Required for DXF, optional for shapefile
    layer_name: str
    target_crs: Optional[str]  # Required for shapefile
    properties: Dict[str, Any]
```

This maintains strict boundaries by:
1. Using a common interface (`GeometryExporter`)
2. Each exporter implementation is isolated
3. Format-specific concerns stay in their modules
4. Export manager knows nothing about specific formats

The export process remains format-agnostic:
```
ProcessedGeometry ──► ExportData ──► GeometryExporter ──► Output File
                          │                  ├─► DXFExporter
                          │                  └─► ShapefileExporter
                          v
                    Format-specific
                    Configuration
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
@dataclass
class ProcessedGeometry:
    """Internal geometry processing result"""
    data: GeometryData
    processing_log: List[str]

class GeometryProcessor:
    """Pure geometry processing"""
    
    def process(self, data: GeometryData) -> ProcessedGeometry:
        """Process geometry without export knowledge"""
        pass

class GeometryOperation(Protocol):
    """Interface for geometry operations"""
    def execute(self, geom: Geometry) -> Geometry: ...

class BufferOperation:
    """Example concrete operation"""
    def execute(self, geom: Geometry) -> Geometry:
        # Pure geometry transformation
        pass
```

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