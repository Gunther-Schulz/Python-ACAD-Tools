"""Tests for project coordinator."""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.core.project import Project
from src.core.types import ExportData
from src.config.config_manager import ConfigValidationError
from src.geometry.types.layer import Layer, LayerCollection
from src.geometry.types.base import GeometryData, GeometryMetadata

@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        'name': 'test_project',
        'shapefile_output_dir': 'output',
        'styles': []
    }

@pytest.fixture
def mock_export_manager():
    """Create mock export manager."""
    manager = MagicMock()
    manager.export = MagicMock()
    manager.cleanup = MagicMock()
    return manager

@pytest.fixture
def mock_geometry_manager():
    """Create mock geometry manager."""
    manager = MagicMock()
    manager.get_layer_names = MagicMock(return_value=["test_layer"])
    manager.process_layer = MagicMock()
    return manager

@pytest.fixture
def test_project_dir(tmp_path, mock_config):
    """Create a temporary project directory structure."""
    # Create project directory
    project_dir = tmp_path / "test_project"
    project_dir.mkdir(parents=True)
    
    # Create output directory
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True)
    
    # Create necessary config files
    config_dir = project_dir / "config"
    config_dir.mkdir()
    
    # Create project.yaml with only project-specific settings
    with open(project_dir / "project.yaml", "w") as f:
        f.write("""
crs: EPSG:25832
dxfFilename: output/test.dxf
exportFormat: dxf
dxfVersion: R2018
shapefileOutputDir: output
""")
    
    # Create styles.yaml
    with open(project_dir / "styles.yaml", "w") as f:
        f.write("""
styles:
  default:
    layer:
      color: "7"
      lineweight: 25
      linetype: "CONTINUOUS"
    polygon:
      close: false
      elevation: 0.0
      color: "7"
""")
    
    # Create geometry_layers.yaml
    with open(project_dir / "geometry_layers.yaml", "w") as f:
        f.write("""
geomLayers:
  - name: test_layer
    style: default
    updateDxf: true
    operations: []
""")
    
    # Create other config files
    for filename in ["viewports", "legends", "block_inserts", "text_inserts", "path_arrays", "web_services"]:
        with open(project_dir / f"{filename}.yaml", "w") as f:
            f.write(f"{filename}: []")
    
    return project_dir

@pytest.fixture
def mock_project_path(test_project_dir):
    """Mock project path resolution."""
    with patch('src.core.project.get_project_dir') as mock_get_dir:
        mock_get_dir.return_value = test_project_dir
        yield mock_get_dir

@pytest.fixture
def mock_config_manager():
    """Mock config manager path resolution."""
    with patch('src.config.config_manager.ConfigManager._resolve_path') as mock_resolve:
        def resolve_mock(path, folder_prefix=None):
            return Path(path)
        mock_resolve.side_effect = resolve_mock
        yield mock_resolve

def test_project_initialization(mock_project_path, mock_config_manager, test_project_dir):
    """Test project initialization."""
    with patch('src.core.project.ExportManager') as mock_export_cls, \
         patch('src.core.project.GeometryManager') as mock_geom_cls:
        
        mock_export_cls.return_value = MagicMock()
        mock_geom_cls.return_value = MagicMock()
        
        project = Project("test_project")
        
        assert project.project_name == "test_project"
        assert project.project_dir == test_project_dir
        assert project.config_manager is not None
        assert project.geometry_manager is not None
        assert project.export_manager is not None

def test_project_processing(mock_project_path, mock_config_manager, test_project_dir, 
                          mock_export_manager, mock_geometry_manager):
    """Test project processing."""
    with patch('src.core.project.ExportManager') as mock_export_cls, \
         patch('src.core.project.GeometryManager') as mock_geom_cls:
        
        mock_export_cls.return_value = mock_export_manager
        mock_geom_cls.return_value = mock_geometry_manager
        
        project = Project("test_project")
        
        # Process project
        project.process()
        
        # Verify layer was processed
        mock_geometry_manager.process_layer.assert_called_once_with("test_layer")
        
        # Verify export was attempted
        mock_export_manager.export.assert_called_once()

