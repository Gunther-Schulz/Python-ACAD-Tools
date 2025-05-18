from typing import Any, Optional, cast, Tuple, Union, Dict
import math
from pathlib import Path
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from ezdxf.entities import DXFGraphic, Point, Line, LWPolyline, Hatch, MText, Text, Insert, Circle, Arc, Polyline as EzdxfPolyline
from ezdxf.enums import TextEntityAlignment
import yaml
from ezdxf.lldxf import const as dxfconstants

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
            ezdxf_entity = await self._add_dxf_mtext(msp, doc, cast(DxfMText, dxf_entity_model), layer_style_config)
        elif isinstance(dxf_entity_model, DxfText): # Simple Text
            ezdxf_entity = await self._add_dxf_text(msp, doc, cast(DxfText, dxf_entity_model), layer_style_config)
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
            entity.dxf.lineweight = dxfconstants.LINEWEIGHT_BYLAYER


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
        if dxf_model.xdata_app_id is not None and dxf_model.xdata_tags:
            try:
                entity.set_xdata(dxf_model.xdata_app_id, dxf_model.xdata_tags)
                self.logger.debug(f"Applied XDATA (AppID: {dxf_model.xdata_app_id}) with {len(dxf_model.xdata_tags)} tags to entity {entity.dxf.handle}")
            except AttributeError:
                self.logger.warning(f"Entity {entity.dxf.handle} (type: {entity.dxftype()}) might not support XDATA directly.", exc_info=False)
            except Exception as e_xdata:
                self.logger.error(f"Failed to set XDATA for entity {entity.dxf.handle}: {e_xdata}", exc_info=True)
        elif (dxf_model.xdata_app_id is not None and dxf_model.xdata_tags is None) or \
             (dxf_model.xdata_app_id is None and dxf_model.xdata_tags is not None):
            self.logger.warning(
                f"XDATA for entity {hasattr(entity, 'dxf') and entity.dxf.handle or 'unknown'} "
                f"was partially specified (app_id: {dxf_model.xdata_app_id is not None}, "
                f"tags: {dxf_model.xdata_tags is not None}). Both app_id and tags are required to set XDATA if either is specified."
            )

    # Placeholder for specific add methods to be added in Part 2
    async def _add_dxf_point(self, msp: Modelspace, model: DxfPoint) -> Optional[Point]:
        """Adds a DXF Point entity to the modelspace."""
        self.logger.info(f"Attempting to add DxfPoint: Layer='{model.layer}', "
                         f"X={model.position.x}, Y={model.position.y}, Z={model.position.z}, "
                         f"TrueColor={model.true_color}, Color256={model.color_256}, Linetype='{model.linetype}', "
                         f"XDATA AppID='{model.xdata_app_id}', Num XDATA Tags={len(model.xdata_tags) if model.xdata_tags else 0}")
        try:
            x, y = model.position.x, model.position.y

            if not (math.isfinite(x) and math.isfinite(y)):
                self.logger.error(f"Invalid non-finite coordinates for DxfPoint on layer '{model.layer}': X={x}, Y={y}. Skipping point.")
                return None

            point_coords_list = [x, y]
            if model.position.z is not None:
                if not math.isfinite(model.position.z):
                    self.logger.warning(
                        f"Invalid non-finite Z-coordinate for DxfPoint on layer '{model.layer}': Z={model.position.z}. Defaulting to 0.0."
                    )
                    point_coords_list.append(0.0)
                else:
                    point_coords_list.append(model.position.z)
            # If model.position.z is None, point_coords_list remains [x, y], ezdxf handles 2D points.

            final_point_coords = tuple(point_coords_list)
            return msp.add_point(location=final_point_coords)
        except Exception as e:
            self.logger.error(f"Error adding DxfPoint on layer '{model.layer}': {e}", exc_info=True)
            return None

    async def _add_dxf_line(self, msp: Modelspace, model: DxfLine) -> Optional[Line]:
        """Adds a DXF Line entity to the modelspace."""
        try:
            start_x, start_y, start_z_opt = model.start_point.x, model.start_point.y, model.start_point.z
            end_x, end_y, end_z_opt = model.end_point.x, model.end_point.y, model.end_point.z

            if not (math.isfinite(start_x) and math.isfinite(start_y) and
                    math.isfinite(end_x) and math.isfinite(end_y)):
                self.logger.error(
                    f"Invalid non-finite X/Y coordinates for DxfLine on layer '{model.layer}': "
                    f"Start=({start_x},{start_y}), End=({end_x},{end_y}). Skipping line."
                )
                return None

            start_z = 0.0
            if start_z_opt is not None:
                if not math.isfinite(start_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite Start Z-coordinate for DxfLine on layer '{model.layer}': Z={start_z_opt}. Defaulting to 0.0."
                    )
                    start_z = 0.0
                else:
                    start_z = start_z_opt

            end_z = 0.0
            if end_z_opt is not None:
                if not math.isfinite(end_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite End Z-coordinate for DxfLine on layer '{model.layer}': Z={end_z_opt}. Defaulting to 0.0."
                    )
                    end_z = 0.0
                else:
                    end_z = end_z_opt

            # ezdxf add_line can take 2D or 3D points.
            # If original Z was None, we effectively use 0.0 due to initialization.
            # If original Z was non-finite, we explicitly use 0.0.
            # If original Z was finite, we use it.
            # This ensures 3D points are always passed if Z was involved.

            # Constructing tuples for add_line:
            # If Z was originally None for both, ezdxf can handle 2D points, but to be explicit with our Z=0 default:
            final_start = (start_x, start_y, start_z)
            final_end = (end_x, end_y, end_z)

            return msp.add_line(start=final_start, end=final_end)
        except Exception as e:
            self.logger.error(f"Error adding DxfLine on layer '{model.layer}': {e}", exc_info=True)
            return None

    async def _add_dxf_lwpolyline(self, msp: Modelspace, model: DxfLWPolyline) -> Optional[LWPolyline]:
        """Adds a DXF LWPolyline entity to the modelspace."""
        try:
            if not model.points:
                self.logger.warning(f"Attempted to add LWPolyline on layer '{model.layer}' with no points. Skipping.")
                return None

            valid_points_data = []
            has_z_values_in_model = False # For logging purposes if Z was provided

            for i, p_model in enumerate(model.points):
                x, y, z_opt = p_model.x, p_model.y, p_model.z
                if not (math.isfinite(x) and math.isfinite(y)):
                    self.logger.error(
                        f"Invalid non-finite X/Y coordinates for vertex {i} in DxfLWPolyline on layer '{model.layer}': "
                        f"Point=({x},{y}). Skipping entire LWPolyline."
                    )
                    return None
                valid_points_data.append((x, y)) # LWPOLYLINE points are 2D (x,y) or (x,y,bulge,s,e)
                if z_opt is not None and z_opt != 0:
                    has_z_values_in_model = True

            if has_z_values_in_model:
                self.logger.debug(f"LWPolyline on layer '{model.layer}': Z coordinates present in input DxfLWPolyline model points were discarded (as expected for LWPolyline vertices).")

            # This check is now effectively done by the loop returning None if model.points was empty initially
            # or if valid_points_data remains empty after filtering (though filtering currently skips whole polyline).
            # If we were to filter individual bad points instead of skipping the whole polyline:
            # if not valid_points_data:
            #     self.logger.warning(f"LWPolyline on layer '{model.layer}' has no valid points after filtering. Skipping.")
            #     return None

            lwpolyline = msp.add_lwpolyline(
                points=valid_points_data,
                dxfattribs={'closed': model.is_closed}
            )
            # Bulge values, if present in DxfLWPolyline model, would need to be set per-vertex
            # e.g., if model.points had [(x,y,bulge), ...]:
            # for i, vertex_model in enumerate(model.points_with_bulge_if_any):
            #    lwpolyline[i] = (vertex_model.x, vertex_model.y, vertex_model.bulge_value)
            return lwpolyline
        except Exception as e:
            self.logger.error(f"Error adding DxfLWPolyline on layer '{model.layer}': {e}", exc_info=True)
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

            hatch.dxf.hatch_style = dxfconstants.HATCH_STYLE_NORMAL # Default, consider making configurable
            model_hatch_props = model.hatch_props
            pattern_name, scale, angle_deg = self._get_hatch_pattern_details(model_hatch_props)

            if pattern_name.upper() == "SOLID":
                hatch.set_solid_fill()
                self.logger.debug(f"Hatch on layer '{model.layer}' set to SOLID fill. Island style: {hatch.dxf.hatch_style}")
                if model_hatch_props and model_hatch_props.pattern_color:
                    color_model_val = model_hatch_props.pattern_color
                    if color_model_val.rgb is not None:
                        hatch.rgb = color_model_val.rgb
                        self.logger.debug(f"Solid Hatch on layer '{model.layer}': Set fill color using RGB: {color_model_val.rgb}")
                    elif color_model_val.aci is not None:
                        resolved_color_aci = get_color_code(color_model_val.aci, self.name_to_aci_map)
                        hatch.dxf.color = resolved_color_aci
                        self.logger.debug(f"Solid Hatch on layer '{model.layer}': Set fill color using ACI: {color_model_val.aci} -> resolved to {resolved_color_aci}")
            else: # Pattern fill
                hatch.set_pattern_fill(name=pattern_name, scale=scale, angle=angle_deg)
                self.logger.debug(f"Hatch on layer '{model.layer}' set to PATTERN fill: {pattern_name}, scale: {scale}, angle: {angle_deg}. Island style: {hatch.dxf.hatch_style}")

            # Add boundary paths
            has_at_least_one_valid_path = False
            if not model.paths:
                self.logger.warning(f"Hatch on layer '{model.layer}' has no paths defined in the model. Skipping hatch entity.")
                # Need to remove the created hatch if it has no paths, or not add it.
                # However, msp.add_hatch() already adds it. We might need to delete it.
                # For now, let's proceed and if no paths are added, it might be an empty hatch.
                # A better approach might be to collect valid paths first, then only call add_hatch if any exist.
                # This change is too large for current scope. Current logic: if no paths, it will be a hatch with 0 paths.
                # DXF viewer might handle this or not. Safest is to not create it.
                # For now, the code will create a hatch, and if no paths are added, it's an empty hatch.
                # Let's adjust: if no paths in model, return None.
                msp.delete_entity(hatch) # Delete the initially created hatch if no paths in model
                self.logger.warning(f"Deleted initially created hatch on layer '{model.layer}' as no paths were defined in the model.")
                return None

            for i, path_model in enumerate(model.paths):
                if not path_model.vertices:
                    self.logger.warning(f"Path {i} for hatch on layer '{model.layer}' has no vertices. Skipping this path.")
                    continue

                current_path_valid_vertices = []
                path_has_invalid_vertex = False
                for j, vertex_model in enumerate(path_model.vertices):
                    x, y = vertex_model.x, vertex_model.y
                    if not (math.isfinite(x) and math.isfinite(y)):
                        self.logger.error(
                            f"Invalid non-finite X/Y for vertex {j} in path {i} for DxfHatch on layer '{model.layer}': "
                            f"Point=({x},{y}). Skipping this entire path."
                        )
                        path_has_invalid_vertex = True
                        break # Stop processing vertices for this path
                    current_path_valid_vertices.append((x, y))

                if not path_has_invalid_vertex and current_path_valid_vertices:
                    # Assuming path_model.is_closed is always boolean as per DxfHatchPath
                    hatch.paths.add_polyline_path(
                        path_vertices=current_path_valid_vertices,
                        is_closed=path_model.is_closed, # is_closed is part of DxfHatchPath model
                        flags=dxfconstants.BOUNDARY_PATH_EXTERNAL
                    )
                    has_at_least_one_valid_path = True
                elif not current_path_valid_vertices and not path_has_invalid_vertex:
                    # This case means path_model.vertices was not empty initially, but became empty (e.g. if we were filtering points)
                    # Currently, this shouldn't happen due to break on invalid vertex.
                    self.logger.warning(f"Path {i} for hatch on layer '{model.layer}' resulted in no valid vertices (though no single vertex was reported invalid). Skipping this path.")

            if not has_at_least_one_valid_path:
                self.logger.warning(f"Hatch on layer '{model.layer}' has no valid boundary paths after validation. Skipping hatch entity.")
                msp.delete_entity(hatch) # Delete the initially created hatch
                return None

            return hatch
        except Exception as e:
            self.logger.error(f"Error adding DxfHatch on layer '{model.layer}': {e}", exc_info=True)
            # If hatch was created but an error occurred later (e.g. during path adding), it might exist in msp.
            # It's safer to ensure it's not left in a partial state if possible, but generic exception handling makes this hard.
            # For now, if an exception occurs, the hatch might still be in modelspace if created before error.
            return None

    def _calculate_text_rotation_rad(self, rotation_degrees: Optional[float]) -> float:
        """Converts text rotation from degrees to radians for ezdxf."""
        return math.radians(rotation_degrees or 0.0)

    def _map_mtext_attachment_point(self, attachment_point_str: Optional[str]) -> int:
        """Maps a string attachment point to ezdxf MTEXT attachment point constants."""
        if not attachment_point_str:
            return dxfconstants.MTEXT_TOP_LEFT
        ap_map = {
            "TOP_LEFT": dxfconstants.MTEXT_TOP_LEFT, "TOP_CENTER": dxfconstants.MTEXT_TOP_CENTER, "TOP_RIGHT": dxfconstants.MTEXT_TOP_RIGHT,
            "MIDDLE_LEFT": dxfconstants.MTEXT_MIDDLE_LEFT, "MIDDLE_CENTER": dxfconstants.MTEXT_MIDDLE_CENTER, "MIDDLE_RIGHT": dxfconstants.MTEXT_MIDDLE_RIGHT,
            "BOTTOM_LEFT": dxfconstants.MTEXT_BOTTOM_LEFT, "BOTTOM_CENTER": dxfconstants.MTEXT_BOTTOM_CENTER, "BOTTOM_RIGHT": dxfconstants.MTEXT_BOTTOM_RIGHT,
        }
        return ap_map.get(attachment_point_str.upper(), dxfconstants.MTEXT_TOP_LEFT)

    async def _add_dxf_mtext(self, msp: Modelspace, doc: Drawing, model: DxfMText, layer_style_config: LayerStyleConfig) -> Optional[MText]:
        """Adds a DXF MText entity to the modelspace."""
        try:
            # Validate insertion point
            ins_x, ins_y, ins_z_opt = model.insertion_point.x, model.insertion_point.y, model.insertion_point.z
            if not (math.isfinite(ins_x) and math.isfinite(ins_y)):
                self.logger.error(
                    f"Invalid non-finite X/Y for DxfMText insertion_point on layer '{model.layer}': "
                    f"IP=({ins_x},{ins_y}). Skipping MText."
                )
                return None

            ins_z = 0.0
            if ins_z_opt is not None:
                if not math.isfinite(ins_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite Z for DxfMText insertion_point on layer '{model.layer}': Z={ins_z_opt}. Defaulting to 0.0."
                    )
                    # ins_z is already 0.0
                else:
                    ins_z = ins_z_opt
            final_ins_pt = (ins_x, ins_y, ins_z)

            # Validate char_height (must be positive)
            char_height = model.char_height
            if not (math.isfinite(char_height) and char_height > 0):
                self.logger.error(
                    f"Invalid non-finite or non-positive char_height for DxfMText on layer '{model.layer}': {char_height}. Skipping MText."
                )
                return None

            # Validate rotation
            rotation_deg = model.rotation
            if rotation_deg is not None and not math.isfinite(rotation_deg):
                self.logger.warning(
                    f"Invalid non-finite rotation for DxfMText on layer '{model.layer}': {rotation_deg}. Defaulting to 0.0 degrees."
                )
                rotation_deg = 0.0 # Default if non-finite
            # _calculate_text_rotation_rad handles None by using 0.0
            rotation_rad = self._calculate_text_rotation_rad(rotation_deg)

            attribs = {
                "char_height": char_height,
                "attachment_point": self._map_mtext_attachment_point(model.attachment_point),
                "style": model.style or self.writer_config.default_text_style or "Standard",
                "rotation": rotation_rad,
            }

            # Validate optional width (must be positive if specified)
            if model.width is not None:
                if math.isfinite(model.width) and model.width > 0:
                    attribs["width"] = model.width
                else:
                    self.logger.warning(
                        f"Invalid non-finite or non-positive width for DxfMText on layer '{model.layer}': {model.width}. Omitting width attribute."
                    )

            # Validate optional line_spacing_factor
            if model.line_spacing_factor is not None:
                if math.isfinite(model.line_spacing_factor):
                    # Assuming ezdxf handles range checks for line_spacing_factor (e.g., 0.25 to 4.0)
                    attribs["line_spacing_factor"] = model.line_spacing_factor
                else:
                    self.logger.warning(
                        f"Invalid non-finite line_spacing_factor for DxfMText on layer '{model.layer}': {model.line_spacing_factor}. Omitting factor."
                    )

            mtext_entity = msp.add_mtext(text=model.text_content, dxfattribs=attribs)
            mtext_entity.dxf.insert = final_ins_pt # Set insertion point after creation for MTEXT

            return mtext_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfMText on layer '{model.layer}': {e}", exc_info=True)
            return None

    async def _add_dxf_text(self, msp: Modelspace, doc: Drawing, dxf_model: DxfText, layer_style_config: LayerStyleConfig) -> Optional[Text]:
        # log_prefix = "DxfEntityConverterService._add_dxf_text" # REMOVING TEMP LOG
        try:
            # # --- TEMP LOGGING: INCOMING DXFTEXT MODEL --- # REMOVING TEMP LOG
            # self.logger.info(f"{log_prefix}: INCOMING_MODEL - Text='{dxf_model.text_content}', "
            #                  f"InsertPt={dxf_model.insertion_point}, HAlign='{dxf_model.halign}', "
            #                  f"VAlign='{dxf_model.valign}', Style='{dxf_model.style}'")
            # # --- END TEMP LOGGING ---

            # Validate insertion point
            ins_x, ins_y, ins_z_opt = dxf_model.insertion_point.x, dxf_model.insertion_point.y, dxf_model.insertion_point.z
            if not (math.isfinite(ins_x) and math.isfinite(ins_y)):
                self.logger.error(
                    f"Invalid non-finite X/Y for DxfText insertion_point on layer '{dxf_model.layer}': "
                    f"IP=({ins_x},{ins_y}). Skipping Text entity."
                )
                return None

            ins_z = 0.0
            if ins_z_opt is not None:
                if not math.isfinite(ins_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite Z for DxfText insertion_point on layer '{dxf_model.layer}': Z={ins_z_opt}. Defaulting to 0.0."
                    )
                    # ins_z is already 0.0
                else:
                    ins_z = ins_z_opt
            final_ins_pt = (ins_x, ins_y, ins_z)

            # Prepare dxfattribs for msp.add_text
            dxfattribs: Dict[str, Any] = {
                "height": dxf_model.height,
                "style": dxf_model.style or self.writer_config.default_text_style or "Standard",
                "rotation": self._calculate_text_rotation_rad(dxf_model.rotation),
            }

            # Map halign from model to ezdxf code
            halign_code = self._map_halign_to_dxf_code(dxf_model.halign)
            dxfattribs["halign"] = halign_code # halign_code is now the integer

            # Map valign from model to ezdxf code
            valign_code = self._map_valign_to_dxf_code(dxf_model.valign)
            dxfattribs["valign"] = valign_code # valign_code is now the integer

            # Create the TEXT entity
            text_entity = msp.add_text(
                text=dxf_model.text_content,
                dxfattribs=dxfattribs
            )

            # # --- TEMP LOGGING: CREATED EZDXF TEXT ENTITY --- # REMOVING TEMP LOG
            # if text_entity:
            #     self.logger.info(f"{log_prefix}: CREATED_ENTITY - Text='{text_entity.dxf.text}', "
            #                      f"InsertPt={text_entity.dxf.insert}, HAlign='{text_entity.dxf.halign}', "
            #                      f"VAlign='{text_entity.dxf.valign}', Style='{text_entity.dxf.style}'")
            # # --- END TEMP LOGGING ---

            if text_entity:
                text_entity.dxf.insert = final_ins_pt
                # For TEXT entities, if alignment is other than LEFT/BASELINE,
                # the `align_point` should also be set to the `insertion_point`.
                # `halign_code` and `valign_code` here are the ezdxf integer constants.
                # DXF default for halign is 0 (LEFT), valign is 0 (BASELINE)
                if dxfattribs.get("halign", 0) != 0 or \
                   dxfattribs.get("valign", 0) != 0:
                    text_entity.dxf.align_point = final_ins_pt
            else:
                 self.logger.warning(f"msp.add_text returned None for text: {dxf_model.text_content}")
                 return None

            # Apply common DxfEntity properties like color, linetype, etc.
            await self._apply_common_dxf_attributes(text_entity, dxf_model, layer_style_config)
            # Apply XDATA after common attributes
            # await self._apply_xdata(text_entity, dxf_model)
            self.logger.debug(f"Successfully added and styled {dxf_model.__class__.__name__} (handle: {text_entity.dxf.handle}) to layer {dxf_model.layer}")

            return text_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfText on layer '{dxf_model.layer}': {e}", exc_info=True)
            return None

    def _map_halign_to_dxf_code(self, halign_str: Optional[str]) -> int:
        if not halign_str:
            return 0 # Default: TEXT_ALIGN_LEFT
        ha_map = {
            "LEFT": 0,
            "CENTER": 1, # CENTER (alone) implies vertical baseline
            "RIGHT": 2,
            # For ALIGNED, MIDDLE, FIT, valign is often 0 (BASELINE)
            # Or they are combined with valign to make MIDDLE_CENTER etc.
            # TextEntityAlignment enum combines these. Direct DXF codes are simpler here.
            "ALIGNED": 3, # Text is drawn between two points, height is scaled.
            "MIDDLE": 4,  # Text is centered horizontally between two points, height is fixed.
                          # This is NOT "MIDDLE_OF_TEXT" vertically unless valign is also middle.
                          # Often used for "MIDDLE_CENTER" when combined with valign=2
            "FIT": 5,     # Text is stretched/compressed between two points, height is fixed.
        }
        # More complex alignments (like MIDDLE_CENTER, TOP_LEFT) are usually handled by
        # setting both halign and valign. e.g. MIDDLE_CENTER = halign=4, valign=2
        # Our DxfText model has separate halign and valign.
        # For now, map based on simple horizontal string.
        # If DxfText intends "MIDDLE_CENTER" by halign="MIDDLE", it should also have valign="MIDDLE".
        return ha_map.get(halign_str.upper(), 0) # Default to 0 (LEFT)

    def _map_valign_to_dxf_code(self, valign_str: Optional[str]) -> int:
        if not valign_str:
            return 0 # Default: TEXT_VALIGN_BASELINE
        va_map = {
            "BASELINE": 0,
            "BOTTOM": 1,
            "MIDDLE": 2, # Vertically middle
            "TOP": 3,
        }
        return va_map.get(valign_str.upper(), 0) # Default to 0 (BASELINE)

    async def _add_dxf_insert(self, msp: Modelspace, doc: Drawing, model: DxfInsert) -> Optional[Insert]:
        """Adds a DXF Insert (Block Reference) entity to the modelspace."""
        try:
            if not doc.blocks.has_entry(model.block_name):
                self.logger.error(f"Block definition '{model.block_name}' not found in document for DxfInsert on layer '{model.layer}'. Cannot add insert.")
                return None

            # Validate insertion point
            ins_x, ins_y, ins_z_opt = model.insertion_point.x, model.insertion_point.y, model.insertion_point.z
            if not (math.isfinite(ins_x) and math.isfinite(ins_y)):
                self.logger.error(
                    f"Invalid non-finite X/Y for DxfInsert insertion_point on layer '{model.layer}' for block '{model.block_name}': "
                    f"IP=({ins_x},{ins_y}). Skipping Insert."
                )
                return None

            ins_z = 0.0
            if ins_z_opt is not None:
                if not math.isfinite(ins_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite Z for DxfInsert insertion_point on layer '{model.layer}' for block '{model.block_name}': Z={ins_z_opt}. Defaulting to 0.0."
                    )
                    # ins_z is already 0.0
                else:
                    ins_z = ins_z_opt
            final_ins_pt = (ins_x, ins_y, ins_z)

            # Validate scales (default to 1.0 if non-finite or zero)
            # DXF scales should not be zero. ezdxf might allow it but AutoCAD might error.
            # Safest is to default non-finite or zero scales to 1.0.
            scale_x = model.scale_x if model.scale_x is not None else 1.0
            if not math.isfinite(scale_x) or scale_x == 0:
                self.logger.warning(f"Invalid scale_x for DxfInsert on layer '{model.layer}' (block '{model.block_name}'): {scale_x}. Defaulting to 1.0.")
                scale_x = 1.0

            scale_y = model.scale_y if model.scale_y is not None else 1.0
            if not math.isfinite(scale_y) or scale_y == 0:
                self.logger.warning(f"Invalid scale_y for DxfInsert on layer '{model.layer}' (block '{model.block_name}'): {scale_y}. Defaulting to 1.0.")
                scale_y = 1.0

            scale_z = model.scale_z if model.scale_z is not None else 1.0
            if not math.isfinite(scale_z) or scale_z == 0:
                self.logger.warning(f"Invalid scale_z for DxfInsert on layer '{model.layer}' (block '{model.block_name}'): {scale_z}. Defaulting to 1.0.")
                scale_z = 1.0

            # Validate rotation
            rotation_deg = model.rotation_degrees if model.rotation_degrees is not None else 0.0
            if not math.isfinite(rotation_deg):
                self.logger.warning(
                    f"Invalid non-finite rotation for DxfInsert on layer '{model.layer}' (block '{model.block_name}'): {rotation_deg}. Defaulting to 0.0 degrees."
                )
                rotation_deg = 0.0

            attribs = {
                "xscale": scale_x,
                "yscale": scale_y,
                "zscale": scale_z,
                "rotation": rotation_deg, # INSERT rotation is in degrees
            }

            insert_entity = msp.add_blockref(name=model.block_name, insert=final_ins_pt, dxfattribs=attribs)

            if model.attributes:
                for tag, value in model.attributes.items():
                    try:
                        insert_entity.add_attrib(tag=tag, text=str(value))
                    except ezdxf.DXFValueError:
                        self.logger.warning(f"Attribute tag '{tag}' not found on block '{model.block_name}' for insert on layer '{model.layer}'. Skipping attribute.")
                    except Exception as e_attr:
                        self.logger.error(f"Error adding attribute '{tag}' to insert of '{model.block_name}' on layer '{model.layer}': {e_attr}", exc_info=True)
            return insert_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfInsert for block '{model.block_name}' on layer '{model.layer}': {e}", exc_info=True)
            return None

    async def _add_dxf_circle(self, msp: Modelspace, model: DxfCircle) -> Optional[Circle]:
        """Adds a DXF Circle entity to the modelspace."""
        try:
            # Validate center point
            center_x, center_y, center_z_opt = model.center.x, model.center.y, model.center.z
            if not (math.isfinite(center_x) and math.isfinite(center_y)):
                self.logger.error(
                    f"Invalid non-finite X/Y for DxfCircle center on layer '{model.layer}': "
                    f"Center=({center_x},{center_y}). Skipping Circle."
                )
                return None

            center_z = 0.0 # Default Z for circle center if not specified or invalid
            if center_z_opt is not None:
                if not math.isfinite(center_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite Z for DxfCircle center on layer '{model.layer}': Z={center_z_opt}. Defaulting to 0.0."
                    )
                    # center_z is already 0.0
                else:
                    center_z = center_z_opt
            final_center_pt = (center_x, center_y, center_z)

            # Validate radius (must be positive)
            radius = model.radius
            if not (math.isfinite(radius) and radius > 0):
                self.logger.error(
                    f"Invalid non-finite or non-positive radius for DxfCircle on layer '{model.layer}': {radius}. Skipping Circle."
                )
                return None

            return msp.add_circle(center=final_center_pt, radius=radius)
        except Exception as e:
            self.logger.error(f"Error adding DxfCircle on layer '{model.layer}': {e}", exc_info=True)
            return None

    async def _add_dxf_arc(self, msp: Modelspace, model: DxfArc) -> Optional[Arc]:
        """Adds a DXF Arc entity to the modelspace."""
        try:
            # Validate center point
            center_x, center_y, center_z_opt = model.center.x, model.center.y, model.center.z
            if not (math.isfinite(center_x) and math.isfinite(center_y)):
                self.logger.error(
                    f"Invalid non-finite X/Y for DxfArc center on layer '{model.layer}': "
                    f"Center=({center_x},{center_y}). Skipping Arc."
                )
                return None

            center_z = 0.0 # Default Z for arc center
            if center_z_opt is not None:
                if not math.isfinite(center_z_opt):
                    self.logger.warning(
                        f"Invalid non-finite Z for DxfArc center on layer '{model.layer}': Z={center_z_opt}. Defaulting to 0.0."
                    )
                    # center_z is already 0.0
                else:
                    center_z = center_z_opt
            final_center_pt = (center_x, center_y, center_z)

            # Validate radius (must be positive)
            radius = model.radius
            if not (math.isfinite(radius) and radius > 0):
                self.logger.error(
                    f"Invalid non-finite or non-positive radius for DxfArc on layer '{model.layer}': {radius}. Skipping Arc."
                )
                return None

            # Validate angles
            start_angle, end_angle = model.start_angle, model.end_angle
            if not (math.isfinite(start_angle) and math.isfinite(end_angle)):
                self.logger.error(
                    f"Invalid non-finite start_angle or end_angle for DxfArc on layer '{model.layer}': "
                    f"Start={start_angle}, End={end_angle}. Skipping Arc."
                )
                return None

            return msp.add_arc(
                center=final_center_pt,
                radius=radius,
                start_angle=start_angle, # Angles are in degrees for ezdxf
                end_angle=end_angle
            )
        except Exception as e:
            self.logger.error(f"Error adding DxfArc on layer '{model.layer}': {e}", exc_info=True)
            return None

    async def _add_dxf_polyline(self, msp: Modelspace, model: DxfPolyline) -> Optional[EzdxfPolyline]:
        """Adds a DXF POLYLINE (heavy polyline with VERTEX entities) to the modelspace."""
        if not model.points:
            self.logger.warning(f"Attempted to add DxfPolyline on layer '{model.layer}' with no points. Skipping.")
            return None
        try:
            validated_vertices = []
            for i, p_model in enumerate(model.points):
                x, y, z_opt = p_model.x, p_model.y, p_model.z

                if not (math.isfinite(x) and math.isfinite(y)):
                    self.logger.error(
                        f"Invalid non-finite X/Y for vertex {i} in DxfPolyline on layer '{model.layer}': "
                        f"Point=({x},{y}). Skipping entire Polyline."
                    )
                    return None # Skip entire polyline if any X/Y is non-finite

                z_coord = 0.0 # Default Z for polyline vertex
                if z_opt is not None:
                    if not math.isfinite(z_opt):
                        self.logger.warning(
                            f"Invalid non-finite Z for vertex {i} in DxfPolyline on layer '{model.layer}': Z={z_opt}. Defaulting to 0.0."
                        )
                        # z_coord is already 0.0
                    else:
                        z_coord = z_opt
                validated_vertices.append((x, y, z_coord))

            # This check is implicitly handled by the loop logic if model.points was empty initially, or if it would return None above.
            # if not validated_vertices:
            #     self.logger.warning(f"Polyline on layer '{model.layer}' has no valid vertices after filtering. Skipping.")
            #     return None

            dxf_flags = dxfconstants.POLYLINE_3D_POLYLINE
            if model.is_closed:
                dxf_flags |= dxfconstants.POLYLINE_CLOSED

            polyline_entity = msp.add_polyline3d(dxfattribs={'flags': dxf_flags})
            polyline_entity.append_vertices(validated_vertices)

            return polyline_entity
        except Exception as e:
            self.logger.error(f"Error adding DxfPolyline on layer '{model.layer}': {e}", exc_info=True)
            return None
