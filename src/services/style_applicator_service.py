"""Concrete implementation of the IStyleApplicator interface."""
from typing import Optional, Any, Dict, Union, cast, List

import geopandas as gpd
import pandas as pd

# ezdxf imports for type hinting, constants, and specific classes used directly
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic, Text, MText, Hatch # Hatch added for cast
from ezdxf.lldxf.const import BYLAYER, BYBLOCK, LINEWEIGHT_BYLAYER, LINEWEIGHT_BYBLOCK, LINEWEIGHT_DEFAULT, BOUNDARY_PATH_EXTERNAL, BOUNDARY_PATH_DEFAULT # MODIFIED
from ezdxf.math import Vec3, Z_AXIS # Used in _align_text_entity_to_view
from ezdxf.enums import MTextEntityAlignment # Used in text helpers

from ..interfaces.style_applicator_interface import IStyleApplicator
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.config_loader_interface import IConfigLoader # For ACI color map
from ..interfaces.dxf_adapter_interface import IDXFAdapter # ADDED
from ..domain.config_models import (
    StyleConfig, NamedStyle, GeomLayerDefinition,
    LayerStyleProperties, TextStyleProperties, HatchStyleProperties, AciColorMappingItem
)
from ..domain.exceptions import ProcessingError, DXFProcessingError, ConfigError
# from .logging_service import LoggingService # Fallback - Keep if still used, otherwise remove

DEFAULT_ACI_COLOR = 7 # White/Black, a common default
DEFAULT_LINETYPE = "Continuous"
# Constants for DXF lineweights (LW values, not necessarily indices) # REMOVED BLOCK
# LW_BYLAYER = -1 # REMOVED
# LW_BYBLOCK = -2 # REMOVED
# LW_DEFAULT = -3 # REMOVED

