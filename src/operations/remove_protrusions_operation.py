import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely.ops import unary_union
from scipy.spatial import ConvexHull
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import ensure_geodataframe

def create_remove_protrusions_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Remove thin protrusions while preserving the main polygon shape.

    This approach:
    1. Identifies the "main body" of each polygon using convex hull
    2. Finds areas that stick out significantly from this main body
    3. Removes only those protruding areas
    4. Preserves the original polygon boundary where it doesn't protrude

    Parameters:
    -----------
    protrusion_threshold : float
        How far a point can be from the main body before it's considered a protrusion (default: 2.0)
    min_protrusion_length : float
        Minimum length of protrusion to remove (default: 3.0)
    buffer_distance : float
        Buffer distance for identifying main body (default: 1.0)
    """
    log_info(f"=== STARTING removeProtrusions operation for layer: {layer_name} ===")

    if layer_name not in all_layers:
        log_error(f"Layer '{layer_name}' not found for remove protrusions operation")
        return None

    input_gdf = all_layers[layer_name].copy()
    if input_gdf.empty:
        log_warning(f"Layer '{layer_name}' is empty")
        return input_gdf

    # Parameters
    protrusion_threshold = operation.get('protrusionThreshold', 2.0)
    min_protrusion_length = operation.get('minProtrusionLength', 3.0)
    buffer_distance = operation.get('bufferDistance', 1.0)

    log_info(f"Using parameters - protrusion_threshold: {protrusion_threshold}, min_protrusion_length: {min_protrusion_length}")

    # Process each geometry
    cleaned_geometries = []
    total_removed = 0

    for idx, row in input_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        log_info(f"Processing feature {idx}: {geom.geom_type}, area={geom.area:.1f}")

        if isinstance(geom, Polygon):
            cleaned_geom, removed_count = _remove_polygon_protrusions_conservative(
                geom, protrusion_threshold, min_protrusion_length, buffer_distance, idx)
        elif isinstance(geom, MultiPolygon):
            cleaned_parts = []
            removed_count = 0
            for i, poly in enumerate(geom.geoms):
                cleaned_poly, part_removed = _remove_polygon_protrusions_conservative(
                    poly, protrusion_threshold, min_protrusion_length, buffer_distance, f"{idx}-{i}")
                removed_count += part_removed
                if cleaned_poly and not cleaned_poly.is_empty:
                    cleaned_parts.append(cleaned_poly)
            cleaned_geom = MultiPolygon(cleaned_parts) if cleaned_parts else None
        else:
            cleaned_geom = geom
            removed_count = 0

        total_removed += removed_count

        if cleaned_geom and not cleaned_geom.is_empty:
            new_row = row.copy()
            new_row.geometry = cleaned_geom
            cleaned_geometries.append(new_row)

    log_info(f"=== COMPLETED removeProtrusions: Removed {total_removed} protrusions from {len(cleaned_geometries)} features ===")

    if cleaned_geometries:
        result_gdf = gpd.GeoDataFrame(cleaned_geometries, crs=crs)
        return ensure_geodataframe(all_layers, project_settings, crs, layer_name, result_gdf)
    else:
        log_warning(f"No valid geometries after removing protrusions for layer '{layer_name}'")
        return gpd.GeoDataFrame(geometry=[], crs=crs)


def _remove_polygon_protrusions_conservative(polygon, protrusion_threshold, min_protrusion_length, buffer_distance, label):
    """Remove protrusions while preserving main polygon shape."""
    if not isinstance(polygon, Polygon) or polygon.is_empty:
        return polygon, 0

    try:
        # Get the main body by buffering inward then outward (erosion/dilation)
        main_body = polygon.buffer(-buffer_distance)
        if main_body.is_empty:
            log_debug(f"Feature {label}: Buffer too large, keeping original")
            return polygon, 0

        main_body = main_body.buffer(buffer_distance)

        # Find areas that stick out from the main body
        protrusions = polygon.difference(main_body)

        if protrusions.is_empty:
            log_debug(f"Feature {label}: No protrusions found")
            return polygon, 0

        # Filter protrusions by size
        significant_protrusions = []
        if isinstance(protrusions, MultiPolygon):
            for protrusion in protrusions.geoms:
                if _is_significant_protrusion(protrusion, min_protrusion_length):
                    significant_protrusions.append(protrusion)
        elif isinstance(protrusions, Polygon):
            if _is_significant_protrusion(protrusions, min_protrusion_length):
                significant_protrusions.append(protrusions)

        if not significant_protrusions:
            log_debug(f"Feature {label}: No significant protrusions found")
            return polygon, 0

        # Remove the significant protrusions
        protrusions_to_remove = unary_union(significant_protrusions)
        cleaned_polygon = polygon.difference(protrusions_to_remove)

        if cleaned_polygon.is_empty or not cleaned_polygon.is_valid:
            log_debug(f"Feature {label}: Cleaning resulted in invalid geometry, keeping original")
            return polygon, 0

        # Ensure we still have a reasonable polygon
        if isinstance(cleaned_polygon, Polygon):
            result_polygon = cleaned_polygon
        elif isinstance(cleaned_polygon, MultiPolygon):
            # Take the largest part if we created multiple polygons
            result_polygon = max(cleaned_polygon.geoms, key=lambda p: p.area)
        else:
            log_debug(f"Feature {label}: Unexpected geometry type after cleaning")
            return polygon, 0

        # Make sure we didn't remove too much area
        area_loss = (polygon.area - result_polygon.area) / polygon.area
        if area_loss > 0.5:  # Don't remove more than 50% of the original area
            log_debug(f"Feature {label}: Would remove too much area ({area_loss:.1%}), keeping original")
            return polygon, 0

        log_info(f"Feature {label}: Removed {len(significant_protrusions)} protrusions, area loss: {area_loss:.1%}")
        return result_polygon, len(significant_protrusions)

    except Exception as e:
        log_error(f"Feature {label}: Error removing protrusions - {e}")
        return polygon, 0


def _is_significant_protrusion(protrusion, min_length):
    """Check if a protrusion is significant enough to remove."""
    if not isinstance(protrusion, Polygon) or protrusion.is_empty:
        return False

    # Use perimeter-to-area ratio to identify thin features
    if protrusion.area <= 0:
        return False

    # Calculate aspect ratio using bounding box
    bounds = protrusion.bounds
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]

    if width <= 0 or height <= 0:
        return False

    aspect_ratio = max(width, height) / min(width, height)
    max_dimension = max(width, height)

    # For extremely small protrusions (area < 1.0), remove them regardless of aspect ratio
    if protrusion.area < 1.0:
        return True

    # For tiny protrusions (area < 10.0), be very aggressive
    if protrusion.area < 10.0 and aspect_ratio > 1.5:
        return True

    # Normal case: Remove if it's thin (high aspect ratio) and long enough
    return aspect_ratio > 3.0 and max_dimension >= min_length
