from src.utils import log_info, log_warning, log_error, log_debug

def explode_blocks(entities, layer_name, target_layer=None):
    """
    Explodes blocks (INSERT entities) into their constituent entities.
    Uses ezdxf's built-in virtual_entities() method which automatically:
    - Applies all transformations (scale, rotate, translate)
    - Handles nested blocks recursively
    - Returns entities in world coordinates (like AutoCAD EXPLODE)
    
    Args:
        entities: List of DXF entities (from modelspace query)
        layer_name: Name of the layer to process (filters INSERT entities on this layer)
        target_layer: Optional layer name to filter exploded entities. If specified, only
                     entities on this layer will be included in the results. Useful for
                     blocks that contain entities on multiple layers.
        
    Returns:
        list: List of exploded entities in world coordinates, ready for geometry conversion
    """
    exploded_entities = []
    insert_count = 0
    skipped_count = 0
    
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
                # Filter by target layer if specified
                if target_layer:
                    try:
                        if hasattr(virtual_entity.dxf, 'layer') and virtual_entity.dxf.layer != target_layer:
                            skipped_count += 1
                            continue
                    except:
                        # Some entities might not have a layer attribute
                        skipped_count += 1
                        continue
                
                exploded_entities.append(virtual_entity)
                    
        except Exception as e:
            log_warning(f"Error exploding block '{entity.dxf.name}' at {entity.dxf.insert}: {str(e)}")
            continue
    
    if target_layer:
        log_debug(f"Exploded {insert_count} INSERT entities into {len(exploded_entities)} entities from layer '{layer_name}' "
                 f"(filtered to target layer '{target_layer}', skipped {skipped_count} entities on other layers)")
    else:
        log_debug(f"Exploded {insert_count} INSERT entities into {len(exploded_entities)} entities from layer '{layer_name}'")
    
    return exploded_entities