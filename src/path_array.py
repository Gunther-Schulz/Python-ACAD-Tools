import random
import ezdxf
from ezdxf import enums
from ezdxf import colors
from ezdxf.lldxf.const import (
    MTEXT_TOP_LEFT, MTEXT_TOP_CENTER, MTEXT_TOP_RIGHT,
    MTEXT_MIDDLE_LEFT, MTEXT_MIDDLE_CENTER, MTEXT_MIDDLE_RIGHT,
    MTEXT_BOTTOM_LEFT, MTEXT_BOTTOM_CENTER, MTEXT_BOTTOM_RIGHT,
    MTEXT_LEFT_TO_RIGHT, MTEXT_TOP_TO_BOTTOM, MTEXT_BY_STYLE,
    MTEXT_AT_LEAST, MTEXT_EXACT
)
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec3
from src.dfx_utils import SCRIPT_IDENTIFIER, add_block_reference, attach_custom_data
from src.utils import log_info, log_warning, log_error
import re
import math
from ezdxf.math import Vec2, area
from ezdxf.math import intersection_line_line_2d
import os
from ezdxf.lldxf.const import DXFValueError
from shapely.geometry import Polygon, Point, LineString
from shapely import MultiLineString, affinity, unary_union
import matplotlib.pyplot as plt
from descartes import PolygonPatch
import numpy as np
import logging
import sys
import matplotlib.patches as patches
from ezdxf.math import intersection_line_line_2d
# Set up file handler
file_handler = logging.FileHandler('path_array_debug.log', mode='w')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Set up console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_formatter = logging.Formatter('%(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Configure root logger
logging.root.setLevel(logging.DEBUG)
logging.root.addHandler(file_handler)
logging.root.addHandler(console_handler)

# Get logger for this module
logger = logging.getLogger(__name__)

def calculate_overlap_ratio(block_shape, polyline_geom):
    logger.debug(f"Block shape: {block_shape}")
    logger.debug(f"Polyline: {polyline_geom}")

    # Create a buffer around the polyline
    buffer_distance = 0.1
    polyline_buffer = polyline_geom.buffer(buffer_distance)
    logger.debug(f"Polyline buffer: {polyline_buffer}")

    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polyline_buffer).area
    outside_area = block_shape.difference(polyline_buffer).area

    logger.debug(f"Block area: {block_area}")
    logger.debug(f"Intersection area: {intersection_area}")
    logger.debug(f"Outside area: {outside_area}")

    if block_area == 0:
        logger.warning("Block area is zero!")
        return 100.0

    outside_percentage = (outside_area / block_area) * 100
    logger.debug(f"Calculated outside percentage: {outside_percentage}")

    return round(outside_percentage, 1)

def calculate_inside_percentage(block_shape, polygon_geom):
    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polygon_geom).area
    
    if block_area == 0:
        logger.warning("Block area is zero!")
        return 0.0  # Assume fully outside if block has no area
    
    inside_percentage = (intersection_area / block_area) * 100
    
    logger.debug(f"Block area: {block_area}, Intersection area: {intersection_area}")
    logger.debug(f"Inside percentage: {inside_percentage}")
    
    return round(inside_percentage, 1)

def is_block_inside_buffer(block_shape, buffer_polygon):
    # Check if all corners of the block are inside the buffer
    return all(Point(coord).within(buffer_polygon) for coord in block_shape.exterior.coords)

