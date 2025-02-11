from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import ezdxf
from ..utils.logging import log_debug, log_info, log_warning, log_error
from .config import ConfigManager

class BaseProcessor:
    """Base class for all processors providing common functionality."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize the base processor.
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config = config_manager
        self.doc: Optional[ezdxf.document.Drawing] = None
        self._initialize()

    def _initialize(self) -> None:
        """Initialize processor-specific resources.
        
        This method should be overridden by subclasses to perform
        any necessary initialization.
        """
        pass

    def set_dxf_document(self, doc: ezdxf.document.Drawing) -> None:
        """Set the DXF document to work with.
        
        Args:
            doc: ezdxf Drawing object
        """
        self.doc = doc
        log_debug(f"DXF document set: {len(self.doc.entitydb)} entities")

    def get_style(self, style_name: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Get style settings from name or direct style dict.
        
        Args:
            style_name: Style name or style dictionary
            
        Returns:
            Style settings dictionary
        """
        return self.config.get_style(style_name)

    def get_color_code(self, color_spec: Union[str, int]) -> int:
        """Get AutoCAD color code from name or code.
        
        Args:
            color_spec: Color name or ACI code
            
        Returns:
            ACI color code
        """
        if isinstance(color_spec, int):
            return color_spec
        return self.config.get_color_code(color_spec) or 7  # Default to white (7)

    def resolve_path(self, path: str) -> str:
        """Resolve a path using the project's folder prefix.
        
        Args:
            path: Path to resolve
            
        Returns:
            Resolved absolute path
        """
        return self.config.resolve_path(path)

    def apply_layer_properties(self, layer_name: str, properties: Dict[str, Any]) -> None:
        """Apply properties to a DXF layer.
        
        Args:
            layer_name: Name of the layer to modify
            properties: Layer properties to apply
        """
        if not self.doc:
            log_warning("No DXF document set, cannot apply layer properties")
            return

        layer = self.doc.layers.get(layer_name)
        if not layer:
            log_warning(f"Layer not found: {layer_name}")
            return

        # Apply basic properties
        if 'color' in properties:
            layer.color = self.get_color_code(properties['color'])
        if 'linetype' in properties:
            layer.linetype = properties['linetype']
        if 'lineweight' in properties:
            layer.lineweight = properties['lineweight']

        # Apply status properties
        layer.plot = properties.get('plot', True)
        layer.locked = properties.get('locked', False)
        layer.frozen = properties.get('frozen', False)
        layer.off = not properties.get('is_on', True)

        # Apply transparency if specified (0-1 float)
        if 'transparency' in properties:
            try:
                transparency = float(properties['transparency'])
                if 0 <= transparency <= 1:
                    layer.transparency = int(transparency * 100)
            except (ValueError, TypeError):
                log_warning(f"Invalid transparency value for layer {layer_name}: {properties['transparency']}")

        log_debug(f"Applied properties to layer {layer_name}: {properties}")

    def create_layer(self, name: str, properties: Dict[str, Any]) -> None:
        """Create a new layer with the specified properties.
        
        Args:
            name: Name of the layer to create
            properties: Layer properties to apply
        """
        if not self.doc:
            log_warning("No DXF document set, cannot create layer")
            return

        if name in self.doc.layers:
            log_debug(f"Layer {name} already exists, updating properties")
        else:
            self.doc.layers.new(name)
            log_debug(f"Created new layer: {name}")

        self.apply_layer_properties(name, properties)

    def validate_document(self) -> bool:
        """Validate that a DXF document is set and usable.
        
        Returns:
            True if document is valid, False otherwise
        """
        if not self.doc:
            log_error("No DXF document set")
            return False
        return True

    def cleanup(self) -> None:
        """Clean up resources used by the processor.
        
        This method should be overridden by subclasses to perform
        any necessary cleanup.
        """
        # Base implementation does nothing
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup() 