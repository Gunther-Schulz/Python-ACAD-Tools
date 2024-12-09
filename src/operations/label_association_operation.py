import os
import sys
from pathlib import Path

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
    QgsLabelingEngineSettings,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsPoint,
    QgsGeometry,
    QgsFeature,
    QgsApplication
)
from PyQt5.QtGui import QColor
import processing

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

def get_best_label_position(geometry, label_text, offset=0, text_height=2.5):
    """Find best label position using improved corner handling."""
    if isinstance(geometry, Point):
        if offset == 0:
            return (geometry, label_text, 0)
        return (Point(geometry.x + offset, geometry.y), label_text, 0)
    
    elif isinstance(geometry, LineString):
        # Adjust label length based on text height and character count
        # This is an approximation - adjust multiplier as needed for your font
        label_length = len(label_text) * text_height * 0.8  # 0.8 is character width to height ratio
        positions = get_line_placement_positions(geometry, label_length)
        
        if not positions:
            # Fallback to midpoint if no good positions found
            point = geometry.interpolate(0.5, normalized=True)
            p1 = geometry.interpolate(0.45, normalized=True)
            p2 = geometry.interpolate(0.55, normalized=True)
            angle = math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))
        else:
            # Use the position with the highest score
            point, angle, _ = max(positions, key=lambda x: x[2])
        
        # Apply offset perpendicular to line direction
        if offset != 0:
            rad_angle = math.radians(angle)
            dx = -math.sin(rad_angle) * offset
            dy = math.cos(rad_angle) * offset
            point = Point(point.x + dx, point.y + dy)
        
        # Adjust angle for readability
        if abs(angle) > 90:
            angle += 180
        if angle > 180:
            angle -= 360
            
        return (point, label_text, angle)
    
    elif isinstance(geometry, Polygon):
        point = get_polygon_anchor_position(geometry)
        
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

def create_label_association_layer(all_layers, project_settings, crs, layer_name, operation):
    """Associates labels from a point layer with geometries from another layer using QGIS PAL."""
    
    # Get style information
    style_manager = StyleManager(project_settings)
    layer_info = next((layer for layer in project_settings.get('geomLayers', []) 
                      if layer.get('name') == layer_name), {})
    style = style_manager.process_layer_style(layer_name, layer_info)
    text_style = style.get('text', {}).copy()
    text_height = text_style.get('height', 2.5)
    
    # Create temporary vector layer for labels
    memory_layer = QgsVectorLayer("Point?crs=" + crs, "temp_labels", "memory")
    provider = memory_layer.dataProvider()
    
    # Add fields using the new recommended way
    fields = QgsFields()
    field = QgsField()
    field.setName("label")
    field.setType(QVariant.String)
    fields.append(field)
    provider.addAttributes(fields)
    memory_layer.updateFields()
    
    # Process source layers and add features
    source_layers = operation.get('sourceLayers', [{'name': layer_name}])
    features_list = []  # List to store features for GeoDataFrame
    
    for source_config in source_layers:
        source_layer_name = source_config.get('name')
        if not source_layer_name:
            continue
            
        # Get source geometry and labels
        source_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, None)
        if source_geometry is None:
            continue
            
        # Convert geometries to QGIS features
        if isinstance(source_geometry, (Point, LineString, Polygon)):
            geometries = [source_geometry]
        else:
            geometries = list(source_geometry.geoms)
            
        for geometry in geometries:
            # Add to QGIS layer
            feature = QgsFeature()
            qgs_geom = QgsGeometry.fromWkt(geometry.wkt)
            feature.setGeometry(qgs_geom)
            
            # Get label text
            label_text = source_config.get('label', '')
            feature.setAttributes([label_text])
            provider.addFeature(feature)
            
            # Add to features list for GeoDataFrame
            features_list.append({
                'geometry': geometry,
                'properties': {'label': label_text}
            })
    
    # Configure labeling settings
    label_settings = QgsPalLayerSettings()
    text_format = QgsTextFormat()
    
    # Apply text styling
    text_format.setSize(text_height)
    text_format.setColor(QColor(text_style.get('color', '#000000')))
    
    # Configure label settings
    label_settings.setFormat(text_format)
    label_settings.fieldName = "label"
    label_settings.placement = QgsPalLayerSettings.AroundPoint
    label_settings.priority = 5
    label_settings.enabled = True
    
    # Apply settings to layer
    labeling = QgsVectorLayerSimpleLabeling(label_settings)
    memory_layer.setLabeling(labeling)
    memory_layer.setLabelsEnabled(True)
    
    # Create GeoDataFrame directly from features list
    if not features_list:
        # Return empty GeoDataFrame with correct structure
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