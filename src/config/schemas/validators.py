"""Custom validation functions for configuration schemas."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

class ValidationError(Exception):
    """Custom validation error with detailed message."""
    def __init__(self, message: str, path: List[str]):
        self.message = message
        self.path = path
        super().__init__(f"{message} (at {' -> '.join(path)})")

def validate_file_path(
    value: str,
    base_dir: str,
    must_exist: bool = True,
    allowed_extensions: Optional[Set[str]] = None,
    path_type: str = "file"
) -> None:
    """Validate a file path in configuration.
    
    Args:
        value: The path to validate
        base_dir: Base directory for relative paths
        must_exist: Whether the path must exist
        allowed_extensions: Set of allowed file extensions
        path_type: Type of path ("file" or "directory")
    """
    path = Path(os.path.join(base_dir, value))
    
    # Check if path exists if required
    if must_exist and not path.exists():
        raise ValidationError(
            f"{path_type.capitalize()} does not exist: {value}",
            ["path"]
        )
    
    # Check if it's the correct type
    if must_exist and path.exists():
        if path_type == "file" and not path.is_file():
            raise ValidationError(
                f"Path is not a file: {value}",
                ["path"]
            )
        elif path_type == "directory" and not path.is_dir():
            raise ValidationError(
                f"Path is not a directory: {value}",
                ["path"]
            )
    
    # Check extension if specified
    if allowed_extensions:
        if path.suffix.lower() not in allowed_extensions:
            raise ValidationError(
                f"Invalid file extension for {value}. Allowed: {', '.join(allowed_extensions)}",
                ["path"]
            )

def validate_style_references(
    geometry_layers: List[Dict[str, Any]],
    available_styles: Set[str]
) -> None:
    """Validate that all style references in geometry layers exist.
    
    Args:
        geometry_layers: List of geometry layer configurations
        available_styles: Set of available style names
    """
    for layer in geometry_layers:
        layer_name = layer.get('name', 'unknown')
        style = layer.get('style')
        
        if isinstance(style, str):
            if style not in available_styles:
                raise ValidationError(
                    f"Style '{style}' referenced by layer '{layer_name}' does not exist",
                    ["geomLayers", layer_name, "style"]
                )
        elif isinstance(style, dict):
            # Inline style definition, no validation needed
            pass

def validate_viewport_references(
    geometry_layers: List[Dict[str, Any]],
    available_viewports: Set[str]
) -> None:
    """Validate that all viewport references in geometry layers exist.
    
    Args:
        geometry_layers: List of geometry layer configurations
        available_viewports: Set of available viewport names
    """
    for layer in geometry_layers:
        layer_name = layer.get('name', 'unknown')
        viewports = layer.get('viewports', [])
        
        for viewport in viewports:
            viewport_name = viewport.get('name')
            if viewport_name not in available_viewports:
                raise ValidationError(
                    f"Viewport '{viewport_name}' referenced by layer '{layer_name}' does not exist",
                    ["geomLayers", layer_name, "viewports"]
                )

def validate_layer_dependencies(geometry_layers: List[Dict[str, Any]]) -> None:
    """Validate layer dependencies in operations.
    
    Args:
        geometry_layers: List of geometry layer configurations
    """
    layer_names = {layer['name'] for layer in geometry_layers}
    
    for layer in geometry_layers:
        layer_name = layer.get('name', 'unknown')
        operations = layer.get('operations', [])
        
        for op in operations:
            layers = op.get('layers', [])
            if isinstance(layers, list):
                for dep_layer in layers:
                    if isinstance(dep_layer, str) and dep_layer not in layer_names:
                        raise ValidationError(
                            f"Layer '{dep_layer}' referenced in operation of layer '{layer_name}' does not exist",
                            ["geomLayers", layer_name, "operations"]
                        )
            elif isinstance(layers, str) and layers not in layer_names:
                raise ValidationError(
                    f"Layer '{layers}' referenced in operation of layer '{layer_name}' does not exist",
                    ["geomLayers", layer_name, "operations"]
                )

def validate_operation_parameters(geometry_layers: List[Dict[str, Any]]) -> None:
    """Validate operation parameters.
    
    Args:
        geometry_layers: List of geometry layer configurations
    """
    for layer in geometry_layers:
        layer_name = layer.get('name', 'unknown')
        operations = layer.get('operations', [])
        
        for op in operations:
            op_type = op.get('type')
            
            # Validate buffer operation parameters
            if op_type == 'buffer':
                if 'distance' not in op:
                    raise ValidationError(
                        f"Buffer operation in layer '{layer_name}' requires 'distance' parameter",
                        ["geomLayers", layer_name, "operations"]
                    )
                if op.get('useBufferTrick', False) and 'bufferDistance' not in op:
                    raise ValidationError(
                        f"Buffer operation with useBufferTrick in layer '{layer_name}' requires 'bufferDistance' parameter",
                        ["geomLayers", layer_name, "operations"]
                    )
            
            # Add more operation-specific validations here 