"""Module for extracting circles from DXF files."""

from src.core.utils import log_info, log_warning, log_error, log_debug

def extract_circle_centers(entities, layer_name):
    """
    Extracts circle centers from entities.
    
    Args:
        entities: List of entities or exploded block entities
        layer_name: Name of the layer to process
        
    Returns:
        list: List of dictionaries containing:
            - coords: (x, y) tuple representing circle center
            - attributes: dict of additional attributes (radius, etc.)
    """
    circle_features = []
    
    for entity_data in entities:
        # Handle both raw entities and exploded block entities
        if isinstance(entity_data, dict):
            entity = entity_data['entity']
            if entity.dxftype() == 'CIRCLE':
                center = entity.dxf.center
                # Apply transformation from block explosion
                insertion = entity_data['insertion']
                scale_x, scale_y = entity_data['scale']
                transformed_x = (center[0] * scale_x) + insertion[0]
                transformed_y = (center[1] * scale_y) + insertion[1]
                # Scale the radius
                radius = entity.dxf.radius * ((scale_x + scale_y) / 2)  # Average scale for radius
                
                circle_features.append({
                    'coords': (transformed_x, transformed_y),
                    'attributes': {
                        'radius': radius
                    }
                })
        else:
            # Handle direct circle entities
            if entity_data.dxftype() == 'CIRCLE':
                center = entity_data.dxf.center
                circle_features.append({
                    'coords': (center[0], center[1]),
                    'attributes': {
                        'radius': entity_data.dxf.radius
                    }
                })
    
    log_debug(f"Extracted {len(circle_features)} circle centers with attributes from layer {layer_name}")
    return circle_features 