def create_path_array(msp, source_layer_name, target_layer_name, block_name, spacing, buffer_distance, scale=1.0, rotation=0.0, debug_visual=False):
    if block_name not in msp.doc.blocks:
        log_warning(f"Block '{block_name}' not found in the document")
        return

    block = msp.doc.blocks[block_name]
    block_shape, block_base_point = get_block_shape_and_base(block, scale)
    
    if block_shape is None:
        log_warning(f"Could not determine shape for block '{block_name}'")
        return

    polylines = msp.query(f'LWPOLYLINE[layer=="{source_layer_name}"]')
    
    fig, ax = plt.subplots(figsize=(12, 8)) if debug_visual else (None, None)

    for polyline in polylines:
        points = [Vec2(p[0], p[1]) for p in polyline.get_points()]
        polyline_geom = LineString([(p.x, p.y) for p in points])
        total_length = polyline_geom.length
        
        # Create a polygon from the polyline
        polyline_polygon = Polygon(polyline_geom)
        
        # Create buffer around the polyline
        buffer_polygon = polyline_geom.buffer(buffer_distance)
        
        # Combine the original polygon and the buffer
        combined_area = polyline_polygon.union(buffer_polygon)
        
        if debug_visual:
            # Plot the combined area
            x, y = combined_area.exterior.xy
            ax.fill(x, y, alpha=0.2, fc='gray', ec='none')
            ax.plot(x, y, color='blue', linewidth=2, linestyle='--', label='Combined Area Boundary')

        block_distance = spacing / 2

        while block_distance < total_length:
            point = polyline_geom.interpolate(block_distance)
            insertion_point = Vec2(point.x, point.y)
            angle = get_angle_at_point(polyline_geom, block_distance / total_length)

            rotated_block_shape = rotate_and_adjust_block(block_shape, block_base_point, insertion_point, angle)
            
            is_inside = is_block_inside_buffer(rotated_block_shape, combined_area)

            if is_inside:
                color = 'green'
                label = "Placed"
                block_ref = add_block_reference(
                    msp,
                    block_name,
                    insertion_point,
                    target_layer_name,
                    scale=scale,
                    rotation=math.degrees(angle) + rotation
                )
                if block_ref:
                    attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
            else:
                color = 'red'
                label = "Skipped"
            
            if debug_visual:
                # Plot block
                block_patch = patches.Polygon(rotated_block_shape.exterior.coords, facecolor=color, edgecolor='black', alpha=0.7)
                ax.add_patch(block_patch)
                
                ax.text(insertion_point.x, insertion_point.y, label, 
                        ha='center', va='center', fontsize=8, 
                        bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))
            
            block_distance += spacing

    if debug_visual:
        ax.set_aspect('equal', 'datalim')
        ax.set_title(f"Block Placement for {block_name}")
        ax.set_xlabel("X Coordinate")
        ax.set_ylabel("Y Coordinate")
        ax.legend()
        plt.tight_layout()
        plt.show()

    log_info(f"Path array creation completed for source layer '{source_layer_name}' using block '{block_name}'")

def get_block_shape_and_base(block, scale):
    shapes = []
    base_point = Vec2(block.base_point[0] * scale, block.base_point[1] * scale)
    
    for entity in block:
        if entity.dxftype() == "LWPOLYLINE":
            points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
            shapes.append(Polygon(points))
        elif entity.dxftype() == "LINE":
            start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
            end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
            shapes.append(LineString([start, end]))
    
    if not shapes:
        logger.warning(f"No shapes found in block {block.name}")
        return None, None
    
    combined_shape = unary_union(shapes)
    logger.debug(f"Combined block shape: {combined_shape}")
    return combined_shape, base_point

def rotate_and_adjust_block(block_shape, base_point, insertion_point, angle):
    # Translate the block shape so that its base point is at the origin
    translated_shape = affinity.translate(block_shape, 
                                          xoff=-base_point.x, 
                                          yoff=-base_point.y)
    
    # Rotate the translated shape around the origin
    rotated_shape = affinity.rotate(translated_shape, 
                                    angle=math.degrees(angle), 
                                    origin=(0, 0))
    
    # Translate the rotated shape to the insertion point
    final_shape = affinity.translate(rotated_shape, 
                                     xoff=insertion_point.x, 
                                     yoff=insertion_point.y)
    
    return final_shape

def plot_polygon(ax, polygon, color, alpha):
    if polygon.geom_type == 'Polygon':
        x, y = polygon.exterior.xy
        ax.fill(x, y, alpha=alpha, fc=color, ec='black')
    elif polygon.geom_type == 'MultiPolygon':
        for geom in polygon.geoms:
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=alpha, fc=color, ec='black')

