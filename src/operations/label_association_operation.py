from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
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

def create_label_association_layer(all_layers, project_settings, crs, operation_config):
    """Associates labels from a point layer with geometries from another layer."""
    
    # Get required parameters
    geometry_layer_name = operation_config.get('geometryLayer')
    label_layer_name = operation_config.get('labelLayer')
    label_column = operation_config.get('labelColumn', 'label')
    
    if not geometry_layer_name or not label_layer_name:
        log_warning("Missing required parameters for label association operation")
        return None
    
    # Get the input layers
    geometry_layer = all_layers.get(geometry_layer_name)
    label_layer = all_layers.get(label_layer_name)
    
    if geometry_layer is None or label_layer is None:
        log_warning(f"Could not find input layers: {geometry_layer_name} or {label_layer_name}")
        return None
    
    log_debug(f"Processing label association between {geometry_layer_name} and {label_layer_name}")
    
    # Create result GeoDataFrame
    result_gdf = geometry_layer.copy()
    result_gdf['associated_label'] = None
    result_gdf['label_position_x'] = None
    result_gdf['label_position_y'] = None
    result_gdf['label_rotation'] = None
    
    # Filter and prepare valid geometries
    valid_mask = geometry_layer.geometry.is_valid & ~geometry_layer.geometry.isna() & ~geometry_layer.geometry.is_empty
    valid_geoms = geometry_layer[valid_mask].copy()
    
    if len(valid_geoms) < len(geometry_layer):
        log_warning(f"Filtered out {len(geometry_layer) - len(valid_geoms)} invalid geometries")
    
    if len(valid_geoms) == 0:
        log_warning("No valid geometries to process")
        return result_gdf
    
    # Create spatial index for valid geometries
    valid_geoms_prep = [prep(geom) for geom in valid_geoms.geometry]
    
    # Process each label point
    for idx, label_row in label_layer.iterrows():
        if label_column not in label_row:
            continue
            
        label_point = label_row.geometry
        if not isinstance(label_point, Point) or not label_point.is_valid or label_point.is_empty:
            log_warning(f"Skipping invalid point geometry in label layer at index {idx}")
            continue
            
        label_text = str(label_row[label_column])
        
        try:
            # Find closest geometry using prepared geometries
            min_dist = float('inf')
            closest_idx = None
            
            for i, (geom_idx, geom_row) in enumerate(valid_geoms.iterrows()):
                if valid_geoms_prep[i].contains(label_point):
                    min_dist = 0
                    closest_idx = geom_idx
                    break
                    
                dist = safe_distance(geom_row.geometry, label_point)
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = geom_idx
            
            if closest_idx is None or min_dist == float('inf'):
                log_warning(f"No valid geometry found for label point at index {idx}")
                continue
            
            closest_geom = valid_geoms.loc[closest_idx].geometry
            
            # Calculate label position and rotation based on geometry type
            position, rotation = calculate_label_position(closest_geom, label_point)
            
            # Store the association with coordinates
            result_gdf.at[closest_idx, 'associated_label'] = label_text
            result_gdf.at[closest_idx, 'label_position_x'] = position.x
            result_gdf.at[closest_idx, 'label_position_y'] = position.y
            result_gdf.at[closest_idx, 'label_rotation'] = rotation
            
        except Exception as e:
            log_warning(f"Error processing label at index {idx}: {str(e)}")
            continue
    
    log_debug(f"Created {len(result_gdf[result_gdf['associated_label'].notna()])} label associations")
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