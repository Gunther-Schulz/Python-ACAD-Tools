import os
import sys
from pathlib import Path

from shapely import MultiLineString

# Set Qt platform to xcb before any Qt imports
os.environ['QT_QPA_PLATFORM'] = 'xcb'
# Disable GUI for headless operation
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

# Get conda environment path
conda_prefix = os.environ.get('CONDA_PREFIX')
if conda_prefix:
    # Add QGIS Python paths
    qgis_python_paths = [
        os.path.join(conda_prefix, 'share', 'qgis', 'python'),
        os.path.join(conda_prefix, 'lib', 'python3.10', 'site-packages'),
        os.path.join(conda_prefix, 'share', 'qgis', 'python', 'plugins'),
    ]
    
    # Add paths to sys.path if they exist
    for path in qgis_python_paths:
        if os.path.exists(path) and path not in sys.path:
            sys.path.append(path)
            print(f"Added QGIS path: {path}")
    
    # Set QGIS prefix path
    os.environ['QGIS_PREFIX_PATH'] = conda_prefix
    
    # Set library path
    lib_path = os.path.join(conda_prefix, 'lib')
    if os.path.exists(lib_path):
        current_lib_path = os.environ.get('LD_LIBRARY_PATH', '')
        os.environ['LD_LIBRARY_PATH'] = f"{lib_path}:{current_lib_path}"
        print(f"Added to LD_LIBRARY_PATH: {lib_path}")

# Print debug information
print("\nPython path:")
for p in sys.path:
    print(f"  {p}")

print("\nLibrary path:")
print(os.environ.get('LD_LIBRARY_PATH', 'Not set'))

# Now try to import QGIS modules
try:
    from qgis.core import *
    from qgis.PyQt.QtCore import QVariant
    from qgis.PyQt import QtCore
    print("\nSuccessfully imported QGIS modules")
except ImportError as e:
    print(f"\nError importing QGIS modules: {e}")
    print("Detailed error information:")
    import traceback
    traceback.print_exc()
    raise

# Initialize QGIS Application in headless mode
QgsApplication.setPrefixPath(os.environ['QGIS_PREFIX_PATH'], True)
qgs = QgsApplication([], False)  # False means non-GUI
qgs.initQgis()

# Import and initialize processing
from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing
from qgis.core import (
    QgsField,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsProcessingFeedback
)

# Initialize Processing framework
Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

from shapely.ops import nearest_points
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd
from src.operations.common_operations import _get_filtered_geometry, _process_layer_info, format_operation_warning
from src.utils import log_debug, log_warning
import math
import numpy as np
from src.style_manager import StyleManager
from qgis.core import (
    QgsPalLayerSettings,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsFields,
    QgsPoint,
    QgsApplication,
    QgsTextFormat,
    Qgis,
    QgsVectorLayerSimpleLabeling,
    QgsUnitTypes,
    QgsWkbTypes,
    QgsProperty,
    QgsRenderContext,
    QgsMapToPixel
)

# Log QGIS version for debugging
log_warning(f"QGIS Version: {Qgis.QGIS_VERSION}")

