import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon, Point, GeometryCollection
from shapely.ops import polygonize, polygonize_full, unary_union, linemerge
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, format_operation_warning
import numpy as np
from scipy.spatial.distance import cdist


def create_polygonize_layer(all_layers, project_settings, crs, layer_name, operation):
    """
    Create boundary polygons from line segments by buffering and unioning.
    
    This operation:
    1. Collects all line segments from source layer(s)
    2. Buffers each line by a small distance to create polygons
    3. Unions all buffered lines to create a single boundary
    4. Extracts the outer boundary polygon(s)
    
    This approach preserves the original line geometry while creating
    closed polygons that represent the outer boundary of the linework.
    """
    log_debug(f"Creating polygonize layer: {layer_name}")
    
    # Get source layers
    source_layers = operation.get('layers', [layer_name])
    if not source_layers:
        source_layers = [layer_name]
    
    # Collect all line segments
    all_lines = []
    
    for layer_info in source_layers:
        source_layer_name, values, column_name = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "polygonize",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue
        
        source_gdf = all_layers[source_layer_name]
        
        if source_gdf.empty:
            log_warning(format_operation_warning(
                layer_name,
                "polygonize",
                f"Source layer '{source_layer_name}' is empty"
            ))
            continue
        
        log_debug(f"Collecting lines from {len(source_gdf)} geometries in layer '{source_layer_name}'")
        
        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            
            if geom is None or geom.is_empty:
                continue
            
            # Handle LineString
            if isinstance(geom, LineString):
                if len(geom.coords) >= 2:
                    all_lines.append(geom)
            
            # Handle MultiLineString
            elif isinstance(geom, MultiLineString):
                for line in geom.geoms:
                    if len(line.coords) >= 2:
                        all_lines.append(line)
            
            # Handle Polygon/MultiPolygon - extract boundaries as lines
            elif isinstance(geom, (Polygon, MultiPolygon)):
                if isinstance(geom, Polygon):
                    if geom.exterior and len(geom.exterior.coords) >= 2:
                        all_lines.append(LineString(geom.exterior.coords))
                else:  # MultiPolygon
                    for poly in geom.geoms:
                        if poly.exterior and len(poly.exterior.coords) >= 2:
                            all_lines.append(LineString(poly.exterior.coords))
    
    if not all_lines:
        log_warning(format_operation_warning(
            layer_name,
            "polygonize",
            "No line segments found to polygonize"
        ))
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    log_debug(f"Found {len(all_lines)} line segments to process")
    
    # Debug: Count total vertices in original lines
    total_original_vertices = sum(len(list(line.coords)) for line in all_lines)
    log_debug(f"Total vertices in original lines: {total_original_vertices}")
    
    # Step 1: Connect endpoints to form outer boundaries
    # This closes gaps so that buffering can create proper closed polygons
    # We connect closest endpoint pairs that would help form the outer boundary
    log_debug("Connecting endpoints to form outer boundaries")
    
    # Extract all endpoints
    endpoints = []
    endpoint_to_lines = {}  # Track which lines use each endpoint
    
    for line_idx, line in enumerate(all_lines):
        coords = list(line.coords)
        start_coord = tuple(coords[0])
        end_coord = tuple(coords[-1])
        
        endpoints.append(start_coord)
        endpoints.append(end_coord)
        
        if start_coord not in endpoint_to_lines:
            endpoint_to_lines[start_coord] = []
        if end_coord not in endpoint_to_lines:
            endpoint_to_lines[end_coord] = []
        
        endpoint_to_lines[start_coord].append(line_idx)
        endpoint_to_lines[end_coord].append(line_idx)
    
    # Find unique endpoints (within small tolerance)
    unique_endpoints = []
    tolerance = 1e-9
    
    for endpoint in endpoints:
        found = False
        for unique_ep in unique_endpoints:
            if Point(endpoint).distance(Point(unique_ep)) < tolerance:
                found = True
                break
        if not found:
            unique_endpoints.append(endpoint)
    
    log_debug(f"Found {len(unique_endpoints)} unique endpoint locations")
    
    # Count how many lines connect to each endpoint
    unique_endpoint_to_lines = {}
    for ep_idx, unique_ep in enumerate(unique_endpoints):
        unique_endpoint_to_lines[ep_idx] = []
        for line_idx, line in enumerate(all_lines):
            coords = list(line.coords)
            start_coord = tuple(coords[0])
            end_coord = tuple(coords[-1])
            if (Point(start_coord).distance(Point(unique_ep)) < tolerance or
                Point(end_coord).distance(Point(unique_ep)) < tolerance):
                unique_endpoint_to_lines[ep_idx].append(line_idx)
    
    # Find endpoints that need connections (odd number of lines = unclosed)
    endpoint_line_count = {ep_idx: len(lines) for ep_idx, lines in unique_endpoint_to_lines.items()}
    unconnected = [ep_idx for ep_idx, count in endpoint_line_count.items() if count % 2 == 1]
    
    log_debug(f"Found {len(unconnected)} endpoints with odd connections that need closing")
    
    # Connect unconnected endpoints by connecting closest pairs
    # This forms closed loops for the outer boundary
    connecting_lines = []
    if len(unique_endpoints) > 1 and len(unconnected) > 0:
        unique_array = np.array(unique_endpoints)
        distances = cdist(unique_array, unique_array)
        np.fill_diagonal(distances, np.inf)
        
        # Set pairs that are already connected by the same line to infinity
        for i in range(len(unique_array)):
            for j in range(i + 1, len(unique_array)):
                lines_i = unique_endpoint_to_lines.get(i, [])
                lines_j = unique_endpoint_to_lines.get(j, [])
                if set(lines_i) & set(lines_j):
                    distances[i, j] = np.inf
                    distances[j, i] = np.inf
        
        # Connect closest pairs of unconnected endpoints
        while len(unconnected) >= 2:
            min_dist = np.inf
            min_i_idx = -1
            min_j_idx = -1
            
            for i in range(len(unconnected)):
                for j in range(i + 1, len(unconnected)):
                    ep_i = unconnected[i]
                    ep_j = unconnected[j]
                    if distances[ep_i, ep_j] < min_dist:
                        min_dist = distances[ep_i, ep_j]
                        min_i_idx = i
                        min_j_idx = j
            
            if min_dist == np.inf or min_i_idx == -1:
                break
            
            ep_i = unconnected[min_i_idx]
            ep_j = unconnected[min_j_idx]
            ep1 = unique_endpoints[ep_i]
            ep2 = unique_endpoints[ep_j]
            connecting_line = LineString([ep1, ep2])
            connecting_lines.append(connecting_line)
            
            log_debug(f"Connecting endpoint {ep_i} to {ep_j} (distance: {min_dist:.6f})")
            
            if min_j_idx > min_i_idx:
                unconnected.pop(min_j_idx)
                unconnected.pop(min_i_idx)
            else:
                unconnected.pop(min_i_idx)
                unconnected.pop(min_j_idx)
        
        # If one endpoint remains, connect it to the closest endpoint
        if len(unconnected) == 1:
            remaining = unconnected[0]
            min_dist = np.inf
            closest_idx = -1
            for other_idx in range(len(unique_array)):
                if other_idx != remaining and distances[remaining, other_idx] < min_dist:
                    min_dist = distances[remaining, other_idx]
                    closest_idx = other_idx
            
            if closest_idx != -1 and min_dist < np.inf:
                ep1 = unique_endpoints[remaining]
                ep2 = unique_endpoints[closest_idx]
                connecting_line = LineString([ep1, ep2])
                connecting_lines.append(connecting_line)
                log_debug(f"Connecting remaining endpoint {remaining} to {closest_idx} (distance: {min_dist:.6f})")
    
    log_debug(f"Created {len(connecting_lines)} connecting lines to close gaps")
    
    # Step 2: Combine original lines with connecting lines, then buffer and union
    all_lines_for_processing = all_lines + connecting_lines
    
    # Get buffer distance from operation parameters (default: 0.1 meters)
    buffer_distance = operation.get('bufferDistance', 0.1)
    log_debug(f"Using buffer distance: {buffer_distance}")
    
    # Step 3: Buffer all lines to create polygons
    buffered_polygons = []
    for line in all_lines_for_processing:
        try:
            buffered = line.buffer(buffer_distance, cap_style=2, join_style=2)  # Round caps and joins
            if isinstance(buffered, Polygon):
                buffered_polygons.append(buffered)
            elif isinstance(buffered, MultiPolygon):
                buffered_polygons.extend(buffered.geoms)
        except Exception as e:
            log_warning(f"Error buffering line: {e}")
            continue
    
    if not buffered_polygons:
        log_warning(format_operation_warning(
            layer_name,
            "polygonize",
            "No valid buffered polygons created"
        ))
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    log_debug(f"Created {len(buffered_polygons)} buffered polygons")
    
    # Step 4: Union all buffered polygons to create boundary
    try:
        unioned = unary_union(buffered_polygons)
        
        # Extract polygons from union result and remove interior rings (fill holes)
        result_polygons = []
        if isinstance(unioned, Polygon):
            # Remove interior rings by creating new polygon with only exterior
            if unioned.interiors:
                log_debug(f"Removing {len(unioned.interiors)} interior rings from polygon")
            result_polygons.append(Polygon(unioned.exterior))
        elif isinstance(unioned, MultiPolygon):
            for poly in unioned.geoms:
                # Remove interior rings from each polygon
                if poly.interiors:
                    log_debug(f"Removing {len(poly.interiors)} interior rings from polygon")
                result_polygons.append(Polygon(poly.exterior))
        elif isinstance(unioned, GeometryCollection):
            for geom in unioned.geoms:
                if isinstance(geom, Polygon):
                    # Remove interior rings
                    if geom.interiors:
                        log_debug(f"Removing {len(geom.interiors)} interior rings from polygon")
                    result_polygons.append(Polygon(geom.exterior))
                elif isinstance(geom, MultiPolygon):
                    for poly in geom.geoms:
                        # Remove interior rings from each polygon
                        if poly.interiors:
                            log_debug(f"Removing {len(poly.interiors)} interior rings from polygon")
                        result_polygons.append(Polygon(poly.exterior))
        
        if not result_polygons:
            log_warning(format_operation_warning(
                layer_name,
                "polygonize",
                "No polygons created from union"
            ))
            return gpd.GeoDataFrame(geometry=[], crs=crs)
        
        log_debug(f"Created {len(result_polygons)} polygon(s) from union")
        
        # Step 5: Filter by area if specified (keep only largest polygons for outer boundaries)
        max_polygons = operation.get('maxPolygons', None)
        min_area = operation.get('minArea', None)
        
        if min_area is not None or max_polygons is not None:
            # Sort by area (largest first)
            result_polygons.sort(key=lambda p: p.area, reverse=True)
            
            if min_area is not None:
                result_polygons = [p for p in result_polygons if p.area >= min_area]
                log_debug(f"Filtered to {len(result_polygons)} polygons with area >= {min_area}")
            
            if max_polygons is not None and len(result_polygons) > max_polygons:
                result_polygons = result_polygons[:max_polygons]
                log_debug(f"Limited to {max_polygons} largest polygons")
        
        # Count vertices in result
        total_result_vertices = sum(len(list(p.exterior.coords)) for p in result_polygons)
        log_debug(f"Vertex preservation: {total_result_vertices} vertices in polygons vs {total_original_vertices} in original lines")
        
        # Create GeoDataFrame
        result_gdf = gpd.GeoDataFrame(geometry=result_polygons, crs=crs)
        
        log_info(f"polygonize for layer '{layer_name}': Created {len(result_polygons)} polygon(s) from {len(all_lines)} line segments")
        
        return result_gdf
        
    except Exception as e:
        log_error(f"Error creating boundary from lines: {e}")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
