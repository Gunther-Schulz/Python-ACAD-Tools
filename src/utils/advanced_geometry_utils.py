"""Advanced geometry utility functions, e.g., for complex envelope creation."""
from typing import Optional, Tuple, List
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, box # Added box
from shapely.ops import unary_union
from ..interfaces.logging_service_interface import ILoggingService # Assuming path from utils

# Note: scipy.spatial.distance was imported in old file but not used in the core envelope logic. Omitting for now.

def _detect_bend_internal(polygon: Polygon, logger: ILoggingService) -> bool:
    """
    Simplified bend detection using minimum rotated rectangle area ratio.
    A low ratio of polygon area to its MBR area suggests a bend.
    """
    if polygon is None or polygon.is_empty or not isinstance(polygon, Polygon) or not polygon.is_valid:
        logger.warning("_detect_bend_internal: Received invalid, empty, or non-Polygon geometry. Cannot detect bend.")
        return False
    try:
        min_rect = polygon.minimum_rotated_rectangle
        if min_rect is None or min_rect.is_empty or min_rect.area == 0:
            logger.debug(f"_detect_bend_internal: Minimum rotated rectangle area is zero or MBR is empty for polygon: {polygon.wkt[:50]}...")
            return False # Cannot determine ratio

        area_ratio = polygon.area / min_rect.area
        is_bend = area_ratio < 0.8 # Threshold from original code
        logger.debug(f"_detect_bend_internal: Polygon area {polygon.area:.2f}, MBR area {min_rect.area:.2f}, ratio {area_ratio:.2f}. Bend detected: {is_bend}")
        return is_bend
    except Exception as e:
        logger.error(f"_detect_bend_internal: Error during bend detection for polygon {polygon.wkt[:50]}...: {e}", exc_info=True)
        return False


def _split_at_bend_internal(polygon: Polygon, logger: ILoggingService) -> Optional[Tuple[Polygon, Polygon]]:
    """
    Split polygon perpendicular to the segments at the most significant bend point.
    Returns a tuple of two polygons if successful, otherwise None.
    """
    if not isinstance(polygon, Polygon) or polygon.is_empty or not polygon.is_valid:
        logger.warning("_split_at_bend_internal: Received invalid, empty or non-Polygon geometry.")
        return None

    try:
        coords = np.array(polygon.exterior.coords)
        if len(coords) < 4: # Need at least a triangle to form 2+ segments
            logger.debug("_split_at_bend_internal: Polygon has too few points to define a bend.")
            return None

        vectors = np.diff(coords, axis=0)
        lengths = np.linalg.norm(vectors, axis=1)

        valid_lengths_mask = lengths > 1e-9
        if not np.all(valid_lengths_mask):
            logger.warning(f"_split_at_bend_internal: Polygon contains zero-length segments. Coords: {coords.tolist()}")
            pass

        normalized_vectors = np.zeros_like(vectors)
        np.divide(vectors, lengths[:, np.newaxis], out=normalized_vectors, where=valid_lengths_mask[:, np.newaxis])

        if len(normalized_vectors) < 2:
             logger.debug("_split_at_bend_internal: Not enough segments to calculate angles after diff.")
             return None

        dot_products = np.sum(normalized_vectors[:-1] * normalized_vectors[1:], axis=1)
        angles = np.arccos(np.clip(dot_products, -1.0, 1.0)) * 180 / np.pi

        if not angles.size:
            logger.debug("_split_at_bend_internal: No angles calculated, cannot find bend point.")
            return None

        bend_idx = np.argmax(angles)
        bend_point_coord = coords[bend_idx + 1]

        dir_before = normalized_vectors[bend_idx]
        dir_after = normalized_vectors[bend_idx + 1]

        perp_before = np.array([-dir_before[1], dir_before[0]])
        perp_after = np.array([-dir_after[1], dir_after[0]])
        split_direction = (perp_before + perp_after) / 2

        norm_split_dir = np.linalg.norm(split_direction)
        if norm_split_dir < 1e-9:
            logger.warning("_split_at_bend_internal: Split direction is near zero vector. Cannot determine split line.")
            split_direction = perp_before
            norm_split_dir = np.linalg.norm(split_direction)
            if norm_split_dir < 1e-9:
                 logger.error("_split_at_bend_internal: Fallback split direction also near zero. Aborting split.")
                 return None

        split_direction /= norm_split_dir

        bounds = polygon.bounds
        line_length = np.sqrt((bounds[2] - bounds[0])**2 + (bounds[3] - bounds[1])**2)
        if line_length < 1e-6: line_length = 1.0

        p1 = bend_point_coord - line_length * split_direction
        p2 = bend_point_coord + line_length * split_direction
        split_line = LineString([p1, p2])

        split_buffer_distance = 0.001 * line_length

        split_poly_geom = polygon.difference(split_line.buffer(split_buffer_distance))

        if isinstance(split_poly_geom, MultiPolygon):
            polys = [p for p in split_poly_geom.geoms if isinstance(p, Polygon) and p.area > 1e-9]
            if len(polys) >= 2:
                logger.debug(f"_split_at_bend_internal: Split into {len(polys)} parts. Returning two largest.")
                polys.sort(key=lambda p: p.area, reverse=True)
                return polys[0], polys[1]
            elif len(polys) == 1:
                 logger.warning("_split_at_bend_internal: Split resulted in one polygon part. Bend split failed effectively.")
                 return None
            else:
                 logger.warning("_split_at_bend_internal: Split resulted in no valid polygon parts.")
                 return None

        elif isinstance(split_poly_geom, Polygon) and split_poly_geom.area > 1e-9 :
            logger.debug("_split_at_bend_internal: Split resulted in a single Polygon, assuming no effective split.")
            return None
        else:
            logger.warning(f"_split_at_bend_internal: Split resulted in unexpected geometry type {type(split_poly_geom)} or it's empty.")
            return None

    except Exception as e:
        logger.error(f"_split_at_bend_internal: Error during split for polygon {polygon.wkt[:50]}...: {e}", exc_info=True)
        return None