def get_line_placement_positions(line, label_length, text_height=2.5):
    """Get possible label positions along a line with improved corner handling."""
    line_length = line.length
    
    # Calculate step size based on text height
    step = max(text_height, line_length / 20)  # Use text height as minimum step
    
    # Calculate actual space needed for text
    # Typical width-to-height ratio is around 0.6 for most fonts
    # Add some padding (1.2) to ensure text doesn't crowd corners
    text_width = label_length * text_height * 0.6 * 1.2
    
    positions = []
    current_dist = text_width / 2  # Start half text width from the start
    
    while current_dist <= (line_length - text_width / 2):  # Stop half text width from the end
        point = line.interpolate(current_dist)
        
        # Look both ahead and behind to detect corners
        look_dist = max(text_width / 2, step)  # Use half text width as minimum look distance
        behind_dist = max(0, current_dist - look_dist)
        ahead_dist = min(line_length, current_dist + look_dist)
        
        point_behind = line.interpolate(behind_dist)
        point_ahead = line.interpolate(ahead_dist)
        
        # Calculate angles between segments
        angle_diff = 0  # Default to 0 for start/end points
        if behind_dist < current_dist and ahead_dist > current_dist:
            angle1 = math.atan2(point.y - point_behind.y, point.x - point_behind.x)
            angle2 = math.atan2(point_ahead.y - point.y, point_ahead.x - point.x)
            angle_diff = abs(math.degrees(angle2 - angle1))
            
            # Skip corners (where angle difference is significant)
            if angle_diff > 30:  # Adjust this threshold as needed
                current_dist += step
                continue
        
        # Use the ahead point for angle calculation
        angle = math.degrees(math.atan2(
            point_ahead.y - point.y,
            point_ahead.x - point.x
        ))
        
        # Normalize angle to ensure text is never upside down (-90 to 90 degrees)
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        
        # Check if we have enough straight space for the label
        space_ahead = line_length - current_dist
        if space_ahead >= text_width / 2:  # Only need half text width ahead since we're centered
            # Calculate a score for this position
            score = 1.0
            if angle_diff < 10:  # Very straight
                score += 2.0
            elif angle_diff < 20:  # Mostly straight
                score += 1.0
            
            # Prefer middle sections of the line
            relative_pos = current_dist / line_length
            if 0.3 <= relative_pos <= 0.7:
                score += 1.0
                
            positions.append((point, angle, score))
        
        current_dist += step
    
    return positions

def get_polygon_anchor_position(polygon, text_width, text_height):
    """Get the best anchor position for a polygon using Mapbox's approach."""
    # Try multiple candidate positions and score them
    candidates = []
    
    # 1. Try centroid
    centroid = polygon.centroid
    if polygon.contains(centroid):
        score = 1.0
        # Bonus for being far from edges
        min_dist_to_boundary = polygon.boundary.distance(centroid)
        score += min_dist_to_boundary / (text_width * 0.5)  # Scale by text size
        candidates.append((centroid, score))
    
    # 2. Try pole of inaccessibility (point furthest from boundary)
    try:
        from shapely.ops import polylabel
        pole = polylabel(polygon, tolerance=text_height/10)
        if polygon.contains(pole):
            score = 1.5  # Higher base score than centroid
            min_dist_to_boundary = polygon.boundary.distance(pole)
            score += min_dist_to_boundary / (text_width * 0.5)
            candidates.append((pole, score))
    except Exception:
        pass
    
    # 3. Try representative point as fallback
    rep_point = polygon.representative_point()
    if polygon.contains(rep_point):
        score = 0.5  # Lower base score
        min_dist_to_boundary = polygon.boundary.distance(rep_point)
        score += min_dist_to_boundary / (text_width * 0.5)
        candidates.append((rep_point, score))
    
    # 4. Try points along major axis using oriented envelope
    try:
        # Get oriented envelope (minimum rotated rectangle)
        mbr = polygon.minimum_rotated_rectangle  # New Shapely way
        if mbr is None:  # Fallback for older Shapely versions
            mbr = polygon.envelope
            
        coords = list(mbr.exterior.coords)
        
        # Calculate lengths of rectangle sides
        side1 = LineString([coords[0], coords[1]])
        side2 = LineString([coords[1], coords[2]])
        
        # Determine major axis
        if side1.length > side2.length:
            major_axis = [coords[0], coords[1]]
        else:
            major_axis = [coords[1], coords[2]]
        
        # Try points along major axis
        for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
            x = major_axis[0][0] + t * (major_axis[1][0] - major_axis[0][0])
            y = major_axis[0][1] + t * (major_axis[1][1] - major_axis[0][1])
            point = Point(x, y)
            if polygon.contains(point):
                score = 0.8  # Medium base score
                min_dist_to_boundary = polygon.boundary.distance(point)
                score += min_dist_to_boundary / (text_width * 0.5)
                candidates.append((point, score))
    except Exception as e:
        log_debug(f"Error calculating major axis points: {str(e)}")
        pass
    
    if not candidates:
        # Ultimate fallback: use centroid regardless of containment
        return polygon.centroid
    
    # Return the position with highest score
    return max(candidates, key=lambda x: x[1])[0]

