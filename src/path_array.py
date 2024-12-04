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
from src.dxf_utils import SCRIPT_IDENTIFIER, add_block_reference, attach_custom_data
from src.utils import log_info, log_warning, log_error
import re
import math
from ezdxf.math import Vec2, area
from ezdxf.math import intersection_line_line_2d
import os
from ezdxf.lldxf.const import DXFValueError
from shapely.geometry import Polygon, Point, LineString
from shapely import MultiLineString, MultiPolygon, affinity, unary_union
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

def create_path_array(msp, source_layer_name, target_layer_name, block_name, spacing, buffer_distance, scale=1.0, rotation=0.0, debug_visual=False, all_layers=None, adjust_for_vertices=True, path_offset=0):
    if block_name not in msp.doc.blocks:
        log_warning(f"Block '{block_name}' not found in the document")
        return

    block = msp.doc.blocks[block_name]
    
    if all_layers is None or source_layer_name not in all_layers:
        log_warning(f"Source layer '{source_layer_name}' not found in all_layers")
        return

    source_geometry = all_layers[source_layer_name]
    log_info(f"Source geometry type: {type(source_geometry)}")
    
    if isinstance(source_geometry, gpd.GeoDataFrame):
        if source_geometry.empty:
            log_warning(f"Source geometry for layer '{source_layer_name}' is empty (GeoDataFrame)")
            return
        geometries = source_geometry.geometry
        log_info(f"Number of geometries in GeoDataFrame: {len(geometries)}")
    else:
        if source_geometry.is_empty:
            log_warning(f"Source geometry for layer '{source_layer_name}' is empty (single geometry)")
            return
        geometries = [source_geometry]
        log_info(f"Single geometry type: {type(source_geometry)}")

    fig, ax = plt.subplots(figsize=(12, 8)) if debug_visual else (None, None)

    placed_blocks = []  # List to store placed block shapes
    processed_geometries = 0

    for geometry in geometries:
        if isinstance(geometry, (LineString, MultiLineString)):
            # For lines, we only need the base point
            base_point = Vec2(block.base_point[0] * scale, block.base_point[1] * scale)
            
            # Handle lines separately
            if isinstance(geometry, LineString):
                process_line(msp, geometry, block_name, target_layer_name, spacing, scale, rotation)
            else:  # MultiLineString
                for line in geometry.geoms:
                    process_line(msp, line, block_name, target_layer_name, spacing, scale, rotation)
        elif isinstance(geometry, (Polygon, MultiPolygon)):
            # For polygons, we need both shape and base point
            block_shape, block_base_point = get_block_shape_and_base(block, scale)
            if block_shape is None:
                log_warning(f"Could not determine shape for block '{block_name}'")
                return
                
            # Use existing polygon logic unchanged
            if isinstance(geometry, Polygon):
                polylines = [LineString(geometry.exterior.coords)]
            else:  # MultiPolygon
                polylines = [LineString(poly.exterior.coords) for poly in geometry.geoms]
            
            for polyline in polylines:
                if isinstance(polyline, LineString) and not polyline.is_empty:
                    process_polyline(msp, polyline, block_shape, block_base_point, block_name, 
                                   target_layer_name, spacing, buffer_distance, scale, rotation, 
                                   debug_visual, ax, placed_blocks, adjust_for_vertices, path_offset)
        else:
            log_warning(f"Skipping unsupported geometry type: {type(geometry)}")
            continue

    log_info(f"Processed {processed_geometries} geometries")

    if debug_visual:
        if processed_geometries > 0:
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
            log_warning("No valid geometries to visualize")

    log_info(f"Path array creation completed for source layer '{source_layer_name}' using block '{block_name}'")

