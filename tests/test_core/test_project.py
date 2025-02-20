"""Tests for the Project class."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.core.project import Project
from src.core.utils import setup_logger

@pytest.fixture
def mock_components():
    """Mock all project components."""
    with patch('src.core.project.ConfigManager') as mock_config, \
         patch('src.core.project.GeometryManager') as mock_geom, \
         patch('src.core.project.StyleManager') as mock_style, \
         patch('src.core.project.DXFExporter') as mock_exporter, \
         patch('src.core.project.DXFStyleValidator') as mock_validator, \
         patch('src.core.project.ExportManager') as mock_export_manager:
        
        # Configure mocks
        mock_config.return_value.load_project_config.return_value.shapefile_output_dir = "output"
        mock_config.return_value.load_geometry_layers.return_value = []
        mock_config.return_value.load_styles.return_value = {}
        
        mock_geom.return_value.get_layer_names.return_value = ["layer1", "layer2"]
        mock_geom.return_value.process_layer.return_value = Mock(update_dxf=True, style="default_style")
        
        # Configure export manager mock
        mock_export_manager.return_value.export = Mock()
        mock_export_manager.return_value.cleanup = Mock()
        
        yield {
            'config': mock_config,
            'geometry': mock_geom,
            'style': mock_style,
            'exporter': mock_exporter,
            'validator': mock_validator,
            'export_manager': mock_export_manager
        }

def test_project_initialization(mock_components, tmp_path):
    """Test project initialization."""
    project = Project("test_project")
    
    # Check component initialization
    mock_components['config'].assert_called_once_with("test_project")
    mock_components['geometry'].assert_called_once()
    mock_components['style'].assert_called_once_with(
        styles=mock_components['config'].return_value.load_styles.return_value,
        validator=mock_components['validator'].return_value
    )
    mock_components['exporter'].assert_called_once()
    mock_components['export_manager'].assert_called_once()
    
    # Check logger setup
    assert project.logger.name == "project.test_project"

def test_project_processing(mock_components):
    """Test project processing workflow."""
    project = Project("test_project")
    
    # Process project
    project.process()
    
    # Verify processing flow
    geom_manager = mock_components['geometry'].return_value
    assert geom_manager.process_layer.call_count == 2  # Two layers processed
    
    # Verify export manager was used correctly
    export_manager = mock_components['export_manager'].return_value
    assert export_manager.export.call_count == 2  # Two layers exported

def test_project_error_handling(mock_components):
    """Test error handling during project processing."""
    project = Project("test_project")
    
    # Configure mock to raise an error
    mock_components['geometry'].return_value.process_layer.side_effect = Exception("Test error")
    
    # Process project and check error handling
    with pytest.raises(Exception) as exc_info:
        project.process()
    
    assert str(exc_info.value) == "Test error"
    
    # Verify cleanup was attempted
    export_manager = mock_components['export_manager'].return_value
    assert export_manager.cleanup.call_count == 1

def test_project_with_log_file(mock_components, tmp_path):
    """Test project with log file output."""
    log_file = os.path.join(tmp_path, "project.log")
    project = Project("test_project", log_file=log_file)
    
    # Trigger some logging
    project.logger.info("Test log message")
    
    # Verify log file
    assert os.path.exists(log_file)
    with open(log_file, 'r') as f:
        log_content = f.read()
        assert "Test log message" in log_content 