def get_point_label_position(point, label_text, text_height, offset=0):
    """Get best label position for a point using Mapbox's approach."""
    # Try multiple positions around the point
    candidates = []
    
    # Calculate text dimensions
    text_width = len(label_text) * text_height * 0.6
    
    # Define possible positions (clockwise from right)
    angles = [0, 45, 90, 135, 180, 225, 270, 315]
    base_offsets = [
        (1, 0),    # Right
        (1, 1),    # Top-right
        (0, 1),    # Top
        (-1, 1),   # Top-left
        (-1, 0),   # Left
        (-1, -1),  # Bottom-left
        (0, -1),   # Bottom
        (1, -1),   # Bottom-right
    ]
    
    # Default offset distance based on text height if not specified
    if offset == 0:
        offset = text_height * 0.5
    
    for angle, (dx, dy) in zip(angles, base_offsets):
        # Calculate position
        x = point.x + dx * offset
        y = point.y + dy * offset
        candidate = Point(x, y)
        
        # Score based on position (prefer right side, then top, etc.)
        score = 1.0
        if dx > 0:  # Right side
            score += 0.5
        if dy > 0:  # Top half
            score += 0.3
            
        candidates.append((candidate, angle, score))
    
    # Return the position with highest score
    best_candidate = max(candidates, key=lambda x: x[2])
    return (best_candidate[0], best_candidate[1])

def check_label_collision(point, existing_labels, buffer_distance=2.0):
    """Check if a label position collides with existing labels using QGIS geometry."""
    new_label_geom = QgsGeometry.fromPointXY(QgsPointXY(point.x, point.y))
    new_label_buffer = new_label_geom.buffer(buffer_distance, 5)
    
    for existing_label in existing_labels:
        if existing_label.intersects(new_label_buffer):
            return True
    return False

def get_best_label_position(geometry, label_text, offset=0, text_height=2.5, existing_labels=None):
    """Find best label position using QGIS labeling engine and collision detection."""
    if existing_labels is None:
        existing_labels = []
    
    if isinstance(geometry, Point):
        if offset == 0:
            return (geometry, label_text, 0)
        return (Point(geometry.x + offset, geometry.y), label_text, 0)
    
    elif isinstance(geometry, LineString):
        # Get all possible positions
        label_length = len(label_text) * text_height * 0.8
        positions = get_line_placement_positions(geometry, label_length, text_height)
        
        # Sort positions by score
        positions.sort(key=lambda x: x[2], reverse=True)
        
        # Try positions until finding one without collision
        for point, angle, score in positions:
            if not check_label_collision(point, existing_labels, text_height):
                return (point, label_text, angle)
        
        # If all positions collide, return the highest scoring position
        if positions:
            return (positions[0][0], label_text, positions[0][1])
        
        # Fallback to midpoint if no positions found
        point = geometry.interpolate(0.5, normalized=True)
        p1 = geometry.interpolate(0.45, normalized=True)
        p2 = geometry.interpolate(0.55, normalized=True)
        angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        return (point, label_text, angle)
    
    elif isinstance(geometry, Polygon):
        # Get candidate positions
        point = get_polygon_anchor_position(geometry, len(label_text) * text_height * 0.6, text_height)
        
        # Check for collisions and try to adjust if needed
        if check_label_collision(point, existing_labels, text_height):
            # Try alternative positions within the polygon
            centroid = geometry.centroid
            alternatives = [
                geometry.representative_point(),
                centroid,
                Point(point.x + text_height, point.y),
                Point(point.x - text_height, point.y),
                Point(point.x, point.y + text_height),
                Point(point.x, point.y - text_height)
            ]
            
            for alt_point in alternatives:
                if geometry.contains(alt_point) and not check_label_collision(alt_point, existing_labels, text_height):
                    point = alt_point
                    break
        
        if offset != 0:
            # Move point away from centroid
            centroid = geometry.centroid
            if not point.equals(centroid):
                dx = point.x - centroid.x
                dy = point.y - centroid.y
                dist = math.sqrt(dx*dx + dy*dy)
                if dist > 0:
                    point = Point(
                        point.x + (dx/dist * offset),
                        point.y + (dy/dist * offset)
                    )
        
        return (point, label_text, 0)
    
    return None