def get_angle_at_point(linestring, param):
    # Get the angle of the tangent at the given parameter
    point = linestring.interpolate(param, normalized=True)
    if param == 0:
        next_point = linestring.interpolate(0.01, normalized=True)
        return math.atan2(next_point.y - point.y, next_point.x - point.x)
    elif param == 1:
        prev_point = linestring.interpolate(0.99, normalized=True)
        return math.atan2(point.y - prev_point.y, point.x - prev_point.x)
    else:
        prev_point = linestring.interpolate(param - 0.01, normalized=True)
        next_point = linestring.interpolate(param + 0.01, normalized=True)
        return math.atan2(next_point.y - prev_point.y, next_point.x - prev_point.x)

def rotate_shape(shape, center, angle):
    # First, rotate the shape around its center
    rotated = affinity.rotate(shape, math.degrees(angle), origin='center')
    
    # Then, translate the rotated shape to the desired center
    translated = affinity.translate(rotated, xoff=center.x, yoff=center.y)
    
    return translated

def get_block_shape(block, scale):
    shapes = []
    for entity in block:
        if entity.dxftype() == "LWPOLYLINE":
            points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
            shapes.append(Polygon(points))
        elif entity.dxftype() == "LINE":
            start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
            end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
            shapes.append(LineString([start, end]))
    
    if not shapes:
        log_warning(f"No suitable entities found in block '{block.name}'")
        return None
    
    # Combine all shapes into a single shape
    combined_shape = unary_union(shapes)
    
    # If the result is a MultiLineString, convert it to a Polygon
    if isinstance(combined_shape, MultiLineString):
        combined_shape = combined_shape.buffer(0.01)  # Small buffer to create a polygon
    
    # Check if we can determine a bounding box
    if combined_shape.is_empty:
        log_warning(f"Could not determine bounding box for block '{block.name}'")
        return None
    
    # Log the bounding box size
    minx, miny, maxx, maxy = combined_shape.bounds
    width = maxx - minx
    height = maxy - miny
    print(f"Block '{block.name}' bounding box size: width={width}, height={height}")
    log_info(f"Block '{block.name}' bounding box size: width={width}, height={height}")
    
    return combined_shape

def is_shape_sufficiently_inside(shape, polyline_polygon, overlap_margin):
    if shape is None:
        log_warning("Block shape is None")
        return False

    intersection_area = shape.intersection(polyline_polygon).area
    shape_area = shape.area
    
    if shape_area == 0:
        log_warning("Shape area is zero")
        return False
    
    overlap_ratio = intersection_area / shape_area
    required_overlap = 1 - overlap_margin
    log_info(f"Overlap ratio: {overlap_ratio}, Required: {required_overlap}")
    
    return overlap_ratio >= required_overlap

def is_point_inside_polyline(point, polyline_points):
    n = len(polyline_points)
    inside = False
    p1x, p1y = polyline_points[0]
    for i in range(n + 1):
        p2x, p2y = polyline_points[i % n]
        if point.y > min(p1y, p2y):
            if point.y <= max(p1y, p2y):
                if point.x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (point.y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or point.x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def does_line_intersect_polyline(start, end, polyline_points):
    for i in range(len(polyline_points)):
        p1 = polyline_points[i]
        p2 = polyline_points[(i + 1) % len(polyline_points)]
        if do_lines_intersect(start, end, p1, p2):
            return True
    return False

def do_lines_intersect(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x)
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

def clip_polygon(subject_polygon, clip_polygon):
    
    def inside(p, cp1, cp2):
        return (cp2.x - cp1.x) * (p.y - cp1.y) > (cp2.y - cp1.y) * (p.x - cp1.x)
    
    output_list = subject_polygon
    cp1 = clip_polygon[-1]
    
    for clip_vertex in clip_polygon:
        cp2 = clip_vertex
        input_list = output_list
        output_list = []
        if not input_list:
            break
        s = input_list[-1]
        for subject_vertex in input_list:
            e = subject_vertex
            if inside(e, cp1, cp2):
                if not inside(s, cp1, cp2):
                    intersection = intersection_line_line_2d((cp1, cp2), (s, e))
                    if intersection:
                        output_list.append(intersection)
                output_list.append(e)
            elif inside(s, cp1, cp2):
                intersection = intersection_line_line_2d((cp1, cp2), (s, e))
                if intersection:
                    output_list.append(intersection)
            s = e
        cp1 = cp2
    
    return output_list

def calculate_polygon_area(points):
    if len(points) < 3:
        return 0.0
    n = len(points)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i].x * points[j].y
        area -= points[j].x * points[i].y
    area = abs(area) / 2.0
    return area

