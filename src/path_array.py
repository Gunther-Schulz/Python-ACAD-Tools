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
import geopandas as gpd


def calculate_overlap_ratio(block_shape, polyline_geom):

    # Create a buffer around the polyline
    buffer_distance = 0.1
    polyline_buffer = polyline_geom.buffer(buffer_distance)


    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polyline_buffer).area
    outside_area = block_shape.difference(polyline_buffer).area



    if block_area == 0:

        return 100.0

    outside_percentage = (outside_area / block_area) * 100


    return round(outside_percentage, 1)

def calculate_inside_percentage(block_shape, polygon_geom):
    # Calculate areas
    block_area = block_shape.area
    intersection_area = block_shape.intersection(polygon_geom).area
    
    if block_area == 0:

        return 0.0  # Assume fully outside if block has no area
    
    inside_percentage = (intersection_area / block_area) * 100
    

    
    return round(inside_percentage, 1)

def is_block_inside_buffer(block_shape, buffer_polygon):
    # Check if all corners of the block are inside the buffer
    return all(Point(coord).within(buffer_polygon) for coord in block_shape.exterior.coords)

def visualize_placement(ax, polyline_geom, combined_area, rotated_block_shape, insertion_point, color, label):
    # Plot the polyline (only if it hasn't been plotted yet)
    if 'Path Polyline' not in [l.get_label() for l in ax.get_lines()]:
        x, y = polyline_geom.xy
        ax.plot(x, y, color='blue', linewidth=2, label='Path Polyline')

    # Plot the combined area (only if it hasn't been plotted yet)
    if 'Combined Area Boundary' not in [l.get_label() for l in ax.get_lines()]:
        x, y = combined_area.exterior.xy
        ax.fill(x, y, alpha=0.2, fc='gray', ec='none')
        ax.plot(x, y, color='blue', linewidth=2, linestyle='--', label='Combined Area Boundary')

    # Plot block
    block_patch = patches.Polygon(rotated_block_shape.exterior.coords, facecolor=color, edgecolor='black', alpha=0.7)
    ax.add_patch(block_patch)
    
    ax.text(insertion_point.x, insertion_point.y, label, 
            ha='center', va='center', fontsize=8, 
            bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))

    # Add legend entries for placed and skipped blocks (only once)
    if 'Placed Block' not in [l.get_label() for l in ax.get_lines()]:
        ax.plot([], [], color='green', marker='s', linestyle='None', markersize=10, label='Placed Block')
    if 'Skipped Block' not in [l.get_label() for l in ax.get_lines()]:
        ax.plot([], [], color='red', marker='s', linestyle='None', markersize=10, label='Skipped Block')

def create_path_array(msp, source_layer_name, target_layer_name, block_name, spacing, buffer_distance, scale=1.0, rotation=0.0, debug_visual=False, all_layers=None):
    if block_name not in msp.doc.blocks:
        log_warning(f"Block '{block_name}' not found in the document")
        return

    block = msp.doc.blocks[block_name]
    block_shape, block_base_point = get_block_shape_and_base(block, scale)
    
    if block_shape is None:
        log_warning(f"Could not determine shape for block '{block_name}'")
        return

    if all_layers is None or source_layer_name not in all_layers:
        log_warning(f"Source layer '{source_layer_name}' not found in all_layers")
        return

    source_geometry = all_layers[source_layer_name]
    log_info(f"Source geometry type: {type(source_geometry)}")
    
    if isinstance(source_geometry, gpd.GeoDataFrame):
        if source_geometry.empty:
            log_warning(f"Source geometry for layer '{source_layer_name}' is empty (GeoDataFrame)")
            return
        polylines = source_geometry.geometry
        log_info(f"Number of geometries in GeoDataFrame: {len(polylines)}")
    else:
        if source_geometry.is_empty:
            log_warning(f"Source geometry for layer '{source_layer_name}' is empty (single geometry)")
            return
        polylines = [source_geometry]
        log_info(f"Single geometry type: {type(source_geometry)}")

    fig, ax = plt.subplots(figsize=(12, 8)) if debug_visual else (None, None)

    placed_blocks = []  # List to store placed block shapes
    processed_polylines = 0

    for polyline in polylines:
        if isinstance(polyline, (LineString, MultiLineString)) and not polyline.is_empty:
            log_info(f"Processing polyline: {polyline.wkt[:100]}...")  # Log first 100 characters of WKT
            process_polyline(msp, polyline, block_shape, block_base_point, block_name, 
                             target_layer_name, spacing, buffer_distance, scale, rotation, 
                             debug_visual, ax, placed_blocks)
            processed_polylines += 1
        else:
            log_warning(f"Skipping invalid or empty polyline: {type(polyline)}")

    log_info(f"Processed {processed_polylines} polylines")

    if debug_visual:
        if processed_polylines > 0:
            ax.set_aspect('equal', 'datalim')
            ax.set_title(f"Block Placement for {block_name}")
            ax.set_xlabel("X Coordinate")
            ax.set_ylabel("Y Coordinate")
            handles, labels = ax.get_legend_handles_labels()
            by_label = dict(zip(labels, handles))
            ax.legend(by_label.values(), by_label.keys())
            plt.tight_layout()
            plt.show()
        else:
            log_warning("No valid polylines to visualize")

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
        return None, None
    
    combined_shape = unary_union(shapes)
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

def process_polyline(msp, polyline_geom, block_shape, block_base_point, block_name, 
                     target_layer_name, spacing, buffer_distance, scale, rotation, 
                     debug_visual, ax, placed_blocks):
    total_length = polyline_geom.length
    
    # Create a polygon from the polyline
    polyline_polygon = Polygon(polyline_geom)
    
    # Create buffer around the polyline
    buffer_polygon = polyline_geom.buffer(buffer_distance)
    
    # Combine the original polygon and the buffer
    combined_area = polyline_polygon.union(buffer_polygon)
    
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
            visualize_placement(ax, polyline_geom, combined_area, rotated_block_shape, insertion_point, color, label)
        
        block_distance += spacing

