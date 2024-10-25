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

    placed_blocks = []  # List to store placed block shapes

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
            angle = get_angle_at_point(polyline_geom, block_distance)

            rotated_block_shape = rotate_and_adjust_block(block_shape, block_base_point, insertion_point, angle)
            
            is_inside = is_block_inside_buffer(rotated_block_shape, combined_area)
            overlaps_existing = any(rotated_block_shape.intersects(placed) for placed in placed_blocks)

            if is_inside and not overlaps_existing:
                color = 'green'
                label = "Placed"
                block_ref = add_block_reference(
                    msp,
                    block_name,
                    insertion_point,
                    target_layer_name,
                    scale=scale,
                    rotation=math.degrees(angle) + rotation  # Apply base rotation
                )
                if block_ref:
                    attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
                    placed_blocks.append(rotated_block_shape)
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

def get_angle_at_point(linestring, distance):
    # Find the segment of the polyline where the block is to be placed
    for i in range(len(linestring.coords) - 1):
        start = Vec2(*linestring.coords[i])
        end = Vec2(*linestring.coords[i + 1])
        segment = LineString([start, end])
        if segment.length >= distance:
            # Calculate the angle of the segment
            dx = end.x - start.x
            dy = end.y - start.y
            tangent_angle = math.atan2(dy, dx)
            return tangent_angle  # Use tangent angle directly
        else:
            distance -= segment.length
    return 0.0  # Default angle if something goes wrong
