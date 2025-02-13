"""Module for processing text in DXF files."""

from shapely.geometry import Point
from src.core.utils import log_debug, log_warning, log_error
from .utils import (
    SCRIPT_IDENTIFIER,
    ensure_layer_exists,
    add_mtext,
    attach_custom_data
)

# Define default text style properties
DEFAULT_TEXT_STYLE = {
    'height': 2.5,  # Default text height
    'font': 'Arial',  # Default font
    'color': 'white',  # Default color (ACI code 7)
    'attachmentPoint': 'MIDDLE_LEFT',  # Default attachment point
    'paragraph': {
        'align': 'LEFT'  # Default alignment
    }
}

class TextProcessor:
    def __init__(self, script_identifier, project_loader, style_manager, layer_manager):
        self.project_loader = project_loader
        self.style_manager = style_manager
        self.layer_manager = layer_manager
        self.script_identifier = script_identifier
        self.name_to_aci = project_loader.name_to_aci

    def process_text_inserts(self, msp):
        """Process text inserts from project settings."""
        text_inserts = self.project_loader.project_settings.get('textInserts', [])
        if not text_inserts:
            log_debug("No text inserts found in project settings")
            return

        # First, collect all unique target layers
        target_layers = {text_config.get('targetLayer', 'Plantext') for text_config in text_inserts}
        
        # Now process new text inserts
        for text_config in text_inserts:
            try:
                # Get target layer
                layer_name = text_config.get('targetLayer', 'Plantext')  # Default to 'Plantext' layer
                
                # Skip if updateDxf is False
                if not text_config.get('updateDxf', False):
                    log_debug(f"Skipping text insert for layer '{layer_name}' as updateDxf flag is not set")
                    continue
                
                # Ensure layer exists
                ensure_layer_exists(msp.doc, layer_name)
                
                # Get text properties
                text = text_config.get('text', '')
                position = text_config.get('position', {})
                x = position.get('x', 0)
                y = position.get('y', 0)
                
                # Get style configuration
                style_name = text_config.get('style')
                text_style = DEFAULT_TEXT_STYLE.copy()  # Start with defaults
                if style_name:
                    style = self.style_manager.get_style(style_name)
                    if style and 'text' in style:
                        text_style.update(style['text'])  # Override defaults with style settings
                
                # Get the correct space (model or paper)
                space = msp.doc.paperspace() if text_config.get('paperspace', False) else msp.doc.modelspace()
                
                # Create MTEXT entity
                result = add_mtext(
                    space,
                    text,
                    x,
                    y,
                    layer_name,
                    text_style.get('font', 'Standard'),
                    text_style=text_style,
                    name_to_aci=self.name_to_aci,
                    max_width=text_style.get('width')
                )
                
                if result and result[0]:
                    mtext = result[0]
                    attach_custom_data(mtext, self.script_identifier)
                    log_debug(f"Added text insert: '{text}' at ({x}, {y})")
                else:
                    log_warning(f"Failed to create text insert for '{text}'")
                    
            except Exception as e:
                log_error(f"Error processing text insert: {str(e)}")

    def add_label_points_to_dxf(self, msp, geo_data, layer_name, layer_info):
        """Add label points with rotation to DXF."""
        log_debug(f"Adding label points to DXF for layer: {layer_name}")
        
        # Get style information from layer_info
        style = layer_info.get('style', {})
        text_style = DEFAULT_TEXT_STYLE.copy()  # Start with defaults
        
        if isinstance(style, dict) and 'text' in style:
            text_style.update(style['text'])  # Override defaults with style settings
        elif isinstance(style, str):
            # If style is a string, it's a preset name
            preset_style, _ = self.style_manager.get_style(style)
            if preset_style and 'text' in preset_style:
                text_style.update(preset_style['text'])
        
        log_debug(f"Text style config: {text_style}")
        
        # Process each label point
        for _, row in geo_data.iterrows():
            try:
                # Get the point geometry (centroid if not a point)
                point = row.geometry
                if not isinstance(point, Point):
                    point = point.centroid
                
                # Get the label text
                label_text = str(row['label'])
                
                # Get rotation (default to 0 if not present)
                rotation = float(row.get('rotation', 0))
                
                # Create text entity
                add_mtext(
                    msp,
                    label_text,
                    point.x,
                    point.y,
                    layer_name,
                    text_style.get('font', 'Standard'),
                    text_style=text_style,
                    name_to_aci=self.name_to_aci
                )
                
                log_debug(f"Added label '{label_text}' at ({point.x}, {point.y}) with rotation {rotation}")
            except Exception as e:
                log_error(f"Error adding label point: {str(e)}")
