"""Tests for project coordinator."""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch
from src.core.project import Project
from src.core.types import ExportData

@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        'name': 'test_project',
        'shapefile_output_dir': 'output',
        'styles': []
    }

@pytest.fixture
def test_project_dir(tmp_path, mock_config):
    """Create a temporary project directory structure."""
    # Create project directory
    project_dir = tmp_path / "test_project"
    project_dir.mkdir(parents=True)
    
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
      lineweight: 0.25
      linetype: "CONTINUOUS"
    entity:
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
    
    # Create viewports.yaml
    with open(project_dir / "viewports.yaml", "w") as f:
        f.write("viewports: []")
    
    # Create legends.yaml
    with open(project_dir / "legends.yaml", "w") as f:
        f.write("legends: []")
    
    # Create block_inserts.yaml
    with open(project_dir / "block_inserts.yaml", "w") as f:
        f.write("blockInserts: []")
    
    # Create text_inserts.yaml
    with open(project_dir / "text_inserts.yaml", "w") as f:
        f.write("textInserts: []")
    
    # Create path_arrays.yaml
    with open(project_dir / "path_arrays.yaml", "w") as f:
        f.write("pathArrays: []")
    
    # Create web_services.yaml
    with open(project_dir / "web_services.yaml", "w") as f:
        f.write("webServices: []")
    
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
    project = Project("test_project")
    
    assert project.project_name == "test_project"
    assert project.project_dir == test_project_dir
    assert project.config_manager is not None
    assert project.geometry_manager is not None
    assert project.export_manager is not None

def test_project_processing(mock_project_path, mock_config_manager, test_project_dir):
    """Test project processing."""
    project = Project("test_project")
    
    # Mock geometry manager to return a test layer
    mock_layer = Mock()
    mock_layer.name = "test_layer"
    mock_layer.update_dxf = True
    mock_layer.style = "default"
    
    project.geometry_manager.get_layer_names = Mock(return_value=["test_layer"])
    project.geometry_manager.process_layer = Mock(return_value=mock_layer)
    
    # Process project
    project.process()
    
    # Verify layer was processed
    project.geometry_manager.process_layer.assert_called_once_with("test_layer")
    
    # Verify export was attempted
    assert project.export_manager.export.called

def test_project_error_handling(mock_project_path, mock_config_manager, test_project_dir):
    """Test project error handling."""
    project = Project("test_project")
    
    # Mock geometry manager to raise an error
    project.geometry_manager.get_layer_names = Mock(return_value=["test_layer"])
    project.geometry_manager.process_layer = Mock(side_effect=ValueError("Test error"))
    
    # Verify error handling
    with pytest.raises(ValueError) as exc:
        project.process()
    assert "Test error" in str(exc.value)
    
    # Verify cleanup was attempted
    assert project.export_manager.cleanup.called

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
    
    project = Project("test_project")
    assert project.folder_prefix == "test_"

def test_project_output_directory_creation(mock_project_path, mock_config_manager, test_project_dir):
    """Test output directory creation."""
    project = Project("test_project")
    
    # Verify output directory was created
    output_dir = test_project_dir / "output"
    assert output_dir.exists()
    assert output_dir.is_dir() 