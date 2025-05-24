"""Concrete implementation of the IStyleApplicator interface."""
from typing import Optional, Any, Dict, Union, cast

import geopandas as gpd

# Attempt ezdxf import
try:
    import ezdxf
    from ezdxf.document import Drawing
    from ezdxf.entities import DXFGraphic, Text, MText
    from ezdxf.lldxf.const import BYLAYER, BYBLOCK
    from ezdxf.math import Vec3, Z_AXIS
    from ezdxf.enums import MTextEntityAlignment
    EZDXF_AVAILABLE = True
except ImportError:
    Drawing = type(None)
    DXFGraphic = type(None)
    Text, MText = type(None), type(None)
    BYLAYER = 256
    BYBLOCK = 0
    Vec3, Z_AXIS = type(None), type(None)
    MTextEntityAlignment = type(None)
    EZDXF_AVAILABLE = False

from ..interfaces.style_applicator_interface import IStyleApplicator
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.config_loader_interface import IConfigLoader # For ACI color map
from ..domain.config_models import (
    StyleConfig, NamedStyle, GeomLayerDefinition,
    LayerStyleProperties, TextStyleProperties, HatchStyleProperties, AciColorMappingItem
)
from ..domain.exceptions import ProcessingError, DXFProcessingError, ConfigError
from .logging_service import LoggingService # Fallback

DEFAULT_ACI_COLOR = 7 # White/Black, a common default
DEFAULT_LINETYPE = "Continuous"
# Constants for DXF lineweights (LW values, not necessarily indices)
LW_BYLAYER = -1
LW_BYBLOCK = -2
LW_DEFAULT = -3

