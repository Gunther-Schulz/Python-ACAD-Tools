"""Tests for configuration manager."""

import os
import pytest
from src.config.config_manager import (
    ConfigManager,
    ConfigError,
    ConfigValidationError,
    ConfigFileNotFoundError
)

def test_config_manager_initialization(test_project_dir):
    """Test ConfigManager initialization."""
    manager = ConfigManager(test_project_dir)
    assert manager.project_dir == test_project_dir
    assert manager.logger.name == f"config_manager.{os.path.basename(test_project_dir)}"

def test_load_project_config(sample_project_files):
    """Test loading project configuration."""
    manager = ConfigManager(sample_project_files)
    config = manager.load_project_config()
    
    assert config.crs == "EPSG:25833"
    assert config.dxf_filename == "output/test.dxf"
    assert config.template_dxf == "templates/base.dxf"
    assert config.export_format == "dxf"
    assert config.dxf_version == "R2010"

def test_load_missing_required_config(test_project_dir):
    """Test loading missing required configuration."""
    manager = ConfigManager(test_project_dir)
    
    with pytest.raises(ConfigFileNotFoundError):
        manager.load_project_config()

def test_load_missing_optional_config(test_project_dir):
    """Test loading missing optional configuration."""
    manager = ConfigManager(test_project_dir)
    
    # Should not raise for optional configs
    styles = manager.load_styles()
    assert styles == {}
    
    layers = manager.load_geometry_layers()
    assert layers == {}

def test_load_invalid_yaml(test_project_dir):
    """Test loading invalid YAML file."""
    # Create invalid YAML file
    with open(os.path.join(test_project_dir, "project.yaml"), "w") as f:
        f.write("invalid: yaml: : :")
    
    manager = ConfigManager(test_project_dir)
    with pytest.raises(ConfigError):
        manager.load_project_config()

def test_load_invalid_config(test_project_dir):
    """Test loading configuration with invalid data."""
    # Create config with missing required field
    with open(os.path.join(test_project_dir, "project.yaml"), "w") as f:
        f.write("""
exportFormat: dxf
dxfVersion: R2010
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    with pytest.raises(ConfigValidationError):
        manager.load_project_config()

def test_load_styles(test_project_dir):
    """Test loading style configuration."""
    # Create styles.yaml
    with open(os.path.join(test_project_dir, "styles.yaml"), "w") as f:
        f.write("""
styles:
  default:
    layer:
      color: red
      lineweight: 13
    entity:
      close: true
    text:
      height: 2.5
      color: blue
  simple:
    layer:
      color: blue
    entity:
      close: false
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    styles = manager.load_styles()
    
    assert len(styles) == 2
    assert styles["default"].layer_properties.color == "red"
    assert styles["default"].text_properties.color == "blue"
    assert styles["simple"].entity_properties.close is False

def test_load_geometry_layers(test_project_dir):
    """Test loading geometry layers configuration."""
    # Create geom_layers.yaml
    with open(os.path.join(test_project_dir, "geom_layers.yaml"), "w") as f:
        f.write("""
geomLayers:
  - name: layer1
    updateDxf: true
    style: default
  - name: layer2
    shapeFile: input/test.shp
    style: simple
        """.strip())
    
    manager = ConfigManager(test_project_dir)
    layers = manager.load_geometry_layers()
    
    assert len(layers["geomLayers"]) == 2
    assert layers["geomLayers"][0]["name"] == "layer1"
    assert layers["geomLayers"][0]["updateDxf"] is True
    assert layers["geomLayers"][1]["shapeFile"] == "input/test.shp" 