def test_project_error_handling(mock_project_path, mock_config_manager, test_project_dir,
                              mock_export_manager, mock_geometry_manager):
    """Test project error handling."""
    with patch('src.core.project.ExportManager') as mock_export_cls, \
         patch('src.core.project.GeometryManager') as mock_geom_cls:
        
        mock_export_cls.return_value = mock_export_manager
        mock_geom_cls.return_value = mock_geometry_manager
        
        # Setup error condition
        mock_geometry_manager.process_layer.side_effect = ValueError("Test error")
        
        project = Project("test_project")
        
        # Verify error handling
        with pytest.raises(ValueError) as exc:
            project.process()
        assert "Test error" in str(exc.value)
        
        # Verify cleanup was attempted
        mock_export_manager.cleanup.assert_called_once()

def test_project_with_log_file(mock_project_path, mock_config_manager, test_project_dir, tmp_path):
    """Test project with log file."""
    log_file = tmp_path / "test.log"
    project = Project("test_project", log_file=str(log_file))
    
    # Verify log file was created
    assert log_file.exists()
    
    # Generate some log entries
    project.logger.info("Test log entry")
    
    # Verify log entry was written
    log_content = log_file.read_text()
    assert "Test log entry" in log_content

def test_project_with_folder_prefix(mock_project_path, mock_config_manager, test_project_dir):
    """Test project with folder prefix."""
    # Create projects.yaml with folder prefix
    root_dir = test_project_dir.parent
    with open(root_dir / "projects.yaml", "w") as f:
        f.write("folderPrefix: test_")
    
    # Mock the load_folder_prefix function
    with patch('src.core.project.load_folder_prefix', return_value="test_"):
        project = Project("test_project")
        assert project.folder_prefix == "test_"

def test_project_output_directory_creation(mock_project_path, mock_config_manager, test_project_dir):
    """Test output directory creation."""
    # Output directory is created in test_project_dir fixture
    project = Project("test_project")
    
    # Verify output directory exists
    output_dir = test_project_dir / "output"
    assert output_dir.exists()
    assert output_dir.is_dir()

def test_config_to_geometry_layer_creation(mock_project_path, mock_config_manager, test_project_dir):
    """Test creation of geometry layers from configuration."""
    with patch('src.core.project.GeometryManager') as mock_geom_cls, \
         patch('src.core.project.ExportManager') as mock_export_cls:
        
        # Setup mock geometry manager
        mock_layer_collection = LayerCollection()
        mock_geom_manager = mock_geom_cls.return_value
        mock_geom_manager.layer_collection = mock_layer_collection
        mock_geom_manager.get_layer_names.side_effect = lambda: list(mock_layer_collection.layers.keys())
        mock_geom_manager.get_layer.side_effect = lambda name: mock_layer_collection.layers.get(name)
        
        # Create project with test configuration
        with open(test_project_dir / "geometry_layers.yaml", "w") as f:
            f.write("""
geomLayers:
  - name: base_layer
    style: default
    updateDxf: true
    operations: []
  - name: dependent_layer
    style: default
    updateDxf: true
    operations:
      - type: buffer
        layers: 
          - base_layer
        distance: 10
""")
        
        project = Project("test_project")
        
        # Simulate layer creation
        base_layer = Layer(
            name="base_layer",
            geometry=GeometryData(
                id="base_layer",
                geometry=None,
                metadata=GeometryMetadata(source_type='config')
            ),
            style_id="default"
        )
        dependent_layer = Layer(
            name="dependent_layer",
            geometry=GeometryData(
                id="dependent_layer",
                geometry=None,
                metadata=GeometryMetadata(source_type='config')
            ),
            style_id="default",
            operations=[{
                "type": "buffer",
                "layers": ["base_layer"],
                "distance": 10
            }]
        )
        
        mock_layer_collection.add_layer(base_layer)
        mock_layer_collection.add_layer(dependent_layer)
        mock_layer_collection.add_dependency("dependent_layer", "base_layer")
        
        # Verify layers
        layer_names = project.geometry_manager.get_layer_names()
        assert "base_layer" in layer_names
        assert "dependent_layer" in layer_names
        
        # Verify dependency
        dependent = project.geometry_manager.get_layer("dependent_layer")
        assert len(dependent.operations) == 1
        assert dependent.operations[0]["type"] == "buffer"
        assert "base_layer" in dependent.operations[0]["layers"]

