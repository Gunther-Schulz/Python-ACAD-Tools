from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np
from shapely.prepared import prep

def safe_distance(geom1, geom2):
    """Calculate distance between geometries with error handling."""
    try:
        if not (geom1.is_valid and geom2.is_valid):
            return float('inf')
        if geom1.is_empty or geom2.is_empty:
            return float('inf')
        dist = geom1.distance(geom2)
        return dist if not np.isnan(dist) else float('inf')
    except Exception:
        return float('inf')

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Associates labels from a point layer with geometries from another layer."""
    log_debug(f"Creating label association layer: {layer_name}")
    log_debug(f"Operation details: {operation}")
    
    # Get source layers
    source_layers = operation.get('layers', [layer_name])
    label_layer_name = operation.get('labelLayer')
    label_column = operation.get('labelColumn', 'label')
    
    if not label_layer_name:
        log_warning(format_operation_warning(
            layer_name,
            "labelAssociation",
            "Missing required labelLayer parameter"
        ))
        return None
    
    combined_geometry = None
    
    # Process source layers
    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None or source_layer_name not in all_layers:
            log_warning(format_operation_warning(
                layer_name,
                "labelAssociation",
                f"Source layer '{source_layer_name}' not found"
            ))
            continue

        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        
        if source_geometry is None:
            log_warning(format_operation_warning(
                layer_name,
                "labelAssociation",
                f"Failed to get filtered geometry for layer '{source_layer_name}'"
            ))
            continue

        if combined_geometry is None:
            combined_geometry = source_geometry
        else:
            try:
                combined_geometry = combined_geometry.union(source_geometry)
            except Exception as e:
                log_warning(format_operation_warning(
                    layer_name,
                    "labelAssociation",
                    f"Error combining geometries: {str(e)}"
                ))
                continue
    
    if combined_geometry is None:
        log_warning(format_operation_warning(
            layer_name,
            "labelAssociation",
            "No valid source geometry found"
        ))
        return None
    
    # Get label layer
    label_layer = all_layers.get(label_layer_name)
    if label_layer is None:
        log_warning(format_operation_warning(
            layer_name,
            "labelAssociation",
            f"Label layer '{label_layer_name}' not found"
        ))
        return None
    
    # Create result GeoDataFrame with the combined geometry
    result_gdf = gpd.GeoDataFrame(geometry=[combined_geometry] if isinstance(combined_geometry, (Point, LineString, Polygon))
                                 else list(combined_geometry.geoms), crs=crs)
    
    result_gdf['associated_label'] = None
    result_gdf['label_position_x'] = None
    result_gdf['label_position_y'] = None
    result_gdf['label_rotation'] = None
    
    # Process each label point
    for idx, label_row in label_layer.iterrows():
        if label_column not in label_row:
            continue
            
        label_point = label_row.geometry
        if not isinstance(label_point, Point) or not label_point.is_valid or label_point.is_empty:
            continue
            
        label_text = str(label_row[label_column])
        
        try:
            # Find closest geometry
            min_dist = float('inf')
            closest_idx = None
            
            for i, geom_row in result_gdf.iterrows():
                dist = safe_distance(geom_row.geometry, label_point)
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i
            
            if closest_idx is None:
                continue
            
            # Calculate label position and rotation
            position, rotation = calculate_label_position(
                result_gdf.loc[closest_idx].geometry,
                label_point
            )
            
            # Store the association
            result_gdf.at[closest_idx, 'associated_label'] = label_text
            result_gdf.at[closest_idx, 'label_position_x'] = position.x
            result_gdf.at[closest_idx, 'label_position_y'] = position.y
            result_gdf.at[closest_idx, 'label_rotation'] = rotation
            
        except Exception as e:
            log_warning(format_operation_warning(
                layer_name,
                "labelAssociation",
                f"Error processing label at index {idx}: {str(e)}"
            ))
            continue
    
    log_debug(f"Created label association layer: {layer_name} with {len(result_gdf)} geometries")
    return result_gdf

def calculate_label_position(geometry, label_point):
    """Calculate optimal position and rotation for label based on geometry type."""
    
    if isinstance(geometry, (Polygon, MultiPolygon)):
        # For polygons, use centroid
        try:
            position = geometry.centroid
            if not position.is_valid:
                position = label_point
            rotation = 0
        except Exception:
            position = label_point
            rotation = 0
        
    elif isinstance(geometry, LineString):
        # For lines, find closest point on line and calculate rotation
        try:
            # Get line coordinates
            coords = list(geometry.coords)
            if len(coords) < 2:
                position = label_point
                rotation = 0
                return position, rotation

            # Find closest point on line using coordinate-based approach
            min_dist = float('inf')
            closest_point = None
            segment_start_idx = 0
            
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                
                # Calculate projection point on line segment
                line_vec = (p2[0] - p1[0], p2[1] - p1[1])
                point_vec = (label_point.x - p1[0], label_point.y - p1[1])
                line_len = line_vec[0]**2 + line_vec[1]**2
                
                if line_len == 0:
                    continue
                    
                t = max(0, min(1, (point_vec[0]*line_vec[0] + point_vec[1]*line_vec[1]) / line_len))
                proj_x = p1[0] + t * line_vec[0]
                proj_y = p1[1] + t * line_vec[1]
                
                # Calculate distance to projection point
                dist = ((label_point.x - proj_x)**2 + (label_point.y - proj_y)**2)**0.5
                
                if dist < min_dist:
                    min_dist = dist
                    closest_point = (proj_x, proj_y)
                    segment_start_idx = i

            if closest_point is None:
                position = label_point
                rotation = 0
                return position, rotation

            # Create point from closest position
            position = Point(closest_point)

            # Calculate rotation based on segment direction
            start = coords[segment_start_idx]
            end = coords[segment_start_idx + 1]
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            
            # Use arctan2 and handle potential division by zero
            if abs(dx) > 1e-10 or abs(dy) > 1e-10:
                rotation = math.degrees(math.atan2(dy, dx))
            else:
                rotation = 0
                
        except Exception as e:
            log_warning(f"Error calculating line label position: {str(e)}")
            position = label_point
            rotation = 0
            
    elif isinstance(geometry, Point):
        # For points, offset the label slightly to the right
        try:
            position = Point(geometry.x + 0.5, geometry.y)
            rotation = 0
        except Exception:
            position = label_point
            rotation = 0
        
    else:
        position = label_point
        rotation = 0
    
    # Final validation
    if not isinstance(position, Point) or not position.is_valid:
        position = label_point
        rotation = 0
        
    return position, rotation