def create_envelope_for_geometry(
    polygon: Polygon,
    padding: float,
    min_ratio: Optional[float],
    cap_style: str,
    logger: ILoggingService,
    recursion_depth: int = 0
) -> Optional[Polygon]:
    """
    Creates an optimized envelope for a single Polygon geometry, handling bends.
    Based on OLDAPP/src/operations/envelope_operation.py
    """
    if polygon is None or not isinstance(polygon, Polygon) or polygon.is_empty:
        logger.debug("create_envelope_for_geometry: Input polygon is None, not a Polygon, or empty.")
        return None

    if not polygon.is_valid:
        logger.warning(f"create_envelope_for_geometry: Input polygon is invalid. WKT: {polygon.wkt[:100]}...")
        return None

    try:
        if min_ratio is not None:
            try:
                min_rect_for_ratio = polygon.minimum_rotated_rectangle
                if min_rect_for_ratio is None or min_rect_for_ratio.is_empty:
                     logger.warning("create_envelope_for_geometry: Could not get MBR for min_ratio check.")
                else:
                    rect_coords = np.array(min_rect_for_ratio.exterior.coords)
                    edges = rect_coords[1:] - rect_coords[:-1]
                    edge_lengths = np.sqrt(np.sum(edges**2, axis=1))

                    if len(edge_lengths) < 2 :
                        logger.warning("create_envelope_for_geometry: MBR for min_ratio check has too few edges.")
                    else:
                        length = np.max(edge_lengths)
                        width = np.min(edge_lengths)

                        current_ratio = length / width if width > 1e-9 else float('inf')
                        logger.debug(f"create_envelope_for_geometry: MinRatio Pre-Check. Current Ratio: {current_ratio:.2f}, Min Required: {min_ratio}")
                        if current_ratio < min_ratio:
                            logger.info(f"create_envelope_for_geometry: Polygon (Area: {polygon.area:.2f}) does not meet min_ratio {min_ratio} (ratio {current_ratio:.2f}). Returning original polygon.")
                            return polygon
            except Exception as e_ratio_check:
                 logger.error(f"create_envelope_for_geometry: Error during min_ratio pre-check: {e_ratio_check}", exc_info=True)
                 return polygon

        MAX_RECURSION_DEPTH = 3
        MIN_AREA_FOR_BEND_PROCESSING = 1e-5

        if recursion_depth > MAX_RECURSION_DEPTH:
            logger.debug(f"create_envelope_for_geometry: Max recursion depth ({MAX_RECURSION_DEPTH}) reached. Returning MBR.")
            return polygon.minimum_rotated_rectangle
        if polygon.area < MIN_AREA_FOR_BEND_PROCESSING:
            logger.debug(f"create_envelope_for_geometry: Polygon area ({polygon.area:.2f}) too small for bend processing. Returning MBR.")
            return polygon.minimum_rotated_rectangle

        if _detect_bend_internal(polygon, logger):
            logger.debug(f"create_envelope_for_geometry: Bend detected for polygon (Area: {polygon.area:.2f}). Attempting split.")
            split_parts = _split_at_bend_internal(polygon, logger)
            if split_parts:
                part1, part2 = split_parts
                valid_parts_for_recursion = []
                if part1 and isinstance(part1, Polygon) and part1.is_valid and part1.area > MIN_AREA_FOR_BEND_PROCESSING:
                    valid_parts_for_recursion.append(part1)
                else:
                    logger.debug("create_envelope_for_geometry: Bend split part1 is invalid, empty, or too small.")

                if part2 and isinstance(part2, Polygon) and part2.is_valid and part2.area > MIN_AREA_FOR_BEND_PROCESSING:
                    valid_parts_for_recursion.append(part2)
                else:
                    logger.debug("create_envelope_for_geometry: Bend split part2 is invalid, empty, or too small.")

                envelopes_from_parts = []
                if valid_parts_for_recursion:
                    for part in valid_parts_for_recursion:
                        env = create_envelope_for_geometry(part, padding, min_ratio, cap_style, logger, recursion_depth + 1)
                        if env:
                            envelopes_from_parts.append(env)

                if len(envelopes_from_parts) > 0:
                    logger.debug(f"create_envelope_for_geometry: Unioning {len(envelopes_from_parts)} envelopes from split parts.")
                    final_envelope = unary_union(envelopes_from_parts)
                    if isinstance(final_envelope, Polygon): return final_envelope
                    elif isinstance(final_envelope, MultiPolygon):
                        logger.warning("create_envelope_for_geometry: Union of split part envelopes resulted in MultiPolygon. Attempting convex_hull or MBR.")
                        return final_envelope.convex_hull
                    else:
                        logger.error(f"create_envelope_for_geometry: Union of split part envelopes is not Polygon/MultiPolygon: {type(final_envelope)}. Returning MBR of original.")
                        return polygon.minimum_rotated_rectangle
                else:
                     logger.debug("create_envelope_for_geometry: No valid envelopes from split parts. Proceeding with MBR of current polygon.")

        logger.debug(f"create_envelope_for_geometry: Proceeding with standard MBR-based envelope for polygon (Area: {polygon.area:.2f}).")

        try:
            mrr = polygon.minimum_rotated_rectangle
            if not isinstance(mrr, Polygon) or mrr.is_empty:
                logger.error(f"create_envelope_for_geometry: Could not compute MBR or MBR is empty/invalid for polygon. WKT: {polygon.wkt[:50]}")
                return None

            mrr_coords = np.array(mrr.exterior.coords)

            mrr_edges = mrr_coords[1:] - mrr_coords[:-1]
            mrr_edge_lengths = np.sqrt(np.sum(mrr_edges**2, axis=1))

            if len(mrr_edge_lengths) < 2 :
                 logger.error(f"create_envelope_for_geometry: MBR has too few edges {len(mrr_edge_lengths)} for polygon {polygon.wkt[:50]}")
                 return mrr

            if min_ratio is not None:
                mrr_length = np.max(mrr_edge_lengths)
                mrr_width = np.min(mrr_edge_lengths)
                mrr_current_ratio = mrr_length / mrr_width if mrr_width > 1e-9 else float('inf')
                logger.debug(f"create_envelope_for_geometry: MBR MinRatio Check. MBR Ratio: {mrr_current_ratio:.2f}, Min Required: {min_ratio}")
                if mrr_current_ratio < min_ratio:
                    logger.info(f"create_envelope_for_geometry: MBR for polygon (Area: {polygon.area:.2f}) does not meet min_ratio {min_ratio} (MBR ratio {mrr_current_ratio:.2f}). Returning original polygon as per spec.")
                    return polygon

            longest_edge_idx = np.argmax(mrr_edge_lengths)

            direction = mrr_edges[longest_edge_idx] / mrr_edge_lengths[longest_edge_idx]
            perpendicular = np.array([-direction[1], direction[0]])

            original_poly_coords = np.array(polygon.exterior.coords)
            center_of_original = np.array(polygon.centroid.coords[0])

            coords_centered_on_original_centroid = original_poly_coords - center_of_original

            proj_main_axis = np.dot(coords_centered_on_original_centroid, direction)
            proj_perp_axis = np.dot(coords_centered_on_original_centroid, perpendicular)

            half_main_extent = (np.max(proj_main_axis) - np.min(proj_main_axis)) / 2.0 + padding
            half_perp_extent = (np.max(proj_perp_axis) - np.min(proj_perp_axis)) / 2.0 + padding

            half_main_extent = max(0, half_main_extent)
            half_perp_extent = max(0, half_perp_extent)

            mrr_center = np.array(mrr.centroid.coords[0])

            if cap_style == 'round':
                radius = half_perp_extent
                if radius * 2 > half_main_extent * 2 :
                    logger.warning(f"create_envelope_for_geometry: Round cap radius ({radius:.2f}) is too large for main extent ({half_main_extent:.2f}). Adjusting radius or cap style.")
                    logger.info("create_envelope_for_geometry: Falling back to MBR due to large radius for round caps.")
                    return mrr

                rect_half_len = half_main_extent - radius

                if rect_half_len < 1e-9:
                    logger.debug(f"create_envelope_for_geometry: Rectangular part for round cap is negligible ({rect_half_len:.2f}). Buffering MBR center by radius.")
                    return Point(mrr_center).buffer(radius)

                rc1 = mrr_center + rect_half_len * direction + radius * perpendicular
                rc2 = mrr_center + rect_half_len * direction - radius * perpendicular
                rc3 = mrr_center - rect_half_len * direction - radius * perpendicular
                rc4 = mrr_center - rect_half_len * direction + radius * perpendicular

                rect_part = Polygon([rc1, rc2, rc3, rc4])

                cap1_center = mrr_center + rect_half_len * direction
                cap2_center = mrr_center - rect_half_len * direction

                cap1 = Point(cap1_center).buffer(radius)
                cap2 = Point(cap2_center).buffer(radius)

                final_geom = unary_union([rect_part, cap1, cap2])
                if isinstance(final_geom, Polygon): return final_geom
                logger.warning(f"create_envelope_for_geometry: Round cap resulted in {type(final_geom)}. Returning MBR.")
                return mrr

            else:  # 'square' caps
                c1 = mrr_center + half_main_extent * direction + half_perp_extent * perpendicular
                c2 = mrr_center + half_main_extent * direction - half_perp_extent * perpendicular
                c3 = mrr_center - half_main_extent * direction - half_perp_extent * perpendicular
                c4 = mrr_center - half_main_extent * direction + half_perp_extent * perpendicular
                return Polygon([c1, c2, c3, c4])

        except Exception as e_std_env:
            logger.error(f"create_envelope_for_geometry: Error during standard envelope creation for polygon {polygon.wkt[:50]}...: {e_std_env}", exc_info=True)
            try:
                return polygon.minimum_rotated_rectangle
            except Exception as e_mbr_fallback:
                logger.error(f"create_envelope_for_geometry: Error getting MBR as fallback: {e_mbr_fallback}", exc_info=True)
                return None

    except Exception as e:
        logger.error(f"create_envelope_for_geometry: Error during envelope creation for polygon {polygon.wkt[:50]}...: {e}", exc_info=True)
        return None
