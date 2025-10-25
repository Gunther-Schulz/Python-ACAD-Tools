from src.utils import log_info, log_warning, log_error, log_debug

def explode_blocks(entities, layer_name):
    """
    Explodes blocks (INSERT entities) into their constituent entities.
    Uses ezdxf's built-in virtual_entities() method which automatically:
    - Applies all transformations (scale, rotate, translate)
    - Handles nested blocks recursively
    - Returns entities in world coordinates (like AutoCAD EXPLODE)
    
    Args:
        entities: List of DXF entities (from modelspace query)
        layer_name: Name of the layer to process (filters INSERT entities on this layer)
        
    Returns:
        list: List of exploded entities in world coordinates, ready for geometry conversion
    """
    exploded_entities = []
    insert_count = 0
    
    for entity in entities:
        # Only process INSERT entities on the specified layer
        if entity.dxftype() != 'INSERT':
            continue
            
        if entity.dxf.layer != layer_name:
            continue
            
        insert_count += 1
        
        try:
            # Use ezdxf's built-in virtual_entities() method
            # This returns transformed entities in WCS (world coordinate system)
            # Handles all transformations: insert point, rotation, scale, extrusion
            # Recursively handles nested blocks
            for virtual_entity in entity.virtual_entities():
                exploded_entities.append(virtual_entity)
                    
        except Exception as e:
            log_warning(f"Error exploding block '{entity.dxf.name}' at {entity.dxf.insert}: {str(e)}")
            continue
    
    log_debug(f"Exploded {insert_count} INSERT entities into {len(exploded_entities)} entities from layer '{layer_name}'")
    return exploded_entities