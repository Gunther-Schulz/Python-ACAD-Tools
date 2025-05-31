from typing import Optional, Any, Dict, List

import geopandas as gpd
import pandas as pd
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic, Text, MText # For type hints
from ezdxf.layouts import Modelspace # For type hints
from ezdxf.lldxf.const import BYLAYER, BOUNDARY_PATH_EXTERNAL, BOUNDARY_PATH_DEFAULT
from ezdxf.enums import MTextEntityAlignment
from ezdxf.math import Vec3, Z_AXIS

from ..interfaces.geometry_processor_interface import IGeometryProcessor
from ..interfaces.dxf_adapter_interface import IDXFAdapter
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.dxf_resource_manager_interface import IDXFResourceManager
from ..interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator # May not be needed here, check usage
from ..domain.geometry_models import GeomLayerDefinition, GeometryType # Assuming GeometryType might also be from geometry_models
from ..domain.style_models import NamedStyle, TextStyleProperties # Keep these if they are used
from ..domain.exceptions import DXFProcessingError, GeometryError, ConfigError

DEFAULT_ACI_COLOR = 7

class GeometryProcessorService(IGeometryProcessor):
    """
    Service responsible for processing geometries from a GeoDataFrame
    and adding them to a DXF drawing, including handling styles and labels.
    """
    def __init__(
        self,
        dxf_adapter: IDXFAdapter,
        logger_service: ILoggingService,
        dxf_resource_manager: IDXFResourceManager
    ):
        self._dxf_adapter = dxf_adapter
        self._logger = logger_service.get_logger(__name__)
        self._dxf_resource_manager = dxf_resource_manager

        if not self._dxf_adapter.is_available():
            self._logger.error("DXF adapter reports ezdxf not available. GeometryProcessorService may not function correctly.")

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
        if not self._dxf_adapter.is_available():
            raise DXFProcessingError("Cannot add geometries to DXF: ezdxf library not available via adapter.")

        if gdf.empty:
            self._logger.debug(f"GeoDataFrame for layer '{layer_name}' is empty. No geometries to add.")
            return

        self._logger.debug(f"Adding {len(gdf)} geometries to DXF layer '{layer_name}'")
        msp = self._dxf_adapter.get_modelspace(dxf_drawing)
        added_count = 0

        try:
            for idx, row in gdf.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    self._logger.info(f"Skipping null or empty geometry for feature at index {idx} in layer '{layer_name}'.")
                    continue

                try:
                    entity: Optional[DXFGraphic] = None
                    is_polygon_type = False

                    if geom.geom_type == 'Point':
                        entity = self._dxf_adapter.add_point(msp, location=(geom.x, geom.y, 0.0), dxfattribs={'layer': layer_name})
                    elif geom.geom_type == 'LineString':
                        coords = list(geom.coords)
                        entity = self._dxf_adapter.add_lwpolyline(msp, points=coords, dxfattribs={'layer': layer_name})
                    elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                        is_polygon_type = True
                        polygons_to_process = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
                        for poly in polygons_to_process:
                            # Pass added_count by a wrapper or handle return value if it needs to be incremented inside
                            self._process_single_polygon_for_dxf(msp, poly, layer_name, style, dxf_drawing)

                        label_text_poly = self._get_label_text_for_feature(row, layer_definition, style, geom.geom_type)
                        if label_text_poly:
                            label_position_poly = self._calculate_label_position(geom, geom.geom_type)
                            self._add_label_to_dxf(msp, label_text_poly, label_position_poly, layer_name, style, dxf_drawing)
                        continue

                    elif geom.geom_type in ['MultiPoint', 'MultiLineString']:
                        for sub_geom in geom.geoms:
                            sub_entity: Optional[DXFGraphic] = None
                            if sub_geom.geom_type == 'Point':
                                sub_entity = self._dxf_adapter.add_point(msp, location=(sub_geom.x, sub_geom.y, 0.0), dxfattribs={'layer': layer_name})
                            elif sub_geom.geom_type == 'LineString':
                                coords_sub = list(sub_geom.coords)
                                sub_entity = self._dxf_adapter.add_lwpolyline(msp, points=coords_sub, dxfattribs={'layer': layer_name})
                            if sub_entity:
                                added_count += 1

                        label_text_multi = self._get_label_text_for_feature(row, layer_definition, style, geom.geom_type)
                        if label_text_multi:
                            label_pos_multi = self._calculate_label_position(geom, geom.geom_type)
                            self._add_label_to_dxf(msp, label_text_multi, label_pos_multi, layer_name, style, dxf_drawing)
                        continue
                    else:
                        self._logger.warning(f"Unsupported geometry type: {geom.geom_type} for feature {idx}")
                        continue

                    if entity:
                        added_count += 1

                    if not is_polygon_type and style and style.text:
                        label_text_simple = self._get_label_text_for_feature(row, layer_definition, style, geom.geom_type)
                        if label_text_simple:
                            label_pos_simple = self._calculate_label_position(geom, geom.geom_type)
                            self._add_label_to_dxf(msp, label_text_simple, label_pos_simple, layer_name, style, dxf_drawing)

                except Exception as e_geom:
                    self._logger.warning(f"Failed to add geometry part for index {idx} (type: {geom.geom_type if geom else 'None'}) to DXF: {e_geom}", exc_info=True)
                    continue
            self._logger.info(f"Processed {added_count} primary geometry entities for layer '{layer_name}'.")

        except Exception as e_main:
            self._logger.error(f"Major error in add_geodataframe_to_dxf for layer '{layer_name}': {e_main}", exc_info=True)
            raise DXFProcessingError(f"Failed to add geometries to DXF layer '{layer_name}': {e_main}")

    def _process_single_polygon_for_dxf(self, msp: Modelspace, poly, layer_name: str, style: Optional[NamedStyle], dxf_drawing: Drawing) -> None:
        """Helper to process a single polygon (exterior and interiors) for DXF output."""
        # Hatch processing
        if style and style.hatch:
            try:
                hatch_dxfattribs = {'layer': layer_name}
                hatch_color_aci: Optional[int] = None
                pattern_name = style.hatch.pattern_name
                is_solid_fill = not pattern_name or pattern_name.upper() == "SOLID"

                if is_solid_fill:
                    hatch_color_aci = style.hatch.color if isinstance(style.hatch.color, int) else DEFAULT_ACI_COLOR

                hatch_entity = self._dxf_adapter.add_hatch(
                    msp,
                    color=hatch_color_aci if is_solid_fill else None,
                    dxfattribs=hatch_dxfattribs
                )
                exterior_coords = list(poly.exterior.coords)
                self._dxf_adapter.add_hatch_boundary_path(hatch_entity, points=exterior_coords, flags=BOUNDARY_PATH_EXTERNAL)
                for interior in poly.interiors:
                    interior_coords = list(interior.coords)
                    self._dxf_adapter.add_hatch_boundary_path(hatch_entity, points=interior_coords, flags=BOUNDARY_PATH_DEFAULT)

                if not is_solid_fill and pattern_name:
                    self._dxf_adapter.set_hatch_pattern_fill(
                        hatch_entity=hatch_entity,
                        pattern_name=pattern_name,
                        color=style.hatch.color if isinstance(style.hatch.color, int) else DEFAULT_ACI_COLOR,
                        scale=style.hatch.scale if style.hatch.scale is not None else 1.0,
                        angle=style.hatch.angle if style.hatch.angle is not None else 0.0
                    )
                elif is_solid_fill and hatch_color_aci is not None:
                        self._dxf_adapter.set_hatch_solid_fill(hatch_entity, hatch_color_aci)
            except Exception as e_hatch:
                self._logger.warning(f"Failed to create or style HATCH for polygon: {e_hatch}", exc_info=True)

        # Always create LWPOLYLINE for polygon boundary
        exterior_coords_poly = list(poly.exterior.coords)
        self._dxf_adapter.add_lwpolyline(msp, points=exterior_coords_poly, close=True, dxfattribs={'layer': layer_name})

        for interior in poly.interiors:
            interior_coords_poly = list(interior.coords)
            self._dxf_adapter.add_lwpolyline(msp, points=interior_coords_poly, close=True, dxfattribs={'layer': layer_name})

    def _get_label_text_for_feature(
        self,
        row: pd.Series,
        layer_definition: Optional[GeomLayerDefinition],
        style: Optional[NamedStyle],
        geom_type: str
    ) -> Optional[str]:
        label_text: Optional[str] = None
        if layer_definition and layer_definition.label_column:
            if layer_definition.label_column in row.index and pd.notna(row[layer_definition.label_column]):
                candidate_text = str(row[layer_definition.label_column])
                if candidate_text.strip():
                    label_text = candidate_text.strip()

        if label_text is None and geom_type not in ['Polygon', 'MultiPolygon']:
            if style and style.text:
                no_col_found_placeholder = f"__NO_COMMON_COL_FOR_{geom_type}__"
                text_content_candidate = no_col_found_placeholder
                for col_name in ['label', 'name', 'id', 'text', 'description']:
                    if col_name in row.index and pd.notna(row[col_name]):
                        current_col_text = str(row[col_name])
                        if current_col_text.strip():
                            text_content_candidate = current_col_text.strip()
                            break
                if text_content_candidate == no_col_found_placeholder:
                     if hasattr(row, 'name') and isinstance(row.name, str) and pd.notna(row.name) and row.name.strip():
                        text_content_candidate = row.name.strip()
                if text_content_candidate and text_content_candidate != no_col_found_placeholder:
                    label_text = text_content_candidate
        return label_text

    def _calculate_label_position(self, geom, geom_type: str) -> tuple:
        try:
            if geom_type == 'Point':
                return (geom.x + 0.1, geom.y + 0.1)
            elif geom_type == 'LineString':
                midpoint = geom.interpolate(0.5, normalized=True)
                return (midpoint.x, midpoint.y)
            elif geom_type in ['Polygon', 'MultiPolygon']:
                try:
                    repr_point = geom.representative_point()
                    return (repr_point.x, repr_point.y)
                except: # Fallback for any shapely error
                    centroid = geom.centroid
                    return (centroid.x, centroid.y)
            else: # Default for other types
                centroid = geom.centroid
                return (centroid.x, centroid.y)
        except Exception as e:
            self._logger.warning(f"Failed to calculate label position for {geom_type}: {e}", exc_info=True)
            bounds = geom.bounds
            return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)

    def _add_label_to_dxf(
        self,
        modelspace: Modelspace,
        label_text: str,
        position: tuple,
        layer_name: str,
        style: Optional[NamedStyle],
        dxf_drawing: Drawing
    ) -> None:
        effective_text_style_name: Optional[str] = None
        text_height = 2.5
        text_color_aci: Optional[int] = None
        attachment_point_enum = MTextEntityAlignment.MIDDLE_CENTER
        text_rotation = 0.0

        if style and style.text:
            text_props = style.text
            if text_props.color is not None:
                text_color_aci = text_props.color if isinstance(text_props.color, int) else DEFAULT_ACI_COLOR

            effective_text_style_name = self._dxf_resource_manager.ensure_text_style(dxf_drawing, text_props)
            if text_props.height is not None:
                text_height = text_props.height
            if text_props.rotation is not None:
                text_rotation = text_props.rotation
            if text_props.attachment_point:
                attachment_point_enum = self._resolve_mtext_attachment_enum(text_props.attachment_point)

        dxfattribs: Dict[str, Any] = {'layer': layer_name}
        if effective_text_style_name:
            dxfattribs['style'] = effective_text_style_name
        if text_color_aci is not None:
            dxfattribs['color'] = text_color_aci

        if "\\n" in label_text or "\\\\P" in label_text.upper() or "\\\\X" in label_text.upper():
            self._logger.debug(f"Adding MTEXT label: '{label_text[:30]}...' to layer {layer_name}")
            try:
                mtext_dxfattribs = dxfattribs.copy()
                mtext_dxfattribs['char_height'] = text_height
                mtext_dxfattribs['attachment_point'] = attachment_point_enum.value
                if text_rotation != 0:
                    mtext_dxfattribs['rotation'] = text_rotation
                self._dxf_adapter.add_mtext(modelspace, label_text, insert=position, dxfattribs=mtext_dxfattribs)
            except Exception as e_mtext:
                self._logger.error(f"Error adding MTEXT '{label_text}': {e_mtext}", exc_info=True)
        else:
            self._logger.debug(f"Adding TEXT label: '{label_text[:30]}...' to layer {layer_name}")
            try:
                text_dxfattribs = dxfattribs.copy()
                halign, valign = self._mtext_attachment_to_text_align_values(attachment_point_enum)
                text_dxfattribs['halign'] = halign
                text_dxfattribs['valign'] = valign
                if halign != 0 or valign != 0:
                    text_dxfattribs['align_point'] = position

                self._dxf_adapter.add_text(
                    modelspace,
                    text=label_text,
                    point=position,
                    height=text_height,
                    rotation=text_rotation,
                    dxfattribs=text_dxfattribs
                )
                # Note: align_to_view logic was in StyleApplicatorService._align_text_entity_to_view
                # If this service is fully responsible for text, that logic should be called here or moved.
                # For now, aligning text to view is considered a separate step potentially done by StyleApplicator.
            except Exception as e_text:
                self._logger.error(f"Error adding TEXT '{label_text}': {e_text}", exc_info=True)

    def _resolve_mtext_attachment_enum(self, attachment_point_str: str) -> MTextEntityAlignment:
        """Resolves attachment point string to ezdxf MTextEntityAlignment enum."""
        try:
            return MTextEntityAlignment[attachment_point_str.upper()]
        except KeyError:
            self._logger.warning(f"Invalid MTEXT attachment point string: '{attachment_point_str}'. Defaulting to MIDDLE_CENTER.")
            return MTextEntityAlignment.MIDDLE_CENTER

    def _mtext_attachment_to_text_align_values(self, mtext_align: MTextEntityAlignment) -> tuple[int, int]:
        """Convert MTEXT MTextEntityAlignment to TEXT halign, valign integer codes."""
        mapping = {
            MTextEntityAlignment.TOP_LEFT: (0, 3), MTextEntityAlignment.TOP_CENTER: (1, 3), MTextEntityAlignment.TOP_RIGHT: (2, 3),
            MTextEntityAlignment.MIDDLE_LEFT: (0, 2), MTextEntityAlignment.MIDDLE_CENTER: (1, 2), MTextEntityAlignment.MIDDLE_RIGHT: (2, 2),
            MTextEntityAlignment.BOTTOM_LEFT: (0, 1), MTextEntityAlignment.BOTTOM_CENTER: (1, 1), MTextEntityAlignment.BOTTOM_RIGHT: (2, 1),
        }
        return mapping.get(mtext_align, (0, 0)) # Default to Left, Baseline for TEXT