def get_block_dimensions(block):
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
    
    for entity in block.entity_space:
        if entity.dxftype() == "LWPOLYLINE":
            for point in entity.get_points():
                x, y = point[:2]
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    
    if min_x == float('inf') or min_y == float('inf') or max_x == float('-inf') or max_y == float('-inf'):
        log_warning(f"No LWPOLYLINE entities found in block '{block.name}'. Using default dimensions.")
        return 1, 1  # Default dimensions if no LWPOLYLINE is found
    
    width = max_x - min_x
    height = max_y - min_y
    return width, height

def get_block_corners(center, width, height, angle):
    half_width = width / 2
    half_height = height / 2
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    
    corners = [
        Vec2(center.x + (half_width * cos_angle - half_height * sin_angle),
             center.y + (half_width * sin_angle + half_height * cos_angle)),
        Vec2(center.x + (half_width * cos_angle + half_height * sin_angle),
             center.y + (half_width * sin_angle - half_height * cos_angle)),
        Vec2(center.x + (-half_width * cos_angle + half_height * sin_angle),
             center.y + (-half_width * sin_angle - half_height * cos_angle)),
        Vec2(center.x + (-half_width * cos_angle - half_height * sin_angle),
             center.y + (-half_width * sin_angle + half_height * cos_angle))
    ]
    return corners

def is_point_inside_or_near_polyline(point, polyline_points, margin):
    if is_point_inside_polyline(point, polyline_points):
        return True
    
    # Check if the point is within the margin of any polyline edge
    for i in range(len(polyline_points)):
        start = Vec2(polyline_points[i][:2])
        end = Vec2(polyline_points[(i + 1) % len(polyline_points)][:2])
        
        # Calculate the distance from the point to the line segment
        line_vec = end - start
        if line_vec.magnitude == 0:
            continue  # Skip zero-length segments
        point_vec = point - start
        try:
            projection = point_vec.project(line_vec)
            if 0 <= projection.magnitude <= line_vec.magnitude:
                distance = (point_vec - projection).magnitude
                if distance <= margin:
                    return True
        except ZeroDivisionError:
            log_warning(f"Zero-length vector encountered in is_point_inside_or_near_polyline. Skipping this segment.")
            continue
    
    return False

def calculate_overlap_ratio(block_shape, polyline_geom):
    # Create a buffer around the polyline to give it some width
    buffer_distance = max(block_shape.bounds[2] - block_shape.bounds[0], 
                          block_shape.bounds[3] - block_shape.bounds[1]) / 2
    polyline_buffer = polyline_geom.buffer(buffer_distance)
    
    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polyline_buffer).area
    
    if block_area == 0:
        logger.warning("Block area is zero!")
        return 100.0  # Assume full overlap if block has no area
    
    overlap_ratio = intersection_area / block_area
    inside_percentage = overlap_ratio * 100
    
    logger.debug(f"Block area: {block_area}, Intersection area: {intersection_area}")
    logger.debug(f"Overlap ratio: {overlap_ratio}, Inside percentage: {inside_percentage}")
    
    return round(inside_percentage, 1)