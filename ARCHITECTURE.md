# Project Architecture

## Overview

This document outlines the architecture for the Python ACAD Tools project, which consists of three main components:

1. Configuration Management
2. Geometry Processing
3. DXF Export

## Directory Structure

```
.
├── src/
│   ├── config/                     # Configuration management
│   │   ├── __init__.py
│   │   ├── config_manager.py      # YAML loading and validation
│   │   ├── project_config.py      # Project-specific config handling
│   │   ├── style_config.py        # Style configuration management
│   │   └── schemas/              # YAML schemas
│   ├── geometry/                   # Geometry processing
│   │   ├── __init__.py
│   │   ├── geometry_manager.py    # Main geometry processing coordinator
│   │   ├── operations/           # Geometry operations
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Base operation class
│   │   │   ├── buffer.py
│   │   │   ├── dissolve.py
│   │   │   ├── intersection.py
│   │   │   └── difference.py
│   │   ├── layer.py             # Layer class definition
│   │   └── shapefile_loader.py  # Shapefile loading utilities
│   ├── export/                    # DXF export functionality
│   │   ├── __init__.py
│   │   ├── dxf_exporter.py      # DXF export coordination
│   │   ├── style_manager.py     # Style application
│   │   └── layer_manager.py     # DXF layer management
│   └── core/                      # Core functionality
│       ├── __init__.py
│       ├── project.py           # Main project class
│       ├── types.py            # Shared type definitions
│       └── utils.py            # Common utilities
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

## Component APIs

### 1. Configuration Management

```python
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ProjectConfig:
    """Strongly typed project configuration"""
    crs: str
    dxf_filename: str
    template_dxf: Optional[str]
    export_format: str
    dxf_version: str
    shapefile_output_dir: Optional[str]

@dataclass
class StyleConfig:
    """Style configuration for layers and entities"""
    layer_properties: Dict[str, Any]
    entity_properties: Dict[str, Any]
    text_properties: Optional[Dict[str, Any]]

class ConfigManager:
    """Manages loading and validation of all configuration files."""
    
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
    
    def load_project_config(self) -> ProjectConfig:
        """Loads and validates project.yaml"""
        pass
        
    def load_geometry_layers(self) -> Dict[str, Any]:
        """Loads and validates geom_layers.yaml"""
        pass
        
    def load_styles(self) -> Dict[str, StyleConfig]:
        """Loads and validates styles.yaml"""
        pass
        
    def validate_config(self, config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Validates configuration against schema"""
        pass
```

### 2. Geometry Processing

```python
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from shapely.geometry import base

@dataclass
class GeometryLayer:
    """Represents a processed geometry layer"""
    name: str
    geometry: base.BaseGeometry
    attributes: Dict[str, Any]
    operations_log: List[str]
    style: Optional[str]
    update_dxf: bool = False

class GeometryOperation:
    """Base class for geometry operations"""
    
    def execute(self, geometry: base.BaseGeometry, **kwargs) -> base.BaseGeometry:
        """Execute the operation on the geometry"""
        raise NotImplementedError

class GeometryManager:
    """Manages geometry processing pipeline"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.layers: Dict[str, GeometryLayer] = {}
        self._operations: Dict[str, GeometryOperation] = {}
    
    def register_operation(self, name: str, operation: GeometryOperation) -> None:
        """Register a new geometry operation"""
        pass
    
    def process_layer(self, layer_name: str) -> GeometryLayer:
        """Process a single layer according to its configuration"""
        pass
    
    def get_layer(self, layer_name: str) -> Optional[GeometryLayer]:
        """Get processed geometry for a layer"""
        pass
```

### 3. Export

```python
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class DXFLayerProperties:
    """DXF layer properties"""
    name: str
    color: Optional[int]
    linetype: Optional[str]
    lineweight: Optional[int]
    plot: bool = True
    frozen: bool = False

class DXFExporter:
    """Handles export of geometries to DXF"""
    
    def __init__(self, style_manager: 'StyleManager', layer_manager: 'LayerManager'):
        self.style_manager = style_manager
        self.layer_manager = layer_manager
    
    def export_layer(self, layer: GeometryLayer, style: StyleConfig) -> None:
        """Export a single geometry layer to DXF"""
        pass
    
    def finalize_export(self) -> None:
        """Finalize the DXF file"""
        pass

class StyleManager:
    """Manages style application"""
    
    def __init__(self, style_configs: Dict[str, StyleConfig]):
        self.style_configs = style_configs
    
    def apply_style(self, geometry: Any, style: StyleConfig) -> None:
        """Apply style to geometry"""
        pass
    
    def get_style(self, style_name: str) -> Optional[StyleConfig]:
        """Get style configuration by name"""
        pass

class LayerManager:
    """Manages DXF layers"""
    
    def create_layer(self, properties: DXFLayerProperties) -> None:
        """Create a new DXF layer"""
        pass
    
    def get_layer(self, name: str) -> Optional[DXFLayerProperties]:
        """Get layer properties by name"""
        pass
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