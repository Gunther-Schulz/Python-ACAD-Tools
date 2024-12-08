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
                attributes['label'] = entity.dxf.text
            elif entity.dxftype() == 'LWPOLYLINE':
                # Use first vertex as basepoint for LWPOLYLINE
                if len(entity.vertices()) > 0:
                    basepoint = entity.vertices()[0]
            elif entity.dxftype() == 'MTEXT':
                basepoint = entity.dxf.insert
                attributes['label'] = entity.text
            elif entity.dxftype() == 'POINT':
                basepoint = entity.dxf.location
            elif entity.dxftype() == 'ELLIPSE':
                basepoint = entity.dxf.center
            elif entity.dxftype() == 'SPLINE':
                # Use first control point as basepoint
                if len(entity.control_points) > 0:
                    basepoint = entity.control_points[0]
            elif entity.dxftype() == 'HATCH':
                # Use the center of the bounding box as basepoint
                bbox = entity.bbox()
                if bbox:
                    basepoint = ((bbox[0] + bbox[2])/2, (bbox[1] + bbox[3])/2)
            elif entity.dxftype() == '3DFACE':
                # Use first vertex as basepoint
                basepoint = entity.dxf.vtx0
            elif entity.dxftype() == 'DIMENSION':
                basepoint = entity.dxf.defpoint
            elif entity.dxftype() == 'LEADER':
                # Use first vertex as basepoint
                if entity.vertices:
                    basepoint = entity.vertices[0]
            
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