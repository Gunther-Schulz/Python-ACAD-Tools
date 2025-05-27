"""Concrete implementation of the IStyleApplicationOrchestrator interface."""
from typing import Optional, Any, Dict, Union, cast, List

import geopandas as gpd
# import ezdxf # Not directly used if adapter handles all
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic, Text, MText, Hatch
from ezdxf.layouts import Modelspace
from ezdxf.lldxf.const import BYLAYER, BYBLOCK, LINEWEIGHT_BYLAYER, LINEWEIGHT_DEFAULT, BOUNDARY_PATH_EXTERNAL, BOUNDARY_PATH_DEFAULT
from ezdxf.math import Vec3, Z_AXIS
from ezdxf.enums import MTextEntityAlignment

from ..interfaces.style_application_orchestrator_interface import IStyleApplicationOrchestrator
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.config_loader_interface import IConfigLoader
from ..interfaces.dxf_adapter_interface import IDXFAdapter
from ..interfaces.dxf_resource_manager_interface import IDXFResourceManager
from ..domain.config_models import (
    StyleConfig, NamedStyle, GeomLayerDefinition,
    LayerStyleProperties, TextStyleProperties, HatchStyleProperties, AciColorMappingItem
)
from ..domain.exceptions import ProcessingError, DXFProcessingError, ConfigError
from src.domain.style_models import DXFLineweight # For lineweight validation if needed directly

DEFAULT_ACI_COLOR = 7
DEFAULT_LINETYPE = "Continuous"