def try_resolve_collision(point, angle, existing_labels, text_height, label_text):
    """Try to resolve label collision by moving the label in the optimal direction."""
    buffer_distance = text_height * len(label_text) * 0.3
    original_geom = QgsGeometry.fromPointXY(QgsPointXY(point.x, point.y))
    
    # First check if there's a collision
    label_buffer = original_geom.buffer(buffer_distance, 5)
    colliding_labels = [label for label in existing_labels if label.intersects(label_buffer)]
    
    if not colliding_labels:
        return point, False
    
    # Calculate the main direction of collision
    collision_vectors = []
    for colliding_label in colliding_labels:
        # Get centroid of colliding label
        centroid = colliding_label.centroid()
        centroid_point = centroid.asPoint()  # Convert to QgsPointXY
        dx = point.x - centroid_point.x()  # Use x() method
        dy = point.y - centroid_point.y()  # Use y() method
        collision_vectors.append((dx, dy))
    
    # Calculate average collision vector
    avg_dx = sum(v[0] for v in collision_vectors) / len(collision_vectors)
    avg_dy = sum(v[1] for v in collision_vectors) / len(collision_vectors)
    
    # Determine if collision is more horizontal or vertical
    is_horizontal = abs(avg_dx) > abs(avg_dy)
    
    # Try different offsets based on the collision direction
    offsets = []
    base_offset = text_height * 1.2  # Base offset distance
    
    if is_horizontal:
        # Try horizontal offsets first, then diagonal
        offsets = [
            (math.copysign(base_offset, avg_dx), 0),  # Horizontal
            (math.copysign(base_offset, avg_dx), base_offset/2),  # Diagonal up
            (math.copysign(base_offset, avg_dx), -base_offset/2),  # Diagonal down
        ]
    else:
        # Try vertical offsets first, then diagonal
        offsets = [
            (0, math.copysign(base_offset, avg_dy)),  # Vertical
            (base_offset/2, math.copysign(base_offset, avg_dy)),  # Diagonal right
            (-base_offset/2, math.copysign(base_offset, avg_dy)),  # Diagonal left
        ]
    
    # Try each offset until finding a non-colliding position
    for offset_x, offset_y in offsets:
        new_point = Point(point.x + offset_x, point.y + offset_y)
        new_geom = QgsGeometry.fromPointXY(QgsPointXY(new_point.x, new_point.y))
        new_buffer = new_geom.buffer(buffer_distance, 5)
        
        if not any(label.intersects(new_buffer) for label in existing_labels):
            return new_point, True
    
    # If no resolution found, try larger offsets as last resort
    last_resort_offset = base_offset * 2
    for dx, dy in [(last_resort_offset, 0), (-last_resort_offset, 0), 
                   (0, last_resort_offset), (0, -last_resort_offset)]:
        new_point = Point(point.x + dx, point.y + dy)
        new_geom = QgsGeometry.fromPointXY(QgsPointXY(new_point.x, new_point.y))
        new_buffer = new_geom.buffer(buffer_distance, 5)
        
        if not any(label.intersects(new_buffer) for label in existing_labels):
            return new_point, True
    
    return point, False

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Creates label points along lines using QGIS PAL labeling system."""
    
    # Get text height from style
    style_manager = StyleManager(project_settings)
    layer_info = next((layer for layer in project_settings.get('geomLayers', []) 
                      if layer.get('name') == layer_name), {})
    style = style_manager.process_layer_style(layer_name, layer_info)
    text_style = style.get('text', {}).copy()
    text_height = text_style.get('height', 2.5)
    
    # Track source layers for statistics
    source_layer_counts = {}
    source_layers = operation.get('sourceLayers', [{'name': layer_name}])
    
    # Track existing label positions for collision detection
    existing_label_geometries = []
    features_list = []
    
    # Process each source layer
    for source_config in source_layers:
        source_layer_name = source_config.get('name')
        if not source_layer_name:
            continue
            
        label_text = source_config.get('label', '')
        spacing = source_config.get('labelSpacing', 100)
        source_layer_counts[source_layer_name] = 0
        
        # Get source geometry
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, None)
        if source_geometry is None or source_geometry.is_empty:
            continue
            
        # Convert to list of LineStrings
        if isinstance(source_geometry, LineString):
            geometries = [source_geometry]
        elif isinstance(source_geometry, MultiLineString):
            geometries = list(source_geometry.geoms)
        else:
            continue
            
        # Process each line
        for line in geometries:
            source_layer_counts[source_layer_name] += 1
            line_length = line.length
            
            # Calculate positions along the line
            current_distance = spacing / 2
            while current_distance < line_length:
                point = line.interpolate(current_distance)
                
                # Calculate angle
                delta = spacing * 0.1
                point_before = line.interpolate(max(0, current_distance - delta))
                point_after = line.interpolate(min(line_length, current_distance + delta))
                
                dx = point_after.x - point_before.x
                dy = point_after.y - point_before.y
                angle = math.degrees(math.atan2(dy, dx))
                
                if angle > 90:
                    angle -= 180
                elif angle < -90:
                    angle += 180
                
                # Check for collisions with existing labels
                collision = False
                label_geom = QgsGeometry.fromPointXY(QgsPointXY(point.x, point.y))
                buffer_distance = text_height * len(label_text) * 0.3
                label_buffer = label_geom.buffer(buffer_distance, 5)
                
                if any(existing_label.intersects(label_buffer) for existing_label in existing_label_geometries):
                    # Try to resolve collision
                    new_point, resolved = try_resolve_collision(
                        point, angle, existing_label_geometries, text_height, label_text
                    )
                    if resolved:
                        point = new_point
                    else:
                        collision = True
                
                if not collision:
                    features_list.append({
                        'geometry': point,
                        'properties': {
                            'label': label_text,
                            'rotation': angle
                        }
                    })
                    new_label_geom = QgsGeometry.fromPointXY(QgsPointXY(point.x, point.y))
                    existing_label_geometries.append(new_label_geom.buffer(buffer_distance, 5))
                
                current_distance += spacing
    
    # Log statistics
    for source_name, count in source_layer_counts.items():
        placed_labels = len([
            f for f in features_list 
            if f['properties']['label'] == next(
                (sl['label'] for sl in source_layers if sl['name'] == source_name), 
                ''
            )
        ])
        
        if placed_labels < count:
            warning_message = (
                f"Only {placed_labels} of {count} possible label positions were used for source layer '{source_name}'. "
                "Check the layer geometry and label spacing settings."
            )
            log_warning(
                format_operation_warning(
                    layer_name,
                    'label_association',
                    warning_message
                )
            )
    
    # Create result GeoDataFrame
    if not features_list:
        return gpd.GeoDataFrame({'geometry': [], 'label': []}, geometry='geometry', crs=crs)
    
    result_gdf = gpd.GeoDataFrame.from_features(features_list, crs=crs)
    result_gdf.attrs['text_style'] = text_style
    
    return result_gdf

def calculate_label_box(point, width, height, angle):
    """Calculate a rotated rectangle representing label bounds."""
    from shapely.affinity import rotate, translate
    
    # Create basic rectangle
    dx = width / 2
    dy = height / 2
    box = Polygon([
        (-dx, -dy), (dx, -dy),
        (dx, dy), (-dx, dy),
        (-dx, -dy)
    ])
    
    # Rotate and translate to position
    box = rotate(box, angle, origin=(0, 0))
    box = translate(box, point.x, point.y)
    
    # Add padding (Mapbox uses 2px)
    box = box.buffer(height * 0.1)  # 10% of text height as padding
    
    return box