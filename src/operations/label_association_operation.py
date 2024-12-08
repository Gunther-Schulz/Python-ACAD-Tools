from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.utils import log_debug, log_warning
import math
import numpy as np

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
    
    # Process each label point
    for idx, label_row in label_layer.iterrows():
        if label_column not in label_row:
            continue
            
        label_point = label_row.geometry
        if not isinstance(label_point, Point):
            log_warning(f"Skipping non-point geometry in label layer at index {idx}")
            continue
            
        label_text = str(label_row[label_column])
        
        # Find closest geometry
        try:
            distances = geometry_layer.geometry.distance(label_point)
            if distances.isna().all():
                log_warning(f"No valid distances found for label point at index {idx}")
                continue
                
            closest_idx = distances.idxmin()
            closest_geom = geometry_layer.loc[closest_idx].geometry
            
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
            # First try using nearest points
            p1, p2 = nearest_points(geometry, label_point)
            position = Point(p1.x, p1.y)
            
            # Calculate rotation based on line direction at nearest point
            distance_along = geometry.project(position)
            if distance_along < geometry.length - 0.1:
                next_point = geometry.interpolate(min(distance_along + 0.1, geometry.length))
                dx = next_point.x - position.x
                dy = next_point.y - position.y
                # Use arctan2 and handle potential division by zero
                if abs(dx) > 1e-10 or abs(dy) > 1e-10:
                    rotation = math.degrees(math.atan2(dy, dx))
                else:
                    rotation = 0
            else:
                rotation = 0
                
        except (ValueError, TypeError, Exception) as e:
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