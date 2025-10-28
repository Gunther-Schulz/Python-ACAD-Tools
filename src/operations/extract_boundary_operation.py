import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon
from src.utils import log_info, log_warning, log_debug
from src.operations.common_operations import format_operation_warning

def create_extract_boundary_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Extract boundaries from polygons and convert them to lines.
    Each polygon's exterior ring becomes a LineString.
    Interior rings (holes) are also converted to LineStrings.
    """
    
    # Get source layers
    source_layers = operation.get('layers', [layer_name])
    if not source_layers:
        source_layers = [layer_name]
    
    # Check if we should include holes
    include_holes = operation.get('includeHoles', False)
    
    lines = []
    
    for source_layer_name in source_layers:
        if isinstance(source_layer_name, dict):
            source_layer_name = source_layer_name.get('name')
        
        if source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "extractBoundary",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue
        
        source_gdf = all_layers[source_layer_name]
        
        if source_gdf.empty:
            log_warning(format_operation_warning(
                layer_name,
                "extractBoundary",
                f"Source layer '{source_layer_name}' is empty"
            ))
            continue
        
        log_debug(f"Extracting boundaries from {len(source_gdf)} geometries in layer '{source_layer_name}'")
        
        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            
            if geom is None or geom.is_empty:
                continue
            
            # Handle Polygon
            if isinstance(geom, Polygon):
                # Add exterior boundary
                if geom.exterior is not None and len(geom.exterior.coords) >= 2:
                    lines.append(LineString(geom.exterior.coords))
                
                # Add interior boundaries (holes) if requested
                if include_holes:
                    for interior in geom.interiors:
                        if len(interior.coords) >= 2:
                            lines.append(LineString(interior.coords))
            
            # Handle MultiPolygon
            elif isinstance(geom, MultiPolygon):
                for poly in geom.geoms:
                    # Add exterior boundary
                    if poly.exterior is not None and len(poly.exterior.coords) >= 2:
                        lines.append(LineString(poly.exterior.coords))
                    
                    # Add interior boundaries (holes) if requested
                    if include_holes:
                        for interior in poly.interiors:
                            if len(interior.coords) >= 2:
                                lines.append(LineString(interior.coords))
            
            # Handle LineString (already a line)
            elif isinstance(geom, LineString):
                lines.append(geom)
            
            # Handle MultiLineString
            elif isinstance(geom, MultiLineString):
                for line in geom.geoms:
                    lines.append(line)
    
    if not lines:
        log_warning(format_operation_warning(
            layer_name,
            "extractBoundary",
            "No boundaries could be extracted"
        ))
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    log_info(f"Extracted {len(lines)} boundary lines for layer '{layer_name}'")
    
    # Create GeoDataFrame with the lines
    result_gdf = gpd.GeoDataFrame(geometry=lines, crs=crs)
    
    return result_gdf

