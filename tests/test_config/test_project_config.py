"""Tests for project configuration."""

import pytest
from src.config.project_config import ProjectConfig

def test_project_config_creation():
    """Test ProjectConfig creation."""
    config = ProjectConfig(
        crs="EPSG:25833",
        dxf_filename="output/test.dxf",
        template_dxf=None,
        export_format="dxf",
        dxf_version="R2010",
        shapefile_output_dir=None
    )
    
    assert config.crs == "EPSG:25833"
    assert config.dxf_filename == "output/test.dxf"
    assert config.template_dxf is None
    assert config.export_format == "dxf"
    assert config.dxf_version == "R2010"
    assert config.shapefile_output_dir is None

def test_project_config_from_dict():
    """Test ProjectConfig creation from dictionary."""
    data = {
        'crs': "EPSG:25833",
        'dxfFilename': "output/test.dxf",
        'template': "templates/base.dxf",
        'exportFormat': "dxf",
        'dxfVersion': "R2010",
        'shapefileOutputDir': "output"
    }
    
    config = ProjectConfig.from_dict(data)
    
    assert config.crs == "EPSG:25833"
    assert config.dxf_filename == "output/test.dxf"
    assert config.template_dxf == "templates/base.dxf"
    assert config.export_format == "dxf"
    assert config.dxf_version == "R2010"
    assert config.shapefile_output_dir == "output"

def test_project_config_from_dict_with_prefix():
    """Test ProjectConfig creation from dictionary with folder prefix."""
    data = {
        'crs': "EPSG:25833",
        'dxfFilename': "output/test.dxf",
        'template': "templates/base.dxf",
        'exportFormat': "dxf",
        'dxfVersion': "R2010"
    }
    
    config = ProjectConfig.from_dict(data, folder_prefix="project1")
    
    assert config.dxf_filename == "project1/output/test.dxf"
    assert config.template_dxf == "project1/templates/base.dxf"

def test_project_config_to_dict():
    """Test ProjectConfig conversion to dictionary."""
    config = ProjectConfig(
        crs="EPSG:25833",
        dxf_filename="output/test.dxf",
        template_dxf="templates/base.dxf",
        export_format="dxf",
        dxf_version="R2010",
        shapefile_output_dir="output"
    )
    
    data = config.to_dict()
    
    assert data['crs'] == "EPSG:25833"
    assert data['dxfFilename'] == "output/test.dxf"
    assert data['template'] == "templates/base.dxf"
    assert data['exportFormat'] == "dxf"
    assert data['dxfVersion'] == "R2010"
    assert data['shapefileOutputDir'] == "output" 