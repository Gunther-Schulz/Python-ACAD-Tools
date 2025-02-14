"""Module for managing layers in DXF files."""

from src.core.utils import log_debug, log_warning
from .utils import ensure_layer_exists, update_layer_properties, sanitize_layer_name
from .utils.style_defaults import DEFAULT_LAYER_STYLE, DEFAULT_ENTITY_STYLE

class LayerManager:
    """Manages DXF layers and their properties."""
    
    def __init__(self, project_loader, style_manager):
        self.project_loader = project_loader
        self.style_manager = style_manager
        self.name_to_aci = project_loader.name_to_aci
        self.layer_properties = {}
        self.doc = None
        self.setup_layers()

    def setup_layers(self):
        """Initialize and setup all layers from project settings."""
        log_debug("Setting up layers...")
        
        # Setup geom layers
        for layer in self.project_loader.project_settings.get('geomLayers', []):
            self._setup_single_layer(layer)
        
        # Setup WMTS/WMS layers
        for layer in self.project_loader.project_settings.get('wmtsLayers', []):
            self._setup_single_layer(layer)
        for layer in self.project_loader.project_settings.get('wmsLayers', []):
            self._setup_single_layer(layer)
            
        log_debug(f"Layer setup complete. Configured layers: {list(self.layer_properties.keys())}")

    def _setup_single_layer(self, layer):
        """Setup a single layer's properties."""
        layer_name = layer['name']
        log_debug(f"Setting up layer: {layer_name}")
        
        # Process style through StyleManager
        style = self.style_manager.process_layer_style(layer_name, layer)
        
        # Store processed style
        self.layer_properties[layer_name] = style
        log_debug(f"Stored properties for layer {layer_name}: {style}")

    def get_layer_properties(self, layer_name):
        """Get layer properties for a given layer name."""
        log_debug(f"Getting properties for layer: {layer_name}")
        
        # Return stored properties or defaults
        return self.layer_properties.get(layer_name, {
            'layer': DEFAULT_LAYER_STYLE.copy(),
            'entity': DEFAULT_ENTITY_STYLE.copy()
        })

    def ensure_layer_exists(self, doc, layer_name, layer_info=None):
        """Ensure a layer exists in the document and has the correct properties."""
        log_debug(f"Ensuring layer exists: {layer_name}")
        
        sanitized_name = sanitize_layer_name(layer_name)
        if sanitized_name not in doc.layers:
            log_debug(f"Creating new layer: {sanitized_name}")
            doc.layers.new(sanitized_name)
        
        layer = doc.layers.get(sanitized_name)
        
        # Get and apply properties
        properties = self.get_layer_properties(layer_name)
        layer_props = properties.get('layer', {})
        self._apply_layer_properties(layer, layer_props)
        
        log_debug(f"Layer {sanitized_name} exists with properties: {layer_props}")
        return layer

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        """Create a new layer in the document."""
        log_debug(f"Creating new layer: {layer_name}")
        return self.ensure_layer_exists(doc, layer_name, layer_info)

    def _apply_layer_properties(self, layer, properties):
        """Apply properties to a layer object."""
        try:
            # First, ensure the layer is not locked or frozen before making changes
            layer.lock = False
            layer.off = False
            
            for key, value in properties.items():
                try:
                    if key == 'locked':
                        layer.lock = value
                    elif key == 'is_on':
                        layer.off = not value
                    elif key == 'frozen':
                        layer.freeze = value
                    else:
                        setattr(layer, key, value)
                    log_debug(f"Set layer property {key}={value}")
                except Exception as e:
                    log_warning(f"Could not set layer property {key}={value}. Error: {str(e)}")
        except Exception as e:
            log_warning(f"Error applying layer properties: {str(e)}")
