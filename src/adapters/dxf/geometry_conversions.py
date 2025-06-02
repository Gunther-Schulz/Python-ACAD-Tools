"""DXF geometry conversion adapter for ezdxf library integration.

This module provides adapter functions for converting between DXF entities and Shapely geometries.
"""
from typing import Optional, Tuple, List, Any, Dict, cast

from shapely.geometry import Point, Polygon, LineString
from shapely.ops import transform as shapely_transform # Alias to avoid confusion

# Import exception from domain
from ...domain.exceptions import DXFGeometryConversionError

# Direct imports for ezdxf as a hard dependency
import ezdxf
from ezdxf.entities import DXFGraphic, Circle, LWPolyline, Polyline, Insert, Text, MText, Line as DXFLine, Arc, Ellipse, Spline, Hatch, Point as DXFPoint, Solid, Trace, Face3d
from ezdxf.math import Vec3, bulge_to_arc, Z_AXIS
from ezdxf.lldxf.const import DXFError, DXFStructureError

def convert_dxf_circle_to_polygon(
    entity: Circle,
    segments: int = 64
) -> Optional[Polygon]:
    """Converts an ezdxf Circle entity to a Shapely Polygon."""
    if not isinstance(entity, Circle):
        return None
    if segments < 3:
        raise DXFGeometryConversionError("Number of segments for circle approximation must be at least 3.")
    try:
        # ezdxf's `vertices` method for Circle returns points on the circumference
        points = list(entity.vertices(angle_span=360, num_segments=segments)) # Ensure full circle
        if not points or len(points) < 3:
            return None
        # Convert Vec3 to (x, y) tuples
        shell_coords = [(p.x, p.y) for p in points]
        return Polygon(shell_coords)
    except (DXFError, DXFStructureError, AttributeError) as e:
        raise DXFGeometryConversionError(f"Error converting DXF Circle to Polygon: {e}") from e

