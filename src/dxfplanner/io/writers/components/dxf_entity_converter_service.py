from typing import Any, Optional, cast, Tuple, Union, Dict
import math
from pathlib import Path
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ezdxf.entities import DXFGraphic, Point, Line, LWPolyline, Hatch, MText, Text, Insert, Circle, Arc, Polyline as EzdxfPolyline
import yaml

from dxfplanner.config.schemas import ProjectConfig, DxfWriterConfig, LayerStyleConfig, HatchPropertiesConfig, TextStyleConfig
from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfPoint, DxfLine, DxfLWPolyline, DxfHatch, DxfCircle, DxfArc,
    DxfText, DxfMText, DxfInsert, AnyDxfEntity, DxfHatchPath, HatchEdgeType,
    DxfPolyline
)
from dxfplanner.domain.interfaces import IDxfEntityConverterService
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.color_utils import get_color_code, convert_transparency
from dxfplanner.geometry.layer_utils import sanitize_layer_name
from dxfplanner.config.common_schemas import ColorModel

logger = get_logger(__name__)

class DxfEntityConverterService(IDxfEntityConverterService):
    """Service for converting DxfEntity domain models to ezdxf DXFGraphic entities."""

    def __init__(self, project_config: ProjectConfig):
        self.project_config = project_config
        self.writer_config: DxfWriterConfig = project_config.dxf_writer
        self.logger = logger
        self.name_to_aci_map: Dict[str, int] = {}

        # Load ACI color map from YAML
        yaml_path_str = self.writer_config.aci_colors_map_path
        if yaml_path_str:
            aci_colors_yaml_path = Path(yaml_path_str)
            # If the path from config is relative, assume it's relative to CWD (project root).
            # A more robust solution might involve resolving relative to the main project config file.
            if not aci_colors_yaml_path.is_absolute():
                aci_colors_yaml_path = Path.cwd() / aci_colors_yaml_path
                self.logger.info(f"ACI colors map path '{yaml_path_str}' from config is relative, resolved to: {aci_colors_yaml_path}")
            else:
                self.logger.info(f"Using absolute ACI colors map path from config: {aci_colors_yaml_path}")
        else:
            # Default to "aci_colors.yaml" in the current working directory (assumed project root)
            aci_colors_yaml_path = Path.cwd() / "aci_colors.yaml"
            self.logger.info(f"No ACI colors map path configured in DxfWriterConfig, defaulting to: {aci_colors_yaml_path}")

        if aci_colors_yaml_path.exists():
            try:
                # TODO: Load ACI colors map from YAML
                with open(aci_colors_yaml_path, 'r') as f:
                    aci_data = yaml.safe_load(f)
                    if isinstance(aci_data, list):
                        for item in aci_data:
                            if isinstance(item, dict) and 'name' in item and 'aciCode' in item:
                                self.name_to_aci_map[str(item['name']).lower()] = int(item['aciCode'])
                        self.logger.info(f"Successfully loaded {len(self.name_to_aci_map)} ACI color name mappings from {aci_colors_yaml_path}")
                    else:
                        self.logger.warning(f"ACI colors YAML file {aci_colors_yaml_path} is not a list of mappings. ACI name resolution will be limited.")
            except Exception as e:
                self.logger.error(f"Failed to load or parse ACI colors YAML from {aci_colors_yaml_path}: {e}", exc_info=True)
        else:
            self.logger.warning(f"ACI colors YAML file not found at {aci_colors_yaml_path}. ACI color name resolution will be limited.")

    async def add_dxf_entity_to_modelspace(
        self,
        msp: Modelspace,
        doc: Drawing,
        dxf_entity_model: AnyDxfEntity,
        layer_style_config: LayerStyleConfig # For applying styles
    ) -> Optional[DXFGraphic]:
        """
        Converts a DxfEntity domain model to an ezdxf entity and adds it to modelspace.
        Applies common styling.
        Returns the created ezdxf entity or None.
        """
        ezdxf_entity: Optional[DXFGraphic] = None
        entity_type_name = dxf_entity_model.__class__.__name__
        self.logger.debug(f"Processing DxfEntity model: {entity_type_name}, Layer: {dxf_entity_model.layer}")

        # Dispatch based on type
        # Specific handlers will be added in Part 2
        if isinstance(dxf_entity_model, DxfPoint):
            ezdxf_entity = await self._add_dxf_point(msp, cast(DxfPoint, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfLWPolyline):
            ezdxf_entity = await self._add_dxf_lwpolyline(msp, cast(DxfLWPolyline, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfHatch):
            ezdxf_entity = await self._add_dxf_hatch(msp, doc, cast(DxfHatch, dxf_entity_model), layer_style_config)
        elif isinstance(dxf_entity_model, DxfMText):
            ezdxf_entity = await self._add_dxf_mtext(msp, doc, cast(DxfMText, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfText): # Simple Text
            ezdxf_entity = await self._add_dxf_text(msp, doc, cast(DxfText, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfInsert): # Block Reference
            ezdxf_entity = await self._add_dxf_insert(msp, doc, cast(DxfInsert, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfLine):
            ezdxf_entity = await self._add_dxf_line(msp, cast(DxfLine, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfCircle):
            ezdxf_entity = await self._add_dxf_circle(msp, cast(DxfCircle, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfArc):
            ezdxf_entity = await self._add_dxf_arc(msp, cast(DxfArc, dxf_entity_model))
        elif isinstance(dxf_entity_model, DxfPolyline):
            ezdxf_entity = await self._add_dxf_polyline(msp, cast(DxfPolyline, dxf_entity_model))
        # Add other types like DxfEllipse, DxfSpline as needed
        else:
            self.logger.warning(f"Unsupported DxfEntity model type: {entity_type_name}. Skipping.")
            return None

        if ezdxf_entity:
            await self._apply_common_dxf_attributes(ezdxf_entity, dxf_entity_model, layer_style_config)
            # Apply XDATA after common attributes
            await self._apply_xdata(ezdxf_entity, dxf_entity_model)
            self.logger.debug(f"Successfully added and styled {entity_type_name} (handle: {ezdxf_entity.dxf.handle}) to layer {dxf_entity_model.layer}")
        else:
            self.logger.warning(f"Failed to create ezdxf entity for {entity_type_name} on layer {dxf_entity_model.layer}")

        return ezdxf_entity

    async def _apply_common_dxf_attributes(
        self,
        entity: DXFGraphic,
        dxf_model: DxfEntity, # Base DxfEntity has common attributes
        layer_style_cfg: LayerStyleConfig
    ) -> None:
        """Applies common DXF attributes (layer, color, linetype, transparency) to an ezdxf entity."""
        s_layer_name = sanitize_layer_name(dxf_model.layer or self.writer_config.default_layer_properties.name if self.writer_config.default_layer_properties else "0")
        entity.dxf.layer = s_layer_name

        # Color
        effective_color_val: Optional[Union[int, Tuple[int, int, int], str, ColorModel]] = None
        if dxf_model.true_color is not None: # This would be an RGB tuple
            effective_color_val = dxf_model.true_color
        elif dxf_model.color_256 is not None: # This would be an ACI int
            effective_color_val = dxf_model.color_256
        elif layer_style_cfg and layer_style_cfg.layer_props and layer_style_cfg.layer_props.color is not None:
            effective_color_val = layer_style_cfg.layer_props.color # This IS a ColorModel instance

        if effective_color_val is not None:
            actual_color_to_pass: Optional[Union[int, Tuple[int, int, int], str]] = None
            if isinstance(effective_color_val, ColorModel):
                if effective_color_val.rgb is not None:
                    actual_color_to_pass = effective_color_val.rgb
                elif effective_color_val.aci is not None:
                    actual_color_to_pass = effective_color_val.aci
                # else: ColorModel validator ensures at least one is present
            else: # It's already an int (ACI), str (name/RGB string), or tuple (RGB)
                actual_color_to_pass = effective_color_val

            if actual_color_to_pass is not None:
                entity.dxf.color = get_color_code(actual_color_to_pass, self.name_to_aci_map)
            # else: if ColorModel was valid but actual_color_to_pass became None (e.g. future logic),
            # default color is handled by get_color_code if actual_color_to_pass is None.

        # Linetype
        effective_linetype = dxf_model.linetype or (layer_style_cfg.layer_props.linetype if layer_style_cfg.layer_props else None)
        if effective_linetype:
            entity.dxf.linetype = effective_linetype
        else:
            # Explicitly set to BYLAYER if not specified, to inherit from layer
            entity.dxf.linetype = "BYLAYER"


        # Lineweight
        # Note: DxfEntity model does not currently have lineweight.
        # It should typically come from LayerStyleConfig or layer properties.
        if layer_style_cfg.layer_props and layer_style_cfg.layer_props.lineweight is not None:
             # ezdxf uses positive integers for lineweight (e.g., 25 for 0.25mm)
            entity.dxf.lineweight = layer_style_cfg.layer_props.lineweight
        else:
            # Explicitly set to BYLAYER if not specified
            entity.dxf.lineweight = ezdxf.const.LINEWEIGHT_BYLAYER


        # Transparency
        # DxfEntity model also does not have transparency. Use LayerStyleConfig.
        effective_transparency = layer_style_cfg.layer_props.transparency if layer_style_cfg.layer_props else None
        if effective_transparency is not None:
            try:
                transparency_value = convert_transparency(effective_transparency)
                if transparency_value is not None: # convert_transparency could return a specific ezdxf const e.g. TRANSPARENCY_BYBLOCK
                    entity.dxf.transparency = transparency_value
                    self.logger.debug(f"Applied transparency {transparency_value} from {effective_transparency}")
                else: # convert_transparency returned None (e.g. for "BYLAYER" string or if it handles discarding)
                    if hasattr(entity.dxf, "transparency"): # Check if attribute exists before discarding
                        entity.dxf.discard("transparency") # CORRECTED: Set BYLAYER by discarding
                    self.logger.debug(f"Set transparency to BYLAYER for entity due to effective_transparency: {effective_transparency}")
            except ValueError as e:
                self.logger.warning(f"Invalid transparency value '{effective_transparency}': {e}. Setting to BYLAYER.")
                if hasattr(entity.dxf, "transparency"): # Check if attribute exists before discarding
                    entity.dxf.discard("transparency") # CORRECTED: Set BYLAYER by discarding
        else:
             # Default to BYLAYER if not specified in layer_style
            if hasattr(entity.dxf, "transparency"): # Check if attribute exists before discarding
                entity.dxf.discard("transparency") # CORRECTED: Set BYLAYER by discarding
            self.logger.debug("Set transparency to BYLAYER for entity (default).")

        # True Color (if applicable and if color was a string like "RGB:10,20,30")
        # get_color_code handles if it's an ACI or a true color string.
        # If get_color_code returned an ACI, true_color should not be set.
        # If it returned ezdxf.rgb2int for a true color, then that's already handled by entity.dxf.color.
        # Modern ezdxf versions might prefer entity.true_color for RGB.
        # For now, relying on entity.dxf.color to handle both ACI and true color via ezdxf.rgb2int.
        # If specific true_color field is needed:
        # if isinstance(effective_color_val, str) and effective_color_val.upper().startswith("RGB:"):
        #     try:
        #         rgb = tuple(map(int, effective_color_val[4:].split(',')))
        #         entity.true_color = rgb # May need ezdxf.colors.RGB(*rgb) for older ezdxf
        #     except ValueError:
        #         self.logger.warning(f"Invalid RGB color string: {effective_color_val}")

    async def _apply_xdata(self, entity: DXFGraphic, dxf_model: DxfEntity) -> None:
        """Applies XDATA to the ezdxf entity if specified in the domain model."""
        if dxf_model.xdata_app_id and dxf_model.xdata_tags:
            try:
                entity.set_xdata(dxf_model.xdata_app_id, dxf_model.xdata_tags)
                self.logger.debug(f"Applied XDATA (AppID: {dxf_model.xdata_app_id}) to entity {entity.dxf.handle}")
            except AttributeError:
                self.logger.warning(f"Entity {entity.dxf.handle} (type: {entity.dxftype()}) might not support XDATA directly.", exc_info=False)
            except Exception as e_xdata:
                self.logger.error(f"Failed to set XDATA for entity {entity.dxf.handle}: {e_xdata}", exc_info=True)
        elif dxf_model.xdata_app_id or dxf_model.xdata_tags: # Only one is present
            self.logger.warning(f"XDATA for entity {hasattr(entity, 'dxf') and entity.dxf.handle or 'unknown'} was partially specified (app_id: {dxf_model.xdata_app_id is not None}, tags: {dxf_model.xdata_tags is not None}). Both app_id and tags are required to set XDATA.")

    # Placeholder for specific add methods to be added in Part 2
    async def _add_dxf_point(self, msp: Modelspace, model: DxfPoint) -> Optional[Point]:
        """Adds a DXF Point entity to the modelspace."""
        try:
            # DxfPoint model uses model.position which is a Coordinate object
            point_coords = (model.position.x, model.position.y)
            if model.position.z is not None:
                point_coords += (model.position.z,)
            return msp.add_point(location=point_coords)
        except Exception as e:
            self.logger.error(f"Error adding DxfPoint: {e}", exc_info=True)
            return None

    async def _add_dxf_line(self, msp: Modelspace, model: DxfLine) -> Optional[Line]:
        """Adds a DXF Line entity to the modelspace."""
        try:
            start = (model.start_point.x, model.start_point.y)
            if model.start_point.z is not None:
                start += (model.start_point.z,)

            end = (model.end_point.x, model.end_point.y)
            if model.end_point.z is not None:
                end += (model.end_point.z,)

            return msp.add_line(start=start, end=end)
        except Exception as e:
            self.logger.error(f"Error adding DxfLine: {e}", exc_info=True)
            return None

    async def _add_dxf_lwpolyline(self, msp: Modelspace, model: DxfLWPolyline) -> Optional[LWPolyline]:
        """Adds a DXF LWPolyline entity to the modelspace."""
        try:
            # LWPOLYLINE points are 2D (x, y) or (x, y, start_width, end_width, bulge)
            # DxfLWPolyline model.points are Coordinates (x,y,z)
            # For now, assume simple (x,y) points and ignore Z for LWPolyline
            points_data = []
            has_z_values = False
            for p in model.points:
                points_data.append((p.x, p.y))
                if p.z is not None and p.z != 0: # Check if any non-zero Z is present
                    has_z_values = True

            if has_z_values:
                self.logger.debug(f"LWPolyline ({model.layer}): Z coordinates present in DxfLWPolyline model points are discarded for LWPolyline entity.")

            if not points_data:
                self.logger.warning("Attempted to add LWPolyline with no points.")
                return None

            lwpolyline = msp.add_lwpolyline(
                points=points_data,
                dxfattribs={'closed': model.is_closed}
            )
            # Bulge values, if present in DxfLWPolyline model, would need to be set per-vertex
            # e.g., if model.points had [(x,y,bulge), ...]:
            # for i, vertex_model in enumerate(model.points_with_bulge_if_any):
            #    lwpolyline[i] = (vertex_model.x, vertex_model.y, vertex_model.bulge_value)
            return lwpolyline
        except Exception as e:
            self.logger.error(f"Error adding DxfLWPolyline: {e}", exc_info=True)
            return None

    def _get_hatch_pattern_details(self, hatch_pattern_config: Optional[HatchPropertiesConfig]) -> tuple[str, float, float]:
        """Extracts hatch pattern name, scale, and angle from config, with defaults."""
        pattern_name = "SOLID" # Default if no config or if style is SOLID and name is missing
        pattern_scale = 1.0
        pattern_angle = 0.0

        if hatch_pattern_config:
            # Determine pattern_name first based on style and name
            if hatch_pattern_config.style and hatch_pattern_config.style.upper() == "SOLID":
                pattern_name = "SOLID"
            elif hatch_pattern_config.pattern_name: # Corrected: Use pattern_name
                pattern_name = hatch_pattern_config.pattern_name # Corrected: Use pattern_name
            # If style is not SOLID and pattern_name is not given, it defaults to "SOLID", which means it will be treated as solid fill later.

            if hatch_pattern_config.scale is not None:
                pattern_scale = hatch_pattern_config.scale
            if hatch_pattern_config.angle is not None:
                pattern_angle = hatch_pattern_config.angle
        return pattern_name, pattern_scale, pattern_angle

    async def _add_dxf_hatch(self, msp: Modelspace, doc: Drawing, model: DxfHatch, layer_style_cfg: LayerStyleConfig) -> Optional[Hatch]:
        """Adds a DXF Hatch entity to the modelspace."""
        try:
            hatch = msp.add_hatch()
            # Common attributes (color, layer, etc.) are applied later by _apply_common_dxf_attributes

            # Set island detection style (defaulting to normal)
            # TODO: Consider making hatch_style configurable if needed via DxfHatch or HatchPropertiesConfig
            hatch.dxf.hatch_style = ezdxf.const.HATCH_STYLE_NORMAL

            model_hatch_props = model.hatch_props

            # Determine if solid fill or pattern fill based on resolved pattern_name
            # _get_hatch_pattern_details will return "SOLID" if it's meant to be a solid fill
            pattern_name, scale, angle_deg = self._get_hatch_pattern_details(model_hatch_props)

            if pattern_name.upper() == "SOLID":
                hatch.set_solid_fill()
                self.logger.debug(f"Hatch set to SOLID fill. Island style: {hatch.dxf.hatch_style}")

                # Revised color setting for SOLID fills:
                if model_hatch_props and model_hatch_props.pattern_color:
                    color_model_val = model_hatch_props.pattern_color # This is a ColorModel instance

                    if color_model_val.rgb is not None:
                        hatch.rgb = color_model_val.rgb # ezdxf handles setting .dxf.color to BYLAYER and .dxf.true_color
                        self.logger.debug(f"Solid Hatch: Set fill color using RGB: {color_model_val.rgb}")
                    elif color_model_val.aci is not None:
                        # Fallback to ACI if RGB is not present in the ColorModel
                        # get_color_code will return the ACI value directly if it's an int.
                        resolved_color_aci = get_color_code(color_model_val.aci, self.name_to_aci_map)
                        hatch.dxf.color = resolved_color_aci
                        self.logger.debug(f"Solid Hatch: Set fill color using ACI: {color_model_val.aci} -> resolved to {resolved_color_aci}")
                    # else: ColorModel is valid but has neither RGB nor ACI - should not happen due to Pydantic validation.
                    # In this case, color would be inherited from layer via _apply_common_dxf_attributes if not set here.
                # If model_hatch_props.pattern_color is None, color will be handled by _apply_common_dxf_attributes

            else: # Pattern fill
                # Pattern fill
                hatch.set_pattern_fill(
                    name=pattern_name,
                    scale=scale,
                    angle=angle_deg, # degrees
                    # color for pattern lines is typically the entity's color, set by _apply_common_dxf_attributes
                )
                self.logger.debug(f"Hatch set to PATTERN fill: {pattern_name}, scale: {scale}, angle: {angle_deg}. Island style: {hatch.dxf.hatch_style}")

            # Add boundary paths
            # DxfHatchPath model is assumed to always represent a polyline path.
            for path_model in model.paths: # path_model is an instance of DxfHatchPath
                path_points = []

                # Consistently use path_model.vertices as per DxfHatchPath definition
                if not path_model.vertices:
                    self.logger.warning(f"Hatch path model for hatch on layer {model.layer or 'unknown'} has no vertices. Skipping this path.")
                    continue

                path_points = [(v.x, v.y) for v in path_model.vertices]

                # TODO: Handle bulge values if DxfHatch polyline paths support them in the DxfHatchPath model in the future.
                # For now, assuming simple vertices.
                hatch.paths.add_polyline_path(
                    path_vertices=path_points,
                    is_closed=path_model.is_closed,
                    flags=ezdxf.const.BOUNDARY_PATH_EXTERNAL # Corrected constant
                    # flags also: HATCH_PATH_FLAG_OUTERMOST, HATCH_PATH_FLAG_DEFAULT (Note: these might also be BOUNDARY_PATH_xxx)
                )
            # The 'else' branch for edge paths has been removed as DxfHatchPath model currently only supports polyline vertices.

            return hatch
        except Exception as e:
            self.logger.error(f"Error adding DxfHatch: {e}", exc_info=True)
            return None

    def _calculate_text_rotation_rad(self, rotation_degrees: Optional[float]) -> float:
        """Converts text rotation from degrees to radians for ezdxf."""
        return math.radians(rotation_degrees or 0.0)

    def _map_mtext_attachment_point(self, attachment_point_str: Optional[str]) -> int:
        """Maps a string attachment point to ezdxf MTEXT attachment point constants."""
        if not attachment_point_str:
            return ezdxf.const.MTEXT_TOP_LEFT
        ap_map = {
            "TOP_LEFT": ezdxf.const.MTEXT_TOP_LEFT, "TOP_CENTER": ezdxf.const.MTEXT_TOP_CENTER, "TOP_RIGHT": ezdxf.const.MTEXT_TOP_RIGHT,
            "MIDDLE_LEFT": ezdxf.const.MTEXT_MIDDLE_LEFT, "MIDDLE_CENTER": ezdxf.const.MTEXT_MIDDLE_CENTER, "MIDDLE_RIGHT": ezdxf.const.MTEXT_MIDDLE_RIGHT,
            "BOTTOM_LEFT": ezdxf.const.MTEXT_BOTTOM_LEFT, "BOTTOM_CENTER": ezdxf.const.MTEXT_BOTTOM_CENTER, "BOTTOM_RIGHT": ezdxf.const.MTEXT_BOTTOM_RIGHT,
        }
        return ap_map.get(attachment_point_str.upper(), ezdxf.const.MTEXT_TOP_LEFT)

    async def _add_dxf_mtext(self, msp: Modelspace, doc: Drawing, model: DxfMText) -> Optional[MText]:
        """Adds a DXF MText entity to the modelspace."""
        try:
            attribs = {
                "char_height": model.char_height,
                "attachment_point": self._map_mtext_attachment_point(model.attachment_point),
                "style": model.style or self.writer_config.default_text_style or "Standard",
                "rotation": self._calculate_text_rotation_rad(model.rotation),
            }
            if model.width is not None: # MTEXT specific width for word wrapping
                attribs["width"] = model.width
            if model.line_spacing_factor is not None:
                attribs["line_spacing_factor"] = model.line_spacing_factor

            # Insertion point
            ins_pt = (model.insertion_point.x, model.insertion_point.y)
            if model.insertion_point.z is not None:
                ins_pt += (model.insertion_point.z,)

            mtext_entity = msp.add_mtext(text=model.text_content, dxfattribs=attribs)
            mtext_entity.dxf.insert = ins_pt # Set insertion point after creation for MTEXT

            return mtext_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfMText: {e}", exc_info=True)
            return None

    async def _add_dxf_text(self, msp: Modelspace, doc: Drawing, model: DxfText) -> Optional[Text]:
        """Adds a DXF Text entity (simple text) to the modelspace."""
        try:
            # For TEXT, alignment is more complex than MTEXT's attachment_point
            # It involves halign, valign, and setting align_point if not left-aligned.
            # DxfText model has halign, valign. Default to LEFT, BASELINE if not provided.
            halign = getattr(ezdxf.const, f"TEXT_ALIGN_{ (model.halign or 'LEFT').upper() }", ezdxf.const.TEXT_ALIGN_LEFT)
            valign = getattr(ezdxf.const, f"TEXT_ALIGN_{ (model.valign or 'BASELINE').upper() }", ezdxf.const.TEXT_ALIGN_BASELINE)

            attribs = {
                "height": model.height,
                "style": model.style or self.writer_config.default_text_style or "Standard",
                "rotation": self._calculate_text_rotation_rad(model.rotation_degrees),
                "halign": halign,
                "valign": valign,
            }
            # Insertion point
            ins_pt = (model.insertion_point.x, model.insertion_point.y)
            if model.insertion_point.z is not None:
                ins_pt += (model.insertion_point.z,)

            text_entity = msp.add_text(text=model.text_string, dxfattribs=attribs)
            text_entity.dxf.insert = ins_pt

            # If alignment is not default (LEFT), set align_point to the same as insertion_point
            if halign != ezdxf.const.TEXT_ALIGN_LEFT or valign != ezdxf.const.TEXT_ALIGN_BASELINE:
                text_entity.dxf.align_point = ins_pt

            return text_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfText: {e}", exc_info=True)
            return None

    async def _add_dxf_insert(self, msp: Modelspace, doc: Drawing, model: DxfInsert) -> Optional[Insert]:
        """Adds a DXF Insert (Block Reference) entity to the modelspace."""
        try:
            if not doc.blocks.has_entry(model.block_name):
                self.logger.error(f"Block definition '{model.block_name}' not found in document. Cannot add insert.")
                # Potentially, this service could request block creation from ResourceSetupService
                # if a block definition is missing and derivable. For now, error out.
                return None

            attribs = {
                "xscale": model.scale_x or 1.0,
                "yscale": model.scale_y or 1.0,
                "zscale": model.scale_z or 1.0,
                "rotation": model.rotation_degrees or 0.0, # INSERT rotation is in degrees
            }
            # Insertion point
            ins_pt = (model.insertion_point.x, model.insertion_point.y)
            if model.insertion_point.z is not None:
                ins_pt += (model.insertion_point.z,)

            insert_entity = msp.add_blockref(name=model.block_name, insert=ins_pt, dxfattribs=attribs)

            # Handle attributes if DxfInsert model has them and block has AttDefs
            if model.attributes:
                # This assumes AttDefs are already on the block definition in the doc
                # and their tags match keys in model.attributes
                for tag, value in model.attributes.items():
                    try:
                        insert_entity.add_attrib(tag=tag, text=str(value))
                        # May need to set attrib position if not auto-placed relative to AttDef
                    except ezdxf.DXFValueError: # Attribute does not exist on block
                        self.logger.warning(f"Attribute tag '{tag}' not found on block '{model.block_name}'. Skipping attribute for insert.")
                    except Exception as e_attr:
                        self.logger.error(f"Error adding attribute '{tag}' to insert of '{model.block_name}': {e_attr}", exc_info=True)
            return insert_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfInsert for block '{model.block_name}': {e}", exc_info=True)
            return None

    async def _add_dxf_circle(self, msp: Modelspace, model: DxfCircle) -> Optional[Circle]:
        """Adds a DXF Circle entity to the modelspace."""
        try:
            center_pt = (model.center.x, model.center.y)
            if model.center.z is not None:
                center_pt += (model.center.z,)
            else:
                center_pt += (0.0,) # Default Z to 0.0 if not provided for Circle
            return msp.add_circle(center=center_pt, radius=model.radius)
        except Exception as e:
            self.logger.error(f"Error adding DxfCircle: {e}", exc_info=True)
            return None

    async def _add_dxf_arc(self, msp: Modelspace, model: DxfArc) -> Optional[Arc]:
        """Adds a DXF Arc entity to the modelspace."""
        try:
            center_coords = (model.center.x, model.center.y)
            if model.center.z is not None:
                center_coords += (model.center.z,)

            return msp.add_arc(
                center=center_coords,
                radius=model.radius,
                start_angle=model.start_angle,
                end_angle=model.end_angle
            )
        except Exception as e:
            self.logger.error(f"Error adding DxfArc: {e}", exc_info=True)
            return None

    async def _add_dxf_polyline(self, msp: Modelspace, model: DxfPolyline) -> Optional[EzdxfPolyline]:
        """Adds a DXF POLYLINE (heavy polyline with VERTEX entities) to the modelspace."""
        if not model.points:
            self.logger.warning("Attempted to add DxfPolyline with no points.")
            return None
        try:
            dxf_flags = ezdxf.const.POLYLINE_3D_POLYLINE # Indicates a 3D polyline
            if model.is_closed:
                dxf_flags |= ezdxf.const.POLYLINE_CLOSED

            # Create the main POLYLINE entity
            # Common properties like layer, color will be applied by _apply_common_dxf_attributes
            polyline_entity = msp.add_polyline3d(dxfattribs={'flags': dxf_flags})

            # Prepare vertex coordinates (x, y, z)
            # Ensure Z defaults to 0.0 if not provided, as POLYLINE vertices are 3D.
            vertex_coordinates = []
            for p in model.points:
                z_coord = p.z if p.z is not None else 0.0
                vertex_coordinates.append((p.x, p.y, z_coord))

            # Append all vertices to the POLYLINE entity
            polyline_entity.append_vertices(vertex_coordinates)

            # Note: Individual VERTEX entity properties (like bulge, start/end width for 2D PLINE)
            # are not supported by this simplified DxfPolyline model.
            # If needed, DxfPolyline model would need to store DxfVertex models.

            return polyline_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfPolyline: {e}", exc_info=True)
            return None
