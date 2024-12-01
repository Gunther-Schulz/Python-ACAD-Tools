from src.utils import log_info, log_warning, log_error

def extract_circle_centers_from_blocks(entities, layer_name):
    """
    Explodes blocks in the specified layer and extracts circle centers.
    
    Args:
        entities: List of DXF entities
        layer_name: Name of the layer to process
        
    Returns:
        list: List of (x, y) tuples representing circle centers
    """
    circle_centers = []
    
    for entity in entities:
        if entity.dxftype() != 'INSERT' or entity.dxf.layer != layer_name:
            continue
            
        try:
            # Get the block reference
            block = entity.block()
            
            # Transform coordinates based on insertion point and scaling
            insertion_point = entity.dxf.insert
            x_scale = entity.dxf.xscale
            y_scale = entity.dxf.yscale
            rotation = entity.dxf.rotation
            
            # Process each entity in the block
            for block_entity in block:
                if block_entity.dxftype() == 'CIRCLE':
                    # Get circle center and transform it
                    center = block_entity.dxf.center
                    
                    # Apply transformation
                    transformed_x = (center[0] * x_scale) + insertion_point[0]
                    transformed_y = (center[1] * y_scale) + insertion_point[1]
                    
                    circle_centers.append((transformed_x, transformed_y))
                    
        except Exception as e:
            log_warning(f"Error processing block: {str(e)}")
            continue
    
    log_warning(f"Extracted {len(circle_centers)} circle centers from blocks in layer {layer_name}")
    return circle_centers