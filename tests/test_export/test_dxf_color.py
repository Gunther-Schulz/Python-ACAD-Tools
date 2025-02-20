"""Tests for DXF color handling."""

import pytest
from pathlib import Path
from src.export.dxf.color import DXFColorConverter, BYLAYER, BYBLOCK, DEFAULT_COLOR

def test_dxf_color_converter_initialization():
    """Test DXFColorConverter initialization."""
    # Test default initialization
    converter = DXFColorConverter()
    assert converter.color_mapping['white']['aci'] == 7
    assert converter.color_mapping['red']['aci'] == 1
    
    # Test custom mapping
    custom_mapping = {
        'custom': {
            'aci': 42,
            'rgb': (128, 128, 128)
        }
    }
    converter = DXFColorConverter(color_mapping=custom_mapping)
    assert converter.color_mapping == custom_mapping
    
    # Test initialization with YAML path
    yaml_content = """
- name: Test Color
  aciCode: 42
  rgb:
  - 128
  - 128
  - 128
"""
    tmp_path = Path("test_colors.yaml")
    tmp_path.write_text(yaml_content)
    converter = DXFColorConverter(color_yaml_path=tmp_path)
    assert converter.color_mapping['test color']['aci'] == 42
    assert converter.color_mapping['test color']['rgb'] == (128, 128, 128)
    tmp_path.unlink()  # Clean up

def test_get_color_code_special_values():
    """Test handling of special color values."""
    converter = DXFColorConverter()
    
    # Test None
    assert converter.get_color_code(None) == DEFAULT_COLOR
    
    # Test BYLAYER and BYBLOCK
    assert converter.get_color_code('BYLAYER') == BYLAYER
    assert converter.get_color_code('byLayer') == BYLAYER  # Case insensitive
    assert converter.get_color_code('BYBLOCK') == BYBLOCK
    assert converter.get_color_code('byBlock') == BYBLOCK  # Case insensitive

def test_get_color_code_named_colors():
    """Test handling of named colors."""
    converter = DXFColorConverter()
    
    # Test basic colors
    assert converter.get_color_code('red') == 1
    assert converter.get_color_code('RED') == 1  # Case insensitive
    assert converter.get_color_code('blue') == 5
    assert converter.get_color_code('white') == 7
    
    # Test unknown color name
    assert converter.get_color_code('nonexistent') == DEFAULT_COLOR

def test_get_color_code_rgb():
    """Test handling of RGB color values."""
    converter = DXFColorConverter()
    
    # Test valid RGB tuples
    assert converter.get_color_code((255, 0, 0)) == (255, 0, 0)
    assert converter.get_color_code([0, 255, 0]) == (0, 255, 0)
    
    # Test RGB value clamping
    assert converter.get_color_code((300, -50, 128)) == (255, 0, 128)

def test_get_color_code_aci():
    """Test handling of ACI color codes."""
    converter = DXFColorConverter()
    
    # Test valid ACI codes
    assert converter.get_color_code(1) == 1
    assert converter.get_color_code(255) == 255
    
    # Test ACI code clamping
    assert converter.get_color_code(-1) == 0
    assert converter.get_color_code(300) == 255

def test_get_rgb_values():
    """Test getting RGB values."""
    converter = DXFColorConverter()
    
    # Test named colors
    assert converter.get_rgb('red') == (255, 0, 0)
    assert converter.get_rgb('green') == (0, 255, 0)
    assert converter.get_rgb('blue') == (0, 0, 255)
    
    # Test RGB tuples
    assert converter.get_rgb((128, 128, 128)) == (128, 128, 128)
    assert converter.get_rgb([255, 0, 128]) == (255, 0, 128)
    
    # Test value clamping
    assert converter.get_rgb((300, -50, 128)) == (255, 0, 128)
    
    # Test special values
    assert converter.get_rgb('BYLAYER') is None
    assert converter.get_rgb('BYBLOCK') is None
    assert converter.get_rgb('nonexistent') is None

def test_is_valid_color():
    """Test color validation."""
    converter = DXFColorConverter()
    
    # Test valid colors
    assert converter.is_valid_color('BYLAYER')
    assert converter.is_valid_color('byblock')
    assert converter.is_valid_color('red')
    assert converter.is_valid_color((128, 128, 128))
    assert converter.is_valid_color(1)
    
    # Test invalid colors
    assert not converter.is_valid_color('nonexistent')
    assert not converter.is_valid_color((256, 0, 0))  # RGB value too large
    assert not converter.is_valid_color(257)  # ACI code too large
    assert not converter.is_valid_color(-1)  # Negative ACI code
    assert not converter.is_valid_color((1, 2))  # Wrong tuple length
    assert not converter.is_valid_color(None)
    assert not converter.is_valid_color({})  # Invalid type

def test_custom_color_mapping():
    """Test using custom color mapping."""
    custom_mapping = {
        'custom-red': {
            'aci': 1,
            'rgb': (255, 0, 0)
        },
        'custom-blue': {
            'aci': 5,
            'rgb': (0, 0, 255)
        },
        'special': {
            'aci': 42,
            'rgb': (128, 128, 128)
        }
    }
    converter = DXFColorConverter(color_mapping=custom_mapping)
    
    # Test custom colors
    assert converter.get_color_code('custom-red') == 1
    assert converter.get_rgb('custom-red') == (255, 0, 0)
    assert converter.get_color_code('custom-blue') == 5
    assert converter.get_rgb('custom-blue') == (0, 0, 255)
    assert converter.get_color_code('special') == 42
    assert converter.get_rgb('special') == (128, 128, 128)
    
    # Test that default colors are not available
    assert converter.get_color_code('red') == DEFAULT_COLOR
    assert converter.get_rgb('red') is None 