class StyleApplicationOrchestratorService(IStyleApplicationOrchestrator):
    """
    Service responsible for resolving style information and applying it
    to various targets like GeoDataFrames, DXF entities, and DXF layers.
    """

    def __init__(
        self,
        logger_service: ILoggingService,
        config_loader: IConfigLoader,
        dxf_adapter: IDXFAdapter,
        dxf_resource_manager: IDXFResourceManager,
    ):
        self._logger = logger_service.get_logger(__name__)
        self._config_loader = config_loader
        self._dxf_adapter = dxf_adapter
        self._dxf_resource_manager = dxf_resource_manager
        self._aci_map: Optional[Dict[str, int]] = None

        if not self._dxf_adapter.is_available():
            self._logger.error("ezdxf library not available via adapter. DXF styling functionality will be severely limited.")

    # --- Moved from StyleApplicatorService ---
    def _get_aci_color_map(self) -> Dict[str, int]:
        if self._aci_map is None:
            try:
                color_items = self._config_loader.get_aci_color_mappings()
                self._aci_map = {item.name.lower(): item.aci_code for item in color_items}
                self._logger.info(f"Loaded ACI color map with {len(self._aci_map)} entries.")
            except (ConfigError, AttributeError, TypeError) as e:
                self._logger.error(f"Failed to load ACI color map: {e}. Color name resolution will fail.", exc_info=True)
                self._aci_map = {}
        return self._aci_map

    def _resolve_aci_color(self, color_value: Union[str, int, None]) -> Optional[int]:
        if color_value is None:
            return None
        if isinstance(color_value, int):
            return color_value
        if isinstance(color_value, str):
            color_map = self._get_aci_color_map()
            aci_code = color_map.get(color_value.lower())
            if aci_code is None:
                self._logger.warning(f"ACI color name '{color_value}' not found in map. Using default ACI {DEFAULT_ACI_COLOR}.")
                return DEFAULT_ACI_COLOR
            return aci_code
        self._logger.warning(f"Unexpected color value type: {type(color_value)}. Value: {color_value}")
        return DEFAULT_ACI_COLOR

    def get_style_for_layer(
        self,
        layer_name: str,
        layer_definition: Optional[GeomLayerDefinition],
        style_config: StyleConfig
    ) -> Optional[NamedStyle]:
        self._logger.debug(f"Getting style for layer: {layer_name}")
        effective_style: Optional[NamedStyle] = None
        if layer_definition and layer_definition.style:
            if isinstance(layer_definition.style, NamedStyle):
                effective_style = layer_definition.style
            elif isinstance(layer_definition.style, str):
                style_name_from_def = layer_definition.style
                effective_style = style_config.styles.get(style_name_from_def)
                if not effective_style:
                    self._logger.warning(f"Style '{style_name_from_def}' referenced by layer '{layer_name}' not found.")
            else:
                self._logger.warning(f"Layer '{layer_name}' style attribute unexpected type: {type(layer_definition.style)}.")
        if not effective_style:
            effective_style = style_config.styles.get(layer_name)
        if not effective_style:
            self._logger.info(f"No specific style for layer '{layer_name}'.")
            return None
        return effective_style

    def apply_style_to_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        style: NamedStyle,
        layer_name: str
    ) -> gpd.GeoDataFrame:
        self._logger.debug(f"Applying style to GDF for layer '{layer_name}'.")
        if gdf.empty:
            return gdf
        gdf_styled = gdf.copy()
        if style.layer:
            s_layer = style.layer
            if s_layer.color is not None:
                gdf_styled["_style_color_aci"] = self._resolve_aci_color(s_layer.color)
            if s_layer.linetype is not None:
                gdf_styled["_style_linetype"] = s_layer.linetype
            if s_layer.lineweight is not None:
                gdf_styled["_style_lineweight"] = s_layer.lineweight
        if style.text:
            s_text = style.text
            if s_text.font is not None:
                gdf_styled["_style_text_font"] = s_text.font
            if s_text.color is not None:
                gdf_styled["_style_text_color_aci"] = self._resolve_aci_color(s_text.color)
            if s_text.height is not None:
                gdf_styled["_style_text_height"] = s_text.height
            if s_text.rotation is not None:
                gdf_styled["_style_text_rotation"] = s_text.rotation
        self._logger.info(f"Added style columns to GDF for layer '{layer_name}'.")
        return gdf_styled

    def _determine_entity_properties_from_style(self, style: NamedStyle, entity_type: str) -> Dict[str, Any]:
        final_props: Dict[str, Any] = {}
        final_props["color"] = DEFAULT_ACI_COLOR # Initialize with default

        # Layer properties (these become defaults for the entity if not overridden)
        if style.layer:
            layer_s = style.layer
            if layer_s.color is not None: # Check if color is explicitly set in style
                resolved_color = self._resolve_aci_color(layer_s.color)
                if resolved_color is not None: # If resolvable, use it
                    final_props['color'] = resolved_color
            # else color remains DEFAULT_ACI_COLOR or will be BYLAYER if not overridden by text/hatch

            final_props['linetype'] = layer_s.linetype.upper() if isinstance(layer_s.linetype, str) else layer_s.linetype
            if final_props['linetype'] is None: final_props['linetype'] = 'BYLAYER' # Ensure not None

            final_props['lineweight'] = layer_s.lineweight if layer_s.lineweight is not None else LINEWEIGHT_BYLAYER
            final_props['transparency'] = layer_s.transparency # Adapter handles None as default for transparency
        else: # No layer style defined, use hard defaults
            final_props['color'] = BYLAYER
            final_props['linetype'] = 'BYLAYER'
            final_props['lineweight'] = LINEWEIGHT_BYLAYER
            final_props['transparency'] = None

        # Text-specific properties override common properties like color
        if entity_type.upper() in ["TEXT", "MTEXT"] and style.text:
            text_s = style.text
            current_text_specific_props: Dict[str, Any] = {}

            if text_s.color is not None: # Text color overrides layer/default color
                resolved_text_color = self._resolve_aci_color(text_s.color)
                if resolved_text_color is not None:
                    final_props['color'] = resolved_text_color

            if text_s.font: current_text_specific_props['font'] = text_s.font
            if text_s.height is not None: current_text_specific_props['height'] = text_s.height
            if text_s.rotation is not None: current_text_specific_props['rotation'] = text_s.rotation
            if text_s.attachment_point: current_text_specific_props['attachment_point'] = text_s.attachment_point.value

            # MTEXT specific properties
            if entity_type.upper() == "MTEXT":
                if text_s.max_width is not None:
                    current_text_specific_props["width"] = text_s.max_width
                if text_s.flow_direction:
                    current_text_specific_props["flow_direction"] = text_s.flow_direction.value
                if text_s.line_spacing_style:
                    current_text_specific_props["line_spacing_style"] = text_s.line_spacing_style.value
                if text_s.line_spacing_factor is not None:
                    current_text_specific_props["line_spacing_factor"] = text_s.line_spacing_factor

            if current_text_specific_props: # If any text-specific properties were actually added
                final_props["text_specific"] = current_text_specific_props

        # Hatch-specific properties
        elif entity_type.upper() == "HATCH" and style.hatch:
            hatch_s = style.hatch
            current_hatch_specific_props: Dict[str, Any] = {}

            if hatch_s.color is not None: # Hatch color can also override common color
                resolved_hatch_color = self._resolve_aci_color(hatch_s.color)
                if resolved_hatch_color is not None:
                    final_props['color'] = resolved_hatch_color

            if hatch_s.pattern_name: current_hatch_specific_props['pattern_name'] = hatch_s.pattern_name
            if hatch_s.scale is not None: current_hatch_specific_props['scale'] = hatch_s.scale
            if hatch_s.angle is not None: current_hatch_specific_props['angle'] = hatch_s.angle
            # Spacing might be used by adapter to define custom pattern if pattern_name is specific
            if hatch_s.spacing is not None: current_hatch_specific_props['spacing'] = hatch_s.spacing

            # Note: hatch 'fill_color_aci' was used in one version of the edit tool's output.
            # For consistency, hatch color now overrides the main 'color' prop, similar to text.
            # If a separate fill_color for hatch pattern itself is needed, adapter should handle it.

            if current_hatch_specific_props:
                 final_props["hatch_specific"] = current_hatch_specific_props

        return final_props

    def _apply_text_entity_specifics(
        self,
        text_entity_cast: Union[Text, MText],
        text_props_from_style: TextStyleProperties,
        resolved_text_specific_props: Dict[str, Any],
        dxf_drawing: Drawing
    ) -> None:
        actual_dxf_text_style_name: Optional[str] = None
        if text_props_from_style.font:
            actual_dxf_text_style_name = self._dxf_resource_manager.ensure_text_style(dxf_drawing, text_props_from_style)
        if actual_dxf_text_style_name:
             text_entity_cast.dxf.style = actual_dxf_text_style_name
        if 'height' in resolved_text_specific_props:
            text_entity_cast.dxf.height = resolved_text_specific_props['height']
        if 'rotation' in resolved_text_specific_props:
            text_entity_cast.dxf.rotation = resolved_text_specific_props['rotation']
        if isinstance(text_entity_cast, MText) and 'attachment_point' in resolved_text_specific_props:
            # attachment_point should be string from model, resolve to enum/int for ezdxf
            # This resolving logic needs to be robust, or moved to adapter. For now, assume direct use.
            # Simplified: assume resolved_text_specific_props['attachment_point'] is already e.g. MTextEntityAlignment.MIDDLE_CENTER.value
            # For a more robust solution, _resolve_attachment_point helper would be needed here.
            attachment_point_value = resolved_text_specific_props['attachment_point']
            if isinstance(attachment_point_value, str): # If it's a string like "MIDDLE_CENTER"
                try:
                    # Example of how one might resolve string to MTextEntityAlignment enum value
                    # This should ideally be part of a helper or the adapter
                    resolved_enum = MTextEntityAlignment[attachment_point_value.upper()]
                    text_entity_cast.dxf.attachment_point = resolved_enum.value
                except KeyError:
                    self._logger.warning(f"Invalid MTEXT attachment point string: {attachment_point_value}")
            elif isinstance(attachment_point_value, int): # If already an int
                 text_entity_cast.dxf.attachment_point = attachment_point_value


        if text_props_from_style.align_to_view:
            self._align_text_entity_to_view(text_entity_cast, dxf_drawing, text_props_from_style)


    def apply_style_to_dxf_entity(
        self,
        entity: DXFGraphic,
        style: NamedStyle,
        dxf_drawing: Drawing
    ) -> None:
        if not self._dxf_adapter.is_available():
            raise DXFProcessingError("ezdxf library not available or adapter failed.")
        entity_type = entity.dxftype()
        self._logger.debug(f"Applying style to DXF entity: {entity.dxf.handle} (Type: {entity_type})")
        resolved_props = self._determine_entity_properties_from_style(style, entity_type)

        # Construct common_props_for_adapter from the flat resolved_props
        common_props_for_adapter: Dict[str, Any] = {}
        if "color" in resolved_props: common_props_for_adapter["color"] = resolved_props["color"]
        if "linetype" in resolved_props: common_props_for_adapter["linetype"] = resolved_props["linetype"]
        if "lineweight" in resolved_props: common_props_for_adapter["lineweight"] = resolved_props["lineweight"]
        if "transparency" in resolved_props: common_props_for_adapter["transparency"] = resolved_props["transparency"]
        # Add other common props here if any were moved to be flat in resolved_props

        if common_props_for_adapter: # Only call if there are properties to set
            self._dxf_adapter.set_entity_properties(entity=entity, **common_props_for_adapter)

        original_text_style_props = style.text if style.text else TextStyleProperties() # For font and align_to_view checks

        if entity_type.upper() in ['TEXT', 'MTEXT']:
            text_specific_dict = resolved_props.get("text_specific", {}) # Use .get() for safety
            # Check if there are specific text properties OR if ensure_text_style or align_to_view needs to be called
            if text_specific_dict or original_text_style_props.font or original_text_style_props.align_to_view:
                try:
                    casted_text_entity = cast(Union[Text, MText], entity)
                    self._apply_text_entity_specifics(
                        casted_text_entity, original_text_style_props, text_specific_dict, dxf_drawing
                    )
                except TypeError as e:
                    self._logger.error(f"TypeError applying text specifics for {entity_type}: {e}", exc_info=True)
        elif entity_type.upper() == 'HATCH':
            hatch_specific_dict = resolved_props.get("hatch_specific", {}) # Use .get()
            if hatch_specific_dict: # Only proceed if there are hatch-specific properties
                try:
                    casted_hatch_entity = cast(Hatch, entity)
                    pattern_name = hatch_specific_dict.get('pattern_name')
                    # The main color for hatch is already in common_props_for_adapter if overridden by hatch style
                    # So, here we primarily care about pattern details.
                    # The color passed to pattern fill methods should be the hatch_specific color if one exists,
                    # falling back to the entity's main color (already set or defaulted by common_props_for_adapter)
                    hatch_pattern_color = resolved_props.get("color") # This will be hatch color if specified, else layer/default

                    scale = hatch_specific_dict.get('scale')
                    angle = hatch_specific_dict.get('angle')

                    if pattern_name and pattern_name.upper() != "SOLID":
                        self._dxf_adapter.set_hatch_pattern_fill(
                            hatch_entity=casted_hatch_entity,
                            pattern_name=pattern_name,
                            color=hatch_pattern_color if hatch_pattern_color is not None else DEFAULT_ACI_COLOR,
                            scale=scale if scale is not None else 1.0,
                            angle=angle if angle is not None else 0.0
                        )
                    elif pattern_name and pattern_name.upper() == "SOLID":
                         self._dxf_adapter.set_hatch_solid_fill(
                            hatch_entity=casted_hatch_entity,
                            color=hatch_pattern_color if hatch_pattern_color is not None else DEFAULT_ACI_COLOR
                        )
                    # If pattern_name is None but hatch_specific_dict has color (meaning it came from HatchStyleProperties.color)
                    # this implies solid fill with that color. The main entity color is already set via common_props_for_adapter.
                    # The set_hatch_solid_fill might be redundant if common_props_for_adapter already set the color correctly for solid.
                    # However, explicit solid fill call might be needed by adapter if hatch was pattern before.
                    elif pattern_name is None and hatch_specific_dict: # some hatch props exist, imply solid
                        self._dxf_adapter.set_hatch_solid_fill(
                            hatch_entity=casted_hatch_entity,
                            color=hatch_pattern_color if hatch_pattern_color is not None else DEFAULT_ACI_COLOR
                        )
                    self._logger.debug(f"Applied HATCH-specific properties to {entity.dxf.handle}: {hatch_specific_dict}")
                except DXFProcessingError as e:
                    self._logger.error(f"DXFAdapter error applying HATCH specifics: {e}", exc_info=True)
                except Exception as e:
                    self._logger.error(f"Unexpected error applying HATCH specifics: {e}", exc_info=True)

    def _apply_hatch_properties( # This method was for CREATING hatches, may need rethink for styling existing
        self,
        dxf_drawing: Drawing,
        msp: Modelspace, # Modelspace where hatch is created
        boundary_path_data: List[Any], # Geometries defining boundary
        layer_name: str, # Target layer for the new hatch
        resolved_props: Dict[str, Any] # Style properties
    ):
        """Applies hatch properties to CREATE a new hatch entity.
        NOTE: This logic is for creating NEW hatches. Applying style to an *existing* hatch
        is handled within apply_style_to_dxf_entity.
        This method is likely kept if the orchestrator is also responsible for hatch *creation*
        as part of a more complex styling operation (e.g. from GeoDataFrame feature that implies hatch).
        For now, assuming it might be called by a higher-level process.
        """
        if not self._dxf_adapter.is_available():
            self._logger.warning("DXF adapter not available, skipping hatch creation.")
            return None # Return None or raise error

        hatch_specific_props = resolved_props.get("hatch_specific_props", {})
        # common_dxf_attribs are the general entity properties like color, linetype from style.layer
        common_dxf_attribs = resolved_props.get("common_props_for_adapter", {})
        # Ensure layer is part of dxfattribs for hatch creation
        dxfattribs_for_creation = {**common_dxf_attribs, "layer": layer_name}

        hatch_color_aci = hatch_specific_props.get('fill_color_aci') # This is for the FILL
        pattern_name = hatch_specific_props.get('pattern_name')
        scale = hatch_specific_props.get('scale', 1.0)
        angle = hatch_specific_props.get('angle', 0.0)

        dxf_hatch = None
        is_pattern_fill = pattern_name and pattern_name.upper() != "SOLID"

        # Determine color for adapter.add_hatch:
        # If pattern fill, DXF hatch entity color attribute itself is often ignored or set to BYLAYER,
        # and pattern color is set separately.
        # If solid fill, DXF hatch entity color attribute is used.
        hatch_entity_color_for_creation = hatch_color_aci if not is_pattern_fill else None # Or BYLAYER

        try:
            dxf_hatch = self._dxf_adapter.add_hatch(
                msp,
                color=hatch_entity_color_for_creation, # Color for solid, None/BYLAYER for pattern
                dxfattribs=dxfattribs_for_creation
            )

            # Add boundary paths - boundary_path_data needs to be processed into usable points
            # This part is highly dependent on how boundary_path_data is structured
            # Assuming it's a list of point lists for now (e.g., for LWPOLYLINE paths)
            # Simplified: Loop through paths if boundary_path_data is structured e.g., [[(x,y),...], [(x,y),...]]
            # For now, assume boundary_path_data is a single exterior path for simplicity if this method is used.
            # This method needs to be robustly defined if it's a primary creation path.
            # Example for a single exterior path:
            if boundary_path_data and isinstance(boundary_path_data[0], list): # e.g. [[(x,y),..]]
                 self._dxf_adapter.add_hatch_boundary_path(dxf_hatch, points=boundary_path_data[0], flags=BOUNDARY_PATH_EXTERNAL)


            if is_pattern_fill:
                self._dxf_adapter.set_hatch_pattern_fill(
                    hatch_entity=dxf_hatch,
                    pattern_name=pattern_name, # type: ignore
                    color=hatch_color_aci, # Color for the pattern lines/dots
                    scale=scale,
                    angle=angle
                )
            else: # Solid fill
                 if hatch_color_aci is not None: # Ensure color is not None for solid fill
                    self._dxf_adapter.set_hatch_solid_fill(hatch_entity=dxf_hatch, color=hatch_color_aci)
            return dxf_hatch
        except DXFProcessingError as e:
            self._logger.error(f"Failed to create hatch for layer '{layer_name}': {e}", exc_info=True)
            # Clean up partially created hatch if possible/needed, or let adapter handle
            return None # Or re-raise
        except Exception as e_unexp:
            self._logger.error(f"Unexpected error creating hatch for '{layer_name}': {e_unexp}", exc_info=True)
            return None


    def _align_text_entity_to_view(self, entity: DXFGraphic, doc: Drawing, text_props: TextStyleProperties) -> None:
        if not self._dxf_adapter.is_available() or not isinstance(entity, (Text, MText)):
            return
        self._logger.debug(f"Aligning entity {entity.dxf.handle} ({entity.dxftype()}) to view.")
        target_z_axis_wcs = Z_AXIS
        try:
            current_z_axis_wcs = Vec3(entity.dxf.extrusion).normalize() if entity.dxf.hasattr('extrusion') else Z_AXIS
            if not current_z_axis_wcs.is_parallel_to(target_z_axis_wcs, tol=1e-9):
                 if isinstance(entity, MText):
                     entity.dxf.extrusion = target_z_axis_wcs
                     entity.dxf.rotation = text_props.rotation if text_props.rotation is not None else 0.0
            entity.dxf.rotation = text_props.rotation if text_props.rotation is not None else (0.0 if isinstance(entity, MText) and entity.dxf.extrusion == target_z_axis_wcs or isinstance(entity, Text) else entity.dxf.rotation)
            if isinstance(entity, MText) and text_props.align_attachment_point:
                try:
                    # This assumes text_props.attachment_point is a string like "MIDDLE_CENTER"
                    # And that MTextEntityAlignment has these as members.
                    # A more robust resolver might be needed here if direct enum access is not desired.
                    if text_props.attachment_point:
                         # Example: attachment_enum = MTextEntityAlignment[text_props.attachment_point.upper()]
                         # entity.dxf.attachment_point = attachment_enum.value
                         # For now, simplified, assuming it's already an int or handled by MText itself
                         pass # Actual setting logic might be complex depending on input
                except Exception as e_attach:
                    self._logger.warning(f"Failed to set MTEXT attachment point during align: {e_attach}")
        except Exception as e:
            self._logger.error(f"Error aligning text entity {entity.dxf.handle}: {e}", exc_info=True)

    def apply_styles_to_dxf_layer(
        self,
        dxf_drawing: Drawing,
        layer_name: str,
        style: NamedStyle
    ) -> None:
        if not self._dxf_adapter.is_available():
            raise DXFProcessingError("Cannot apply styles to DXF layer: adapter not available.")
        self._logger.debug(f"Applying style to DXF layer: {layer_name}")
        dxf_layer: Optional[Any] = None
        try:
            dxf_layer = self._dxf_adapter.get_layer(dxf_drawing, layer_name)
            if dxf_layer is None:
                self._dxf_adapter.create_dxf_layer(dxf_drawing, layer_name)
                dxf_layer = self._dxf_adapter.get_layer(dxf_drawing, layer_name)
                if dxf_layer is None: raise DXFProcessingError(f"Failed to create/retrieve layer '{layer_name}'.")
        except Exception as e:
            self._logger.error(f"Error managing layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Error managing layer '{layer_name}': {str(e)}") from e

        if style.layer:
            s_layer = style.layer
            layer_props_to_set: Dict[str, Any] = {}
            if s_layer.color is not None: layer_props_to_set['color'] = self._resolve_aci_color(s_layer.color)
            if s_layer.linetype is not None:
                # Pass LayerStyleProperties to ensure_linetype for full context
                self._dxf_resource_manager.ensure_linetype(dxf_drawing, s_layer)
                layer_props_to_set['linetype'] = s_layer.linetype
            else: layer_props_to_set['linetype'] = "BYLAYER"
            if s_layer.lineweight is not None:
                # Assuming s_layer.lineweight is already validated int by model
                if DXFLineweight.is_valid_lineweight(s_layer.lineweight): # Or use adapter.validate_lineweight
                    layer_props_to_set['lineweight'] = s_layer.lineweight
                else:
                    self._logger.warning(f"Invalid lineweight {s_layer.lineweight} for '{layer_name}', using default.")
                    layer_props_to_set['lineweight'] = DXFLineweight.DEFAULT.value # -3
            else: layer_props_to_set['lineweight'] = LINEWEIGHT_BYLAYER

            if s_layer.plot is not None: layer_props_to_set['plot'] = s_layer.plot
            if s_layer.is_on is not None: layer_props_to_set['on'] = s_layer.is_on
            if s_layer.frozen is not None: layer_props_to_set['frozen'] = s_layer.frozen
            if s_layer.locked is not None: layer_props_to_set['locked'] = s_layer.locked

            if dxf_layer and layer_props_to_set:
                try:
                    # Pass doc and layer_name to adapter, not the layer_entity directly
                    self._dxf_adapter.set_layer_properties(doc=dxf_drawing, layer_name=layer_name, **layer_props_to_set)
                except Exception as e:
                     self._logger.error(f"Error setting layer props for '{layer_name}': {e}", exc_info=True)
        try:
            msp = self._dxf_adapter.get_modelspace(dxf_drawing)
            entities_on_layer = self._dxf_adapter.query_entities(msp, query_string=f'*[layer=="{layer_name}"]')
            if entities_on_layer:
                for entity in entities_on_layer:
                    if hasattr(entity, 'dxftype'):
                        self.apply_style_to_dxf_entity(entity, style, dxf_drawing)
        except Exception as e:
            self._logger.error(f"Could not process entities on layer {layer_name}: {e}", exc_info=True)

    def clear_caches(self) -> None:
        if self._aci_map is not None:
            self._logger.debug(f"Clearing ACI color map cache with {len(self._aci_map)} entries")
            self._aci_map = None

    def get_cache_info(self) -> Dict[str, Any]:
        return {
            "aci_map_entries": len(self._aci_map) if self._aci_map else 0,
            "aci_map_loaded": self._aci_map is not None
        }
