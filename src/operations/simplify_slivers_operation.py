import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import ensure_geodataframe

def create_simplify_slivers_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Conservative sliver removal using Douglas-Peucker simplification.

    This is a much safer approach than trying to identify specific thin sections.
    It uses topology-preserving simplification that naturally removes small details
    while preserving the overall polygon shape.

    Parameters:
    -----------
    tolerance : float
        Simplification tolerance (default: 0.1)
    preserve_topology : bool
        Whether to preserve topology (default: True)
    min_area_threshold : float
        Remove polygons smaller than this after simplification (default: 10.0)
    """
    log_info(f"=== STARTING simplifySlivers operation for layer: {layer_name} ===")

    if layer_name not in all_layers:
        log_error(f"Layer '{layer_name}' not found for simplify slivers operation")
        return None

    input_gdf = all_layers[layer_name].copy()
    if input_gdf.empty:
        log_warning(f"Layer '{layer_name}' is empty")
        return input_gdf

    # Conservative parameters
    tolerance = operation.get('tolerance', 0.1)  # Very small tolerance
    preserve_topology = operation.get('preserveTopology', True)
    min_area_threshold = operation.get('minAreaThreshold', 10.0)

    log_info(f"Using CONSERVATIVE simplification - tolerance: {tolerance}, preserve_topology: {preserve_topology}")

    # Process each geometry
    simplified_geometries = []
    removed_count = 0
    simplified_count = 0

    for idx, row in input_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        log_debug(f"Processing feature {idx}: {geom.geom_type}, area={geom.area:.1f}")

        try:
            # Apply Douglas-Peucker simplification
            simplified_geom = geom.simplify(tolerance, preserve_topology=preserve_topology)

            # Check if the result is valid and not too small
            if (simplified_geom and
                not simplified_geom.is_empty and
                simplified_geom.is_valid and
                simplified_geom.area >= min_area_threshold):

                new_row = row.copy()
                new_row.geometry = simplified_geom
                simplified_geometries.append(new_row)

                # Count if we actually simplified something
                if isinstance(geom, Polygon) and isinstance(simplified_geom, Polygon):
                    original_coords = len(geom.exterior.coords)
                    simplified_coords = len(simplified_geom.exterior.coords)
                    if simplified_coords < original_coords:
                        simplified_count += 1
                        log_debug(f"Feature {idx}: simplified from {original_coords} to {simplified_coords} coordinates")

            else:
                log_debug(f"Feature {idx}: removed due to small area ({simplified_geom.area if simplified_geom else 0:.1f})")
                removed_count += 1

        except Exception as e:
            log_warning(f"Feature {idx}: simplification failed - {e}, keeping original")
            new_row = row.copy()
            simplified_geometries.append(new_row)

    log_info(f"=== COMPLETED simplifySlivers: Simplified {simplified_count} features, removed {removed_count} small features ===")

    if simplified_geometries:
        result_gdf = gpd.GeoDataFrame(simplified_geometries, crs=crs)
        return ensure_geodataframe(all_layers, project_settings, crs, layer_name, result_gdf)
    else:
        log_warning(f"No valid geometries after simplification for layer '{layer_name}'")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
