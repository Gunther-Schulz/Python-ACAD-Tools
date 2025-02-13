"""Module for managing layers in DXF files."""

import ezdxf
from src.core.utils import log_debug, log_warning
from .utils import ensure_layer_exists, update_layer_properties, sanitize_layer_name
from .utils.style_defaults import DEFAULT_LAYER_STYLE

class LayerManager:
    def __init__(self, project_loader, style_manager):
        self.project_loader = project_loader
        self.style_manager = style_manager
        self.layer_properties = {}
        self.colors = {}
        self.name_to_aci = project_loader.name_to_aci
        self.all_layers = {}
        self.doc = None
        self.default_layer_style = DEFAULT_LAYER_STYLE.copy()
        self.setup_layers()

    def setup_layers(self):
        """Initialize and setup all layers from project settings"""
        # Initialize default properties for ALL layers first
        self.initialize_layer_properties()
        
        # Setup geom layers
        for layer in self.project_loader.project_settings['geomLayers']:
            self._setup_single_layer(layer)
            
            # Also setup properties for any layers created through operations
            if 'operations' in layer:
                result_layer_name = layer['name']
                if result_layer_name not in self.layer_properties:
                    # Initialize with default properties if not already set
                    self.add_layer_properties(result_layer_name, {
                        'color': "White",  # Default color
                        'locked': False,
                        'close': True
                    })
        
        # Setup WMTS/WMS layers
        for layer in self.project_loader.project_settings.get('wmtsLayers', []):
            self._setup_single_layer(layer)
        for layer in self.project_loader.project_settings.get('wmsLayers', []):
            self._setup_single_layer(layer)

    def _setup_single_layer(self, layer):
        """Setup a single layer's properties"""
        layer_name = layer['name']
        
        # Ensure layer has properties, even if just defaults
        if layer_name not in self.layer_properties:
            self.layer_properties[layer_name] = {
                'layer': self.default_layer_style.copy(),
                'entity': {
                    'close': False
                }
            }
            self.colors[layer_name] = self.default_layer_style['color']
        
        # Process layer style if it exists
        if 'style' in layer:
            layer_style = self.style_manager.process_layer_style(layer_name, layer)
            self.add_layer_properties(layer_name, layer, layer_style)

    def initialize_layer_properties(self):
        """Initialize properties for all layers"""
        for layer in self.project_loader.project_settings['geomLayers']:
            layer_name = layer['name']
            
            if layer_name in self.layer_properties:
                continue
            
            if (layer.get('style') or 
                any(key in layer for key in [
                    'color', 'linetype', 'lineweight', 'plot', 'locked', 
                    'frozen', 'is_on', 'transparency', 'close', 'linetypeScale', 
                    'linetypeGeneration'
                ])):
                self.add_layer_properties(layer_name, layer)

    def add_layer_properties(self, layer_name, layer, processed_style=None):
        """Add properties for a layer"""
        # Always get properties from StyleManager
        properties = processed_style or self.style_manager.process_layer_style(layer_name, layer)
        
        # Store the properties
        self.layer_properties[layer_name] = {
            'layer': properties,
            'entity': {}  # Entity properties if needed
        }
        
        # Store color for quick access
        if 'color' in properties:
            self.colors[layer_name] = properties['color']

    def ensure_layer_exists(self, doc, layer_name, layer_info=None):
        """Ensure a layer exists in the document"""
        if layer_name not in doc.layers:
            self.create_new_layer(doc, None, layer_name, layer_info, add_geometry=False)
        else:
            if layer_info:
                self.apply_layer_properties(doc.layers.get(layer_name), layer_info)

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        """Create a new layer in the document"""
        log_debug(f"Creating new layer: {layer_name}")
        sanitized_layer_name = sanitize_layer_name(layer_name)  
        properties = self.layer_properties.get(layer_name, {})
        
        ensure_layer_exists(doc, sanitized_layer_name)
        
        # Apply properties after layer creation
        if properties:
            layer = doc.layers.get(sanitized_layer_name)
            update_layer_properties(layer, properties, self.name_to_aci)
        
        log_debug(f"Created new layer: {sanitized_layer_name}")
        log_debug(f"Layer properties: {properties}")
        
        return doc.layers.get(sanitized_layer_name)

    def apply_layer_properties(self, layer, layer_properties):
        """Apply properties to an existing layer"""
        update_layer_properties(layer, layer_properties, self.name_to_aci)
        log_debug(f"Updated layer properties: {layer_properties}")

    def get_layer_properties(self, layer_name):
        """Get properties for a specific layer"""
        return self.layer_properties.get(layer_name, {})

    def create_layer(self, layer_name: str, layer_style: dict = None) -> None:
        """Create a new layer in the DXF document."""
        if layer_name in self.layer_properties:
            return

        # Use default style if none provided
        if layer_style is None:
            layer_style = self.default_layer_style

        # Create the layer
        self.layer_properties[layer_name] = {
            'layer': layer_style,
            'entity': {}
        }
        
        # Apply style properties
        layer = self.doc.layers.new(name=layer_name)
        layer.color = layer_style.get('color', self.default_layer_style['color'])
        layer.linetype = layer_style.get('linetype', self.default_layer_style['linetype'])
        layer.lineweight = layer_style.get('lineweight', self.default_layer_style['lineweight'])
        layer.plot = layer_style.get('plot', self.default_layer_style['plot'])
        layer.locked = layer_style.get('locked', self.default_layer_style['locked'])
        layer.frozen = layer_style.get('frozen', self.default_layer_style['frozen'])
        layer.is_on = layer_style.get('is_on', self.default_layer_style['is_on'])
