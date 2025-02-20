"""Tests for configuration validators."""

import os
import pytest
from pathlib import Path
from src.config.schemas.validators import (
    ValidationError,
    validate_file_path,
    validate_style_references,
    validate_viewport_references,
    validate_layer_dependencies,
    validate_operation_parameters
)

def test_validate_file_path(tmp_path):
    """Test file path validation."""
    # Create test files
    test_file = tmp_path / "test.dxf"
    test_file.write_text("")
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    
    # Test existing file
    validate_file_path(
        str(test_file.relative_to(tmp_path)),
        str(tmp_path),
        must_exist=True,
        allowed_extensions={'.dxf'}
    )
    
    # Test non-existent file when must_exist=False
    validate_file_path(
        "nonexistent.dxf",
        str(tmp_path),
        must_exist=False,
        allowed_extensions={'.dxf'}
    )
    
    # Test directory validation
    validate_file_path(
        str(test_dir.relative_to(tmp_path)),
        str(tmp_path),
        must_exist=True,
        path_type="directory"
    )
    
    # Test invalid extension
    with pytest.raises(ValidationError) as exc:
        validate_file_path(
            str(test_file.relative_to(tmp_path)),
            str(tmp_path),
            allowed_extensions={'.shp'}
        )
    assert "Invalid file extension" in str(exc.value)
    
    # Test non-existent file when must_exist=True
    with pytest.raises(ValidationError) as exc:
        validate_file_path(
            "nonexistent.dxf",
            str(tmp_path),
            must_exist=True
        )
    assert "does not exist" in str(exc.value)
    
    # Test wrong path type
    with pytest.raises(ValidationError) as exc:
        validate_file_path(
            str(test_dir.relative_to(tmp_path)),
            str(tmp_path),
            must_exist=True,
            path_type="file"
        )
    assert "Path is not a file" in str(exc.value)

def test_validate_style_references():
    """Test style reference validation."""
    available_styles = {"style1", "style2"}
    
    # Test valid style references
    layers = [
        {"name": "layer1", "style": "style1"},
        {"name": "layer2", "style": "style2"},
        {"name": "layer3", "style": {"layer": {"color": "red"}}}  # Inline style
    ]
    validate_style_references(layers, available_styles)
    
    # Test invalid style reference
    layers = [
        {"name": "layer1", "style": "nonexistent"}
    ]
    with pytest.raises(ValidationError) as exc:
        validate_style_references(layers, available_styles)
    assert "Style 'nonexistent' referenced by layer 'layer1' does not exist" in str(exc.value)

def test_validate_viewport_references():
    """Test viewport reference validation."""
    available_viewports = {"vp1", "vp2"}
    
    # Test valid viewport references
    layers = [
        {
            "name": "layer1",
            "viewports": [{"name": "vp1"}, {"name": "vp2"}]
        }
    ]
    validate_viewport_references(layers, available_viewports)
    
    # Test invalid viewport reference
    layers = [
        {
            "name": "layer1",
            "viewports": [{"name": "nonexistent"}]
        }
    ]
    with pytest.raises(ValidationError) as exc:
        validate_viewport_references(layers, available_viewports)
    assert "Viewport 'nonexistent' referenced by layer 'layer1' does not exist" in str(exc.value)

def test_validate_layer_dependencies():
    """Test layer dependency validation."""
    # Test valid layer dependencies
    layers = [
        {"name": "layer1"},
        {
            "name": "layer2",
            "operations": [
                {"type": "buffer", "layers": ["layer1"]},
                {"type": "union", "layers": [{"name": "layer1"}]}
            ]
        }
    ]
    validate_layer_dependencies(layers)
    
    # Test invalid layer dependency
    layers = [
        {"name": "layer1"},
        {
            "name": "layer2",
            "operations": [
                {"type": "buffer", "layers": ["nonexistent"]}
            ]
        }
    ]
    with pytest.raises(ValidationError) as exc:
        validate_layer_dependencies(layers)
    assert "Layer 'nonexistent' referenced in operation of layer 'layer2' does not exist" in str(exc.value)

def test_validate_operation_parameters():
    """Test operation parameter validation."""
    # Test valid buffer operation
    layers = [
        {
            "name": "layer1",
            "operations": [
                {
                    "type": "buffer",
                    "distance": 1.0
                }
            ]
        }
    ]
    validate_operation_parameters(layers)
    
    # Test buffer operation with useBufferTrick
    layers = [
        {
            "name": "layer1",
            "operations": [
                {
                    "type": "buffer",
                    "distance": 1.0,
                    "useBufferTrick": True,
                    "bufferDistance": 0.1
                }
            ]
        }
    ]
    validate_operation_parameters(layers)
    
    # Test missing distance parameter
    layers = [
        {
            "name": "layer1",
            "operations": [
                {
                    "type": "buffer"
                }
            ]
        }
    ]
    with pytest.raises(ValidationError) as exc:
        validate_operation_parameters(layers)
    assert "Buffer operation in layer 'layer1' requires 'distance' parameter" in str(exc.value)
    
    # Test missing bufferDistance with useBufferTrick
    layers = [
        {
            "name": "layer1",
            "operations": [
                {
                    "type": "buffer",
                    "distance": 1.0,
                    "useBufferTrick": True
                }
            ]
        }
    ]
    with pytest.raises(ValidationError) as exc:
        validate_operation_parameters(layers)
    assert "Buffer operation with useBufferTrick in layer 'layer1' requires 'bufferDistance' parameter" in str(exc.value) 