def get_block_shape_and_base(block, scale):
    shapes = []
    base_point = Vec2(block.base_point[0] * scale, block.base_point[1] * scale)
    
    for entity in block:
        entity_type = entity.dxftype()
        
        if entity_type == "LWPOLYLINE":
            points = [(p[0] * scale, p[1] * scale) for p in entity.get_points()]
            shapes.append(Polygon(points))
        elif entity_type == "LINE":
            start = (entity.dxf.start.x * scale, entity.dxf.start.y * scale)
            end = (entity.dxf.end.x * scale, entity.dxf.end.y * scale)
            shapes.append(LineString([start, end]))
        elif entity_type == "CIRCLE":
            # Create a polygon approximating the circle
            center_x = entity.dxf.center.x * scale
            center_y = entity.dxf.center.y * scale
            radius = entity.dxf.radius * scale
            
            # Create a circle approximation with more points for better accuracy
            num_points = 64  # Increased from 32 for better accuracy
            angles = np.linspace(0, 2*np.pi, num_points)
            points = []
            for angle in angles:
                x = center_x + radius * np.cos(angle)
                y = center_y + radius * np.sin(angle)
                points.append((x, y))
            # Close the polygon by adding the first point again
            points.append(points[0])
            
            try:
                circle_polygon = Polygon(points)
                if not circle_polygon.is_valid:
                    log_warning("Invalid circle polygon created, attempting to fix...")
                    circle_polygon = circle_polygon.buffer(0)  # Try to fix invalid geometry
                
                if circle_polygon.is_valid and circle_polygon.area > 0:
                    shapes.append(circle_polygon)
                    log_info(f"Successfully created circle polygon with area: {circle_polygon.area}")
                else:
                    log_warning(f"Failed to create valid circle polygon. Area: {circle_polygon.area}")
            except Exception as e:
                log_warning(f"Error creating circle polygon: {str(e)}")
    
    if not shapes:
        log_warning("No supported shapes found in block")
        return None, None
    
    try:
        combined_shape = unary_union(shapes)
        if combined_shape.is_valid and combined_shape.area > 0:
            return combined_shape, base_point
        else:
            log_warning("Created invalid or zero-area combined shape")
            return None, None
    except Exception as e:
        log_warning(f"Error creating combined shape: {str(e)}")
        return None, None

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
                     debug_visual, ax, placed_blocks, adjust_for_vertices, path_offset=0):
    total_length = polyline_geom.length
    
    # Create offset path for block placement
    if path_offset != 0:
        try:
            # Positive offset moves points inside
            offset_path = polyline_geom.parallel_offset(
                path_offset, 
                'left',  # 'left' creates offset towards inside
                join_style=2,  # Round join style
                mitre_limit=2.0
            )
            if offset_path.is_empty:
                log_warning("Failed to create offset path, using original path")
                offset_path = polyline_geom
        except Exception as e:
            log_warning(f"Error creating offset path: {str(e)}, using original path")
            offset_path = polyline_geom
    else:
        offset_path = polyline_geom
    
    # Create a polygon from the polyline
    polyline_polygon = Polygon(polyline_geom)
    
    # Create buffer around the polyline
    buffer_polygon = polyline_geom.buffer(buffer_distance)
    
    # Combine the original polygon and the buffer
    combined_area = polyline_polygon.union(buffer_polygon)
    
    block_distance = spacing / 2
    
    while block_distance < total_length:
        point = offset_path.interpolate(block_distance)
        insertion_point = Vec2(point.x, point.y)
        
        # Get all nearby vertices and segments
        vertex_info = get_nearby_vertices_and_segments(polyline_geom, point, tolerance=spacing/2)
        
        if adjust_for_vertices and vertex_info['vertices']:
            angle = calculate_optimal_angle(vertex_info['segments'], block_shape)
        else:
            angle = get_angle_at_point(polyline_geom, block_distance)
        
        
        rotated_block_shape = rotate_and_adjust_block(block_shape, block_base_point, insertion_point, angle)
        
        is_inside = is_block_inside_buffer(rotated_block_shape, combined_area)
        overlaps_existing = any(rotated_block_shape.intersects(placed) for placed in placed_blocks)
        
        
        if is_inside and not overlaps_existing:
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
                placed_blocks.append(rotated_block_shape)
            else:
                log_warning("Failed to create block reference")
        else:
            color = 'red'
            label = "Skipped"
        
        if debug_visual:
            visualize_placement(ax, polyline_geom, combined_area, rotated_block_shape, insertion_point, color, label)
        
        block_distance += spacing

