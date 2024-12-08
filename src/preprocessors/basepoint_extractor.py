from src.utils import log_debug

def extract_entity_basepoints(entities, layer_name):
    """
    Extracts basepoints from any DXF entity.
    
    Args:
        entities: List of DXF entities
        layer_name: Name of the layer to process
        
    Returns:
        list: List of dictionaries containing:
            - coords: (x, y) tuple representing entity basepoint
            - attributes: dict of additional attributes (entity type, scale, rotation, etc.)
    """
    basepoint_features = []
    
    for entity in entities:
        try:
            # Get basepoint based on entity type
            basepoint = None
            attributes = {'entity_type': entity.dxftype()}
            
            if entity.dxftype() == 'INSERT':
                basepoint = entity.dxf.insert
                attributes.update({
                    'block_name': entity.dxf.name,
                    'x_scale': getattr(entity.dxf, 'xscale', 1.0),
                    'y_scale': getattr(entity.dxf, 'yscale', 1.0),
                    'rotation': getattr(entity.dxf, 'rotation', 0.0)
                })
            elif entity.dxftype() == 'LINE':
                basepoint = entity.dxf.start
            elif entity.dxftype() == 'CIRCLE':
                basepoint = entity.dxf.center
            elif entity.dxftype() == 'ARC':
                basepoint = entity.dxf.center
            elif entity.dxftype() == 'TEXT':
                basepoint = entity.dxf.insert
            elif entity.dxftype() == 'POINT':
                basepoint = entity.dxf.location
            
            if basepoint is not None:
                basepoint_features.append({
                    'coords': (basepoint[0], basepoint[1]),
                    'attributes': attributes
                })
                
        except Exception as e:
            log_debug(f"Error processing entity basepoint: {str(e)}")
            continue
    
    log_debug(f"Extracted {len(basepoint_features)} basepoints from layer {layer_name}")
    return basepoint_features 