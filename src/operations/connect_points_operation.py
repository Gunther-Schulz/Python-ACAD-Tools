import geopandas as gpd
from shapely.geometry import Point, LineString, MultiPoint
from src.utils import log_info, log_warning, log_error, log_debug
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, format_operation_warning
import numpy as np
from scipy.spatial.distance import cdist

def create_connect_points_layer(all_layers, project_settings, crs, layer_name, operation):
    log_debug(f"Creating connect points layer: {layer_name}")

    source_layers = operation.get('layers', [])
    if not source_layers:
        source_layers = [layer_name]  # Use the current layer if no source specified

    # Get the maximum distance for grouping (optional)
    max_group_distance = operation.get('maxDistance')

    all_points = []

    for layer_info in source_layers:
        source_layer_name, values, column_name = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            continue

        source_gdf = all_layers[source_layer_name]

        for idx, row in source_gdf.iterrows():
            geom = row.geometry
            if isinstance(geom, Point):
                all_points.append((geom.x, geom.y))
            elif isinstance(geom, MultiPoint):
                all_points.extend([(p.x, p.y) for p in geom.geoms])

    if not all_points:
        log_warning(format_operation_warning(
            layer_name,
            "connect-points",
            "No points found to connect"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None

    if len(all_points) == 1:
        log_warning(format_operation_warning(
            layer_name,
            "connect-points",
            "Only one point found - cannot create connecting line"
        ))
        all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
        return None

    # Convert points to numpy array for efficient distance calculation
    points_array = np.array(all_points)

    if max_group_distance is not None:
        # Group points based on maximum distance
        groups = []
        remaining_indices = set(range(len(points_array)))

        while remaining_indices:
            # Start a new group with the first remaining point
            current_group = [remaining_indices.pop()]
            current_group_changed = True

            # Keep adding points to the current group while possible
            while current_group_changed:
                current_group_changed = False
                current_points = points_array[current_group]

                # Check each remaining point
                indices_to_remove = set()
                for idx in remaining_indices:
                    point = points_array[idx].reshape(1, -1)
                    # Calculate distances to all points in current group
                    distances = cdist(point, current_points)
                    if np.min(distances) <= max_group_distance:
                        current_group.append(idx)
                        indices_to_remove.add(idx)
                        current_group_changed = True

                # Remove added points from remaining indices
                remaining_indices -= indices_to_remove

            groups.append(current_group)

        # Create a line for each group
        lines = []
        for group in groups:
            if len(group) > 1:
                # Sort points within group by nearest neighbor
                group_points = points_array[group]
                path = [0]
                remaining_points = list(range(1, len(group_points)))

                while remaining_points:
                    current = path[-1]
                    current_point = group_points[current].reshape(1, -1)
                    remaining_points_array = group_points[remaining_points]

                    distances = cdist(current_point, remaining_points_array)[0]
                    nearest_idx = np.argmin(distances)
                    next_point_idx = remaining_points[nearest_idx]

                    path.append(next_point_idx)
                    remaining_points.remove(next_point_idx)

                connected_points = [group_points[i] for i in path]
                lines.append(LineString(connected_points))
            elif len(group) == 1:
                log_debug(f"Group with single point found - skipping line creation")

        if not lines:
            log_warning(format_operation_warning(
                layer_name,
                "connect-points",
                "No lines created after grouping"
            ))
            all_layers[layer_name] = gpd.GeoDataFrame(geometry=[], crs=crs)
            return None

        # Create GeoDataFrame with multiple lines
        result_gdf = gpd.GeoDataFrame(geometry=lines, crs=crs)
        all_layers[layer_name] = result_gdf

        log_debug(f"Created connect points layer: {layer_name} with {len(lines)} separate lines")
        return result_gdf

    else:
        # Original behavior when no maxDistance is specified
        remaining_points = list(range(1, len(points_array)))
        path = [0]

        while remaining_points:
            current = path[-1]
            current_point = points_array[current].reshape(1, -1)
            remaining_points_array = points_array[remaining_points]

            distances = cdist(current_point, remaining_points_array)[0]
            nearest_idx = np.argmin(distances)
            next_point_idx = remaining_points[nearest_idx]

            path.append(next_point_idx)
            remaining_points.remove(next_point_idx)

        connected_points = [points_array[i] for i in path]
        line = LineString(connected_points)

        result_gdf = gpd.GeoDataFrame(geometry=[line], crs=crs)
        all_layers[layer_name] = result_gdf

        log_debug(f"Created connect points layer: {layer_name} connecting {len(all_points)} points")
        return result_gdf
