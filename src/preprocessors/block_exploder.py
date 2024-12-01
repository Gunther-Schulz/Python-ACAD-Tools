from src.utils import log_info, log_warning, log_error

def explode_blocks(entities, layer_name):
    """
    Explodes blocks in the specified layer into their constituent entities.
    
    Args:
        entities: List of DXF entities
        layer_name: Name of the layer to process
        
    Returns:
        list: List of exploded entities
    """
    exploded_entities = []
    
    for entity in entities:
        if entity.dxftype() != 'INSERT' or entity.dxf.layer != layer_name:
            continue
            
        try:
            # Get the block reference
            block = entity.block()
            
            # Get transformation parameters
            insertion_point = entity.dxf.insert
            x_scale = entity.dxf.xscale
            y_scale = entity.dxf.yscale
            rotation = entity.dxf.rotation
            
            # Add all entities from the block with their transformations
            for block_entity in block:
                # Store original entity with transformation info
                exploded_entities.append({
                    'entity': block_entity,
                    'insertion': insertion_point,
                    'scale': (x_scale, y_scale),
                    'rotation': rotation
                })
                    
        except Exception as e:
            log_warning(f"Error exploding block: {str(e)}")
            continue
    
    log_info(f"Exploded {len(exploded_entities)} blocks in layer {layer_name}")
    return exploded_entities