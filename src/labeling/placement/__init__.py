"""Core functionality for label placement and management in DXF files.

This module provides a flexible and extensible system for placing labels on geometric
entities in DXF files, with support for various placement strategies and collision avoidance.
"""

from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Layout
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
import geopandas as gpd

from ...utils.logging import log_debug, log_warning

@dataclass
class LabelPlacementOptions:
    """Configuration options for label placement."""
    position: str = "centroid"  # centroid, center, boundary, along_line
    offset_x: float = 0
    offset_y: float = 0
    rotation: float = 0
    avoid_collisions: bool = True
    min_distance: float = 1.0
    label_spacing: float = 100  # For line features
    leader_line: bool = False
    leader_style: Dict[str, Any] = None

class LabelPlacer:
    """Handles the placement of labels on geometric entities."""
    
    def __init__(self, layout: Layout, style_manager: Any):
        self.layout = layout
        self.style_manager = style_manager
        self.placed_labels: List[Tuple[Point, float, float]] = []  # [(position, width, height), ...]

    def get_label_position(self, geom: Any, options: LabelPlacementOptions) -> Optional[Tuple[float, float, float]]:
        """Calculate the optimal position for a label based on geometry type and options.
        
        Args:
            geom: Shapely geometry object
            options: Label placement configuration
            
        Returns:
            Tuple of (x, y, rotation) coordinates for label placement, or None if position cannot be determined
        """
        try:
            if isinstance(geom, Point):
                return self._get_point_label_position(geom, options)
            elif isinstance(geom, LineString):
                return self._get_line_label_position(geom, options)
            elif isinstance(geom, (Polygon, MultiPolygon)):
                return self._get_polygon_label_position(geom, options)
            else:
                log_warning(f"Unsupported geometry type for labeling: {type(geom)}")
                return None
        except Exception as e:
            log_warning(f"Error determining label position: {str(e)}")
            return None

    def _get_point_label_position(self, point: Point, options: LabelPlacementOptions) -> Tuple[float, float, float]:
        """Get label position for point geometry."""
        x, y = point.x + options.offset_x, point.y + options.offset_y
        return (x, y, options.rotation)

    def _get_line_label_position(self, line: LineString, options: LabelPlacementOptions) -> Tuple[float, float, float]:
        """Get label position for line geometry."""
        if options.position == "along_line":
            # Place label at midpoint and align with line angle
            midpoint = line.interpolate(0.5, normalized=True)
            if line.length > 1:  # Avoid division by zero or tiny lines
                angle = self._calculate_line_angle(line)
            else:
                angle = 0
            return (midpoint.x + options.offset_x, midpoint.y + options.offset_y, angle)
        else:
            # Default to midpoint with specified rotation
            midpoint = line.interpolate(0.5, normalized=True)
            return (midpoint.x + options.offset_x, midpoint.y + options.offset_y, options.rotation)

    def _get_polygon_label_position(self, polygon: Polygon, options: LabelPlacementOptions) -> Tuple[float, float, float]:
        """Get label position for polygon geometry."""
        if options.position == "centroid":
            point = polygon.centroid
        else:  # center or default
            point = polygon.envelope.centroid
            
        return (point.x + options.offset_x, point.y + options.offset_y, options.rotation)

    def _calculate_line_angle(self, line: LineString) -> float:
        """Calculate the angle of a line segment in degrees."""
        start, end = line.coords[0], line.coords[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        import math
        angle = math.degrees(math.atan2(dy, dx))
        # Normalize angle to 0-360 range
        return angle % 360

    def check_collision(self, x: float, y: float, width: float, height: float) -> bool:
        """Check if a label at the given position would collide with existing labels."""
        for pos, w, h in self.placed_labels:
            # Simple bounding box collision check
            if (abs(x - pos[0]) < (width + w) / 2 and 
                abs(y - pos[1]) < (height + h) / 2):
                return True
        return False

    def add_label(self, text: str, geom: Any, layer: str, style: Dict[str, Any], 
                 options: Optional[LabelPlacementOptions] = None) -> bool:
        """Add a label to the layout with collision avoidance.
        
        Args:
            text: The text content of the label
            geom: The geometry to label
            layer: Target DXF layer
            style: Text style configuration
            options: Label placement options
            
        Returns:
            bool: True if label was placed successfully, False otherwise
        """
        if options is None:
            options = LabelPlacementOptions()

        # Get initial position
        pos = self.get_label_position(geom, options)
        if pos is None:
            return False

        x, y, rotation = pos
        
        # Get text dimensions (approximate)
        char_height = style.get('height', 2.5)
        width = len(text) * char_height * 0.7  # Approximate width
        height = char_height

        # Check for collisions if enabled
        if options.avoid_collisions:
            attempts = 0
            while self.check_collision(x, y, width, height) and attempts < 8:
                # Try different positions around the original point
                import math
                angle = attempts * 45
                distance = options.min_distance + attempts * 2
                x = pos[0] + distance * math.cos(math.radians(angle))
                y = pos[1] + distance * math.sin(math.radians(angle))
                attempts += 1
                
            if attempts >= 8:
                log_warning(f"Could not find collision-free position for label: {text}")
                return False

        # Create the text entity
        try:
            dxfattribs = {
                'layer': layer,
                'height': char_height,
                'rotation': rotation
            }
            
            # Apply style properties
            if 'color' in style:
                dxfattribs['color'] = style['color']
            if 'style' in style:
                dxfattribs['style'] = style['style']

            mtext = self.layout.add_mtext(text, dxfattribs=dxfattribs)
            mtext.set_location((x, y))
            
            # Add leader line if requested
            if options.leader_line and isinstance(geom, (Polygon, MultiPolygon)):
                self._add_leader_line(mtext, geom.centroid, (x, y), options)

            # Record label position for collision detection
            self.placed_labels.append(((x, y), width, height))
            
            return True

        except Exception as e:
            log_warning(f"Error adding label: {str(e)}")
            return False

    def _add_leader_line(self, mtext: Any, anchor: Point, text_pos: Tuple[float, float], 
                        options: LabelPlacementOptions) -> None:
        """Add a leader line between the text and its anchor point."""
        if not options.leader_style:
            options.leader_style = {'color': 7}  # Default white

        try:
            points = [(anchor.x, anchor.y), text_pos]
            self.layout.add_lwpolyline(
                points,
                dxfattribs={
                    'layer': mtext.dxf.layer,
                    'color': options.leader_style.get('color', 7)
                }
            )
        except Exception as e:
            log_warning(f"Error adding leader line: {str(e)}")
