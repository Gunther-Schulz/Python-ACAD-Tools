from typing import AsyncIterator, Optional, Any, List, Tuple, Union
import logging
import math
import numpy as np
import networkx as nx

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import ILabelPlacementService, PlacedLabel, IStyleService, ITextStyle
from dxfplanner.config.schemas import LabelSettings
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
from shapely.ops import polylabel
from shapely.affinity import rotate, translate
from shapely.prepared import prep
# Import other necessary dependencies from OLDAPP logic later, e.g., shapely, networkx

# It's good practice to get a logger instance per module
logger = logging.getLogger(__name__)

class LabelPlacementServiceImpl(ILabelPlacementService):
    """
    Service implementation for advanced label placement.
    This service will adapt logic from OLDAPP/src/operations/label_association_operation.py
    """

    def __init__(self,
                 app_config: Optional[Any] = None,
                 specific_config: Optional[Any] = None,
                 logger: Optional[logging.Logger] = None,
                 style_service: Optional[IStyleService] = None):
        """
        Constructor for LabelPlacementServiceImpl.
        Dependencies (like full app config or specific parts) will be injected.
        """
        self.app_config = app_config
        self.specific_config = specific_config
        self.logger = logger if logger else logging.getLogger(__name__)
        self.style_service = style_service

        self.logger.info("LabelPlacementServiceImpl initialized.")
        if self.style_service:
            self.logger.info("StyleService injected into LabelPlacementServiceImpl.")
        else:
            self.logger.warning("StyleService NOT injected into LabelPlacementServiceImpl.")

    async def place_labels_for_features(
        self,
        features: AsyncIterator[GeoFeature],
        layer_name: str,
        config: LabelSettings,
    ) -> AsyncIterator[PlacedLabel]:
        """
        Calculates optimal placements for labels for a stream of geographic features.
        Implements main logic for points, lines, and polygons using new helpers.
        """
        self.logger.debug(
            f"Starting label placement for layer '{layer_name}' "
            f"with text_height: {config.text_height}, "
            f"offset_x: {config.offset_x}, offset_y: {config.offset_y}"
        )

        placed_labels_boxes: List[Polygon] = []
        avoidance_geometries: List[Union[Polygon, LineString, Point]] = []

        async for feature in features:
            if not feature.geometry:
                self.logger.warning(f"Feature in layer {layer_name} has no geometry. Skipping label.")
                continue

            # Determine label text
            current_label_text = ""
            if config.fixed_label_text:
                current_label_text = config.fixed_label_text
            elif config.label_attribute and config.label_attribute in feature.attributes:
                current_label_text = str(feature.attributes[config.label_attribute])

            if not current_label_text:
                self.logger.debug(f"No label text found for feature in layer {layer_name}, skipping.")
                continue

            # Determine geometry type and generate candidate positions
            geom = feature.geometry
            candidates = []
            if isinstance(geom, Point):
                # Use get_point_label_position
                pos, angle = self.get_point_label_position(
                    geom, current_label_text, config.text_height, config.offset, getattr(config, 'point_position_preference', None)
                )
                candidates.append((pos, angle))
            elif isinstance(geom, (LineString,)):
                # Generate anchor/candidate positions for lines
                # Example: use _get_line_anchor_points and _find_best_line_label_position
                try:
                    anchor_points = self._get_line_anchor_points(geom, config)
                    best_pos, best_score, best_angle = self._find_best_line_label_position(
                        geom, anchor_points, current_label_text, config, placed_labels_boxes, avoidance_geometries
                    )
                    if best_pos is not None:
                        candidates.append((best_pos, best_angle))
                except Exception as e:
                    self.logger.error(f"Error generating line label candidates for feature in {layer_name}: {e}", exc_info=True)
            elif isinstance(geom, (Polygon, MultiPolygon)):
                # Use get_polygon_anchor_position
                anchor = self.get_polygon_anchor_position(
                    geom, config.text_height * len(current_label_text), config.text_height
                )
                candidates.append((anchor, 0.0))
            else:
                self.logger.warning(f"Unsupported geometry type for feature in {layer_name}. Skipping label.")
                continue

            # Evaluate candidates and check for collisions
            for pos, angle in candidates:
                # Use _evaluate_candidate_position for collision and constraint checks
                result = self._evaluate_candidate_position(
                    current_label_text, pos, angle, getattr(config, 'text_style', ''), layer_name, geom, config,
                    placed_labels_boxes, avoidance_geometries
                )
                if result:
                    label_box, score = result
                    placed_labels_boxes.append(label_box)
                    yield PlacedLabel(
                        text=current_label_text,
                        position=Coordinate(x=pos.x, y=pos.y),
                        rotation=angle
                    )
                    break # Only place one label per feature

        if False: # pragma: no cover
            yield

    # --- Helper methods adapted from OLDAPP/src/operations/label_association_operation.py ---

    def _calculate_vertex_angle(self, p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float]) -> float:
        """Calculate angle at vertex p2 in degrees."""
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])

        dot_product = np.dot(v1, v2)
        norms = np.linalg.norm(v1) * np.linalg.norm(v2)

        if norms == 0:
            return 180.0 # Ensure float

        cos_angle = dot_product / norms
        # Ensure domain of arccos due to potential floating point inaccuracies
        cos_angle = min(1.0, max(-1.0, cos_angle))

        return math.degrees(math.acos(cos_angle))

    def _calculate_local_angle(self, point: Point, local_context: nx.Graph, coords: List[Tuple[float, float]]) -> float:
        """Calculate angle at a point using local network context."""
        # coords here are the original line's coordinates, local_context is a subgraph
        edges = list(local_context.edges(data=True))
        if not edges:
            return 0.0 # Ensure float

        # Get nearby segments from the local_context graph
        # The geometry of segments should be stored in the graph edges if this pattern is followed
        segments = [edge[2]['geometry'] for edge in edges if 'geometry' in edge[2] and isinstance(edge[2]['geometry'], LineString)]

        if not segments:
            # Fallback or error? Original seemed to imply segments would be there.
            # For now, let's find the segment in the original line that `point` is on or nearest to,
            # if local_context doesn't directly yield segments.
            # This part might need refinement based on how G is constructed and what local_context contains.
            # The original's `local_context` was from `nx.ego_graph(G, nearest_vertex, radius=2)`
            # where G's edges had 'geometry'.
            self.logger.debug("_calculate_local_angle: No segments with geometry found in local_context. This might indicate an issue or a different graph structure.")
            # Fallback: find closest segment from the main line's coords if point is on it.
            # This is a simplified fallback, true logic would need more robust segment finding.
            if len(coords) < 2: return 0.0
            min_dist = float('inf')
            closest_segment_coords = (coords[0], coords[1])
            for i in range(len(coords) -1):
                segment = LineString([coords[i], coords[i+1]])
                dist = point.distance(segment)
                if dist < min_dist:
                    min_dist = dist
                    closest_segment_coords = (coords[i], coords[i+1])

            # Calculate angle along this fallback closest segment
            return math.degrees(math.atan2(
                closest_segment_coords[1][1] - closest_segment_coords[0][1],
                closest_segment_coords[1][0] - closest_segment_coords[0][0]
            ))

        # Find closest segment among those from local_context
        closest_segment = min(segments, key=lambda s: s.distance(point))

        # Calculate angle along closest segment
        segment_coords = list(closest_segment.coords)
        return math.degrees(math.atan2(
            segment_coords[-1][1] - segment_coords[0][1],
            segment_coords[-1][0] - segment_coords[0][0]
        ))

    def _calculate_corner_penalty(self, G: nx.Graph, point: Point, coords: List[Tuple[float, float]], text_width: float) -> float:
        """Calculate corner penalty using NetworkX path analysis."""
        corner_penalty = 0.0 # Ensure float

        if not G or not coords or len(coords) < 2: # Basic check
            return 0.0

        # Find vertex in original coords nearest to the interpolated point
        # This assumes G's nodes correspond to indices of coords
        # Ensure G's nodes are 0-indexed matching coords list
        valid_nodes_in_G = [n for n in range(len(coords)) if n in G]
        if not valid_nodes_in_G:
             self.logger.warning("_calculate_corner_penalty: Coords indices not in G or G is empty.")
             return 0.0

        nearest_vertex_idx = min(valid_nodes_in_G,
                                 key=lambda i: Point(coords[i]).distance(point))

        # Use NetworkX to find nearby vertices in G from this nearest_vertex_idx
        # cutoff is text_width
        try:
            # single_source_dijkstra_path_length returns a dict {node: length}
            nearby_vertices_lengths = nx.single_source_dijkstra_path_length(G, nearest_vertex_idx,
                                                                      cutoff=text_width)
        except nx.NodeNotFound:
             self.logger.warning(f"_calculate_corner_penalty: Node {nearest_vertex_idx} not found in graph G.")
             return 0.0

        for v_idx, dist_from_source_node in nearby_vertices_lengths.items():
            # v_idx is an index into the original 'coords' list
            if 0 < v_idx < len(coords)-1: # Check if it's an internal vertex
                # Get local subgraph around this vertex v_idx from G
                # radius=1 means immediate neighbors
                local_subgraph_at_v = nx.ego_graph(G, v_idx, radius=1)

                # To calculate angle at v_idx, we need its predecessor and successor in original line
                # Check if v_idx-1 and v_idx+1 are actual nodes in G and connected to v_idx in local_subgraph_at_v
                # (ego_graph should ensure they are connected if they are neighbors in G)
                if (v_idx-1) in local_subgraph_at_v and (v_idx+1) in local_subgraph_at_v:
                    prev_point_coords = coords[v_idx-1]
                    curr_point_coords = coords[v_idx]
                    next_point_coords = coords[v_idx+1]

                    angle = self._calculate_vertex_angle(prev_point_coords, curr_point_coords, next_point_coords)

                    if angle < 150:  # Angle threshold for corners
                        dist_to_corner_geom = Point(coords[v_idx])
                        # The penalty should be based on distance from the original 'point' to this 'corner'
                        dist_point_to_corner = dist_to_corner_geom.distance(point)

                        if dist_point_to_corner < text_width: # Only consider corners within text_width of the point
                            angle_factor = (150.0 - angle) / 150.0
                            # Penalty diminishes as 'point' is further from 'corner'
                            distance_factor = max(0.0, 1.0 - (dist_point_to_corner / text_width))
                            corner_penalty += angle_factor * distance_factor

        return corner_penalty

    def _calculate_curvature_score(self, local_context: nx.Graph, coords: List[Tuple[float, float]]) -> float:
        """Calculate curvature score using NetworkX local structure analysis."""
        # local_context is an ego_graph around a point on the line
        # coords is the full list of coordinates for the original line

        if len(local_context) < 3: # Not enough context for curvature
            return 0.0

        angles = []
        # Ensure edges are sorted or processed in a way that represents segments along the path
        # The original script did: `edges = list(local_context.edges())` then iterates `for i in range(len(edges)-1):`
        # This assumes edges are somehow ordered or that finding connected segments is robust.
        # A more robust way might be to find paths through the local_context.
        # For simplicity, let's try to replicate the original, assuming G's nodes are indices of coords.

        # We need to find sequences of three vertices (v_prev, v_curr, v_next) in local_context
        # that form connected segments of the original line.

        sorted_nodes_in_context = sorted(list(local_context.nodes()))

        for i in range(len(sorted_nodes_in_context) - 2):
            v_prev_idx = sorted_nodes_in_context[i]
            v_curr_idx = sorted_nodes_in_context[i+1]
            v_next_idx = sorted_nodes_in_context[i+2]

            # Check if these form a contiguous part of the original line by checking node indices
            # and connectivity in the local_context (which implies connectivity in G)
            if (v_curr_idx == v_prev_idx + 1 and v_next_idx == v_curr_idx + 1 and
                local_context.has_edge(v_prev_idx, v_curr_idx) and
                local_context.has_edge(v_curr_idx, v_next_idx)):

                angle = self._calculate_vertex_angle(
                    coords[v_prev_idx],
                    coords[v_curr_idx],
                    coords[v_next_idx]
                )
                angles.append(angle)

        if not angles:
            return 0.0

        avg_angle = sum(angles) / len(angles)
        if avg_angle > 170:  # Nearly straight
            return 2.0
        elif avg_angle > 150:  # Slightly curved
            return 1.0
        else:  # Significantly curved
            return 0.0

    def _apply_offset_to_point(self, point: Point, offset_x: float, offset_y: float, angle: Optional[float] = None) -> Point:
        """Apply x,y offset to point, considering rotation angle.

        Args:
            point: The base point to offset
            offset_x: Offset along text direction (positive = right, negative = left)
            offset_y: Offset perpendicular to text (positive = up, negative = down)
            angle: Text rotation angle in degrees
        """
        if angle is not None:
            angle_rad = math.radians(angle)
            rotated_x = offset_x * math.cos(angle_rad) - offset_y * math.sin(angle_rad)
            rotated_y = offset_x * math.sin(angle_rad) + offset_y * math.cos(angle_rad)
            return Point(point.x + rotated_x, point.y + rotated_y)
        else:
            return Point(point.x + offset_x, point.y + offset_y)

    def get_polygon_anchor_position(self, polygon: Polygon, text_width: float, text_height: float) -> Point:
        """Get the best anchor position for a polygon. Adapts Mapbox's approach."""
        candidates: List[Tuple[Point, float]] = [] # (point, score)

        # 1. Try centroid
        centroid = polygon.centroid
        if polygon.contains(centroid):
            score = 1.0
            min_dist_to_boundary = polygon.boundary.distance(centroid)
            if text_width > 0: # Avoid division by zero
                 score += min_dist_to_boundary / (text_width * 0.5)
            candidates.append((centroid, score))

        # 2. Try pole of inaccessibility
        try:
            # polylabel is an optional import, handle its absence
            pole = polylabel(polygon, tolerance=text_height / 10.0 if text_height > 0 else 0.1)
            if polygon.contains(pole):
                score = 1.5
                min_dist_to_boundary = polygon.boundary.distance(pole)
                if text_width > 0:
                    score += min_dist_to_boundary / (text_width * 0.5)
                candidates.append((pole, score))
        except ImportError:
            self.logger.debug("shapely.ops.polylabel not available. Skipping pole of inaccessibility.")
        except Exception as e:
            self.logger.debug(f"Error calculating pole of inaccessibility: {e}")
            pass # Continue if polylabel fails for other reasons

        # 3. Try representative point
        rep_point = polygon.representative_point()
        if polygon.contains(rep_point): # Should always be true by definition, but check anyway
            score = 0.5
            min_dist_to_boundary = polygon.boundary.distance(rep_point)
            if text_width > 0:
                score += min_dist_to_boundary / (text_width * 0.5)
            candidates.append((rep_point, score))

        # 4. Try points along major axis of minimum rotated rectangle
        try:
            mbr = polygon.minimum_rotated_rectangle
            if mbr and mbr.geom_type == 'Polygon' and not mbr.is_empty:
                coords_mbr = list(mbr.exterior.coords) # Renamed from coords to avoid conflict

                side1 = LineString([coords_mbr[0], coords_mbr[1]])
                side2 = LineString([coords_mbr[1], coords_mbr[2]])

                major_axis_pts = [coords_mbr[0], coords_mbr[1]] if side1.length > side2.length else [coords_mbr[1], coords_mbr[2]]

                for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
                    x = major_axis_pts[0][0] + t * (major_axis_pts[1][0] - major_axis_pts[0][0])
                    y = major_axis_pts[0][1] + t * (major_axis_pts[1][1] - major_axis_pts[0][1])
                    point_on_axis = Point(x, y)
                    if polygon.contains(point_on_axis):
                        score = 0.8
                        min_dist_to_boundary = polygon.boundary.distance(point_on_axis)
                        if text_width > 0:
                             score += min_dist_to_boundary / (text_width * 0.5)
                        candidates.append((point_on_axis, score))
            else:
                 self.logger.debug("Could not get valid minimum_rotated_rectangle for polygon.")
        except Exception as e:
            self.logger.debug(f"Error calculating major axis points for polygon: {e}")
            pass

        if not candidates:
            self.logger.debug("No valid candidate anchor positions found for polygon, falling back to centroid.")
            return polygon.centroid # Fallback

        return max(candidates, key=lambda item: item[1])[0]

    def get_point_label_position(self,
                                 point: Point,
                                 label_text: str, # Used for text_width calculation
                                 text_height: float,
                                 offset_config: Any, # From LabelSettings.offset (can be dict, number, list)
                                 point_position_preference: Optional[str] = None # e.g., "top-right"
                                 ) -> Tuple[Point, float]: # Returns (position_point, angle)
        """Get best label position for a point feature."""
        # Simplified: Using a similar approach to OLDAPP for offsets and positions
        # Actual text_width would come from calculate_text_dimensions later
        # For now, a rough estimate:
        font_size = text_height # Assuming text_height is font_size
        char_width_factor = 0.6 # Arial-like
        # text_width_estimate = len(label_text) * font_size * char_width_factor # Not used directly here

        # Resolve offset_x, offset_y from various config formats
        offset_x_val, offset_y_val = (0.0, 0.0)
        if isinstance(offset_config, (int, float)):
            offset_x_val, offset_y_val = float(offset_config), float(offset_config)
        elif isinstance(offset_config, dict):
            offset_x_val = float(offset_config.get('x', 0.0))
            offset_y_val = float(offset_config.get('y', 0.0))
        elif isinstance(offset_config, (list, tuple)) and len(offset_config) >= 2:
            offset_x_val = float(offset_config[0])
            offset_y_val = float(offset_config[1])

        effective_offset_x = offset_x_val
        effective_offset_y = offset_y_val
        if offset_x_val == 0 and offset_y_val == 0 and text_height > 0: # Use default only if both are zero
            effective_offset_x = effective_offset_y = text_height * 0.5

        POSITION_MAP = {
            "right": (0, (1, 0)), "top-right": (45, (1, 1)), "top": (90, (0, 1)),
            "top-left": (135, (-1, 1)), "left": (180, (-1, 0)), "bottom-left": (225, (-1, -1)),
            "bottom": (270, (0, -1)), "bottom-right": (315, (1, -1))
        }

        candidate_positions: List[Tuple[Point, float, float]] = [] # (point, angle, score)

        if point_position_preference and point_position_preference.lower() in POSITION_MAP:
            angle, (dx, dy) = POSITION_MAP[point_position_preference.lower()]
            final_pos = self._apply_offset_to_point(point, dx * effective_offset_x, dy * effective_offset_y, angle=0) # Text angle is separate
            candidate_positions.append((final_pos, float(angle), 2.0))
        else:
            for angle_deg, (dx_norm, dy_norm) in POSITION_MAP.values():
                offset_point = Point(point.x + dx_norm * effective_offset_x, point.y + dy_norm * effective_offset_y)
                score = 1.0
                if dx_norm > 0: score += 0.5
                if dy_norm > 0: score += 0.3
                candidate_positions.append((offset_point, float(angle_deg), score))

        if not candidate_positions:
            return point, 0.0

        best_candidate = max(candidate_positions, key=lambda item: item[2])
        return best_candidate[0], best_candidate[1]


    # --- Candidate Generation & Evaluation Helpers (Batch 3) ---

    async def _get_text_dimensions(self, text: str, text_style_name: str, layer_name: str) -> Tuple[float, float]:
        """
        Retrieves the approximate width and height of a text string for a given style.
        This should ideally use the IStyleService to get font metrics.
        """
        if not self.style_service:
            logger.warning("StyleService not available for _get_text_dimensions. Returning estimated dimensions.")
            # Fallback to a very rough estimate if style service is not available
            # Average char width 0.5 * text height, text height is 1.0 unit by default
            # This needs to be significantly improved with actual font metrics.
            return len(text) * 0.5 * 1.0, 1.0

        text_style: Optional[ITextStyle] = await self.style_service.get_text_style_properties(text_style_name, layer_name)
        if not text_style or not text_style.font_properties:
            logger.warning(f"Text style '{text_style_name}' or its font properties not found for layer '{layer_name}'. Estimating dimensions.")
            return len(text) * 0.5 * (text_style.height if text_style and text_style.height and text_style.height > 0 else 1.0), \
                   (text_style.height if text_style and text_style.height and text_style.height > 0 else 1.0)

        # This is still a simplification. Actual text bounding box is complex.
        # TODO: Integrate with a more accurate text measurement (e.g., using ezdxf's font_manager or similar)
        char_width_approx = text_style.font_properties.cap_height * 0.6 # Very rough approximation
        if text_style.width_factor and text_style.width_factor > 0:
            char_width_approx *= text_style.width_factor

        text_height = text_style.height if text_style.height and text_style.height > 0 else text_style.font_properties.cap_height
        text_width = len(text) * char_width_approx
        return text_width, text_height

    def _calculate_label_box(self, anchor_point: Point, text_width: float, text_height: float, angle_deg: float,
                             alignment_point: int = 7) -> Polygon:
        """
        Calculates the bounding box of a label given its anchor point, dimensions, angle, and alignment.
        Alignment point follows DXF MTEXT attachment points (1-9).
        1: TopLeft, 2: TopCenter, 3: TopRight
        4: MiddleLeft, 5: MiddleCenter, 6: MiddleRight
        7: BottomLeft, 8: BottomCenter, 9: BottomRight
        """
        # Create a basic horizontal box at origin
        half_w, half_h = text_width / 2.0, text_height / 2.0

        if alignment_point == 1:  # TopLeft
            dx, dy = half_w, -half_h
        elif alignment_point == 2:  # TopCenter
            dx, dy = 0, -half_h
        elif alignment_point == 3:  # TopRight
            dx, dy = -half_w, -half_h
        elif alignment_point == 4:  # MiddleLeft
            dx, dy = half_w, 0
        elif alignment_point == 5:  # MiddleCenter
            dx, dy = 0, 0
        elif alignment_point == 6:  # MiddleRight
            dx, dy = -half_w, 0
        elif alignment_point == 7:  # BottomLeft (Default)
            dx, dy = half_w, half_h
        elif alignment_point == 8:  # BottomCenter
            dx, dy = 0, half_h
        elif alignment_point == 9:  # BottomRight
            dx, dy = -half_w, half_h
        else: # Default to BottomLeft (MTEXT default)
            dx, dy = half_w, half_h

        # Create corners relative to the alignment point adjusted box center
        corners = [
            (-half_w + dx, -half_h + dy),  # Bottom-left
            ( half_w + dx, -half_h + dy),  # Bottom-right
            ( half_w + dx,  half_h + dy),  # Top-right
            (-half_w + dx,  half_h + dy)   # Top-left
        ]
        box = Polygon(corners)

        # Rotate box around the relative (0,0) which is its alignment-adjusted center
        box = rotate(box, angle_deg, origin=(dx, dy), use_radians=False)
        # Translate box to the actual anchor_point
        box = translate(box, xoff=anchor_point.x - dx, yoff=anchor_point.y - dy)
        return box

    def _check_collision(self, label_box: Polygon,
                         obstacles: List[Union[Polygon, LineString, Point]],
                         prepared_obstacles: Optional[List[Any]] = None) -> bool: # Any for PreparedGeometry
        """Checks if the label_box collides with any of the obstacles."""
        if prepared_obstacles:
            for prep_obstacle in prepared_obstacles:
                if prep_obstacle.intersects(label_box): # intersects is fast for prepared geometries
                    return True
        else:
            for obstacle in obstacles:
                if label_box.intersects(obstacle):
                    return True
        return False

    def _is_label_inside_polygon(self, label_box: Polygon, feature_polygon: Polygon,
                                 prepared_feature_polygon: Optional[Any] = None) -> bool: # Any for PreparedGeometry
        """Checks if the label_box is entirely within the feature_polygon."""
        # A simple containment check. May need to be more sophisticated (e.g., area of intersection).
        if prepared_feature_polygon:
            return prepared_feature_polygon.contains(label_box)
        return feature_polygon.contains(label_box)

    def _evaluate_candidate_position(
        self,
        label_text: str,
        anchor_point: Point,
        angle_deg: float,
        text_style_name: str, # For _get_text_dimensions
        layer_name: str,      # For _get_text_dimensions
        feature_geom: Union[Point, LineString, Polygon, MultiPolygon],
        config: LabelSettings,
        placed_labels_boxes: List[Polygon], # BBoxes of already placed labels
        avoidance_geometries: List[Union[Polygon, LineString, Point]], # Other fixed obstacles
        prepared_feature_geom: Optional[Any] = None, # Prepared version of feature_geom if polygon
        prepared_avoidance: Optional[List[Any]] = None # Prepared versions of avoidance_geometries
    ) -> Optional[Tuple[Polygon, float]]: # Returns (label_box, score) or None if invalid
        """
        Evaluates a single candidate label position.
        Returns the label_box and a score if valid, otherwise None.
        Score is higher for better placements.
        """
        # This method will be significantly expanded.
        # For now, a basic implementation.

        # 1. Get text dimensions (async part needs to be handled carefully if called from sync context)
        #    For now, assuming this service method might become async or this helper is called from an async context.
        #    If _get_text_dimensions remains async, this method needs to be async too.
        #    Let's assume for now it's refactored to be callable or style_service is pre-loaded.
        #    For initial structure, we'll call it and deal with async nature later.
        # text_width, text_height = await self._get_text_dimensions(label_text, text_style_name, layer_name)
        # Placeholder for synchronous adaptation or if style_service calls are made sync
        text_width, text_height = 0.0, 0.0 # Placeholder - this MUST be replaced
        if self.style_service:
             # This is a simplification - in reality, we'd need to ensure style_service.get_text_style_properties
             # is either sync or this whole evaluation chain is async.
             # For now, to avoid making this whole method async immediately:
            try:
                # Attempt a simplified, potentially synchronous-compatible fetch or estimation
                # This is a conceptual placeholder. A real solution needs careful async/sync handling.
                # For now, let's assume a sync estimation is possible.
                text_style = self.style_service.get_cached_text_style(text_style_name, layer_name) # Fictional sync method
                if text_style and text_style.height and text_style.height > 0 :
                    text_height = text_style.height
                    text_width = len(label_text) * text_height * 0.6 * (text_style.width_factor or 1.0) # Rough
                else: # Fallback if not found or no height
                    text_height = 1.0 # Default height
                    text_width = len(label_text) * 0.6 # Rough
            except Exception: # Broad except for placeholder
                 text_height = 1.0 # Default height
                 text_width = len(label_text) * 0.6 # Rough
        else: # Fallback if no style service
            text_height = 1.0 # Default height
            text_width = len(label_text) * 0.6 # Rough

        if text_width == 0 or text_height == 0: # Should not happen with fallbacks
            logger.warning(f"Could not determine text dimensions for '{label_text}' with style '{text_style_name}'. Skipping.")
            return None


        # 2. Calculate label bounding box
        #    Use config.label_alignment_point if available, otherwise default (e.g., 7 for BottomLeft)
        alignment_point = getattr(config, 'label_alignment_point', 7)
        label_box = self._calculate_label_box(anchor_point, text_width, text_height, angle_deg, alignment_point)

        # 3. Collision checks
        # 3a. Check collision with already placed labels
        if self._check_collision(label_box, placed_labels_boxes): # No need for prepared for this dynamic list
            return None

        # 3b. Check collision with fixed avoidance geometries
        if self._check_collision(label_box, avoidance_geometries, prepared_avoidance):
            return None

        # 4. Placement constraints (e.g., inside parent polygon for polygon labels)
        if isinstance(feature_geom, (Polygon, MultiPolygon)):
            # For MultiPolygon, check if it's inside ANY of its constituent polygons.
            # This could be refined (e.g., prefer placement in the largest polygon part).
            is_inside = False
            if isinstance(feature_geom, MultiPolygon):
                target_polygons = list(feature_geom.geoms)
            else: # Single Polygon
                target_polygons = [feature_geom]

            for poly_part in target_polygons:
                # Use prepared geometry if available for the specific part (if MultiPolygon prepared element-wise)
                # This part of logic needs careful handling of prepared_feature_geom for MultiPolygons.
                # For simplicity, assuming prepared_feature_geom is for the dominant polygon or handled externally.
                current_prepared_poly = None
                if prepared_feature_geom:
                    # This is tricky: prepared_feature_geom might be a single prepared Polygon
                    # or a list of them if MultiPolygon. Assume single for now.
                    # TODO: Refine for MultiPolygon and list of prepared geometries
                    if not isinstance(feature_geom, MultiPolygon): # Only use if original was single Polygon
                         current_prepared_poly = prepared_feature_geom

                if self._is_label_inside_polygon(label_box, poly_part, current_prepared_poly):
                    # Check if label is 'too far' from boundary if configured (label_must_touch_boundary)
                    if getattr(config, 'label_must_touch_boundary', False) and isinstance(poly_part, Polygon):
                        # Check if label_box intersects or is very close to the boundary of poly_part
                        # This is a simplistic check; distance to boundary might be better.
                        if not label_box.intersects(poly_part.boundary):
                            continue # Skip if it must touch boundary and doesn't

                    # Check for minimum inside area/percentage if configured
                    min_inside_area_ratio = getattr(config, 'min_label_area_inside_percent', 100.0)
                    if min_inside_area_ratio < 100.0:
                        intersection_area = label_box.intersection(poly_part).area
                        if (intersection_area / label_box.area) * 100.0 < min_inside_area_ratio:
                            continue # Not enough of the label is inside this part

                    is_inside = True
                    break # Found a suitable polygon part

            if not is_inside:
                return None

        # 5. Calculate score (placeholder, higher is better)
        #    Score could depend on:
        #    - Proximity to preferred anchor (e.g. centroid for polygons, middle for lines)
        #    - Alignment with line segments
        #    - Distance from other labels (already incorporated by collision check, but could be a soft penalty)
        #    - Curvature (for lines, penalize placement on highly curved segments if label is straight)
        #    - etc.
        score = 1.0 # Default score for any valid placement

        # Example: Penalize if label box is not fully contained for polygons (even if partially allowed)
        if isinstance(feature_geom, (Polygon, MultiPolygon)):
            # This check is somewhat redundant if _is_label_inside_polygon requires full containment
            # and min_inside_area_ratio is 100.
            # However, if partial placement is allowed, this can refine the score.
            if not label_box.within(feature_geom): # within is stricter than contains for the label_box
                # If partial overlap is allowed by config, reduce score
                if getattr(config, 'min_label_area_inside_percent', 100.0) < 100.0:
                    score *= 0.8 # Penalty for not being fully within
                else: # Should have been caught by _is_label_inside_polygon if 100% required
                    pass


        # TODO: Add more sophisticated scoring based on config and feature type.
        # For example, for lines, score based on alignment with segment, distance from ends.
        # For points, score based on preferred offset quadrant.

        return label_box, score


    # --- Main Service Method ---
