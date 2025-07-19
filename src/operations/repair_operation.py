import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from shapely.validation import make_valid
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import (
    _process_layer_info,
    _get_filtered_geometry,
    _clean_single_geometry,
    _remove_thin_growths,
    _clean_polygon,
    _remove_empty_geometries,
    make_valid_geometry,
    format_operation_warning,
    ensure_geodataframe
)
import traceback


def create_repair_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Create a repaired layer by applying various geometry cleaning and repair operations.

    This operation can fix common geometry issues like:
    - Self-intersections
    - Invalid geometries
    - Empty geometries
    - Thin artifacts/growths
    - Polygon slivers
    - Small polygons below minimum area

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
        Operation configuration with repair options

    Returns:
    --------
    GeoDataFrame or None
        Repaired geometries or None if operation fails
    """
    log_debug(f"Creating repair layer: {layer_name}")
    log_debug(f"Operation details: {operation}")

    # Get operation parameters with defaults
    source_layer_name = operation.get('sourceLayer', layer_name)
    buffer_repair = operation.get('bufferRepair', True)
    remove_empty_geometries = operation.get('removeEmptyGeometries', True)
    remove_thin_growths = operation.get('removeThinGrowths', False)
    thin_growth_threshold = operation.get('thinGrowthThreshold', 0.001)
    sliver_removal_distance = operation.get('sliverRemovalDistance', 0.001)
    min_area = operation.get('minArea', 0.0)
    make_valid_flag = operation.get('makeValid', True)
    simplify_flag = operation.get('simplify', False)
    simplify_tolerance = operation.get('simplifyTolerance', 0.01)
    preserve_topology = operation.get('preserveTopology', True)
    remove_failures = operation.get('removeFailures', True)

    # Get source layer
    if source_layer_name not in all_layers:
        log_error(format_operation_warning(
            layer_name,
            "repair",
            f"Source layer '{source_layer_name}' not found"
        ))
        return None

    source_gdf = all_layers[source_layer_name].copy()

    if source_gdf.empty:
        log_warning(f"Source layer '{source_layer_name}' is empty for repair operation")
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    log_info(f"Starting repair of {len(source_gdf)} geometries in layer '{source_layer_name}'")

    # Track repair statistics
    original_count = len(source_gdf)
    repaired_count = 0
    failed_count = 0
    removed_count = 0

    # Apply repair operations in sequence
    repaired_geometries = []
    repair_logs = []

    for idx, row in source_gdf.iterrows():
        geometry = row.geometry
        original_geometry = geometry
        repair_steps = []

        try:
            # Step 1: Remove empty geometries first
            if remove_empty_geometries and (geometry is None or geometry.is_empty):
                repair_steps.append("removed_empty")
                removed_count += 1
                continue

            # Step 2: Basic buffer repair for invalid geometries
            if buffer_repair and geometry is not None and hasattr(geometry, 'is_valid') and not geometry.is_valid:
                try:
                    cleaned_geom = _clean_single_geometry(all_layers, project_settings, crs, geometry)
                    if cleaned_geom is not None and not cleaned_geom.is_empty:
                        geometry = cleaned_geom
                        repair_steps.append("buffer_repair")
                    elif remove_failures:
                        repair_steps.append("buffer_repair_failed_removed")
                        failed_count += 1
                        continue
                except Exception as e:
                    log_debug(f"Buffer repair failed for feature {idx}: {e}")
                    if remove_failures:
                        repair_steps.append("buffer_repair_exception_removed")
                        failed_count += 1
                        continue

            # Step 3: Make valid if requested
            if make_valid_flag and geometry is not None:
                if hasattr(geometry, 'is_valid') and not geometry.is_valid:
                    try:
                        valid_geom = make_valid(geometry)
                        if valid_geom is not None and not valid_geom.is_empty:
                            geometry = valid_geom
                            repair_steps.append("make_valid")
                        elif remove_failures:
                            repair_steps.append("make_valid_failed_removed")
                            failed_count += 1
                            continue
                    except Exception as e:
                        log_debug(f"Make valid failed for feature {idx}: {e}")
                        if remove_failures:
                            repair_steps.append("make_valid_exception_removed")
                            failed_count += 1
                            continue

            # Step 4: Remove thin growths/artifacts
            if remove_thin_growths and geometry is not None:
                try:
                    cleaned_geom = _remove_thin_growths(all_layers, project_settings, crs, geometry, thin_growth_threshold)
                    if cleaned_geom is not None and not cleaned_geom.is_empty:
                        geometry = cleaned_geom
                        repair_steps.append("remove_thin_growths")
                    elif remove_failures:
                        repair_steps.append("thin_growth_removal_failed_removed")
                        failed_count += 1
                        continue
                except Exception as e:
                    log_debug(f"Thin growth removal failed for feature {idx}: {e}")
                    if remove_failures:
                        repair_steps.append("thin_growth_exception_removed")
                        failed_count += 1
                        continue

            # Step 5: Clean polygons (remove slivers)
            if geometry is not None and isinstance(geometry, (Polygon, MultiPolygon)):
                try:
                    if isinstance(geometry, Polygon):
                        cleaned_geom = _clean_polygon(all_layers, project_settings, crs, geometry, sliver_removal_distance, min_area)
                    else:  # MultiPolygon
                        cleaned_polys = []
                        for poly in geometry.geoms:
                            cleaned_poly = _clean_polygon(all_layers, project_settings, crs, poly, sliver_removal_distance, min_area)
                            if cleaned_poly is not None:
                                cleaned_polys.append(cleaned_poly)

                        if cleaned_polys:
                            if len(cleaned_polys) == 1:
                                cleaned_geom = cleaned_polys[0]
                            else:
                                cleaned_geom = MultiPolygon(cleaned_polys)
                        else:
                            cleaned_geom = None

                    if cleaned_geom is not None and not cleaned_geom.is_empty:
                        geometry = cleaned_geom
                        repair_steps.append("clean_polygon")
                    elif remove_failures:
                        repair_steps.append("polygon_cleaning_failed_removed")
                        failed_count += 1
                        continue
                except Exception as e:
                    log_debug(f"Polygon cleaning failed for feature {idx}: {e}")
                    if remove_failures:
                        repair_steps.append("polygon_cleaning_exception_removed")
                        failed_count += 1
                        continue

            # Step 6: Apply minimum area filter
            if (min_area > 0 and geometry is not None and
                isinstance(geometry, (Polygon, MultiPolygon)) and
                geometry.area < min_area):
                repair_steps.append("below_min_area_removed")
                removed_count += 1
                continue

            # Step 7: Simplify if requested
            if simplify_flag and geometry is not None and simplify_tolerance > 0:
                try:
                    simplified_geom = geometry.simplify(simplify_tolerance, preserve_topology=preserve_topology)
                    if simplified_geom is not None and not simplified_geom.is_empty:
                        geometry = simplified_geom
                        repair_steps.append("simplified")
                except Exception as e:
                    log_debug(f"Simplification failed for feature {idx}: {e}")
                    # Don't remove for simplification failure, keep original

            # Final validation
            if geometry is not None and hasattr(geometry, 'is_valid') and geometry.is_valid:
                # Create new row with repaired geometry
                new_row = row.copy()
                new_row.geometry = geometry
                repaired_geometries.append(new_row)

                if repair_steps:
                    repaired_count += 1
                    repair_logs.append(f"Feature {idx}: {', '.join(repair_steps)}")
            elif remove_failures:
                repair_steps.append("final_validation_failed_removed")
                failed_count += 1
            else:
                # Keep original geometry if repair failed and removeFailures is False
                new_row = row.copy()
                new_row.geometry = original_geometry
                repaired_geometries.append(new_row)

        except Exception as e:
            log_warning(f"Unexpected error repairing feature {idx}: {e}")
            if remove_failures:
                failed_count += 1
            else:
                # Keep original geometry
                new_row = row.copy()
                new_row.geometry = original_geometry
                repaired_geometries.append(new_row)

    # Create result GeoDataFrame
    if repaired_geometries:
        result_gdf = gpd.GeoDataFrame(repaired_geometries, crs=crs)

        # Final cleanup of empty geometries
        if remove_empty_geometries:
            before_final_cleanup = len(result_gdf)
            result_gdf = result_gdf[~result_gdf.geometry.is_empty & result_gdf.geometry.notna()]
            after_final_cleanup = len(result_gdf)
            if before_final_cleanup != after_final_cleanup:
                removed_count += (before_final_cleanup - after_final_cleanup)
    else:
        result_gdf = gpd.GeoDataFrame(geometry=[], crs=crs)

    # Log repair statistics
    final_count = len(result_gdf)
    log_info(f"Repair operation completed for layer '{layer_name}':")
    log_info(f"  Original geometries: {original_count}")
    log_info(f"  Repaired geometries: {repaired_count}")
    log_info(f"  Failed repairs: {failed_count}")
    log_info(f"  Removed geometries: {removed_count}")
    log_info(f"  Final geometries: {final_count}")

    # Log detailed repair steps if debug is enabled
    if repair_logs:
        log_debug("Detailed repair operations:")
        for log_entry in repair_logs[:10]:  # Limit to first 10 for readability
            log_debug(f"  {log_entry}")
        if len(repair_logs) > 10:
            log_debug(f"  ... and {len(repair_logs) - 10} more")

    return result_gdf
