"""Tests for DXF-specific validation."""

import pytest
from src.export.dxf.validators import DXFStyleValidator

def test_dxf_text_height_validation():
    """Test DXF text height validation."""
    validator = DXFStyleValidator()
    
    # Test valid heights
    assert validator.validate_text_height(0.1)
    assert validator.validate_text_height(1.0)
    assert validator.validate_text_height(1000.0)
    
    # Test invalid heights
    assert not validator.validate_text_height(0.09)  # Too small
    assert not validator.validate_text_height(1001.0)  # Too large
    assert not validator.validate_text_height(-1.0)  # Negative

def test_dxf_line_weight_validation():
    """Test DXF line weight validation."""
    validator = DXFStyleValidator()
    
    # Test valid weights
    assert validator.validate_line_weight(-3)  # Minimum DXF weight
    assert validator.validate_line_weight(0)
    assert validator.validate_line_weight(211)  # Maximum DXF weight
    
    # Test invalid weights
    assert not validator.validate_line_weight(-4)  # Too small
    assert not validator.validate_line_weight(212)  # Too large

def test_dxf_transparency_validation():
    """Test DXF transparency validation."""
    validator = DXFStyleValidator()
    
    # Test valid transparency values
    assert validator.validate_transparency(0)  # Opaque
    assert validator.validate_transparency(128)  # Semi-transparent
    assert validator.validate_transparency(255)  # Transparent
    
    # Test invalid transparency values
    assert not validator.validate_transparency(-1)  # Too small
    assert not validator.validate_transparency(256)  # Too large 