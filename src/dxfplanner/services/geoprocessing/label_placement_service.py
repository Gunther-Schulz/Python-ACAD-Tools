from typing import AsyncIterator, Optional, Tuple, Union
from logging import Logger
import math

from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString, Polygon as ShapelyPolygon
# from shapely.wkb import loads as shapely_loads # REMOVED - No longer used
from shapely.errors import GEOSException

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo, PolylineGeo, PolygonGeo # ADDED PointGeo, PolylineGeo, PolygonGeo
from dxfplanner.domain.interfaces import ILabelPlacementService, PlacedLabel
from dxfplanner.config.style_schemas import LabelingConfig, TextStylePropertiesConfig # For type hints
from dxfplanner.core.logging_config import get_logger # For default logger

# Default logger for the module if not injected
default_logger = get_logger(__name__)

class LabelPlacementService(ILabelPlacementService):
    """
    A simple label placement service.
    - Point features: Label placed at the point's coordinates.
    - Line features: Label placed at the line's midpoint, rotated to the segment's angle.
    - Polygon features: Label placed at the polygon's representative point (guaranteed inside).
    Offsets and text rotation from config are applied. No collision detection.
    """

    def __init__(self, logger: Optional[Logger] = None):
        self.logger = logger or default_logger
        self.logger.info("LabelPlacementService initialized.")

    async def place_labels_for_features(
        self,
        features: AsyncIterator[GeoFeature],
        layer_name: str, # For context, logging
        config: LabelingConfig,
        text_style_properties: TextStylePropertiesConfig,
    ) -> AsyncIterator[PlacedLabel]:
        if not config.enabled:
            self.logger.debug(f"Labeling disabled for layer '{layer_name}' via LabelingConfig.enabled=False.")
            return

        self.logger.info(f"LabelPlacementService: Starting label placement for layer '{layer_name}'. Label attr: '{config.label_attribute}', Fixed text: '{config.fixed_text}'") # DEBUG
        feature_count = 0 # DEBUG
        async for feature in features:
            feature_count += 1 # DEBUG
            self.logger.debug(f"LabelPlacementService: Processing feature #{feature_count}, ID: {feature.id or 'N/A'}, Properties: {feature.properties}") # INFO to DEBUG

            label_text: Optional[str] = None
            if config.fixed_text:
                label_text = config.fixed_text
            elif config.label_attribute:
                label_text = feature.properties.get(config.label_attribute)
                if label_text is not None:
                    label_text = str(label_text)
                else:
                    self.logger.warning(f"LabelPlacementService: Label attribute '{config.label_attribute}' not found or is None in feature {feature.id or 'N/A'}. Skipping.") # DEBUG
                    continue
            else:
                self.logger.warning(f"LabelPlacementService: Neither fixed_text nor label_attribute for layer '{layer_name}'. Skipping feature {feature.id or 'N/A'}.") # DEBUG
                continue

            self.logger.debug(f"LabelPlacementService: Determined label_text: '{label_text}' for feature {feature.id or 'N/A'}.") # INFO to DEBUG
            if not label_text:
                self.logger.debug(f"LabelPlacementService: Empty label text for feature {feature.id or 'N/A'}. Skipping.") # INFO to DEBUG
                continue

            if feature.geometry is None:
                self.logger.warning(f"LabelPlacementService: Feature {feature.id or 'N/A'} has no geometry. Skipping.") # DEBUG
                continue

            shapely_geom: Optional[Union[ShapelyPoint, ShapelyLineString, ShapelyPolygon]] = None
            try:
                if isinstance(feature.geometry, PointGeo):
                    coords = feature.geometry.coordinates
                    shapely_geom = ShapelyPoint(coords.x, coords.y) if coords.z is None else ShapelyPoint(coords.x, coords.y, coords.z)
                elif isinstance(feature.geometry, PolylineGeo):
                    shapely_coords = [(c.x, c.y) if c.z is None else (c.x, c.y, c.z) for c in feature.geometry.coordinates]
                    if shapely_coords:
                        shapely_geom = ShapelyLineString(shapely_coords)
                    else:
                        self.logger.debug(f"LabelPlacementService: PolylineGeo for feature {feature.id or 'N/A'} has empty coordinates. Skipping.") # DEBUG
                        continue
                elif isinstance(feature.geometry, PolygonGeo):
                    exterior_coords = [(c.x, c.y) if c.z is None else (c.x, c.y, c.z) for c in feature.geometry.coordinates[0]]
                    interior_coords_list = [
                        [(c.x, c.y) if c.z is None else (c.x, c.y, c.z) for c in interior_ring]
                        for interior_ring in feature.geometry.coordinates[1:]
                    ]
                    if exterior_coords:
                        shapely_geom = ShapelyPolygon(exterior_coords, holes=interior_coords_list if interior_coords_list else None)
                        self.logger.debug(f"LabelPlacementService: Constructed ShapelyPolygon for feature {feature.id or 'N/A'}. IsValid: {shapely_geom.is_valid}, IsEmpty: {shapely_geom.is_empty}") # INFO to DEBUG
                    else:
                        self.logger.debug(f"LabelPlacementService: PolygonGeo for feature {feature.id or 'N/A'} has empty exterior ring. Skipping.") # DEBUG
                        continue
                else:
                    self.logger.warning(f"LabelPlacementService: Unsupported Pydantic geometry type '{type(feature.geometry).__name__}' for feature {feature.id or 'N/A'}. Skipping.") # DEBUG
                    continue

                if shapely_geom is None:
                    self.logger.warning(f"LabelPlacementService: Shapely_geom is None after construction for feature {feature.id or 'N/A'}. Skipping.") # INFO to DEBUG
                    continue

            except Exception as e_construct:
                self.logger.error(f"LabelPlacementService: Error constructing Shapely geometry for feature {feature.id or 'N/A'}: {e_construct}. Skipping.") # DEBUG
                continue

            anchor_point: Optional[Tuple[float, float]] = None
            geometry_rotation_degrees: float = 0.0

            if isinstance(shapely_geom, ShapelyPoint):
                anchor_point = (shapely_geom.x, shapely_geom.y)
            elif isinstance(shapely_geom, ShapelyLineString):
                if shapely_geom.is_empty or shapely_geom.length == 0:
                    self.logger.debug(f"LineString for feature {feature.id or 'N/A'} is empty or has zero length. Cannot place label.")
                    continue
                midpoint = shapely_geom.interpolate(0.5, normalized=True)
                anchor_point = (midpoint.x, midpoint.y)

                try:
                    coords = list(shapely_geom.coords)
                    if len(coords) >= 2:
                        p1 = None
                        p2 = None
                        if len(coords) == 2:
                             p1, p2 = coords[0], coords[1]
                        else: # len(coords) > 2
                            mid_idx = len(coords) // 2
                            p1 = coords[mid_idx - 1]
                            p2 = coords[mid_idx]

                        if p1 and p2:
                            dx = p2[0] - p1[0]
                            dy = p2[1] - p1[1]
                            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                                geometry_rotation_degrees = math.degrees(math.atan2(dy, dx))
                except Exception as e_rot:
                    self.logger.warning(f"Could not determine rotation for LineString feature {feature.id or 'N/A'}: {e_rot}")

            elif isinstance(shapely_geom, ShapelyPolygon):
                if shapely_geom.is_empty:
                    self.logger.debug(f"LabelPlacementService: Polygon for feature {feature.id or 'N/A'} is empty. Cannot place label.") # DEBUG
                    continue
                try:
                    if not shapely_geom.is_valid:
                        self.logger.debug(f"LabelPlacementService: Polygon for feature {feature.id or 'N/A'} is invalid. Attempting buffer(0).") # INFO to DEBUG
                        shapely_geom_buffered = shapely_geom.buffer(0) # Use new var
                        if not shapely_geom_buffered.is_valid or shapely_geom_buffered.is_empty or not isinstance(shapely_geom_buffered, ShapelyPolygon) :
                             self.logger.warning(f"LabelPlacementService: Polygon for feature {feature.id or 'N/A'} buffer(0) failed or resulted in non-polygon/empty. Valid: {shapely_geom_buffered.is_valid}, Empty: {shapely_geom_buffered.is_empty}, Type: {type(shapely_geom_buffered)}. Skipping label.") # DEBUG
                             continue
                        shapely_geom = shapely_geom_buffered # Assign back if successful
                        self.logger.debug(f"LabelPlacementService: Polygon for feature {feature.id or 'N/A'} after buffer(0). IsValid: {shapely_geom.is_valid}, IsEmpty: {shapely_geom.is_empty}") # INFO to DEBUG

                    # Ensure it's still a polygon and not empty after potential buffer.
                    if not isinstance(shapely_geom, ShapelyPolygon) or shapely_geom.is_empty:
                        self.logger.warning(f"LabelPlacementService: Feature {feature.id or 'N/A'} geometry became non-polygon or empty. Skipping label.") # DEBUG
                        continue

                    rp = shapely_geom.representative_point()
                    anchor_point = (rp.x, rp.y)
                    self.logger.debug(f"LabelPlacementService: Anchor point (rep_point) for feature {feature.id or 'N/A'}: {anchor_point}") # INFO to DEBUG
                except GEOSException as e_rp:
                    self.logger.error(f"LabelPlacementService: GEOSException for representative_point on feature {feature.id or 'N/A'}: {e_rp}. Trying centroid.") # DEBUG
                    try:
                        centroid = shapely_geom.centroid
                        anchor_point = (centroid.x, centroid.y)
                        self.logger.debug(f"LabelPlacementService: Anchor point (centroid) for feature {feature.id or 'N/A'}: {anchor_point}") # INFO to DEBUG
                    except Exception as e_cent:
                        self.logger.error(f"LabelPlacementService: Centroid failed for feature {feature.id or 'N/A'}: {e_cent}. Skipping.") # DEBUG
                        continue
                except Exception as e_gen_poly:
                    self.logger.error(f"LabelPlacementService: Unexpected error processing polygon for feature {feature.id or 'N/A'}: {e_gen_poly}. Skipping.") # DEBUG
                    continue
            else:
                self.logger.warning(f"LabelPlacementService: Unsupported Shapely geometry type '{shapely_geom.geom_type}' for feature {feature.id or 'N/A'}. Skipping.") # DEBUG
                continue

            if anchor_point is None:
                self.logger.debug(f"LabelPlacementService: Could not determine anchor point for feature {feature.id or 'N/A'}. Skipping label.") # INFO to DEBUG
                continue

            final_x = anchor_point[0] + (config.offset_xy[0] if config.offset_xy else 0.0)
            final_y = anchor_point[1] + (config.offset_xy[1] if config.offset_xy else 0.0)

            final_rotation_degrees = geometry_rotation_degrees + (text_style_properties.rotation_degrees or 0.0)
            final_rotation_degrees %= 360

            final_z = shapely_geom.z if hasattr(shapely_geom, 'z') and isinstance(shapely_geom, ShapelyPoint) else 0.0

            placed_label = PlacedLabel(
                text=label_text,
                position=Coordinate(x=final_x, y=final_y, z=final_z),
                rotation=final_rotation_degrees
            )
            self.logger.debug(f"LabelPlacementService: Yielding PlacedLabel for feature {feature.id or 'N/A'}: Text='{label_text}', Pos=({final_x:.2f},{final_y:.2f}), Rot={final_rotation_degrees:.2f}") # INFO to DEBUG
            yield placed_label
        self.logger.info(f"LabelPlacementService: Finished processing all {feature_count} features for layer '{layer_name}'.") # DEBUG