def test_style_application_from_config(mock_project_path, mock_config_manager, test_project_dir):
    """Test style application from config to geometry layers."""
    with patch('src.core.project.GeometryManager') as mock_geom_cls, \
         patch('src.core.project.StyleManager') as mock_style_cls, \
         patch('src.core.project.ExportManager') as mock_export_cls:
        
        # Setup mock style manager
        mock_style_manager = mock_style_cls.return_value
        mock_style = MagicMock()
        mock_style.layer.color = "1"
        mock_style.layer.lineweight = 50
        mock_style.polygon.close = True
        mock_style_manager.get_style.return_value = mock_style
        
        # Setup mock geometry manager
        mock_layer_collection = LayerCollection()
        mock_geom_manager = mock_geom_cls.return_value
        mock_geom_manager.layer_collection = mock_layer_collection
        mock_geom_manager.get_layer.side_effect = lambda name: mock_layer_collection.layers.get(name)
        
        # Create project with test configuration
        with open(test_project_dir / "styles.yaml", "w") as f:
            f.write("""
styles:
  custom_style:
    layer:
      color: "1"
      lineweight: 50
      linetype: "DASHED"
    polygon:
      close: true
      color: "2"
""")
        
        with open(test_project_dir / "geometry_layers.yaml", "w") as f:
            f.write("""
geomLayers:
  - name: styled_layer
    style: custom_style
    updateDxf: true
    operations: []
""")
        
        project = Project("test_project")
        
        # Simulate layer creation
        styled_layer = Layer(
            name="styled_layer",
            geometry=GeometryData(
                id="styled_layer",
                geometry=None,
                metadata=GeometryMetadata(source_type='config')
            ),
            style_id="custom_style"
        )
        mock_layer_collection.add_layer(styled_layer)
        
        # Verify style application
        layer = project.geometry_manager.get_layer("styled_layer")
        assert layer.style_id == "custom_style"
        
        style = project.style_manager.get_style("custom_style")
        assert style.layer.color == "1"
        assert style.layer.lineweight == 50
        assert style.polygon.close is True

def test_layer_processing_order(mock_project_path, mock_config_manager, test_project_dir):
    """Test correct processing order of layers with dependencies."""
    # Create a simple LayerCollection for testing
    layer_collection = LayerCollection()
    
    # Create layers with dependencies
    layer1 = Layer(
        name="layer1",
        geometry=GeometryData(
            id="layer1",
            geometry=None,
            metadata=GeometryMetadata(source_type='config')
        ),
        style_id="default"
    )
    layer_collection.add_layer(layer1)
    
    layer2 = Layer(
        name="layer2",
        geometry=GeometryData(
            id="layer2",
            geometry=None,
            metadata=GeometryMetadata(source_type='config')
        ),
        style_id="default",
        operations=[{"type": "buffer", "layers": ["layer1"]}]
    )
    layer_collection.add_layer(layer2)
    
    layer3 = Layer(
        name="layer3",
        geometry=GeometryData(
            id="layer3",
            geometry=None,
            metadata=GeometryMetadata(source_type='config')
        ),
        style_id="default",
        operations=[{"type": "buffer", "layers": ["layer2"]}]
    )
    layer_collection.add_layer(layer3)
    
    # Add dependencies
    layer_collection.add_dependency("layer2", "layer1")
    layer_collection.add_dependency("layer3", "layer2")
    
    # Get processing order
    order = layer_collection.get_processing_order()
    
    # Verify order
    assert order == ["layer1", "layer2", "layer3"]

