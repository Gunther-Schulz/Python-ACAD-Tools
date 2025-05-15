# src/dxfplanner/geometry/transformations.py
from typing import List, Optional, Union, Any, Dict, Tuple, AsyncIterator
import math
import asyncio

from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString, Polygon as ShapelyPolygon
from shapely.ops import transform as shapely_transform_op

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPolygonGeo, GeometryCollectionGeo, AnyGeoGeometry
from dxfplanner.domain.models.dxf_models import AnyDxfEntity, DxfLine, DxfLWPolyline, DxfHatch, DxfHatchPath, DxfMText, DxfText, DxfInsert, DxfArc, DxfCircle # Added DxfMText, DxfLine, DxfInsert etc.
from dxfplanner.domain.operations import OperationType, TransformGeometryOperationConfig, CreateBufferOperationConfig, CreateLabelsOperationConfig
from dxfplanner.domain.interfaces import IGeometryTransformer, ICoordinateService
from dxfplanner.services.style_service import StyleService, StyleObjectConfig
from dxfplanner.config.schemas import (
    LayerConfig,
    OperationsConfig,
    LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig,
    HatchPropertiesConfig,
    TextParagraphPropertiesConfig,
    ColorModel
)
from dxfplanner.core.exceptions import GeometryTransformationError, ConfigurationError
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.utils import (
    convert_shapely_to_anygeogeometry,
    create_dxf_hatch_paths,
    get_dominant_geometry_type,
    is_multi_part_shapely_geometry,
    get_feature_bounds_string,
    calculate_mtext_width_for_content
)

logger = get_logger(__name__)

