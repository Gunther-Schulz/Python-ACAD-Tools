"""Module for managing layers in DXF files."""

import ezdxf
from src.core.utils import log_debug, log_warning
from src.dxf_utils import ensure_layer_exists, update_layer_properties, sanitize_layer_name
from src.dxf_utils.style_defaults import DEFAULT_LAYER_STYLE, DEFAULT_ENTITY_STYLE

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
        # Setup geom layers
        for layer in self.project_loader.project_settings['geomLayers']:
            # Setup main layer
            self._setup_single_layer(layer)
            self.all_layers[layer['name']] = layer
            
            # Setup hatch layers - treat them exactly like normal layers
            if 'hatches' in layer:
                for hatch in layer['hatches']:
                    self._setup_single_layer(hatch)
                    self.all_layers[hatch['name']] = hatch
        
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
                self.layer_properties[layer_name] = {
                    'layer': style['layer'],
                    'entity': style.get('entity', {})
                }

                # Store the full layer info for later use
                self.all_layers[layer_name] = layer
        else:
            self.layer_properties[layer_name] = {
                'layer': self.default_layer_style.copy(),
                'entity': {'close': False}
            }

    def initialize_layer_properties(self):
        """Initialize properties for all layers"""
        for layer in self.project_loader.project_settings['geomLayers']:
            # Process main layer
            layer_name = layer['name']
            if layer_name not in self.layer_properties:
                if (layer.get('style') or 
                    any(key in layer for key in [
                        'color', 'linetype', 'lineweight', 'plot', 'locked', 
                        'frozen', 'is_on', 'transparency', 'close', 'linetypeScale', 
                        'linetypeGeneration'
                    ])):
                    self.add_layer_properties(layer_name, layer)
            
            # Process any hatch layers
            if 'hatches' in layer:
                for hatch in layer['hatches']:
                    hatch_name = hatch['name']
                    if hatch_name not in self.layer_properties:
                        if hatch.get('style'):
                            self.add_layer_properties(hatch_name, hatch)

    def add_layer_properties(self, layer_name, layer, processed_style=None):
        """Add properties for a layer"""
        if processed_style:
            layer_properties, entity_properties = processed_style
        else:
            # If layer has a style, get it from style manager
            if 'style' in layer:
                style, warning = self.style_manager.get_style(layer['style'])
                if style and 'layer' in style:
                    layer_properties = style['layer']
                    entity_properties = style.get('entity', {})
                else:
                    layer_properties = self.default_layer_style.copy()
                    entity_properties = self.default_entity_style.copy()
            else:
                # Get properties from StyleManager for direct properties
                layer_properties, entity_properties = self.style_manager.process_layer_style(layer_name, layer)
        
        # Store the properties
        self.layer_properties[layer_name] = {
            'layer': layer_properties,
            'entity': entity_properties
        }
        
        # Store color for quick access
        if 'color' in layer_properties:
            self.colors[layer_name] = layer_properties['color']
            
        log_debug(f"Added properties for layer {layer_name}: {layer_properties}")

    def ensure_layer_exists(self, doc, layer_name, layer_info=None):
        """Ensure a layer exists in the document"""
        # Get the full layer info from stored layers if not provided
        if layer_info is None:
            layer_info = self.all_layers.get(layer_name, {})
            
        if layer_name not in doc.layers:
            self.create_new_layer(doc, None, layer_name, layer_info, add_geometry=False)
        else:
            if layer_info:
                # Get style from layer info
                style_name = layer_info.get('style')
                if style_name:
                    style, warning = self.style_manager.get_style(style_name)
                    if style and 'layer' in style:
                        layer = doc.layers.get(layer_name)
                        update_layer_properties(layer, style['layer'], self.name_to_aci)

    def create_new_layer(self, doc, msp, layer_name, layer_info, add_geometry=True):
        """Create a new layer in the document"""
        sanitized_layer_name = sanitize_layer_name(layer_name)
        
        # Create the layer
        ensure_layer_exists(doc, sanitized_layer_name)
        layer = doc.layers.get(sanitized_layer_name)
        
        # Get style from layer info
        if layer_info and 'style' in layer_info:
            style_name = layer_info['style']
            style, warning = self.style_manager.get_style(style_name)
            if style and 'layer' in style:
                update_layer_properties(layer, style['layer'], self.name_to_aci)
                log_debug(f"Applied style {style_name} to layer {layer_name}")
        
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