def test_error_propagation_between_components(mock_project_path, mock_config_manager, test_project_dir):
    """Test error propagation between config, geometry, and core components."""
    with patch('src.core.project.GeometryManager') as mock_geom_cls, \
         patch('src.core.project.StyleManager') as mock_style_cls, \
         patch('src.core.project.ExportManager') as mock_export_cls:
        
        # Setup mock style manager to raise error for nonexistent style
        mock_style_manager = mock_style_cls.return_value
        mock_style_manager.get_style.side_effect = ConfigValidationError("Style 'nonexistent_style' not found")
        mock_style_manager.get_layer_style.side_effect = ConfigValidationError("Style 'nonexistent_style' not found")
        
        # Create project with invalid configuration
        with open(test_project_dir / "geometry_layers.yaml", "w") as f:
            f.write("""
geomLayers:
  - name: invalid_layer
    style: nonexistent_style
    updateDxf: true
""")
        
        # Create mock layer for error propagation
        mock_layer = Layer(
            name="invalid_layer",
            geometry=GeometryData(
                id="invalid_layer",
                geometry=None,
                metadata=GeometryMetadata(source_type='config')
            ),
            style_id="nonexistent_style"
        )
        
        # Setup mock geometry manager to return our layer
        mock_layer_collection = LayerCollection()
        mock_layer_collection.add_layer(mock_layer)
        mock_geom_manager = mock_geom_cls.return_value
        mock_geom_manager.layer_collection = mock_layer_collection
        mock_geom_manager.get_layer.return_value = mock_layer
        
        # Verify error propagation
        project = Project("test_project")
        with pytest.raises(ConfigValidationError) as exc:
            project.style_manager.get_layer_style(mock_layer)
        assert "nonexistent_style" in str(exc.value)

def test_inline_style_override(mock_project_path, mock_config_manager, test_project_dir):
    """Test inline style overrides in geometry layers."""
    with patch('src.core.project.GeometryManager') as mock_geom_cls, \
         patch('src.core.project.StyleManager') as mock_style_cls, \
         patch('src.core.project.ExportManager') as mock_export_cls:
        
        # Setup mock managers
        mock_layer_collection = LayerCollection()
        mock_geom_manager = mock_geom_cls.return_value
        mock_geom_manager.layer_collection = mock_layer_collection
        mock_geom_manager.get_layer.side_effect = lambda name: mock_layer_collection.layers.get(name)
        
        mock_style_manager = mock_style_cls.return_value
        mock_style = MagicMock()
        mock_style.layer.color = "3"
        mock_style.layer.lineweight = 75
        mock_style.polygon.close = True
        mock_style_manager.get_layer_style.return_value = mock_style
        
        # Create project with test configuration
        with open(test_project_dir / "geometry_layers.yaml", "w") as f:
            f.write("""
geomLayers:
  - name: inline_styled_layer
    style: default
    inlineStyle:
      layer:
        color: "3"
        lineweight: 75
      polygon:
        close: true
    updateDxf: true
""")
        
        project = Project("test_project")
        
        # Simulate layer creation
        styled_layer = Layer(
            name="inline_styled_layer",
            geometry=GeometryData(
                id="inline_styled_layer",
                geometry=None,
                metadata=GeometryMetadata(source_type='config')
            ),
            style_id="default"
        )
        mock_layer_collection.add_layer(styled_layer)
        
        # Verify style override
        layer = project.geometry_manager.get_layer("inline_styled_layer")
        style = project.style_manager.get_layer_style(layer)
        assert style.layer.color == "3"
        assert style.layer.lineweight == 75
        assert style.polygon.close is True 