class GeometryTransformerImpl(IGeometryTransformer):
    def __init__(self, style_service: StyleService, default_text_height: float = 2.5):
        self.style_service = style_service
        self.default_text_height = default_text_height
        self.logger = get_logger(__name__)

    async def transform_feature_to_dxf_entities(
        self, feature: GeoFeature, layer_config: LayerConfig
    ) -> AsyncIterator[AnyDxfEntity]:
        self.logger.debug(f"Transforming feature ID {feature.id or 'N/A'} for layer '{layer_config.name}' using direct style application.")

        style_config: StyleObjectConfig = self.style_service.get_resolved_style_for_feature(
            layer_config=layer_config,
            feature_attributes=feature.properties
        )
        self.logger.debug(f"Resolved style for feature {feature.id or 'N/A'} on layer {layer_config.name}: {style_config.model_dump_json(exclude_none=True, indent=2)}")

        base_dxf_attrs = self._extract_base_dxf_attrs(style_config, feature.properties)
        target_layer_name = layer_config.name

        if isinstance(feature.geometry, PointGeo):
            async for entity in self._point_to_dxf_text_or_insert(feature.geometry, feature.properties, style_config, base_dxf_attrs, target_layer_name):
                yield entity
        elif isinstance(feature.geometry, PolylineGeo):
            async for entity in self._polyline_to_dxf_entities(feature.geometry, feature.properties, style_config, base_dxf_attrs, target_layer_name):
                yield entity
        elif isinstance(feature.geometry, PolygonGeo):
            async for entity in self._polygon_to_dxf_entities(feature.geometry, feature.properties, style_config, base_dxf_attrs, target_layer_name):
                yield entity
        elif isinstance(feature.geometry, MultiPolygonGeo):
            for polygon_geo in feature.geometry.geometries:
                async for entity in self._polygon_to_dxf_entities(polygon_geo, feature.properties, style_config, base_dxf_attrs, target_layer_name):
                    yield entity
        elif isinstance(feature.geometry, GeometryCollectionGeo):
            for geom_item in feature.geometry.geometries:
                temp_feature = GeoFeature(geometry=geom_item, properties=feature.properties, crs=feature.crs)
                async for entity in self.transform_feature_to_dxf_entities(temp_feature, layer_config):
                    yield entity
        else:
            self.logger.warning(f"Unsupported geometry type: {type(feature.geometry)} for feature ID {feature.id or 'N/A'} on layer {target_layer_name}")

    def _extract_base_dxf_attrs(self, style_config: StyleObjectConfig, feature_props: Dict[str, Any]) -> dict:
        attrs = {'attributes': feature_props}
        if style_config.layer_props:
            lp = style_config.layer_props
            if isinstance(lp.color, int):
                attrs['color_256'] = lp.color
            elif isinstance(lp.color, tuple) and len(lp.color) == 3 and all(isinstance(c, int) for c in lp.color):
                attrs['true_color'] = lp.color
            elif isinstance(lp.color, str):
                if lp.color.upper() == "BYLAYER": attrs['color_256'] = 256
                elif lp.color.upper() == "BYBLOCK": attrs['color_256'] = 0
            attrs['linetype'] = lp.linetype
            attrs['lineweight'] = lp.lineweight
            attrs['transparency'] = lp.transparency
            attrs['ltscale'] = lp.linetype_scale
            attrs['visible'] = lp.is_on
        return attrs

    def _apply_base_style_to_entity(self, entity: AnyDxfEntity, base_attrs: dict, layer_name: str):
        entity.layer = layer_name
        entity.attributes = base_attrs.get('attributes', entity.attributes)

        if 'color_256' in base_attrs:
            entity.color_256 = base_attrs['color_256']
        if 'true_color' in base_attrs:
            entity.true_color = base_attrs['true_color']

        entity.linetype = base_attrs.get('linetype', entity.linetype)
        entity.lineweight = base_attrs.get('lineweight', entity.lineweight)
        entity.transparency = base_attrs.get('transparency', entity.transparency)
        entity.ltscale = base_attrs.get('ltscale', entity.ltscale)
        entity.visible = base_attrs.get('visible', entity.visible)

    async def _point_to_dxf_circle(
        self, point: PointGeo, properties: Dict[str, Any], style_config: StyleObjectConfig, base_dxf_attrs: dict, layer_name: str
    ) -> AsyncIterator[AnyDxfEntity]:
        self.logger.debug(f"Attempting to create DxfCircle for point on layer {layer_name} from attributes: {properties}")
        try:
            radius = float(properties.get("radius"))
            if radius <= 0:
                self.logger.warning(f"Invalid radius {radius} for DxfCircle on layer {layer_name}. Skipping.")
                return
        except (TypeError, ValueError):
            self.logger.warning(f"Radius attribute for DxfCircle on layer {layer_name} is missing or not a valid number: {properties.get('radius')}. Skipping.")
            return

        circle = DxfCircle(
            center=Coordinate(x=point.x, y=point.y, z=point.z if point.z is not None else 0.0),
            radius=radius,
        )
        self._apply_base_style_to_entity(circle, base_dxf_attrs, layer_name)
        # Apply specific styling from text_props if relevant (e.g. color)
        tp = style_config.text_props # Assuming general point styling might be in text_props
        if tp and tp.color:
            if isinstance(tp.color, int): circle.color_256 = tp.color
            elif isinstance(tp.color, tuple) and len(tp.color) == 3: circle.true_color = tp.color

        yield circle
        self.logger.info(f"Successfully created DxfCircle on layer {layer_name} with center ({point.x},{point.y}) and radius {radius}")
        await asyncio.sleep(0)

    async def _point_to_dxf_arc(
        self, point: PointGeo, properties: Dict[str, Any], style_config: StyleObjectConfig, base_dxf_attrs: dict, layer_name: str
    ) -> AsyncIterator[AnyDxfEntity]:
        self.logger.debug(f"Attempting to create DxfArc for point on layer {layer_name} from attributes: {properties}")
        try:
            radius = float(properties.get("radius"))
            start_angle = float(properties.get("start_angle"))
            end_angle = float(properties.get("end_angle"))
            if radius <= 0:
                self.logger.warning(f"Invalid radius {radius} for DxfArc on layer {layer_name}. Skipping.")
                return
        except (TypeError, ValueError):
            self.logger.warning(
                f"Arc attributes (radius, start_angle, end_angle) on layer {layer_name} are missing or not valid numbers. "
                f"Radius: {properties.get('radius')}, Start: {properties.get('start_angle')}, End: {properties.get('end_angle')}. Skipping."
            )
            return

        arc = DxfArc(
            center=Coordinate(x=point.x, y=point.y, z=point.z if point.z is not None else 0.0),
            radius=radius,
            start_angle=start_angle,
            end_angle=end_angle,
        )
        self._apply_base_style_to_entity(arc, base_dxf_attrs, layer_name)
        tp = style_config.text_props # Assuming general point styling might be in text_props
        if tp and tp.color:
            if isinstance(tp.color, int): arc.color_256 = tp.color
            elif isinstance(tp.color, tuple) and len(tp.color) == 3: arc.true_color = tp.color

        yield arc
        self.logger.info(f"Successfully created DxfArc on layer {layer_name} with center ({point.x},{point.y}), radius {radius}, angles ({start_angle}, {end_angle})")
        await asyncio.sleep(0)

    async def _point_to_dxf_text_or_insert(
        self, point: PointGeo, properties: Dict[str, Any], style_config: StyleObjectConfig, base_dxf_attrs: dict, layer_name: str
    ) -> AsyncIterator[AnyDxfEntity]:
        # Check for custom entity types like Circle or Arc first
        entity_type_attr = properties.get("dxf_entity_type")
        if entity_type_attr == "circle":
            async for entity in self._point_to_dxf_circle(point, properties, style_config, base_dxf_attrs, layer_name):
                yield entity
            return # Important to return after handling
        elif entity_type_attr == "arc":
            async for entity in self._point_to_dxf_arc(point, properties, style_config, base_dxf_attrs, layer_name):
                yield entity
            return # Important to return after handling

        tp = style_config.text_props
        text_content = None
        if tp:
            if tp.fixed_label_text:
                text_content = tp.fixed_label_text
            elif tp.label_attribute and tp.label_attribute in properties:
                text_content = str(properties[tp.label_attribute])

        if tp and tp.insert_block_name:
            insert = DxfInsert(
                block_name=tp.insert_block_name,
                insertion_point=Coordinate(x=point.x, y=point.y, z=point.z if point.z is not None else 0.0),
                x_scale=tp.insert_block_scale if tp.insert_block_scale is not None else 1.0,
                y_scale=tp.insert_block_scale if tp.insert_block_scale is not None else 1.0,
                z_scale=tp.insert_block_scale if tp.insert_block_scale is not None else 1.0,
                rotation=tp.rotation if tp.rotation is not None else 0.0,
            )
            self._apply_base_style_to_entity(insert, base_dxf_attrs, layer_name)
            if tp.color:
                if isinstance(tp.color, int): insert.color_256 = tp.color
                elif isinstance(tp.color, tuple) and len(tp.color) == 3: insert.true_color = tp.color
            yield insert
        elif text_content and tp:
            mtext = DxfMText(
                insertion_point=Coordinate(x=point.x, y=point.y, z=point.z if point.z is not None else 0.0),
                text_content=text_content,
                char_height=tp.height if tp.height is not None else self.default_text_height,
                width=tp.mtext_width,
                rotation=tp.rotation if tp.rotation is not None else 0.0,
                style=tp.font,
                attachment_point=tp.attachment_point,
                flow_direction=tp.flow_direction,
                line_spacing_style=tp.line_spacing_style,
                line_spacing_factor=tp.line_spacing_factor,
                bg_fill_enabled=tp.bg_fill_enabled,
                bg_fill_color=tp.bg_fill_color,
                width_factor=tp.width_factor,
                oblique_angle=tp.oblique_angle,
            )
            self._apply_base_style_to_entity(mtext, base_dxf_attrs, layer_name)
            if tp.color:
                if isinstance(tp.color, int): mtext.color_256 = tp.color
                elif isinstance(tp.color, tuple) and len(tp.color) == 3: mtext.true_color = tp.color
            yield mtext
        else:
            self.logger.debug(f"Point feature at ({point.x},{point.y}) on layer {layer_name} did not yield DXF entity based on style/attributes.")
        await asyncio.sleep(0)

    async def _polyline_to_dxf_entities(
        self, polyline: PolylineGeo, properties: Dict[str, Any], style_config: StyleObjectConfig, base_dxf_attrs: dict, layer_name: str
    ) -> AsyncIterator[AnyDxfEntity]:
        if not polyline.coordinates or len(polyline.coordinates) < 2:
            self.logger.warning(f"Polyline on layer {layer_name} with < 2 coordinates. Skipping.")
            return
        coords = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 else 0.0) for c in polyline.coordinates]
        is_closed = coords[0] == coords[-1] if coords else False

        lwpoly = DxfLWPolyline(points=coords, is_closed=is_closed)
        self._apply_base_style_to_entity(lwpoly, base_dxf_attrs, layer_name)
        yield lwpoly
        await asyncio.sleep(0)

    async def _polygon_to_dxf_entities(
        self, polygon: PolygonGeo, properties: Dict[str, Any], style_config: StyleObjectConfig, base_dxf_attrs: dict, layer_name: str
    ) -> AsyncIterator[AnyDxfEntity]:
        if not polygon.shell or len(polygon.shell) < 3:
            self.logger.warning(f"Polygon on layer {layer_name} with shell < 3 coordinates. Skipping.")
            return

        shell_coords = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 else 0.0) for c in polygon.shell]
        if shell_coords[0] != shell_coords[-1]:
            shell_coords.append(shell_coords[0])

        if base_dxf_attrs.get('visible', True):
            boundary_poly = DxfLWPolyline(points=shell_coords, is_closed=True)
            self._apply_base_style_to_entity(boundary_poly, base_dxf_attrs, layer_name)
            yield boundary_poly

        hole_paths_for_hatch: List[DxfHatchPath] = []
        for hole_coords_tuples in polygon.holes:
            if len(hole_coords_tuples) >= 3:
                hole_c = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 else 0.0) for c in hole_coords_tuples]
                if hole_c[0] != hole_c[-1]:
                    hole_c.append(hole_c[0])

                if base_dxf_attrs.get('visible', True):
                    hole_poly = DxfLWPolyline(points=hole_c, is_closed=True)
                    self._apply_base_style_to_entity(hole_poly, base_dxf_attrs, layer_name)
                    yield hole_poly
                hole_paths_for_hatch.append(DxfHatchPath(vertices=hole_c, is_closed=True))
            else:
                self.logger.warning(f"Polygon hole on layer {layer_name} with < 3 coordinates. Skipping hole boundary.")

        if style_config.hatch_props:
            hp = style_config.hatch_props
            main_hatch_path = DxfHatchPath(vertices=shell_coords, is_closed=True)
            all_hatch_paths = [main_hatch_path] + hole_paths_for_hatch

            hatch = DxfHatch(
                paths=all_hatch_paths,
                pattern_name=hp.pattern_name if hp.pattern_name else "SOLID",
                pattern_scale=hp.scale if hp.scale is not None else 1.0,
                pattern_angle=hp.angle if hp.angle is not None else 0.0,
                hatch_style_enum=hp.style if hp.style else 'NORMAL',
                associative=True
            )
            self._apply_base_style_to_entity(hatch, base_dxf_attrs, layer_name)

            if hp.color:
                if isinstance(hp.color, int): hatch.color_256 = hp.color
                elif isinstance(hp.color, tuple) and len(hp.color) == 3: hatch.true_color = hp.color
            if hp.transparency is not None:
                hatch.transparency = hp.transparency
            yield hatch
        await asyncio.sleep(0)
