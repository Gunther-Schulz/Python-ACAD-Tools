from typing import AsyncIterator, Optional, Tuple
from logging import Logger
import math

from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString, Polygon as ShapelyPolygon
from shapely.wkb import loads as shapely_loads
from shapely.errors import GEOSException

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo, PolylineGeo, PolygonGeo
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

        self.logger.debug(f"Starting label placement for layer '{layer_name}'. Label attr: '{config.label_attribute}', Fixed text: '{config.fixed_text}'")

        async for feature in features:
            label_text: Optional[str] = None
            if config.fixed_text:
                label_text = config.fixed_text
            elif config.label_attribute:
                label_text = feature.attributes.get(config.label_attribute)
                if label_text is not None:
                    label_text = str(label_text) # Ensure string
                else:
                    self.logger.warning(f"Label attribute '{config.label_attribute}' not found or is None in feature {feature.id or 'N/A'} attributes: {feature.attributes}. Skipping label.")
                    continue
            else:
                self.logger.warning(f"Neither fixed_text nor label_attribute specified in LabelingConfig for layer '{layer_name}'. Skipping label for feature {feature.id or 'N/A'}.")
                continue

            if not label_text: # Handles case where attribute exists but is empty string, or fixed_text is empty
                self.logger.debug(f"Empty label text for feature {feature.id or 'N/A'} on layer '{layer_name}'. Skipping label.")
                continue

            if feature.geometry is None or feature.geometry.wkb is None:
                self.logger.warning(f"Feature {feature.id or 'N/A'} has no WKB geometry. Skipping label placement.")
                continue

            try:
                shapely_geom = shapely_loads(feature.geometry.wkb)
            except GEOSException as e:
                self.logger.error(f"Failed to load WKB geometry for feature {feature.id or 'N/A'}: {e}. Skipping label placement.")
                continue
            except Exception as e_gen: # Catch other potential errors during WKB loading
                self.logger.error(f"Unexpected error loading WKB for feature {feature.id or 'N/A'}: {e_gen}. Skipping label placement.")
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
                    self.logger.debug(f"Polygon for feature {feature.id or 'N/A'} is empty. Cannot place label.")
                    continue
                try:
                    if not shapely_geom.is_valid:
                        self.logger.debug(f"Polygon for feature {feature.id or 'N/A'} is invalid. Attempting to buffer by 0.")
                        shapely_geom = shapely_geom.buffer(0)
                        if not shapely_geom.is_valid or shapely_geom.is_empty:
                             self.logger.warning(f"Polygon for feature {feature.id or 'N/A'} could not be made valid or became empty. Skipping label.")
                             continue

                    if not isinstance(shapely_geom, ShapelyPolygon) or shapely_geom.is_empty:
                        self.logger.warning(f"Polygon for feature {feature.id or 'N/A'} became non-polygon or empty after buffer(0). Skipping label.")
                        continue

                    rp = shapely_geom.representative_point()
                    anchor_point = (rp.x, rp.y)
                except GEOSException as e_rp:
                    self.logger.error(f"GEOSException during representative_point for feature {feature.id or 'N/A'}: {e_rp}. Trying centroid.")
                    try:
                        centroid = shapely_geom.centroid
                        anchor_point = (centroid.x, centroid.y)
                    except Exception as e_cent:
                        self.logger.error(f"Failed to get centroid after representative_point failed for feature {feature.id or 'N/A'}: {e_cent}. Skipping.")
                        continue
                except Exception as e_gen_poly:
                    self.logger.error(f"Unexpected error processing polygon for feature {feature.id or 'N/A'}: {e_gen_poly}. Skipping.")
                    continue

            else:
                self.logger.warning(f"Unsupported geometry type '{shapely_geom.geom_type}' for feature {feature.id or 'N/A'}. Skipping label placement.")
                continue

            if anchor_point is None:
                self.logger.debug(f"Could not determine anchor point for feature {feature.id or 'N/A'}. Skipping label.")
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
            self.logger.debug(f"Placed label for feature {feature.id or 'N/A'}: Text='{label_text}', Pos=({final_x:.2f},{final_y:.2f}), Rot={final_rotation_degrees:.2f}")
            yield placed_label
