import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from src.utils import log_info, log_warning, log_debug
from src.operations.common_operations import format_operation_warning

def create_remove_interior_rings_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Remove interior rings (holes) from polygons, keeping only the exterior ring.
    
    This operation extracts only the outer boundary of polygons, filling in any holes.
    Useful for creating continuous planning boundaries that shouldn't have interior exclusions.
    
    Parameters:
    -----------
    all_layers : dict
        Dictionary of all available layers
    project_settings : dict
        Project configuration settings
    crs : str
        Coordinate reference system
    layer_name : str
        Name of the layer to create
    operation : dict
        Operation configuration (no additional options required)
        
    Returns:
    --------
    GeoDataFrame or None
        Geometries with interior rings removed, or None if operation fails
    """
    log_debug(f"Creating remove interior rings layer: {layer_name}")
    
    # Get source layer (defaults to current layer)
    source_layers = operation.get('layers', [layer_name])
    
    if not source_layers:
        log_warning(format_operation_warning(
            layer_name,
            "removeInteriorRings",
            "No source layers specified"
        ))
        return None
    
    result_geometries = []
    
    for layer_info in source_layers:
        source_layer_name = layer_info if isinstance(layer_info, str) else layer_info.get('name')
        
        if source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "removeInteriorRings",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue
        
        source_gdf = all_layers[source_layer_name]
        
        if source_gdf.empty:
            log_warning(format_operation_warning(
                layer_name,
                "removeInteriorRings",
                f"Source layer '{source_layer_name}' is empty"
            ))
            continue
        
        # Process each geometry
        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            
            if geom is None or geom.is_empty:
                continue
            
            # Extract exterior ring only
            if isinstance(geom, Polygon):
                # Create new polygon from exterior ring only
                exterior_only = Polygon(geom.exterior.coords)
                result_geometries.append(exterior_only)
                
            elif isinstance(geom, MultiPolygon):
                # For each polygon in multipolygon, extract exterior ring
                exterior_polygons = []
                for poly in geom.geoms:
                    exterior_only = Polygon(poly.exterior.coords)
                    exterior_polygons.append(exterior_only)
                
                # Return as MultiPolygon to maintain structure
                if len(exterior_polygons) == 1:
                    result_geometries.append(exterior_polygons[0])
                else:
                    result_geometries.append(MultiPolygon(exterior_polygons))
            else:
                # For non-polygon types (lines, points), keep as-is
                result_geometries.append(geom)
    
    if not result_geometries:
        log_warning(format_operation_warning(
            layer_name,
            "removeInteriorRings",
            "No valid geometries found"
        ))
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    result_gdf = gpd.GeoDataFrame(geometry=result_geometries, crs=crs)
    log_debug(f"Removed interior rings from {len(result_geometries)} geometries in layer '{layer_name}'")
    
    return result_gdf