class StyleApplicatorService(IStyleApplicator):
    """Service for applying styles to geometric data and DXF entities."""

    def __init__(
        self,
        config_loader: IConfigLoader,
        logger_service: ILoggingService,
        # lin_file_path: Optional[str] = "acadiso.lin" # Path to linetype definition file
    ):
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)

        self._config_loader = config_loader
        self._aci_map: Optional[Dict[str, int]] = None
        # self._lin_file_path = lin_file_path # For _ensure_dxf_linetype

        if not EZDXF_AVAILABLE:
            self._logger.error("ezdxf library not available. DXF styling functionality will be severely limited.")

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

                self._aci_map = {item.name.lower(): item.aciCode for item in color_items}
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

    def _ensure_dxf_linetype(self, drawing: Drawing, linetype_name: Optional[str]) -> None:
        """Ensures a DXF linetype exists by name, creates it if needed."""
        if not EZDXF_AVAILABLE or linetype_name is None or linetype_name == "BYLAYER":
            return

        # Check if linetype already exists
        if linetype_name in drawing.linetypes:
            self._logger.debug(f"Linetype '{linetype_name}' already exists in DXF.")
            return

        # Define common linetypes with their patterns
        common_linetypes = {
            "DASHED": {
                "pattern": [1.2, 0.5, -0.7],
                "description": "Dashed ----  ----  ----  ----  ----"
            },
            "DOTTED": {
                "pattern": [0.2, 0.0, -0.2],
                "description": "Dotted .  .  .  .  .  .  .  .  ."
            },
            "DASHDOT": {
                "pattern": [1.0, 0.5, -0.25, 0.0, -0.25],
                "description": "Dash dot -----.-----.-----.-----."
            },
            "CENTER": {
                "pattern": [1.25, 0.625, -0.25, 0.125, -0.25],
                "description": "Center -----  -  -----  -  -----"
            },
            "PHANTOM": {
                "pattern": [1.25, 0.625, -0.25, 0.125, -0.25, 0.125, -0.25],
                "description": "Phantom -----  --  --  -----  --"
            }
        }

        # Try to create the linetype if it's a known common type
        if linetype_name in common_linetypes:
            try:
                linetype_def = common_linetypes[linetype_name]
                drawing.linetypes.add(
                    name=linetype_name,
                    pattern=linetype_def["pattern"],
                    description=linetype_def["description"]
                )
                self._logger.info(f"Successfully created linetype '{linetype_name}' in DXF.")
            except Exception as e:
                self._logger.error(f"Failed to create linetype '{linetype_name}': {e}", exc_info=True)
        else:
            # For unknown linetypes, create a simple dashed pattern as fallback
            try:
                drawing.linetypes.add(
                    name=linetype_name,
                    pattern=[1.0, 0.5, -0.5],  # Simple dash pattern
                    description=f"Custom linetype {linetype_name}"
                )
                self._logger.warning(f"Created fallback dashed pattern for unknown linetype '{linetype_name}'.")
            except Exception as e:
                self._logger.error(f"Failed to create fallback linetype '{linetype_name}': {e}", exc_info=True)

    def _ensure_dxf_text_style(self, drawing: Drawing, text_props: Optional[TextStyleProperties]) -> Optional[str]:
        """Ensures a DXF text style exists for the given font name, returns the style name."""
        if not EZDXF_AVAILABLE or text_props is None or text_props.font is None:
            return None # No font specified, or ezdxf not available.

        text_style_name = text_props.font # Assuming text_props.font is the desired DXF text style name

        if text_style_name not in drawing.styles:
            self._logger.info(f"Text style '{text_style_name}' not found. Creating new DXF text style.")
            try:
                # ezdxf uses the style name as the font name if ttf is not specified.
                # For TrueType fonts, the actual TTF file name (e.g., "arial.ttf") is critical.
                # The TextStyleProperties.font is currently just a name. We might need a font_file field.
                # For now, we assume `font` is the name that ezdxf should use for the style.
                # CAD software will then try to find a corresponding font (e.g. Arial.shx, Arial.ttf)
                dxf_text_style = drawing.styles.new(text_style_name)
                # if text_props.font_file: # If we had a font_file property
                #     dxf_text_style.dxf.font = text_props.font_file
                # if text_props.height and text_props.height > 0: # Text styles in DXF can have fixed height 0.0
                #     dxf_text_style.dxf.height = text_props.height # Usually text height is per-entity
                self._logger.info(f"Created DXF text style '{text_style_name}'. Font mapping relies on CAD application.")
            except Exception as e:
                self._logger.error(f"Failed to create DXF text style '{text_style_name}': {e}", exc_info=True)
                return None # Failed to create
        return text_style_name

    def apply_style_to_dxf_entity(
        self,
        entity: DXFGraphic,
        style: NamedStyle,
        dxf_drawing: Drawing
    ) -> None:
        if not EZDXF_AVAILABLE:
            # This check might be redundant if apply_styles_to_dxf_layer also checks, but good for direct calls.
            raise DXFProcessingError("Cannot apply style to DXF entity: ezdxf library not available.")

        self._logger.debug(f"Applying style to DXF entity {entity.dxftype()} (handle: {entity.dxf.handle})")

        # General graphic properties from style.layer
        if style.layer:
            s_layer = style.layer
            entity.dxf.color = self._resolve_aci_color(s_layer.color) if s_layer.color is not None else BYLAYER

            if s_layer.linetype is not None:
                self._ensure_dxf_linetype(dxf_drawing, s_layer.linetype)
                entity.dxf.linetype = s_layer.linetype
            else:
                entity.dxf.linetype = "BYLAYER" # DXF default for entities

            entity.dxf.lineweight = s_layer.lineweight if s_layer.lineweight is not None else LW_BYLAYER

            # Transparency might not be supported by all entity types or DXF versions in the same way.
            # Safest to apply only if entity has 'transparency' attribute.
            if hasattr(entity.dxf, 'transparency') and s_layer.transparency is not None:
                # ezdxf expects transparency as float 0.0 (opaque) to 1.0 (fully transparent)
                # Assuming s_layer.transparency is 0-100 or 0-255, needs normalization if so.
                # For now, assume it's 0.0 to 1.0 directly. Or, if it's an ACI-like value, needs mapping.
                # Let's assume direct 0.0-1.0 for now.
                entity.dxf.transparency = s_layer.transparency

            # Plot style name - usually BYLAYER for entities, controlled by layer plot style table ref
            # entity.dxf.plotstyle_name = "BYLAYER"

        # Entity-type specific styling
        entity_type = entity.dxftype()
        if entity_type in ('TEXT', 'MTEXT') and style.text:
            s_text = style.text
            text_entity = cast(Union[ezdxf.entities.Text, ezdxf.entities.MText], entity)

            # Text Style (Font)
            if s_text.font:
                text_style_name = self._ensure_dxf_text_style(dxf_drawing, s_text)
                if text_style_name:
                    text_entity.dxf.style = text_style_name

            # Text Height
            if s_text.height is not None and s_text.height > 0:
                if entity_type == 'TEXT':
                    cast(ezdxf.entities.Text, text_entity).dxf.height = s_text.height
                elif entity_type == 'MTEXT':
                    cast(ezdxf.entities.MText, text_entity).dxf.char_height = s_text.height

            # Text Rotation
            if s_text.rotation is not None:
                text_entity.dxf.rotation = s_text.rotation # degrees

            # Text Color (override layer color if specified in text style)
            if s_text.color is not None:
                text_entity.dxf.color = self._resolve_aci_color(s_text.color)
            # Other text properties like alignment for TEXT, MTEXT attachment_point can be set here if needed.

        elif entity_type == 'HATCH' and style.hatch:
            s_hatch = style.hatch
            hatch_entity = cast(ezdxf.entities.Hatch, entity)

            if s_hatch.pattern_name is not None:
                hatch_entity.dxf.pattern_name = s_hatch.pattern_name
            if s_hatch.scale is not None and s_hatch.scale > 0:
                hatch_entity.dxf.pattern_scale = s_hatch.scale
            if s_hatch.angle is not None:
                hatch_entity.dxf.pattern_angle = s_hatch.angle # degrees
            # Hatch color usually follows general entity color (from style.layer), but can be overridden
            if s_hatch.color is not None:
                hatch_entity.dxf.color = self._resolve_aci_color(s_hatch.color)
            # Hatch background color, pattern_type, etc. could also be styled.

        # Add styling for other specific DXF types like INSERT (block scaling/rotation), DIMENSION, etc. if needed.
        # self._logger.debug(f"Finished applying style to DXF entity {entity.dxftype()} (handle: {entity.dxf.handle})")
        pass # End of method, explicit pass to signify completion of planned logic here

    def _align_text_entity_to_view(self, entity: DXFGraphic, doc: Drawing, text_props: TextStyleProperties) -> None:
        """Aligns TEXT or MTEXT entity to be readable from the current view (WCS Z-axis)."""
        if not EZDXF_AVAILABLE or not isinstance(entity, (Text, MText)):
            return

        self._logger.debug(f"Aligning entity {entity.dxf.handle} ({entity.dxftype()}) to view.")

        # Simplified: align to be flat with WCS XY plane (readable from top-down Z-axis view)
        # This means the text's own Z-axis should align with WCS Z-axis.
        # For TEXT entities, this means rotation should be relative to WCS X-axis.
        # For MTEXT, its OCS Z-axis should align with WCS Z-axis.

        target_z_axis_wcs = Z_AXIS # World Z-axis (0,0,1)

        try:
            if entity.dxf.hasattr('extrusion'): # Should be OCS Z-axis
                current_z_axis_wcs = Vec3(entity.dxf.extrusion).normalize()
            else: # For TEXT entities that might not have extrusion explicitly if default (0,0,1)
                current_z_axis_wcs = Z_AXIS

            # If current_z_axis is already aligned with target_z_axis (or its inverse), no rotation needed for flattening
            if not current_z_axis_wcs.is_parallel_to(target_z_axis_wcs, tol=1e-9):
                 # This case indicates the text is already on a plane not parallel to XY_WCS
                 # The old code's rotation logic was to make it parallel.
                 # For MTEXT, setting extrusion to (0,0,1) makes it parallel to XY_WCS
                 # For TEXT, rotation is planar, so if its OCS is not (0,0,1), it's complex.
                 # Most TEXT entities are created with OCS aligned to WCS unless explicitly set.
                 # Let's assume for TEXT its OCS Z is (0,0,1) and we only adjust planar rotation.
                 if isinstance(entity, MText):
                     entity.dxf.extrusion = target_z_axis_wcs # Make MTEXT plane parallel to WCS XY
                     # MTEXT rotation is relative to its OCS X-axis.
                     # After setting extrusion to (0,0,1), its OCS X is (1,0,0) WCS.
                     # A rotation of 0 means text reads along WCS X.
                     entity.dxf.rotation = text_props.rotation if text_props.rotation is not None else 0.0
                 # For TEXT, if we ensure its OCS is (0,0,1), then its dxf.rotation is directly in XY WCS.
                 # However, TEXT rotation is applied *after* OCS transformation.
                 # If TEXT OCS Z is not (0,0,1), then just setting dxf.rotation isn't enough.
                 # The original align_to_view was more complex for arbitrary OCS.
                 # For simplicity, we assume TEXT entities are typically on XY plane or this needs more.

            # After potentially re-orienting MTEXT OCS, apply planar rotation if specified
            # For TEXT, this is its primary rotation.
            if text_props.rotation is not None:
                 entity.dxf.rotation = text_props.rotation
            else: # Default to 0 rotation if not specified, after potential OCS alignment for MTEXT
                 if isinstance(entity, MText) and entity.dxf.extrusion == target_z_axis_wcs:
                      entity.dxf.rotation = 0.0
                 elif isinstance(entity, Text): # Assume TEXT is on XY plane
                      entity.dxf.rotation = 0.0


            # Attachment point adjustment (simplified from original)
            if isinstance(entity, MText) and text_props.align_attachment_point:
                # This is a placeholder. The original logic was complex.
                # A common strategy after aligning to view is to use a center attachment.
                try:
                    entity.dxf.attachment_point = MTextEntityAlignment.MIDDLE_CENTER
                except Exception as e_attach:
                    self._logger.warning(f"Failed to set MTEXT attachment point during align: {e_attach}")

            self._logger.debug(f"Entity {entity.dxf.handle} aligned. New rotation: {entity.dxf.get('rotation', 'N/A')}")

        except Exception as e:
            self._logger.error(f"Error aligning text entity {entity.dxf.handle}: {e}", exc_info=True)

    def apply_styles_to_dxf_layer(
        self,
        dxf_drawing: Drawing,
        layer_name: str,
        style: NamedStyle
    ) -> None:
        if not EZDXF_AVAILABLE:
            raise DXFProcessingError("Cannot apply styles to DXF layer: ezdxf library not available.")

        self._logger.debug(f"Applying style to DXF layer: {layer_name}")
        try:
            dxf_layer = dxf_drawing.layers.get(layer_name)
        except ezdxf.DXFTableEntryError:
            self._logger.info(f"DXF Layer '{layer_name}' not found in drawing. Creating it...")
            try:
                dxf_layer = dxf_drawing.layers.new(layer_name)
                self._logger.info(f"Successfully created DXF layer '{layer_name}'")
            except Exception as e:
                self._logger.error(f"Failed to create DXF layer '{layer_name}': {e}", exc_info=True)
                return

        if style.layer: # Apply properties from the 'layer' part of NamedStyle
            s_layer = style.layer
            if s_layer.color is not None:
                dxf_layer.color = self._resolve_aci_color(s_layer.color)
            if s_layer.linetype is not None:
                self._ensure_dxf_linetype(dxf_drawing, s_layer.linetype)
                dxf_layer.linetype = s_layer.linetype
            else: # Default linetype for layer if not specified in style
                dxf_layer.linetype = DEFAULT_LINETYPE

            if s_layer.lineweight is not None:
                # ezdxf uses specific codes for lineweights, e.g. 13 for 0.13mm, -1 for ByLayer, -2 ByBlock, -3 Default
                # Assuming s_layer.lineweight is one of these codes directly.
                dxf_layer.lineweight = s_layer.lineweight

            if s_layer.plot is not None:
                dxf_layer.dxf.plot = int(s_layer.plot) # DXF plot flag is 0 or 1

            if s_layer.is_on is not None:
                if s_layer.is_on:
                    dxf_layer.on()
                else:
                    dxf_layer.off()

            if s_layer.frozen is not None:
                if s_layer.frozen:
                    dxf_layer.freeze()
                else:
                    dxf_layer.thaw()

            if s_layer.locked is not None:
                if s_layer.locked:
                    dxf_layer.lock()
                else:
                    dxf_layer.unlock()

            # Transparency on DXF layers is complex, often not a direct layer property in older DXF
            # It might be an extended data or only per-entity. For now, not setting at layer level.
            # if s_layer.transparency is not None: self._logger.warning("Layer-level transparency not directly set in DXF via this service yet.")

            self._logger.info(f"Applied layer-level properties from style to DXF layer '{layer_name}'.")
        else:
            self._logger.debug(f"No specific 'layer' properties in NamedStyle for DXF layer '{layer_name}'. Layer defaults maintained.")

        # Apply style to entities on this layer if the style has entity-specific parts or needs to override layer settings
        if EZDXF_AVAILABLE: # Guard the whole block
            # Query entities on the specified layer from the modelspace.
            # TODO: Consider if entities can be in other blocks or layouts if layer_name is global and used there.
            # For now, assuming styling is primarily for modelspace entities.
            msp = dxf_drawing.modelspace()
            entities_on_layer = msp.query(f'*[layer=="{layer_name}"]')

            if entities_on_layer:
                self._logger.info(f"Found {len(entities_on_layer)} entities on DXF layer '{layer_name}'. Applying entity-specific styles.")
                for entity in entities_on_layer:
                    # Ensure entity is a DXFGraphic (it should be from query)
                    if isinstance(entity, DXFGraphic):
                        self.apply_style_to_dxf_entity(entity, style, dxf_drawing)
                    else:
                        self._logger.warning(f"Skipping non-DXFGraphic entity found on layer '{layer_name}': {type(entity)}")
                self._logger.info(f"Finished applying entity-specific styles for DXF layer '{layer_name}'.")
            else:
                self._logger.debug(f"No entities found on DXF layer '{layer_name}' to apply entity-specific styles.")
        else:
            self._logger.warning(f"Skipping entity-specific styling for layer '{layer_name}': ezdxf not available.")
        # self._logger.warning(f"Entity-specific styling for layer '{layer_name}' based on overall style is not yet implemented.") # Remove this old warning

    def add_geodataframe_to_dxf(
        self,
        dxf_drawing: Drawing,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        style: Optional[NamedStyle] = None,
        layer_definition: Optional[GeomLayerDefinition] = None
    ) -> None:
        """Adds geometries from a GeoDataFrame to a DXF drawing with optional label placement."""
        if not EZDXF_AVAILABLE:
            raise DXFProcessingError("Cannot add geometries to DXF: ezdxf library not available.")

        if gdf.empty:
            self._logger.debug(f"GeoDataFrame for layer '{layer_name}' is empty. No geometries to add.")
            return

        self._logger.debug(f"Adding {len(gdf)} geometries to DXF layer '{layer_name}'")

        try:
            # Get the modelspace
            msp = dxf_drawing.modelspace()

            # Check if labels should be added
            should_add_labels = (
                layer_definition and
                layer_definition.label_column and
                layer_definition.label_column in gdf.columns
            )

            if should_add_labels:
                self._logger.debug(f"Will add labels from column '{layer_definition.label_column}' for layer '{layer_name}'")

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
                        entity = msp.add_point((geom.x, geom.y), dxfattribs={'layer': layer_name})

                    elif geom.geom_type == 'LineString':
                        # Add as a polyline
                        coords = list(geom.coords)
                        entity = msp.add_lwpolyline(coords, dxfattribs={'layer': layer_name})

                    elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                        # Handle polygons
                        if geom.geom_type == 'Polygon':
                            polygons = [geom]
                        else:
                            polygons = list(geom.geoms)

                        for poly in polygons:
                            # Add exterior ring as polyline
                            exterior_coords = list(poly.exterior.coords)
                            entity = msp.add_lwpolyline(exterior_coords, close=True, dxfattribs={'layer': layer_name})

                            if entity:
                                added_count += 1

                            # Add interior rings (holes) if any
                            for interior in poly.interiors:
                                interior_coords = list(interior.coords)
                                hole_entity = msp.add_lwpolyline(interior_coords, close=True, dxfattribs={'layer': layer_name})
                                if hole_entity:
                                    added_count += 1

                        # Add label for polygon if requested
                        if should_add_labels:
                            label_text = str(row[layer_definition.label_column])
                            if label_text and label_text.strip():
                                label_position = self._calculate_label_position(geom, 'Polygon')
                                self._add_label_to_dxf(
                                    msp, label_text, label_position, layer_name, style, dxf_drawing
                                )
                        continue  # Skip the common processing below for polygons

                    elif geom.geom_type in ['MultiPoint', 'MultiLineString']:
                        # Handle multi-geometries
                        for sub_geom in geom.geoms:
                            if sub_geom.geom_type == 'Point':
                                entity = msp.add_point((sub_geom.x, sub_geom.y), dxfattribs={'layer': layer_name})
                            elif sub_geom.geom_type == 'LineString':
                                coords = list(sub_geom.coords)
                                entity = msp.add_lwpolyline(coords, dxfattribs={'layer': layer_name})

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

                    # Add label for non-polygon geometries if requested
                    if should_add_labels and entity:
                        label_text = str(row[layer_definition.label_column])
                        if label_text and label_text.strip():
                            label_position = self._calculate_label_position(geom, geom.geom_type)
                            self._add_label_to_dxf(
                                msp, label_text, label_position, layer_name, style, dxf_drawing
                            )

                except Exception as e:
                    self._logger.warning(f"Failed to add geometry {idx} to DXF: {e}")
                    continue

            self._logger.info(f"Successfully added {added_count} entities to DXF layer '{layer_name}'")

        except Exception as e:
            self._logger.error(f"Failed to add GeoDataFrame geometries to DXF layer '{layer_name}': {e}", exc_info=True)
            raise DXFProcessingError(f"Failed to add geometries to DXF layer '{layer_name}': {e}")

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
        modelspace,
        label_text: str,
        position: tuple,
        layer_name: str,
        style: Optional[NamedStyle],
        dxf_drawing: Drawing
    ) -> None:
        """Add a text label to the DXF drawing with proper styling."""
        try:
            # Determine text properties from style
            text_height = 2.5  # Default height
            text_style_name = None
            text_color = None
            rotation = 0.0
            attachment_point = None

            if style and style.text:
                text_props = style.text
                if text_props.height and text_props.height > 0:
                    text_height = text_props.height
                if text_props.font:
                    text_style_name = self._ensure_dxf_text_style(dxf_drawing, text_props)
                if text_props.color:
                    text_color = self._resolve_aci_color(text_props.color)
                if text_props.rotation is not None:
                    rotation = text_props.rotation
                if text_props.attachment_point:
                    attachment_point = self._resolve_attachment_point(text_props.attachment_point)

            # Create DXF attributes for the text
            text_dxfattribs = {'layer': layer_name}
            if text_color is not None:
                text_dxfattribs['color'] = text_color

            # Decide whether to use TEXT or MTEXT based on content and style
            use_mtext = (
                '\n' in label_text or  # Multi-line text
                len(label_text) > 50 or  # Long text
                (style and style.text and (
                    style.text.max_width and style.text.max_width > 0 or
                    style.text.flow_direction or
                    style.text.line_spacing_style
                ))
            )

            if use_mtext:
                # Use MTEXT for multi-line or styled text
                mtext_entity = modelspace.add_mtext(
                    label_text,
                    dxfattribs=text_dxfattribs
                )
                mtext_entity.dxf.insert = Vec3(position[0], position[1], 0)
                mtext_entity.dxf.char_height = text_height
                mtext_entity.dxf.rotation = rotation

                if text_style_name:
                    mtext_entity.dxf.style = text_style_name

                if attachment_point:
                    try:
                        mtext_entity.dxf.attachment_point = attachment_point
                    except:
                        # Fallback to middle center if attachment point fails
                        mtext_entity.dxf.attachment_point = MTextEntityAlignment.MIDDLE_CENTER
                else:
                    # Default to middle center for better label appearance
                    mtext_entity.dxf.attachment_point = MTextEntityAlignment.MIDDLE_CENTER

                # Apply additional MTEXT properties if available
                if style and style.text:
                    text_props = style.text
                    if text_props.max_width and text_props.max_width > 0:
                        mtext_entity.dxf.width = text_props.max_width
                    if text_props.line_spacing_factor:
                        mtext_entity.dxf.line_spacing_factor = text_props.line_spacing_factor

                # Apply align_to_view if specified
                if style and style.text and style.text.align_to_view:
                    self._align_text_entity_to_view(mtext_entity, dxf_drawing, style.text)

            else:
                # Use simple TEXT for single-line text
                text_entity = modelspace.add_text(
                    label_text,
                    dxfattribs=text_dxfattribs
                )
                text_entity.dxf.insert = Vec3(position[0], position[1], 0)
                text_entity.dxf.height = text_height
                text_entity.dxf.rotation = rotation

                if text_style_name:
                    text_entity.dxf.style = text_style_name

                # For TEXT entities, set horizontal and vertical alignment
                if attachment_point:
                    # Convert MTEXT attachment to TEXT alignment
                    halign, valign = self._mtext_attachment_to_text_align(attachment_point)
                    text_entity.dxf.halign = halign
                    text_entity.dxf.valign = valign
                    # If alignment is not default, set align_point
                    if halign != 0 or valign != 0:
                        text_entity.dxf.align_point = Vec3(position[0], position[1], 0)
                else:
                    # Default center alignment for labels
                    text_entity.dxf.halign = 1  # Center
                    text_entity.dxf.valign = 2  # Middle
                    text_entity.dxf.align_point = Vec3(position[0], position[1], 0)

                # Apply align_to_view if specified
                if style and style.text and style.text.align_to_view:
                    self._align_text_entity_to_view(text_entity, dxf_drawing, style.text)

        except Exception as e:
            self._logger.warning(f"Failed to add label '{label_text}' at position {position}: {e}")

    def _resolve_attachment_point(self, attachment_point_str: str):
        """Resolve attachment point string to ezdxf constant."""
        if not EZDXF_AVAILABLE:
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
        if not EZDXF_AVAILABLE:
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
