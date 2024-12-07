from src.utils import log_debug

def extract_block_basepoints(entities, layer_name):
    """
    Extracts basepoints (insertion points) from block references.
    
    Args:
        entities: List of DXF entities
        layer_name: Name of the layer to process
        
    Returns:
        list: List of dictionaries containing:
            - coords: (x, y) tuple representing block insertion point
            - attributes: dict of additional attributes (block name, scale, rotation)
    """
    basepoint_features = []
    
    for entity in entities:
        if entity.dxftype() != 'INSERT':
            continue
            
        try:
            # Get insertion point and other block attributes
            insertion_point = entity.dxf.insert
            
            basepoint_features.append({
                'coords': (insertion_point[0], insertion_point[1]),
                'attributes': {
                    'block_name': entity.dxf.name,
                    'x_scale': getattr(entity.dxf, 'xscale', 1.0),
                    'y_scale': getattr(entity.dxf, 'yscale', 1.0),
                    'rotation': getattr(entity.dxf, 'rotation', 0.0)
                }
            })
                
        except Exception as e:
            log_debug(f"Error processing block basepoint: {str(e)}")
            continue
    
    log_debug(f"Extracted {len(basepoint_features)} block basepoints from layer {layer_name}")
    return basepoint_features 