def extract_dxf_entity_basepoint(
    entity: DXFGraphic,
) -> Optional[Tuple[Point, Dict[str, Any]]]:
    """Extracts a representative basepoint (as Shapely Point) and attributes from a DXF entity."""
    basepoint_coords: Optional[Tuple[float, float]] = None
    attributes: Dict[str, Any] = {'dxf_type': entity.dxftype()}
    shapely_point: Optional[Point] = None

    try:
        entity_type = entity.dxftype()

        if entity_type == 'INSERT':
            insert_entity = cast(Insert, entity)
            basepoint_coords = (insert_entity.dxf.insert.x, insert_entity.dxf.insert.y)
            attributes.update({
                'block_name': insert_entity.dxf.name,
                'x_scale': getattr(insert_entity.dxf, 'xscale', 1.0),
                'y_scale': getattr(insert_entity.dxf, 'yscale', 1.0),
                'rotation': getattr(insert_entity.dxf, 'rotation', 0.0)
            })
        elif entity_type == 'LINE':
            line_entity = cast(DXFLine, entity)
            basepoint_coords = (line_entity.dxf.start.x, line_entity.dxf.start.y)
        elif entity_type == 'CIRCLE':
            circle_entity = cast(Circle, entity)
            basepoint_coords = (circle_entity.dxf.center.x, circle_entity.dxf.center.y)
            attributes['radius'] = circle_entity.dxf.radius
        elif entity_type == 'ARC':
            arc_entity = cast(Arc, entity)
            basepoint_coords = (arc_entity.dxf.center.x, arc_entity.dxf.center.y)
            attributes['radius'] = arc_entity.dxf.radius
            attributes['start_angle'] = arc_entity.dxf.start_angle
            attributes['end_angle'] = arc_entity.dxf.end_angle
        elif entity_type == 'TEXT':
            text_entity = cast(Text, entity)
            basepoint_coords = (text_entity.dxf.insert.x, text_entity.dxf.insert.y)
            attributes['text_string'] = text_entity.dxf.text
            attributes['text_height'] = text_entity.dxf.height
            attributes['text_rotation'] = text_entity.dxf.rotation
        elif entity_type == 'MTEXT':
            mtext_entity = cast(MText, entity)
            basepoint_coords = (mtext_entity.dxf.insert.x, mtext_entity.dxf.insert.y)
            attributes['mtext_string'] = mtext_entity.text # Mtext content
            attributes['mtext_height'] = mtext_entity.dxf.char_height
            attributes['mtext_rotation'] = mtext_entity.dxf.rotation
        elif entity_type == 'LWPOLYLINE':
            lwpolyline_entity = cast(LWPolyline, entity)
            if lwpolyline_entity.vertices:
                first_vertex = lwpolyline_entity.vertices[0]
                basepoint_coords = (first_vertex[0], first_vertex[1]) # (x,y) from (x,y,start_width,end_width,bulge)
        elif entity_type == 'POLYLINE': # Old style polyline
            polyline_entity = cast(Polyline, entity)
            # Get first vertex coordinates
            if polyline_entity.vertices:
                first_vertex_entity = polyline_entity.vertices[0] # This is a Vertex entity
                basepoint_coords = (first_vertex_entity.dxf.location.x, first_vertex_entity.dxf.location.y)
        elif entity_type == 'POINT': # DXF Point entity
            point_entity = cast(DXFPoint, entity)
            basepoint_coords = (point_entity.dxf.location.x, point_entity.dxf.location.y)
        elif entity_type == 'ELLIPSE':
            ellipse_entity = cast(Ellipse, entity)
            basepoint_coords = (ellipse_entity.dxf.center.x, ellipse_entity.dxf.center.y)
            attributes['major_axis_ratio'] = ellipse_entity.dxf.ratio
            attributes['start_param'] = ellipse_entity.dxf.start_param
            attributes['end_param'] = ellipse_entity.dxf.end_param
        elif entity_type == 'SPLINE':
            spline_entity = cast(Spline, entity)
            if spline_entity.control_points:
                first_ctrl_pt = spline_entity.control_points[0]
                basepoint_coords = (first_ctrl_pt.x, first_ctrl_pt.y)
        elif entity_type == 'HATCH': # This is often complex to get a single 'basepoint'
            hatch_entity = cast(Hatch, entity)
            # Option 1: Use first point of the first path if available
            try:
                if hatch_entity.paths:
                    first_path = hatch_entity.paths[0]
                    if isinstance(first_path, ezdxf.entities.hatch.PolylinePath):
                        if first_path.vertices:
                            basepoint_coords = (first_path.vertices[0][0], first_path.vertices[0][1]) # (x,y) from (x,y,bulge)
                    elif isinstance(first_path, ezdxf.entities.hatch.EdgePath):
                        # EdgePath consists of lines, arcs, etc. Take start of first edge.
                        if first_path.edges:
                            first_edge = first_path.edges[0]
                            if first_edge.EDGE_TYPE == "LineEdge":
                                basepoint_coords = (first_edge.start.x, first_edge.start.y)
                            elif first_edge.EDGE_TYPE == "ArcEdge":
                                # For arc, center might be more stable, or start point
                                basepoint_coords = (first_edge.start_point().x, first_edge.start_point().y)
                                attributes['hatch_edge_type'] = 'ArcEdge_start'
                            # Add more edge types if needed (EllipseEdge, SplineEdge)
            except Exception:
                pass # Fallback to None if path access fails
            attributes['hatch_pattern_name'] = hatch_entity.dxf.pattern_name
        elif entity_type == 'SOLID' or entity_type == 'TRACE': # Usually rectangular
            solid_entity = cast(Solid, entity)
            basepoint_coords = (solid_entity.dxf.vtx0.x, solid_entity.dxf.vtx0.y) # First vertex
        elif entity_type == '3DFACE':
            face_entity = cast(Face3d, entity)
            basepoint_coords = (face_entity.dxf.vtx0.x, face_entity.dxf.vtx0.y) # First vertex
        # Add more entity types as needed, e.g., LEADER, DIMENSION, etc.

        if basepoint_coords:
            shapely_point = Point(basepoint_coords)
            return shapely_point, attributes

    except (DXFError, DXFStructureError, AttributeError, IndexError, TypeError):
        # Gracefully skip if basepoint extraction fails for an entity
        pass

    return None # If no basepoint could be determined or an error occurred
