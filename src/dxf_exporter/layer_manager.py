"""Module for managing layers in DXF files."""

import ezdxf
from src.core.utils import log_debug, log_warning
from .utils import ensure_layer_exists, update_layer_properties, sanitize_layer_name
from .utils.style_defaults import DEFAULT_LAYER_STYLE, DEFAULT_ENTITY_STYLE

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
        self.default_entity_style = DEFAULT_ENTITY_STYLE.copy()
        self.setup_layers()

    def setup_layers(self):
        """Initialize and setup all layers from project settings"""
        # Initialize default properties for ALL layers first
        self.initialize_layer_properties()
        
        # Setup geom layers
        for layer in self.project_loader.project_settings['geomLayers']:
            self._setup_single_layer(layer)
            
            # Store the full layer info for later use when creating layers
            self.all_layers[layer['name']] = layer
            
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
        
        # If layer has a style, get and store it
        if 'style' in layer:
            style_name = layer['style']
            
            # Get the style from style manager
            style, warning = self.style_manager.get_style(style_name)
            
            if style and 'layer' in style:
                # Store the layer properties
                self.layer_properties[layer_name] = {
                    'layer': style['layer'],
                    'entity': style.get('entity', {})
                }

                # Handle hatches if they exist
                if 'hatches' in layer:
                    for hatch in layer['hatches']:
                        hatch_layer_name = hatch['name']
                        
                        # Use hatch's style if specified, otherwise use parent layer's style
                        hatch_style_name = hatch.get('style', style_name)
                        
                        hatch_style, _ = self.style_manager.get_style(hatch_style_name)
                        
                        if hatch_style:
                            # For hatches, use either the 'hatch' section or the 'layer' section
                            hatch_props = hatch_style.get('hatch', hatch_style.get('layer', {}))
                            
                            self.layer_properties[hatch_layer_name] = {
                                'layer': hatch_props,
                                'entity': hatch_style.get('entity', {})
                            }
        else:
            self.layer_properties[layer_name] = {
                'layer': self.default_layer_style.copy(),
                'entity': {'close': False}
            }

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
        if processed_style:
            layer_properties, entity_properties = processed_style
        else:
            # Get properties from StyleManager
            layer_properties, entity_properties = self.style_manager.process_layer_style(layer_name, layer)
        
        # Store the properties
        self.layer_properties[layer_name] = {
            'layer': layer_properties,
            'entity': entity_properties
        }
        
        # Store color for quick access
        if 'color' in layer_properties:
            self.colors[layer_name] = layer_properties['color']

    def ensure_layer_exists(self, doc, layer_name, layer_info=None):
        """Ensure a layer exists in the document"""
        # Get the full layer info from stored layers if not provided
        if layer_info is None:
            layer_info = self.all_layers.get(layer_name, {})
            
        if layer_name not in doc.layers:
            self.create_new_layer(doc, None, layer_name, layer_info, add_geometry=False)
        else:
            if layer_info:
                self.apply_layer_properties(doc.layers.get(layer_name), layer_info)

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        """Create a new layer in the document"""
        sanitized_layer_name = sanitize_layer_name(layer_name)
        
        # Get stored properties for this layer
        properties = self.layer_properties.get(layer_name, {})
        
        # Create the layer
        ensure_layer_exists(doc, sanitized_layer_name)
        layer = doc.layers.get(sanitized_layer_name)
        
        # Apply the properties
        if properties and 'layer' in properties:
            layer_props = properties['layer']
            update_layer_properties(layer, layer_props, self.name_to_aci)

        # Create hatch layers if this is a main layer
        if layer_info and 'hatches' in layer_info:
            for hatch in layer_info['hatches']:
                hatch_layer_name = hatch['name']
                # Create the hatch layer with its own layer info
                self.create_new_layer(doc, msp, hatch_layer_name, hatch, add_geometry=False)
        
        return layer

    def apply_layer_properties(self, layer, layer_info):
        """Apply properties to an existing layer"""
        
        # Get stored properties for this layer
        properties = self.layer_properties.get(layer.dxf.name, {})
        
        # Apply the properties
        if properties and 'layer' in properties:
            layer_props = properties['layer']
            update_layer_properties(layer, layer_props, self.name_to_aci)

    def get_layer_properties(self, layer_name):
        """Get layer properties for a given layer name."""
        log_debug(f"Getting properties for layer: {layer_name}")
        
        # First check if we have stored properties for this layer
        if layer_name not in self.layer_properties:
            log_debug(f"No stored properties found for layer {layer_name}, using defaults")
            return {
                'layer': self.default_layer_style.copy(),
                'entity': self.default_entity_style.copy()
            }
        
        stored_props = self.layer_properties[layer_name]
        log_debug(f"Raw stored properties: {stored_props}")
        
        # If stored_props['layer'] is a tuple (from style_manager.process_layer_style),
        # we need to merge layer and entity properties
        if isinstance(stored_props.get('layer'), tuple):
            layer_props, entity_props = stored_props['layer']
            result = {
                'layer': layer_props,
                'entity': entity_props
            }
        else:
            result = stored_props
            
        log_debug(f"Processed layer properties: {result}")
        return result

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