class StyleApplicatorService(IStyleApplicator):
    """Service for applying styles to geometric data and DXF entities."""

    def __init__(
        self,
        config_loader: IConfigLoader,
        logger_service: ILoggingService,
        dxf_adapter: IDXFAdapter, # ADDED
        # lin_file_path: Optional[str] = "acadiso.lin" # Remove this if not used by adapter directly for linetypes
    ):
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)

        self._config_loader = config_loader
        self._dxf_adapter = dxf_adapter # STORED
        self._aci_map: Optional[Dict[str, int]] = None
        # self._lin_file_path = lin_file_path # Remove if not needed

        # Replace direct EZDXF_AVAILABLE check with adapter check
        if not self._dxf_adapter.is_available():
            self._logger.error("ezdxf library not available via adapter. DXF styling functionality will be severely limited.")

    def _get_aci_color_map(self) -> Dict[str, int]:
        """Lazily loads and caches the ACI color map."""
        if self._aci_map is None:
            try:
                # Assuming IConfigLoader has a method to get the raw ACI color list
                # or the AppConfig directly holds the parsed AciColorMappingItem list.
                # This part depends on IConfigLoader actual implementation detail for color map access.
                # For now, let's assume it can provide the list of AciColorMappingItem.
                # Option 1: If AppConfig has it directly
                # app_cfg = self._config_loader.get_app_config() # This might be too broad just for colors
                # color_items = app_cfg.aci_color_mappings # If AppConfig had a field like this

                # Option 2: Specific method on IConfigLoader for color data
                color_items = self._config_loader.get_aci_color_mappings() # Assumed method

                self._aci_map = {item.name.lower(): item.aci_code for item in color_items}
                self._logger.info(f"Loaded ACI color map with {len(self._aci_map)} entries.")
            except (ConfigError, AttributeError, TypeError) as e: # AttributeError if assumed method missing
                self._logger.error(f"Failed to load ACI color map: {e}. Color name resolution will fail.", exc_info=True)
                self._aci_map = {}
        return self._aci_map

    def _resolve_aci_color(self, color_value: Union[str, int, None]) -> Optional[int]:
        """Resolves a color string (name) or int (ACI code) to an ACI code."""
        if color_value is None:
            return None # Or BYLAYER if that's the implicit default for None
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

    # --- Interface Implementations (Initial Pass) ---

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
                self._logger.debug(f"Using inline style for layer '{layer_name}'.")
                effective_style = layer_definition.style
            elif isinstance(layer_definition.style, str):
                style_name_from_def = layer_definition.style
                self._logger.debug(f"Layer '{layer_name}' definition references style name: '{style_name_from_def}'.")
                effective_style = style_config.styles.get(style_name_from_def)
                if not effective_style:
                    self._logger.warning(f"Style '{style_name_from_def}' referenced by layer '{layer_name}' not found in global StyleConfig.")
            else:
                self._logger.warning(f"Layer '{layer_name}' has style attribute of unexpected type: {type(layer_definition.style)}.")

        if not effective_style:
            # Try layer name directly in global styles if no style from definition
            self._logger.debug(f"No style from layer definition for '{layer_name}'. Trying layer name in global styles.")
            effective_style = style_config.styles.get(layer_name)
            if effective_style:
                self._logger.debug(f"Found style '{layer_name}' in global StyleConfig for layer '{layer_name}'.")

        if not effective_style:
            self._logger.info(f"No specific style found for layer '{layer_name}'. Returning None (no style). Consider default styles if needed.")
            return None

        return effective_style

    def apply_style_to_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        style: NamedStyle,
        layer_name: str
    ) -> gpd.GeoDataFrame:
        self._logger.debug(f"Applying style to GeoDataFrame for layer '{layer_name}'.")
        if gdf.empty:
            self._logger.debug(f"GeoDataFrame for layer '{layer_name}' is empty. No styles to apply.")
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
            # Add other layer properties as columns if needed for other consumers (e.g., plot, transparency)

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
            # Add other text properties like alignment if necessary for GDF representation

        # Hatch properties are typically not represented directly in GDF attributes in this way,
        # but could be if a specific use case required it (e.g., _style_hatch_pattern_name).

        self._logger.info(f"Added style attribute columns to GeoDataFrame for layer '{layer_name}'.")
        return gdf_styled

    def _ensure_dxf_linetype(self, drawing: Drawing, layer_props: Optional[LayerStyleProperties]) -> None:
        """Ensures a DXF linetype exists by name, creates it if needed using the DXF adapter."""
        if layer_props is None or layer_props.linetype is None:
            return

        linetype_name = layer_props.linetype
        if linetype_name.upper() in ["BYLAYER", "BYBLOCK", "CONTINUOUS"]:
            return

        pattern_to_use: Optional[List[float]] = None
        description_to_use: str = f"Linetype {linetype_name}"

        if layer_props.linetype_pattern is not None and isinstance(layer_props.linetype_pattern, list):
            pattern_to_use = layer_props.linetype_pattern
            description_to_use = f"Custom linetype {linetype_name} from style pattern"
            self._logger.debug(f"Using linetype pattern for '{linetype_name}' from style definition.")
        else:
            common_linetypes = {
                "DASHED": {"pattern": [1.2, -0.7], "description": "Dashed ----"},
                "DOTTED": {"pattern": [0.0, -0.2], "description": "Dotted . . ."},
                "DASHDOT": {"pattern": [1.0, -0.25, 0.0, -0.25], "description": "Dash dot --- . ---"},
                "CENTER": {"pattern": [1.25, -0.25, 0.25, -0.25], "description": "Center ____ _ ____"},
                "PHANTOM": {"pattern": [1.25, -0.25, 0.25, -0.25, 0.25, -0.25], "description": "Phantom ____ __ ____"}
            }
            if linetype_name.upper() in common_linetypes:
                linetype_def = common_linetypes[linetype_name.upper()]
                pattern_to_use = linetype_def["pattern"]
                description_to_use = linetype_def["description"]
                self._logger.debug(f"Using common linetype pattern for '{linetype_name}'.")
            else:
                self._logger.warning(f"Linetype '{linetype_name}' is not a predefined common type and has no pattern in style. Creating with a default dashed pattern.")
                pattern_to_use = [1.0, -0.5]  # Default pattern for unknown custom types
                description_to_use = f"Custom linetype {linetype_name} (defaulted pattern)"

        if pattern_to_use is not None:
            try:
                self._dxf_adapter.create_linetype(
                    doc=drawing,
                    ltype_name=linetype_name,
                    pattern=pattern_to_use,
                    description=description_to_use
                )
                self._logger.info(f"Ensured/Created linetype '{linetype_name}' in DXF via adapter.")
            except DXFProcessingError as e: # Catch specific error from adapter
                self._logger.error(f"Adapter failed to create/ensure linetype '{linetype_name}': {e}", exc_info=True)
            # No need for general Exception catch if adapter handles it and raises DXFProcessingError

    def _ensure_dxf_text_style(self, drawing: Drawing, text_props: Optional[TextStyleProperties]) -> Optional[str]:
        """Ensures a DXF text style exists, returns the style name. Uses DXF adapter."""
        if text_props is None or text_props.font is None: # Adapter handles its availability
            return None

        font_face_name = text_props.font
        # Style name generation logic can remain, adapter doesn't do this.
        style_name_candidate = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in font_face_name)
        if not style_name_candidate.strip() or style_name_candidate.lower() == "none":
            self._logger.warning(f"Cannot derive a valid style name from font: {font_face_name}. Using default style provided by DXF library.")
            return None # Let DXF use its default style

        style_name = f"Style_{style_name_candidate}" # Consistent prefix

        self._logger.debug(f"Ensuring text style '{style_name}' for font '{font_face_name}' via adapter.")
        try:
            self._dxf_adapter.create_text_style(
                doc=drawing, # Pass doc correctly
                style_name=style_name,
                font_name=font_face_name
            )
            self._logger.info(f"Ensured/Created text style '{style_name}' for font '{font_face_name}' via adapter.")
            return style_name
        except DXFProcessingError as e: # Catch specific error from adapter
            self._logger.error(f"Adapter failed to create text style '{style_name}' for font '{font_face_name}': {e}", exc_info=True)
            return None # Indicate failure to create/ensure style
        # No need for general Exception catch

    def apply_style_to_dxf_entity(
        self,
        entity: DXFGraphic,
        style: NamedStyle,
        dxf_drawing: Drawing
    ) -> None:
        """Applies style properties to a DXF entity using the DXF adapter."""
        if not self._dxf_adapter.is_available():
            self._logger.error("DXF library not available via adapter, cannot apply style to DXF entity.")
            raise DXFProcessingError("Cannot apply style to DXF entity: ezdxf library not available or adapter failed.")

        self._logger.debug(f"Applying style to DXF entity {entity.dxftype()} (handle: {entity.dxf.handle if hasattr(entity, 'dxf') else 'N/A'})" )

        common_props_for_adapter: Dict[str, Any] = {}

        if style.layer:
            s_layer = style.layer
            resolved_color = self._resolve_aci_color(s_layer.color) if s_layer.color is not None else BYLAYER
            common_props_for_adapter['color'] = resolved_color

            if s_layer.linetype is not None and s_layer.linetype.upper() not in ["BYLAYER", "BYBLOCK", "CONTINUOUS"]:
                self._ensure_dxf_linetype(dxf_drawing, s_layer)
                common_props_for_adapter['linetype'] = s_layer.linetype
            else:
                common_props_for_adapter['linetype'] = "BYLAYER"

            lw = s_layer.lineweight if s_layer.lineweight is not None else LINEWEIGHT_BYLAYER
            common_props_for_adapter['lineweight'] = lw

            if s_layer.transparency is not None:
                common_props_for_adapter['transparency'] = s_layer.transparency

        entity_type = entity.dxftype()
        specific_props_to_set_directly: Dict[str, Any] = {}
        common_props_to_set_directly: Dict[str, Any] = {} # For hatch color override case

        if entity_type in ('TEXT', 'MTEXT') and style.text:
            s_text = style.text
            if s_text.font:
                text_style_name = self._ensure_dxf_text_style(dxf_drawing, s_text)
                if text_style_name:
                    specific_props_to_set_directly['style'] = text_style_name

            if s_text.height is not None and s_text.height > 0:
                if entity_type == 'TEXT':
                    specific_props_to_set_directly['height'] = s_text.height
                elif entity_type == 'MTEXT':
                    specific_props_to_set_directly['char_height'] = s_text.height

            if s_text.rotation is not None:
                specific_props_to_set_directly['rotation'] = s_text.rotation

            # Text color overrides general layer color if specified
            if s_text.color is not None:
                resolved_text_color = self._resolve_aci_color(s_text.color)
                common_props_for_adapter['color'] = resolved_text_color


        elif entity_type == 'HATCH' and style.hatch:
            s_hatch = style.hatch
            if s_hatch.pattern_name is not None:
                specific_props_to_set_directly['pattern_name'] = s_hatch.pattern_name
            if s_hatch.scale is not None and s_hatch.scale > 0:
                specific_props_to_set_directly['pattern_scale'] = s_hatch.scale
            if s_hatch.angle is not None:
                specific_props_to_set_directly['pattern_angle'] = s_hatch.angle

            # Hatch color overrides general layer color if specified
            if s_hatch.color is not None:
                resolved_hatch_color = self._resolve_aci_color(s_hatch.color)
                # This color needs to be set directly on hatch, not through common_props typically
                common_props_to_set_directly['color'] = resolved_hatch_color


        # Apply common properties via adapter
        if common_props_for_adapter:
            try:
                self._dxf_adapter.set_entity_properties(
                    entity=entity,
                    color=common_props_for_adapter.get('color'),
                    linetype=common_props_for_adapter.get('linetype'),
                    lineweight=common_props_for_adapter.get('lineweight'),
                    transparency=common_props_for_adapter.get('transparency')
                )
            except DXFProcessingError as e: # Catch specific error from adapter
                self._logger.error(f"Adapter failed to set common properties on entity {entity.dxftype()}: {e}", exc_info=True)
            # Removed general Exception catch, assuming adapter handles internal ezdxf errors and raises DXFProcessingError

        # TODO: (P1.A Follow-up) Refactor IDXFAdapter.set_entity_properties to handle arbitrary key-value pairs (e.g., **kwargs),
        # or add specific adapter methods for text (style, height, rotation) and hatch (pattern_name, scale, angle) properties.
        # For now, directly setting these DXF attributes for properties not covered by the current adapter method.
        if specific_props_to_set_directly or (entity_type == 'HATCH' and 'color' in common_props_to_set_directly):
            try:
                # Type casting for clarity, though direct access would often work
                if entity_type == 'TEXT':
                    text_entity_cast = cast(ezdxf.entities.Text, entity)
                    if 'style' in specific_props_to_set_directly:
                        # --- TEMPORARY DEBUGGING ---
                        val_to_assign = specific_props_to_set_directly['style']
                        current_val = text_entity_cast.dxf.style
                        raise ValueError(f"TEMP DEBUG: About to assign. Current: {current_val} (type: {type(current_val)}). To assign: {val_to_assign} (type: {type(val_to_assign)})")
                        # --- END TEMPORARY DEBUGGING ---
                        # self._logger.debug(f"SERVICE_DEBUG: Before assignment - text_entity_cast.dxf.style: {text_entity_cast.dxf.style}, type: {type(text_entity_cast.dxf.style)}")
                        # self._logger.debug(f"SERVICE_DEBUG: specific_props_to_set_directly: {specific_props_to_set_directly}")
                        # text_entity_cast.dxf.style = specific_props_to_set_directly['style']
                        # self._logger.debug(f"SERVICE_DEBUG: After assignment - text_entity_cast.dxf.style: {text_entity_cast.dxf.style}, type: {type(text_entity_cast.dxf.style)}")
                    if 'height' in specific_props_to_set_directly: text_entity_cast.dxf.height = specific_props_to_set_directly['height']
                    if 'rotation' in specific_props_to_set_directly: text_entity_cast.dxf.rotation = specific_props_to_set_directly['rotation']
                elif entity_type == 'MTEXT':
                    mtext_entity_cast = cast(ezdxf.entities.MText, entity)
                    if 'style' in specific_props_to_set_directly: mtext_entity_cast.dxf.style = specific_props_to_set_directly['style']
                    if 'char_height' in specific_props_to_set_directly: mtext_entity_cast.dxf.char_height = specific_props_to_set_directly['char_height']
                    if 'rotation' in specific_props_to_set_directly: mtext_entity_cast.dxf.rotation = specific_props_to_set_directly['rotation']
                elif entity_type == 'HATCH':
                    hatch_entity_cast = cast(ezdxf.entities.Hatch, entity)
                    if 'pattern_name' in specific_props_to_set_directly: hatch_entity_cast.dxf.pattern_name = specific_props_to_set_directly['pattern_name']
                    if 'pattern_scale' in specific_props_to_set_directly: hatch_entity_cast.dxf.pattern_scale = specific_props_to_set_directly['pattern_scale']
                    if 'pattern_angle' in specific_props_to_set_directly: hatch_entity_cast.dxf.pattern_angle = specific_props_to_set_directly['pattern_angle']
                    # Ensure HATCH color set here if it was overridden
                    if 'color' in common_props_to_set_directly and common_props_to_set_directly['color'] is not None : # Check if hatch color was in specific_props
                        hatch_entity_cast.dxf.color = common_props_to_set_directly['color'] # Apply hatch specific color

                log_keys = list(specific_props_to_set_directly.keys())
                if entity_type == 'HATCH' and 'color' in common_props_to_set_directly:
                    log_keys.append('color (hatch specific)')
                self._logger.debug(f"Direct DXF attributes {log_keys} set for {entity.dxftype()}.")
            except Exception as e: # Keep general exception here as direct .dxf access can fail in many ways
                self._logger.error(f"Error setting specific DXF attributes on entity {entity.dxftype()}: {e}", exc_info=True)

    def _align_text_entity_to_view(self, entity: DXFGraphic, doc: Drawing, text_props: TextStyleProperties) -> None:
        """Aligns TEXT or MTEXT entity to be readable from the current view (WCS Z-axis)."""
        if not self._dxf_adapter.is_available() or not isinstance(entity, (Text, MText)):
            return

        # TODO: (P1.A Follow-up) This method's internal logic relies heavily on direct ezdxf entity.dxf attribute access
        # and ezdxf.math types (Vec3, Z_AXIS). To fully refactor this away from direct ezdxf use,
        # IDXFAdapter would need new methods for:
        #   - Getting/setting entity extrusion (OCS Z-axis).
        #   - Getting/setting entity rotation.
        #   - Getting/setting MTEXT attachment points.
        #   - Potentially abstracting vector math if complex operations are needed.
        # For now, leaving internal ezdxf calls, as the primary DXF availability check is adapter-based.
        # Ensure `Text` and `MText` types are resolvable for `isinstance`. This might require
        # `from ezdxf.entities import Text, MText` at the top if not already present,
        # or adjust type checking if these direct ezdxf types are to be fully hidden from this service.
        # For now, assuming they are available for the retained logic.

        self._logger.debug(f"Aligning entity {entity.dxf.handle} ({entity.dxftype()}) to view.")

        target_z_axis_wcs = Z_AXIS # World Z-axis (0,0,1)

        try:
            if entity.dxf.hasattr('extrusion'):
                current_z_axis_wcs = Vec3(entity.dxf.extrusion).normalize()
            else:
                current_z_axis_wcs = Z_AXIS

            if not current_z_axis_wcs.is_parallel_to(target_z_axis_wcs, tol=1e-9):
                 if isinstance(entity, MText):
                     entity.dxf.extrusion = target_z_axis_wcs
                     entity.dxf.rotation = text_props.rotation if text_props.rotation is not None else 0.0

            if text_props.rotation is not None:
                 entity.dxf.rotation = text_props.rotation
            else:
                 if isinstance(entity, MText) and entity.dxf.extrusion == target_z_axis_wcs:
                      entity.dxf.rotation = 0.0
                 elif isinstance(entity, Text):
                      entity.dxf.rotation = 0.0

            if isinstance(entity, MText) and text_props.align_attachment_point:
                try:
                    entity.dxf.attachment_point = MTextEntityAlignment.MIDDLE_CENTER
                except Exception as e_attach:
                    self._logger.warning(f"Failed to set MTEXT attachment point during align: {e_attach}")

            self._logger.debug(f"Entity {entity.dxf.handle} aligned. New rotation: {entity.dxf.get('rotation', 'N/A')}, Extrusion: {entity.dxf.get('extrusion', 'N/A')}")

        except Exception as e:
            self._logger.error(f"Error aligning text entity {entity.dxf.handle}: {e}", exc_info=True)

    def apply_styles_to_dxf_layer(
        self,
        dxf_drawing: Drawing,
        layer_name: str,
        style: NamedStyle
    ) -> None:
        # Adapter availability check already at the top and correct.
        if not self._dxf_adapter.is_available():
            # Message already updated to mention adapter failure possibility.
            raise DXFProcessingError("Cannot apply styles to DXF layer: ezdxf library not available or adapter failed.")

        self._logger.debug(f"Applying style to DXF layer: {layer_name}")

        dxf_layer: Optional[Any] = None
        try:
            # Get layer using adapter - This seems correct.
            dxf_layer = self._dxf_adapter.get_layer(dxf_drawing, layer_name)
            if dxf_layer is None:
                self._logger.info(f"DXF Layer '{layer_name}' not found via adapter. Attempting to create it.")
                # Create layer using adapter - This seems correct.
                self._dxf_adapter.create_dxf_layer(dxf_drawing, layer_name) # Default properties set by adapter
                dxf_layer = self._dxf_adapter.get_layer(dxf_drawing, layer_name)
                if dxf_layer is None:
                    raise DXFProcessingError(f"Failed to create or retrieve layer '{layer_name}' via adapter.")
                self._logger.info(f"Successfully created and retrieved DXF layer '{layer_name}' via adapter.")
            else:
                self._logger.debug(f"Retrieved DXF layer '{layer_name}' via adapter.")
        # Consolidate exception handling for layer get/create
        except DXFProcessingError as e:
            self._logger.error(f"Adapter error managing layer '{layer_name}': {e}", exc_info=True)
            raise # Re-raise as this is critical for styling
        except Exception as e: # Catch-all for truly unexpected issues during layer management
            self._logger.error(f"Unexpected error managing layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Unexpected error managing layer '{layer_name}'. Error: {str(e)}") from e

        if style.layer:
            s_layer = style.layer
            # DEBUG: Print s_layer.is_on value immediately after assignment
            # print(f"SERVICE_DEBUG_PRINT: s_layer.is_on initial value: {s_layer.is_on}, type: {type(s_layer.is_on)}") # TEMP DEBUG REMOVED
            self._logger.debug(f"Layer style properties from NamedStyle: color={s_layer.color}, linetype={s_layer.linetype}, lineweight={s_layer.lineweight}, plot={s_layer.plot}, is_on={s_layer.is_on}, frozen={s_layer.frozen}, locked={s_layer.locked}")

            layer_props_to_set: Dict[str, Any] = {}

            if s_layer.color is not None:
                layer_props_to_set['color'] = self._resolve_aci_color(s_layer.color)

            # Ensure DEFAULT_LINETYPE is available/defined if used as fallback
            # Assuming DEFAULT_LINETYPE = "Continuous" or similar standard value
            if s_layer.linetype is not None:
                self._ensure_dxf_linetype(dxf_drawing, s_layer) # Ensures linetype exists
                layer_props_to_set['linetype'] = s_layer.linetype
            else: # Explicitly set to BYLAYER if None, adapter should handle it
                layer_props_to_set['linetype'] = "BYLAYER"

            if s_layer.lineweight is not None:
                # Local import of DXFLineweight is acceptable for this validation block
                from src.domain.style_models import DXFLineweight
                if DXFLineweight.is_valid_lineweight(s_layer.lineweight):
                    layer_props_to_set['lineweight'] = s_layer.lineweight
                else:
                    self._logger.warning(f"Invalid lineweight value {s_layer.lineweight} for layer '{layer_name}', using default.")
                    layer_props_to_set['lineweight'] = DXFLineweight.DEFAULT.value
            else: # Explicitly set to LINEWEIGHT_BYLAYER if None
                 layer_props_to_set['lineweight'] = LINEWEIGHT_BYLAYER

            if s_layer.plot is not None:
                layer_props_to_set['plot'] = s_layer.plot
            if s_layer.is_on is not None:
                layer_props_to_set['on'] = s_layer.is_on
            if s_layer.frozen is not None:
                layer_props_to_set['frozen'] = s_layer.frozen
            if s_layer.locked is not None:
                layer_props_to_set['locked'] = s_layer.locked

            if dxf_layer and layer_props_to_set:
                try:
                    # DEBUG: Print layer_props_to_set before calling adapter
                    # self._logger.debug(f"SERVICE_DEBUG: layer_props_to_set before adapter call: {layer_props_to_set}")
                    # print(f"SERVICE_DEBUG_PRINT: layer_props_to_set before adapter call: {layer_props_to_set}") # TEMP DEBUG REMOVED
                    self._dxf_adapter.set_layer_properties(
                        doc=dxf_drawing, # MODIFIED: Pass doc
                        layer_name=layer_name, # MODIFIED: Pass layer_name
                        **layer_props_to_set
                    )
                    self._logger.info(f"Applied layer-level properties to DXF layer '{layer_name}' via adapter.")
                except DXFProcessingError as e:
                    self._logger.error(f"Adapter failed to set properties for layer '{layer_name}': {e}", exc_info=True)
                # Keeping general Exception catch here for robustness, as **kwargs might lead to unexpected adapter issues
                except Exception as e:
                     self._logger.error(f"Unexpected error setting layer properties for '{layer_name}' via adapter: {e}", exc_info=True)
        else:
            self._logger.debug(f"No specific 'layer' properties in NamedStyle for DXF layer '{layer_name}'. Layer defaults/current state maintained by adapter.")

        # Entity processing part - This also seems largely correct.
        # Adapter availability check already done.
        try:
            msp = self._dxf_adapter.get_modelspace(dxf_drawing) # Uses adapter
            entities_on_layer = self._dxf_adapter.query_entities(msp, query_string=f'*[layer=="{layer_name}"]') # Uses adapter

            if entities_on_layer:
                self._logger.info(f"Found {len(entities_on_layer)} entities on DXF layer '{layer_name}' (via adapter query). Applying entity-specific styles.")
                for entity in entities_on_layer:
                    if hasattr(entity, 'dxftype'): # Basic check
                        self.apply_style_to_dxf_entity(entity, style, dxf_drawing) # Already refactored
                    else:
                        self._logger.warning(f"Skipping non-DXFGraphic-like entity found on layer '{layer_name}': {type(entity)}")
                self._logger.info(f"Finished applying entity-specific styles for DXF layer '{layer_name}'.")
            else:
                self._logger.debug(f"No entities found on DXF layer '{layer_name}' to apply entity-specific styles (via adapter query).")
        except DXFProcessingError as e:
            self._logger.error(f"Could not process entities on layer {layer_name} for styling: {e}", exc_info=True)
        except Exception as e: # Catch any other unexpected errors
            self._logger.error(f"Unexpected error processing entities on layer {layer_name} for styling: {e}", exc_info=True)

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
        """Adds geometries from a GeoDataFrame to a DXF drawing with optional label placement."""
        if not self._dxf_adapter.is_available():
            raise DXFProcessingError("Cannot add geometries to DXF: ezdxf library not available.")

        if gdf.empty:
            self._logger.debug(f"GeoDataFrame for layer '{layer_name}' is empty. No geometries to add.")
            return

        self._logger.debug(f"Adding {len(gdf)} geometries to DXF layer '{layer_name}'")

        try:
            # Apply layer-level styling first if style is provided
            if style:
                self.apply_styles_to_dxf_layer(dxf_drawing, layer_name, style)

            # Get the modelspace
            msp = self._dxf_adapter.get_modelspace(dxf_drawing) # USE ADAPTER

            # Process each geometry in the GeoDataFrame
            added_count = 0
            for idx, row in gdf.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue

                try:
                    entity = None

                    # Handle different geometry types
                    if geom.geom_type == 'Point':
                        # Add as a point entity
                        entity = self._dxf_adapter.add_point(msp, location=(geom.x, geom.y, 0.0), dxfattribs={'layer': layer_name})

                    elif geom.geom_type == 'LineString':
                        # Add as a polyline
                        coords = list(geom.coords)
                        entity = self._dxf_adapter.add_lwpolyline(msp, points=coords, dxfattribs={'layer': layer_name})

                    elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                        # Handle polygons - create both HATCH and LWPOLYLINE entities based on styling
                        if geom.geom_type == 'Polygon':
                            polygons = [geom]
                        else:
                            polygons = list(geom.geoms)

                        for poly in polygons:
                            # Create HATCH entity for filled polygons if hatch styling is present
                            if style and style.hatch:
                                try:
                                    # Create HATCH entity with boundary path from polygon
                                    hatch_dxfattribs = {'layer': layer_name}
                                    hatch_color_for_adapter: Optional[int] = None
                                    if not style.hatch.pattern_name: # Solid fill implies color is main hatch color
                                        hatch_color_for_adapter = self._resolve_aci_color(style.hatch.color) if style.hatch.color else DEFAULT_ACI_COLOR

                                    hatch_entity = self._dxf_adapter.add_hatch(
                                        msp,
                                        color=hatch_color_for_adapter, # Pass color if solid, pattern color handled by set_pattern_fill
                                        dxfattribs=hatch_dxfattribs
                                    )

                                    # Add exterior boundary path
                                    exterior_coords = list(poly.exterior.coords)
                                    self._dxf_adapter.add_hatch_boundary_path(hatch_entity, points=exterior_coords, flags=BOUNDARY_PATH_EXTERNAL)

                                    # Add interior boundaries (holes) if any
                                    for interior in poly.interiors:
                                        interior_coords = list(interior.coords)
                                        self._dxf_adapter.add_hatch_boundary_path(hatch_entity, points=interior_coords, flags=BOUNDARY_PATH_DEFAULT)

                                    # Apply hatch styling USING ADAPTER
                                    if style.hatch.pattern_name:
                                        self._dxf_adapter.set_hatch_pattern_fill(
                                            hatch_entity=hatch_entity,
                                            pattern_name=style.hatch.pattern_name,
                                            color=self._resolve_aci_color(style.hatch.color) if style.hatch.color else DEFAULT_ACI_COLOR,
                                            scale=style.hatch.scale if style.hatch.scale else 1.0,
                                            angle=style.hatch.angle if style.hatch.angle else 0.0
                                        )
                                    else: # Solid fill
                                        self._dxf_adapter.set_hatch_solid_fill(
                                            hatch_entity=hatch_entity,
                                            color=self._resolve_aci_color(style.hatch.color) if style.hatch.color else DEFAULT_ACI_COLOR
                                        )

                                    # NOTE: Hatch entities are fully styled by the adapter methods above.
                                    # Layer is set during add_hatch, colors are set by set_hatch_*_fill methods.
                                    # No additional apply_style_to_dxf_entity call needed for hatch entities.
                                    added_count += 1

                                except Exception as e: # Keep general exception for this complex block
                                    self._logger.warning(f"Failed to create or style HATCH entity for polygon: {e}", exc_info=True)

                            # Always create LWPOLYLINE for polygon boundary (for visibility/editing)
                            exterior_coords = list(poly.exterior.coords)
                            entity = self._dxf_adapter.add_lwpolyline(msp, points=exterior_coords, close=True, dxfattribs={'layer': layer_name})

                            if entity:
                                added_count += 1
                                # Apply style to boundary polyline
                                if style:
                                    try:
                                        self.apply_style_to_dxf_entity(entity, style, dxf_drawing)
                                    except Exception as e:
                                        self._logger.warning(f"Failed to apply style to polygon boundary: {e}")

                            # Add interior rings (holes) as separate polylines
                            for interior in poly.interiors:
                                interior_coords = list(interior.coords)
                                hole_entity = self._dxf_adapter.add_lwpolyline(msp, points=interior_coords, close=True, dxfattribs={'layer': layer_name})
                                if hole_entity:
                                    added_count += 1
                                    # Apply style to hole polyline
                                    if style:
                                        try:
                                            self.apply_style_to_dxf_entity(hole_entity, style, dxf_drawing)
                                        except Exception as e:
                                            self._logger.warning(f"Failed to apply style to polygon hole: {e}")

                        # Add label for polygon if requested
                        label_text_to_add = self._get_label_text_for_feature(row, layer_definition, style, 'Polygon')
                        if label_text_to_add:
                            label_position = self._calculate_label_position(geom, 'Polygon') # 'geom' from iterrows is correct for polygon
                            self._add_label_to_dxf(
                                msp, label_text_to_add, label_position, layer_name, style, dxf_drawing
                            )
                        continue  # Skip the common processing below for polygons

                    elif geom.geom_type in ['MultiPoint', 'MultiLineString']:
                        # Handle multi-geometries
                        for sub_geom in geom.geoms:
                            if sub_geom.geom_type == 'Point':
                                entity = self._dxf_adapter.add_point(msp, location=(sub_geom.x, sub_geom.y, 0.0), dxfattribs={'layer': layer_name})
                            elif sub_geom.geom_type == 'LineString':
                                coords = list(sub_geom.coords)
                                entity = self._dxf_adapter.add_lwpolyline(msp, points=coords, dxfattribs={'layer': layer_name})

                            if entity:
                                added_count += 1
                        continue  # Skip the common processing below for multi-geometries

                    else:
                        self._logger.warning(f"Unsupported geometry type: {geom.geom_type} for feature {idx}")
                        continue

                    # Common processing for non-polygon geometries
                    if entity:
                        added_count += 1

                        # Apply style to individual entity if provided
                        if style:
                            try:
                                self.apply_style_to_dxf_entity(entity, style, dxf_drawing)
                            except Exception as e:
                                self._logger.warning(f"Failed to apply style to entity {idx}: {e}")

                        # Create TEXT entity if text styling is present (for annotations)
                        if style and style.text: # Keep this outer check for style.text presence
                           label_text_to_add = self._get_label_text_for_feature(row, layer_definition, style, geom.geom_type)
                           if label_text_to_add:
                               text_position = self._calculate_label_position(geom, geom.geom_type)
                               self._add_label_to_dxf(msp, label_text_to_add, text_position, layer_name, style, dxf_drawing)
                            # Error handling for _add_label_to_dxf can be inside it or remain here if preferred.
                            # For now, keeping explicit try-except around _add_label_to_dxf if it's complex.
                            # However, _get_label_text_for_feature should not raise, only return None or str.

                except Exception as e:
                    self._logger.warning(f"Failed to add geometry {idx} to DXF: {e}")
                    continue

            self._logger.info(f"Finished adding {added_count} geometries and their styles to layer '{layer_name}'.")

        except Exception as e:
            self._logger.error(f"Failed to add GeoDataFrame geometries to DXF layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add geometries to DXF layer '{layer_name}': {e}")

    def _get_label_text_for_feature(
        self,
        row: pd.Series,
        layer_definition: Optional[GeomLayerDefinition],
        style: Optional[NamedStyle],
        geom_type: str
    ) -> Optional[str]:
        """Determines the label text for a given feature based on layer def, style, and common cols."""
        label_text: Optional[str] = None

        # 1. Try layer_definition.label_column first (primary source for all geom_types if defined)
        if layer_definition and layer_definition.label_column:
            if layer_definition.label_column in row.index and pd.notna(row[layer_definition.label_column]):
                candidate_text = str(row[layer_definition.label_column])
                if candidate_text.strip(): # Ensure not just whitespace
                    label_text = candidate_text.strip()

        # 2. If no label from layer_definition, AND it's a non-polygon WITH style.text, try common columns
        #    This allows general text annotations for points/lines if style.text is present,
        #    even if layer_definition.label_column isn't set or doesn't yield text.
        if label_text is None and geom_type not in ['Polygon', 'MultiPolygon']:
            if style and style.text:
                # This logic is from the original "Create TEXT entity if text styling is present" block
                # Default fallback if no common column is found or they are all empty/NA
                # Using a unique placeholder to distinguish from actual empty string after strip
                no_col_found_placeholder = f"__NO_COMMON_COL_FOR_{geom_type}__"
                text_content_candidate = no_col_found_placeholder

                for col_name in ['label', 'name', 'id', 'text', 'description']:
                    if col_name in row.index and pd.notna(row[col_name]):
                        current_col_text = str(row[col_name])
                        if current_col_text.strip(): # Ensure column itself has meaningful content
                            text_content_candidate = current_col_text.strip()
                            break

                # Legacy: if still placeholder, check for Series attribute 'name' (less common for GeoDataFrame rows)
                if text_content_candidate == no_col_found_placeholder:
                     if hasattr(row, 'name') and isinstance(row.name, str) and pd.notna(row.name) and row.name.strip():
                        text_content_candidate = row.name.strip()

                if text_content_candidate and text_content_candidate != no_col_found_placeholder:
                    label_text = text_content_candidate

        return label_text

    def _calculate_label_position(self, geom, geom_type: str) -> tuple:
        """Calculate the appropriate position for a label based on geometry type."""
        try:
            if geom_type == 'Point':
                # For points, place label slightly offset to avoid overlap
                return (geom.x + 0.1, geom.y + 0.1)

            elif geom_type == 'LineString':
                # For lines, place at the midpoint
                midpoint = geom.interpolate(0.5, normalized=True)
                return (midpoint.x, midpoint.y)

            elif geom_type in ['Polygon', 'MultiPolygon']:
                # For polygons, place at centroid (representative point for complex shapes)
                try:
                    # Use representative_point() for complex polygons to ensure it's inside
                    repr_point = geom.representative_point()
                    return (repr_point.x, repr_point.y)
                except:
                    # Fallback to centroid
                    centroid = geom.centroid
                    return (centroid.x, centroid.y)

            else:
                # Default to centroid for other geometry types
                centroid = geom.centroid
                return (centroid.x, centroid.y)

        except Exception as e:
            self._logger.warning(f"Failed to calculate label position for {geom_type}: {e}")
            # Return a default position
            bounds = geom.bounds
            return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)

    def _add_label_to_dxf(
        self,
        modelspace: Any, # Should be ezdxf.layouts.Modelspace or equivalent from adapter
        label_text: str,
        position: tuple,
        layer_name: str,
        style: Optional[NamedStyle],
        dxf_drawing: Drawing # Added for _ensure_dxf_text_style consistency
    ) -> None:
        """Adds a text or MTEXT label to the DXF modelspace using the DXF adapter."""
        # Adapter checks for its own availability internally
        effective_text_style_name: Optional[str] = None
        text_height = 2.5  # Default height
        text_color_aci: Optional[int] = None
        attachment_point = MTextEntityAlignment.MIDDLE_CENTER # Default for MTEXT
        text_rotation = 0.0

        if style and style.text:
            text_props = style.text
            effective_text_style_name = self._ensure_dxf_text_style(dxf_drawing, text_props)
            if text_props.height is not None:
                text_height = text_props.height
            if text_props.color is not None:
                text_color_aci = self._resolve_aci_color(text_props.color)
            if text_props.rotation is not None:
                text_rotation = text_props.rotation
            if text_props.attachment_point: # For MTEXT
                attachment_point = self._resolve_attachment_point(text_props.attachment_point.value)


        dxfattribs: Dict[str, Any] = {'layer': layer_name}
        if effective_text_style_name:
            dxfattribs['style'] = effective_text_style_name
        if text_color_aci is not None:
            dxfattribs['color'] = text_color_aci
        else: # Default to BYLAYER if no specific color
            dxfattribs['color'] = BYLAYER


        # Determine if MTEXT is needed (multi-line, specific formatting)
        if "\\n" in label_text or "\\\\P" in label_text or "\\\\X" in label_text: # Check for MTEXT specific newlines # MODIFIED
            self._logger.debug(f"Adding MTEXT label: \'{label_text[:30]}...\' to layer {layer_name}")
            try:
                # For MTEXT, ensure char_height is used, and set attachment point
                mtext_dxfattribs = dxfattribs.copy()
                mtext_dxfattribs['char_height'] = text_height
                mtext_dxfattribs['attachment_point'] = attachment_point
                # Width might be needed for MTEXT depending on how text flow is handled.
                # For simplicity, not setting width, allowing auto-width or default.

                # Rotation for MTEXT is handled by dxf.rotation
                if text_rotation != 0: # ezdxf default is 0
                    mtext_dxfattribs['rotation'] = text_rotation

                self._dxf_adapter.add_mtext(
                    msp=modelspace,
                    text=label_text,
                    insert=position, # Using tuple directly as per add_mtext definition
                    dxfattribs=mtext_dxfattribs
                )
            except DXFProcessingError as e:
                self._logger.error(f"Adapter failed to add MTEXT \'{label_text}\': {e}", exc_info=True)
            except Exception as e:
                self._logger.error(f"Unexpected error adding MTEXT \'{label_text}\': {e}", exc_info=True)

        else: # Single line text, use TEXT entity
            text_specific_attrs = dxfattribs.copy()
            if attachment_point: # MTEXT enum needs conversion for TEXT
                halign, valign = self._mtext_attachment_to_text_align(attachment_point)
                text_specific_attrs['halign'] = halign
                text_specific_attrs['valign'] = valign
                if halign != 0 or valign != 0: # If not default (left, baseline)
                    text_specific_attrs['align_point'] = position
            else: # Default for TEXT if no attachment point specified
                text_specific_attrs['halign'] = 0 # TEXT_ALIGN_LEFT (ezdxf default for halign if align_point is set)
                text_specific_attrs['valign'] = 0 # TEXT_ALIGN_BASELINE (ezdxf default for valign if align_point is set)

            text_entity = self._dxf_adapter.add_text(
                modelspace,
                text=label_text,
                point=position, # add_text uses 'point' not 'insert'
                height=text_height,
                rotation=text_rotation,
                style=effective_text_style_name,
                dxfattribs=text_specific_attrs
            )

            if text_entity and style and style.text and style.text.align_to_view:
                self._align_text_entity_to_view(text_entity, dxf_drawing, style.text) # Already reviewed

    def _resolve_attachment_point(self, attachment_point_str: str):
        """Resolve attachment point string to ezdxf constant."""
        if not self._dxf_adapter.is_available():
            return None

        # Mapping of common attachment point names to ezdxf constants
        attachment_map = {
            'TOP_LEFT': MTextEntityAlignment.TOP_LEFT,
            'TOP_CENTER': MTextEntityAlignment.TOP_CENTER,
            'TOP_RIGHT': MTextEntityAlignment.TOP_RIGHT,
            'MIDDLE_LEFT': MTextEntityAlignment.MIDDLE_LEFT,
            'MIDDLE_CENTER': MTextEntityAlignment.MIDDLE_CENTER,
            'MIDDLE_RIGHT': MTextEntityAlignment.MIDDLE_RIGHT,
            'BOTTOM_LEFT': MTextEntityAlignment.BOTTOM_LEFT,
            'BOTTOM_CENTER': MTextEntityAlignment.BOTTOM_CENTER,
            'BOTTOM_RIGHT': MTextEntityAlignment.BOTTOM_RIGHT,
        }

        return attachment_map.get(attachment_point_str.upper(), MTextEntityAlignment.MIDDLE_CENTER)

    def _mtext_attachment_to_text_align(self, attachment_point) -> tuple:
        """Convert MTEXT attachment point to TEXT horizontal and vertical alignment."""
        if not self._dxf_adapter.is_available():
            return (1, 2)  # Default center, middle

        # Map MTEXT attachment to TEXT halign, valign
        # halign: 0=left, 1=center, 2=right, 3=aligned, 4=middle, 5=fit
        # valign: 0=baseline, 1=bottom, 2=middle, 3=top

        if attachment_point == MTextEntityAlignment.TOP_LEFT:
            return (0, 3)  # left, top
        elif attachment_point == MTextEntityAlignment.TOP_CENTER:
            return (1, 3)  # center, top
        elif attachment_point == MTextEntityAlignment.TOP_RIGHT:
            return (2, 3)  # right, top
        elif attachment_point == MTextEntityAlignment.MIDDLE_LEFT:
            return (0, 2)  # left, middle
        elif attachment_point == MTextEntityAlignment.MIDDLE_CENTER:
            return (1, 2)  # center, middle
        elif attachment_point == MTextEntityAlignment.MIDDLE_RIGHT:
            return (2, 2)  # right, middle
        elif attachment_point == MTextEntityAlignment.BOTTOM_LEFT:
            return (0, 1)  # left, bottom
        elif attachment_point == MTextEntityAlignment.BOTTOM_CENTER:
            return (1, 1)  # center, bottom
        elif attachment_point == MTextEntityAlignment.BOTTOM_RIGHT:
            return (2, 1)  # right, bottom
        else:
            return (1, 2)  # default center, middle

    def clear_caches(self) -> None:
        """Clears all cached data to free memory. Useful for long-running processes."""
        if self._aci_map is not None:
            self._logger.debug(f"Clearing ACI color map cache with {len(self._aci_map)} entries")
            self._aci_map = None

    def get_cache_info(self) -> Dict[str, int]:
        """Returns information about cached data for monitoring."""
        return {
            "aci_map_entries": len(self._aci_map) if self._aci_map else 0,
            "aci_map_loaded": self._aci_map is not None
        }
