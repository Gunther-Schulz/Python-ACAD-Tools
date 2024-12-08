from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.utils import log_debug, log_warning
import math

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
    result_gdf['label_position'] = None
    result_gdf['label_rotation'] = None
    
    # Process each label point
    for idx, label_row in label_layer.iterrows():
        if label_column not in label_row:
            continue
            
        label_point = label_row.geometry
        label_text = str(label_row[label_column])
        
        # Find closest geometry
        distances = geometry_layer.geometry.distance(label_point)
        closest_idx = distances.idxmin()
        closest_geom = geometry_layer.loc[closest_idx].geometry
        
        # Calculate label position and rotation based on geometry type
        position, rotation = calculate_label_position(closest_geom, label_point)
        
        # Store the association
        result_gdf.at[closest_idx, 'associated_label'] = label_text
        result_gdf.at[closest_idx, 'label_position'] = position
        result_gdf.at[closest_idx, 'label_rotation'] = rotation
    
    log_debug(f"Created {len(result_gdf)} label associations")
    return result_gdf

def calculate_label_position(geometry, label_point):
    """Calculate optimal position and rotation for label based on geometry type."""
    
    if isinstance(geometry, (Polygon, MultiPolygon)):
        # For polygons, use centroid
        position = geometry.centroid
        rotation = 0
        
    elif isinstance(geometry, LineString):
        # For lines, find closest point on line and calculate rotation
        distance_along = geometry.project(label_point)
        position = geometry.interpolate(distance_along)
        
        # Calculate rotation angle based on line direction at that point
        if distance_along < geometry.length - 0.1:
            next_point = geometry.interpolate(distance_along + 0.1)
            dx = next_point.x - position.x
            dy = next_point.y - position.y
            rotation = math.degrees(math.atan2(dy, dx))
        else:
            rotation = 0
            
    elif isinstance(geometry, Point):
        # For points, offset the label slightly to the right
        position = Point(geometry.x + 0.5, geometry.y)
        rotation = 0
        
    else:
        position = label_point
        rotation = 0
    
    return position, rotation 