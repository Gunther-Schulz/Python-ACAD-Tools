from typing import Optional, Any, Dict, List

import geopandas as gpd
import pandas as pd
import os
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
from ..interfaces.data_source_interface import IDataSource
from ..interfaces.path_resolver_interface import IPathResolver
from ..domain.geometry_models import GeomLayerDefinition, GeometryType
from ..domain.style_models import NamedStyle, TextStyleProperties
from ..domain.config_models import SpecificProjectConfig, StyleConfig
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
        dxf_resource_manager: IDXFResourceManager,
        data_source: IDataSource,
        path_resolver: IPathResolver
    ):
        self._dxf_adapter = dxf_adapter
        self._logger = logger_service.get_logger(__name__)
        self._dxf_resource_manager = dxf_resource_manager
        self._data_source = data_source
        self._path_resolver = path_resolver

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
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
        # This is a simplified mapping. For full accuracy, review ezdxf MTEXT details.
        # Horizontal alignment (dxf.halign)
        # Vertical alignment (dxf.valign seems less directly mapped, usually part of attachment point)
        attachment_map_horizontal = {
            MTextEntityAlignment.TOP_LEFT: 0, # Left
            MTextEntityAlignment.TOP_CENTER: 1, # Center
            MTextEntityAlignment.TOP_RIGHT: 2, # Right
            MTextEntityAlignment.MIDDLE_LEFT: 0,
            MTextEntityAlignment.MIDDLE_CENTER: 1,
            MTextEntityAlignment.MIDDLE_RIGHT: 2,
            MTextEntityAlignment.BOTTOM_LEFT: 0,
            MTextEntityAlignment.BOTTOM_CENTER: 1,
            MTextEntityAlignment.BOTTOM_RIGHT: 2,
        }
        # For vertical alignment, ezdxf MTEXT primarily uses insertion point and attachment point.
        # dxf.valign is more for Text entity. We'll use 0 (Baseline) as a default for Text if needed.
        # Let's assume MTEXT handles vertical alignment primarily via its `dxf.attachment_point`.
        # The `halign` can be derived from `attachment_point` string if we have a mapping.
        # This function might be better placed in a utility or the adapter if it gets complex.

        halign = attachment_map_horizontal.get(mtext_align, 0) # Default to Left if not found
        valign = 0 # Default, as MTEXT handles this differently

        return (halign, valign) # Example, review ezdxf docs for best MTEXT alignment handling

    def create_layer_from_definition(
        self,
        layer_def: GeomLayerDefinition,
        dxf_drawing: Optional[Any],
        style_config: StyleConfig,
        base_crs: str,
        project_root: str,
        project_config: SpecificProjectConfig,
        project_name: str
    ) -> Optional[gpd.GeoDataFrame]:
        """
        Creates a GeoDataFrame for a layer based on its definition.
        This might involve loading from a shapefile, GeoJSON, or extracting from DXF.
        """
        self._logger.info(f"Creating layer '{layer_def.name}' from definition.")
        gdf: Optional[gpd.GeoDataFrame] = None

        try:
            if layer_def.geojson_file:
                if not project_config.path_aliases:
                    self._logger.warning(f"Path aliases not defined for project '{project_name}'. Cannot resolve alias for {layer_def.geojson_file}")
                    # Fallback or raise error depending on desired strictness
                    # For now, attempt to use project_root if path seems relative, or assume absolute
                    if not os.path.isabs(layer_def.geojson_file):
                        actual_path = os.path.join(project_root, layer_def.geojson_file)
                    else:
                        actual_path = layer_def.geojson_file
                else:
                    context = self._path_resolver.create_context(
                        project_name=project_name,
                        project_root=project_root,
                        aliases=project_config.path_aliases
                    )
                    actual_path = self._path_resolver.resolve_path(layer_def.geojson_file, context=context, context_key='geojsonFile')

                self._logger.debug(f"GeoJSON source: {layer_def.geojson_file}, resolved to: {actual_path}")
                if actual_path and os.path.exists(actual_path):
                    gdf = self._data_source.load_geojson_file(actual_path, crs=base_crs)
                    self._logger.info(f"Loaded {len(gdf) if gdf is not None else 0} features from GeoJSON: {actual_path}")
                else:
                    self._logger.warning(f"GeoJSON file not found after path resolution: Original='{layer_def.geojson_file}', Resolved='{actual_path}'")

            elif layer_def.shape_file:
                if not project_config.path_aliases:
                    self._logger.warning(f"Path aliases not defined for project '{project_name}'. Cannot resolve alias for {layer_def.shape_file}")
                    if not os.path.isabs(layer_def.shape_file):
                        actual_path = os.path.join(project_root, layer_def.shape_file)
                    else:
                        actual_path = layer_def.shape_file
                else:
                    context = self._path_resolver.create_context(
                        project_name=project_name,
                        project_root=project_root,
                        aliases=project_config.path_aliases
                    )
                    actual_path = self._path_resolver.resolve_path(layer_def.shape_file, context=context, context_key='shapeFile')
                self._logger.debug(f"Shapefile source: {layer_def.shape_file}, resolved to: {actual_path}")
                if actual_path and os.path.exists(actual_path):
                    gdf = self._data_source.load_shapefile(actual_path, crs=base_crs)
                    self._logger.info(f"Loaded {len(gdf) if gdf is not None else 0} features from Shapefile: {actual_path}")
                else:
                    self._logger.warning(f"Shapefile not found after path resolution: Original='{layer_def.shape_file}', Resolved='{actual_path}'")

            elif layer_def.dxf_layer:
                self._logger.debug(f"DXF layer source: {layer_def.dxf_layer}")
                if dxf_drawing:
                    # This was returning List[ezdxf.entity] - needs conversion to GeoDataFrame
                    # entities = self._dxf_adapter.extract_entities_from_layer(dxf_drawing, layer_def.dxf_layer, base_crs)
                    # gdf = self._dxf_adapter.entities_to_geodataframe(entities, base_crs) # Placeholder
                    self._logger.warning("DXF layer extraction to GeoDataFrame is not fully implemented in GeometryProcessorService.create_layer_from_definition.")
                    # For now, return empty to avoid downstream errors if this path is taken.
                    gdf = gpd.GeoDataFrame(columns=['geometry'], crs=base_crs)
                    # self._logger.info(f"Extracted {len(gdf) if gdf is not None else 0} features from DXF layer: {layer_def.dxf_layer}")
                else:
                    self._logger.warning(f"DXF layer '{layer_def.dxf_layer}' requested, but no DXF drawing provided.")
            else:
                # Not an error if it's an operations-only layer, ProjectOrchestrator handles that logic before calling this
                self._logger.debug(f"Layer '{layer_def.name}' has no direct file source (GeoJSON/Shapefile/DXF layer). Assumed to be operations-based or empty.")
                # Return an empty GeoDataFrame to signify no data from a direct source
                gdf = gpd.GeoDataFrame(columns=['geometry'], crs=base_crs)

            # Apply selectByProperties if defined and gdf is not None
            if gdf is not None and layer_def.select_by_properties:
                self._logger.debug(f"Applying selectByProperties to layer '{layer_def.name}'")
                for col, value in layer_def.select_by_properties.items():
                    if col in gdf.columns:
                        # Handle potential type mismatches, e.g. if config has int but GDF has str
                        try:
                            if gdf[col].dtype == object and isinstance(value, (int, float)):
                                # Attempt conversion if GDF column is object and query value is numeric
                                gdf = gdf[gdf[col].astype(type(value)) == value]
                            elif gdf[col].dtype != type(value) and isinstance(value, str):
                                gdf = gdf[gdf[col].astype(str) == str(value)]
                            else:
                                gdf = gdf[gdf[col] == value]
                        except Exception as filter_ex:
                            self._logger.warning(f"Could not apply filter '{col}'='{value}' on layer '{layer_def.name}' due to type mismatch or other error: {filter_ex}. Column type: {gdf[col].dtype}, Value type: {type(value)}")
                    else:
                        self._logger.warning(f"Column '{col}' for selectByProperties not found in layer '{layer_def.name}'. Available columns: {list(gdf.columns)}")
                self._logger.info(f"Layer '{layer_def.name}' after selectByProperties: {len(gdf)} features")

        except DXFProcessingError as e:
            self._logger.error(f"DXF Processing error creating layer '{layer_def.name}': {e}")
            raise GeometryError(f"DXF error for layer '{layer_def.name}': {e}") from e
        except FileNotFoundError as e:
            self._logger.error(f"File not found error creating layer '{layer_def.name}': {e}")
            raise GeometryError(f"File not found for layer '{layer_def.name}': {e}") from e
        except Exception as e:
            self._logger.error(f"Unexpected error creating layer '{layer_def.name}': {e}", exc_info=True)
            raise GeometryError(f"Unexpected error creating layer '{layer_def.name}': {e}") from e

        return gdf

    # Ensure other methods of IGeometryProcessor are also implemented or marked as pass/NotImplementedError
    def apply_operation(
        self,
        operation_params: Any, # AllOperationParams
        source_layers: Dict[str, gpd.GeoDataFrame],
    ) -> gpd.GeoDataFrame:
        self._logger.info(f"Applying operation: {operation_params.type if hasattr(operation_params, 'type') else 'Unknown type'}")
        # Placeholder - actual operation logic would be dispatched here
        # based on operation_params.type to specific handlers or methods.
        # Example: if operation_params.type == "buffer": ...
        # For now, return an empty GeoDataFrame or raise NotImplementedError
        # to indicate it's not fully implemented.

        # A very basic example for 'buffer' (highly simplified)
        if hasattr(operation_params, 'type') and operation_params.type == "buffer":
            if operation_params.layers and len(operation_params.layers) > 0:
                first_layer_name = operation_params.layers[0]
                if first_layer_name in source_layers:
                    source_gdf = source_layers[first_layer_name]
                    if not source_gdf.empty:
                        distance = getattr(operation_params, 'distance', 10.0) # default 10 if not specified
                        buffered_gdf = source_gdf.copy()
                        buffered_gdf['geometry'] = source_gdf.geometry.buffer(distance)
                        self._logger.info(f"Applied buffer of {distance} to layer '{first_layer_name}'.")
                        return buffered_gdf
                    else:
                        self._logger.warning(f"Source layer '{first_layer_name}' for buffer operation is empty.")
                else:
                    self._logger.warning(f"Source layer '{first_layer_name}' not found for buffer operation.")
            else:
                self._logger.warning("Buffer operation specified but no source layers provided in params.")
        elif hasattr(operation_params, 'type') and operation_params.type == "union":
            # Basic union example
            if operation_params.layers and len(operation_params.layers) > 0:
                gdfs_to_union = []
                for layer_name in operation_params.layers:
                    if layer_name in source_layers and not source_layers[layer_name].empty:
                        gdfs_to_union.append(source_layers[layer_name])
                    else:
                        self._logger.warning(f"Layer '{layer_name}' for union not found or is empty.")
                if len(gdfs_to_union) > 1:
                    # Ensure all GDFs have the same CRS or reproject
                    # This is a simplified union, real union might need schema alignment etc.
                    # combined_gdf = gpd.overlay(gdfs_to_union[0], gdfs_to_union[1], how='union') # if only 2
                    # For multiple: gpd.pd.concat then unary_union or cascaded_union
                    self._logger.info(f"Performing union on {len(gdfs_to_union)} GeoDataFrames.")
                    # Placeholder: gpd.GeoDataFrame(pd.concat(gdfs_to_union, ignore_index=True)).unary_union # or similar
                    # This is non-trivial. For now, let's just return the first one as a mock.
                    if gdfs_to_union:
                       self._logger.warning("Union operation is a placeholder, returning first GDF.")
                       return gdfs_to_union[0]
                elif gdfs_to_union: # Only one valid gdf
                    return gdfs_to_union[0]
            else:
                self._logger.warning("Union operation specified but no/insufficient source layers.")

        self._logger.warning(f"Operation type '{operation_params.type if hasattr(operation_params, 'type') else 'Unknown'}' is not fully implemented in GeometryProcessorService.apply_operation.")
        # Return an empty GeoDataFrame to avoid breaking the flow if an operation isn't critical path / handled
        # Determine a common CRS or use the first available one
        common_crs = None
        for gdf_val in source_layers.values():
            if gdf_val.crs:
                common_crs = gdf_val.crs
                break
        return gpd.GeoDataFrame(columns=['geometry'], crs=common_crs)

    def merge_layers(
        self,
        layers_to_merge: List[gpd.GeoDataFrame],
        target_crs: Optional[str] = None
    ) -> gpd.GeoDataFrame:
        self._logger.info(f"Merging {len(layers_to_merge)} layers.")
        # Placeholder implementation
        if not layers_to_merge:
            return gpd.GeoDataFrame(columns=['geometry'], crs=target_crs)
        # Basic concat, assumes schemas are compatible enough for this example
        merged_gdf = pd.concat(layers_to_merge, ignore_index=True)
        # Ensure it's a GeoDataFrame
        if not isinstance(merged_gdf, gpd.GeoDataFrame):
             merged_gdf = gpd.GeoDataFrame(merged_gdf, geometry='geometry', crs=layers_to_merge[0].crs if layers_to_merge[0].crs else target_crs)

        if target_crs and merged_gdf.crs and merged_gdf.crs != target_crs:
            merged_gdf = merged_gdf.to_crs(target_crs)
        elif not merged_gdf.crs and target_crs:
            merged_gdf.crs = target_crs

        return merged_gdf

    def reproject_layer(self, layer: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
        self._logger.info(f"Reprojecting layer to CRS: {target_crs}")
        if layer.crs is None:
            self._logger.warning("Source layer has no CRS defined. Cannot reproject. Returning as is.")
            return layer
        if layer.crs == target_crs:
            return layer
        return layer.to_crs(target_crs)