def get_nearby_vertices_and_segments(linestring, point, tolerance):
    vertices = []
    segments = []
    
    for i, vertex in enumerate(linestring.coords):
        if Point(vertex).distance(point) < tolerance:
            vertices.append(i)
    
    if not vertices:
        return {'vertices': [], 'segments': []}
    
    # Get all segments connected to the vertices
    for i in range(vertices[0] - 1, vertices[-1] + 1):
        if i >= 0 and i < len(linestring.coords) - 1:
            segments.append(LineString([linestring.coords[i], linestring.coords[i+1]]))
    
    return {'vertices': vertices, 'segments': segments}

def calculate_optimal_angle(segments, block_shape):
    if not segments:
        return 0
    
    # Calculate the average direction of all segments
    avg_angle = sum(math.atan2(seg.coords[1][1] - seg.coords[0][1],
                               seg.coords[1][0] - seg.coords[0][0]) for seg in segments) / len(segments)
    
    # Adjust the angle to maximize contact points
    best_angle = avg_angle
    max_contacts = 0
    
    for angle in [avg_angle + i * math.pi/180 for i in range(-10, 11)]:  # Check ±10 degrees
        rotated_block = affinity.rotate(block_shape, angle, origin=(0, 0))
        contacts = sum(rotated_block.touches(seg) for seg in segments)
        if contacts > max_contacts:
            max_contacts = contacts
            best_angle = angle
    
    return best_angle

# New function to handle lines
def process_line(msp, line, block_name, target_layer_name, spacing, scale, rotation):
    if line.is_empty:
        return
        
    coords = list(line.coords)
    total_length = line.length
    current_distance = spacing / 2
    
    while current_distance < total_length:
        point = line.interpolate(current_distance)
        insertion_point = Vec2(point.x, point.y)
        
        # Find current segment
        accumulated_length = 0
        current_segment_index = 0
        
        for i in range(len(coords) - 1):
            segment = LineString([coords[i], coords[i + 1]])
            if accumulated_length + segment.length >= current_distance:
                current_segment_index = i
                break
            accumulated_length += segment.length
            
        # Calculate distance from start of current segment
        local_distance = current_distance - accumulated_length
        segment = LineString([coords[current_segment_index], coords[current_segment_index + 1]])
        
        # Get angles for current and next segment (if exists)
        curr_angle = math.atan2(
            coords[current_segment_index + 1][1] - coords[current_segment_index][1],
            coords[current_segment_index + 1][0] - coords[current_segment_index][0]
        )
        
        # If we're approaching a corner and not at the last segment
        if current_segment_index < len(coords) - 2:
            next_angle = math.atan2(
                coords[current_segment_index + 2][1] - coords[current_segment_index + 1][1],
                coords[current_segment_index + 2][0] - coords[current_segment_index + 1][0]
            )
            
            # Normalize angle difference to ensure shortest rotation path
            angle_diff = next_angle - curr_angle
            if angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            elif angle_diff < -math.pi:
                angle_diff += 2 * math.pi
                
            # Calculate distance to next corner
            dist_to_corner = segment.length - local_distance
            
            # If we're within spacing distance of the corner
            if dist_to_corner < spacing:
                # Calculate interpolation factor (0 at spacing distance, 1 at corner)
                t = 1 - (dist_to_corner / spacing)
                # Smoothly interpolate between angles
                final_angle = curr_angle + (angle_diff * t)
            else:
                final_angle = curr_angle
        else:
            final_angle = curr_angle
            
        # Add block reference with interpolated angle
        block_ref = add_block_reference(
            msp,
            block_name,
            insertion_point,
            target_layer_name,
            scale=scale,
            rotation=math.degrees(final_angle) + rotation
        )
        
        if block_ref:
            attach_custom_data(block_ref, SCRIPT_IDENTIFIER)
        
        current_distance += spacing

