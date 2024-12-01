import geopandas as gpd
from shapely.geometry import box, MultiPolygon, Polygon
from src.utils import log_info, log_warning
from src.operations.common_operations import _process_layer_info, format_operation_warning

def create_envelope_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Creates a minimum-area bounding rectangle (envelope) for each input geometry.
    The envelope may be rotated to achieve minimum area.
    For MultiPolygons, creates a separate envelope for each constituent polygon.
    """
    log_info(f"Creating envelope layer: {layer_name}")
    
    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]
    
    padding = operation.get('padding', 0)
    result_geometries = []
    
    def process_single_geometry(geom):
        if geom is None:
            return None
            
        # Handle MultiPolygon by processing each polygon separately
        if isinstance(geom, MultiPolygon):
            return [create_envelope(poly, padding) for poly in geom.geoms]
        else:
            return [create_envelope(geom, padding)]
    
    def create_envelope(geom, padding):
        # Get the minimum rotated rectangle
        min_rect = geom.minimum_rotated_rectangle
        
        # Apply padding if needed
        if padding:
            # Create a buffer around the rotated rectangle
            # The buffer is applied perpendicular to each edge
            min_rect = min_rect.buffer(padding, join_style=2)  # join_style=2 for mitered joins
            # Get the minimum rotated rectangle of the buffered geometry
            min_rect = min_rect.minimum_rotated_rectangle
        
        return min_rect
    
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]
        
        if source_gdf.empty:
            continue
            
        # Process each geometry and handle MultiPolygons
        for geom in source_gdf.geometry:
            envelopes = process_single_geometry(geom)
            if envelopes:
                result_geometries.extend(envelopes)
    
    if not result_geometries:
        log_warning(format_operation_warning(
            layer_name,
            "envelope",
            "No geometries found to create envelopes"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None
    
    # Create GeoDataFrame with the results
    result_gdf = gpd.GeoDataFrame(geometry=result_geometries, crs=crs)
    all_layers[layer_name] = result_gdf
    
    log_info(f"Created envelope layer: {layer_name} with {len(result_geometries)} envelopes")
    return result_gdf 