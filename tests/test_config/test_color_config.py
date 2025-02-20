"""Tests for color configuration."""

import pytest
from pathlib import Path
from src.config.color_config import load_color_mapping

def test_load_color_mapping_default():
    """Test loading default color mapping when no file is provided."""
    mapping = load_color_mapping(None)
    
    # Check basic colors are present with correct format
    assert mapping['white']['aci'] == 7
    assert mapping['white']['rgb'] == (255, 255, 255)
    assert mapping['red']['aci'] == 1
    assert mapping['red']['rgb'] == (255, 0, 0)
    assert mapping['blue']['aci'] == 5
    assert mapping['blue']['rgb'] == (0, 0, 255)
    assert mapping['bylayer']['aci'] == 256
    assert mapping['bylayer']['rgb'] is None
    
    # Check all required colors are present
    required_colors = {
        'white', 'red', 'yellow', 'green', 'cyan', 'blue', 'magenta',
        'black', 'gray', 'light-grey', 'dark-grey', 'bylayer', 'byblock'
    }
    assert set(mapping.keys()) == required_colors

def test_load_color_mapping_from_file(tmp_path):
    """Test loading color mapping from YAML file."""
    # Create a test YAML file
    yaml_content = """
- name: Custom Red
  aciCode: 1
  rgb:
  - 255
  - 0
  - 0
- name: Custom Blue
  aciCode: 5
  rgb:
  - 0
  - 0
  - 255
- name: Special Color
  aciCode: 42
  rgb:
  - 128
  - 128
  - 128
"""
    yaml_path = tmp_path / "test_colors.yaml"
    yaml_path.write_text(yaml_content)
    
    mapping = load_color_mapping(yaml_path)
    
    # Check custom colors are loaded correctly
    assert mapping['custom red']['aci'] == 1
    assert mapping['custom red']['rgb'] == (255, 0, 0)
    assert mapping['custom blue']['aci'] == 5
    assert mapping['custom blue']['rgb'] == (0, 0, 255)
    assert mapping['special color']['aci'] == 42
    assert mapping['special color']['rgb'] == (128, 128, 128)

def test_load_color_mapping_invalid_file(tmp_path):
    """Test loading color mapping from invalid YAML file returns defaults."""
    # Create an invalid YAML file
    yaml_path = tmp_path / "invalid_colors.yaml"
    yaml_path.write_text("invalid: yaml: content: - [}")
    
    mapping = load_color_mapping(yaml_path)
    
    # Should fall back to default mapping
    assert mapping['white']['aci'] == 7
    assert mapping['white']['rgb'] == (255, 255, 255)
    assert mapping['red']['aci'] == 1
    assert mapping['red']['rgb'] == (255, 0, 0)

def test_load_color_mapping_nonexistent_file():
    """Test loading color mapping from nonexistent file returns defaults."""
    mapping = load_color_mapping(Path("nonexistent.yaml"))
    
    # Should fall back to default mapping
    assert mapping['white']['aci'] == 7
    assert mapping['white']['rgb'] == (255, 255, 255)
    assert mapping['red']['aci'] == 1
    assert mapping['red']['rgb'] == (255, 0, 0)

def test_load_color_mapping_case_insensitive(tmp_path):
    """Test color names are case insensitive."""
    yaml_content = """
- name: UPPER CASE
  aciCode: 100
  rgb:
  - 200
  - 200
  - 200
- name: lower case
  aciCode: 101
  rgb:
  - 100
  - 100
  - 100
- name: Mixed Case
  aciCode: 102
  rgb:
  - 150
  - 150
  - 150
"""
    yaml_path = tmp_path / "test_colors.yaml"
    yaml_path.write_text(yaml_content)
    
    mapping = load_color_mapping(yaml_path)
    
    assert mapping['upper case']['aci'] == 100
    assert mapping['upper case']['rgb'] == (200, 200, 200)
    assert mapping['lower case']['aci'] == 101
    assert mapping['lower case']['rgb'] == (100, 100, 100)
    assert mapping['mixed case']['aci'] == 102
    assert mapping['mixed case']['rgb'] == (150, 150, 150) 