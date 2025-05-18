from typing import Any, Dict, Tuple, AsyncIterator, Set
import math
import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout
from ezdxf.math import Vec3 # For MTEXT rotation if needed, or general vector ops

from dxfplanner.config.schemas import ProjectConfig, DxfWriterConfig, LayerConfig as DomainLayerConfig, LinetypeConfig, TextStyleConfig # Renamed LayerConfig to avoid clash
from dxfplanner.config.dxf_writer_schemas import ( # Import specific block configs
    BlockDefinitionConfig, AnyBlockEntityConfig, BlockPointConfig, BlockLineConfig,
    BlockPolylineConfig, BlockCircleConfig, BlockArcConfig, BlockTextConfig,
    HeaderVariablesConfig, InsUnitsEnum # Added HeaderVariablesConfig and InsUnitsEnum
)
from dxfplanner.domain.models.dxf_models import AnyDxfEntity
from dxfplanner.domain.interfaces import IDxfResourceSetupService
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.layer_utils import sanitize_layer_name

logger = get_logger(__name__)

class DxfResourceSetupService(IDxfResourceSetupService):
    """Service for setting up DXF document resources."""

    def __init__(self, project_config: ProjectConfig): # Changed from app_config: AppConfig
        self.project_config = project_config
        self.writer_config: DxfWriterConfig = project_config.dxf_writer # Updated path
        self.logger = logger
        # <NEW LOGGING START>
        lc_type = type(self.writer_config.layer_configs)
        lc_len = len(self.writer_config.layer_configs) if self.writer_config.layer_configs is not None else "None"
        lc_content_str = str(self.writer_config.layer_configs)
        if len(lc_content_str) > 150: # Keep log manageable
            lc_content_str = lc_content_str[:150] + "..."
        self.logger.info(
            f"DxfResourceSetupService initialized. writer_config.layer_configs: "
            f"Type={lc_type}, Length={lc_len}, Content='{lc_content_str}'"
        )
        # <NEW LOGGING END>

    async def setup_document_resources(
        self,
        doc: Drawing,
        entities_by_layer_config: Dict[str, Tuple[DomainLayerConfig, AsyncIterator[AnyDxfEntity]]] # Type hint for LayerConfig updated
    ) -> None:
        self.logger.info("Setting up document resources...")

        # 1. Setup DXF version from config
        if self.writer_config.dxf_version:
            try:
                doc.header['$ACADVER'] = self.writer_config.dxf_version
                self.logger.info(f"Set DXF version to: {self.writer_config.dxf_version}")
            except Exception as e:
                self.logger.error(f"Failed to set $ACADVER to {self.writer_config.dxf_version}: {e}", exc_info=True)
        else:
            # ezdxf sets a default (usually R2000/AC1015 or R2013/AC1027 depending on ezdxf.new() args)
            # For consistency, we can ensure a specific default if not provided.
            # current_acadver = doc.header.get('$ACADVER', 'AC1027') # AC1027 is R2013
            # doc.header['$ACADVER'] = current_acadver
            self.logger.info(f"DXF version not specified in config, using ezdxf default: {doc.acad_version}")

        # 2. Setup other header variables from HeaderVariablesConfig
        header_conf = self.writer_config.header_variables
        if header_conf is None:
            self.logger.info("No explicit HeaderVariablesConfig in DxfWriterConfig, creating one with defaults.")
            header_conf = HeaderVariablesConfig() # Instantiate with Pydantic defaults
        else:
            self.logger.info("Using HeaderVariablesConfig from DxfWriterConfig.")

        applied_vars_log = []
        try:
            if header_conf.insunits is not None:
                doc.header['$INSUNITS'] = header_conf.insunits.value # Enum uses .value
                applied_vars_log.append(f"$INSUNITS={header_conf.insunits.name}({header_conf.insunits.value})")
            if header_conf.lunits is not None:
                doc.header['$LUNITS'] = header_conf.lunits
                applied_vars_log.append(f"$LUNITS={header_conf.lunits}")
            if header_conf.luprec is not None:
                doc.header['$LUPREC'] = header_conf.luprec
                applied_vars_log.append(f"$LUPREC={header_conf.luprec}")
            if header_conf.measurement is not None:
                doc.header['$MEASUREMENT'] = header_conf.measurement
                applied_vars_log.append(f"$MEASUREMENT={header_conf.measurement}")
            if header_conf.lwdisplay is not None:
                doc.header['$LWDISPLAY'] = 1 if header_conf.lwdisplay else 0 # Convert bool to int
                applied_vars_log.append(f"$LWDISPLAY={(1 if header_conf.lwdisplay else 0)}")

            if header_conf.additional_vars:
                self.logger.debug(f"Processing {len(header_conf.additional_vars)} additional header variables.")
                for key, value in header_conf.additional_vars.items():
                    # Basic validation for key format
                    if isinstance(key, str) and key.startswith("$") and key.isupper():
                        doc.header[key] = value
                        applied_vars_log.append(f"{key}={value}")
                        self.logger.debug(f"Set additional header variable: {key} = {value}")
                    else:
                        self.logger.warning(
                            f"Skipping additional header variable '{key}': Name must be a string, start with '$', and be uppercase (e.g., '$USERI1')."
                        )
            if applied_vars_log:
                self.logger.info(f"Applied header variables: {', '.join(applied_vars_log)}")
            else:
                self.logger.info("No specific header variables were applied from HeaderVariablesConfig.")

        except Exception as e:
            self.logger.error(f"Error applying header variables: {e}", exc_info=True)

        # 3. Setup Layers, Linetypes, Text Styles, Block Definitions (existing logic)
        self.logger.info("Proceeding with Layers, Linetypes, Text Styles, Block Definitions setup.")
        await self._create_layers_from_config(doc)
        await self._create_linetypes_from_config(doc)
        await self._create_text_styles_from_config(doc)
        # Removed entities_by_layer_config from this call as it's not used for configured blocks
        await self._create_block_definitions_from_config(doc)
        self.logger.info("Document resources setup complete.")

    async def _create_layers_from_config(self, doc: Drawing) -> None:
        """Creates layers in the DXF document based on the configuration."""
        # writer_config.layers is DxfLayerConfig from dxf_writer_schemas, not LayerConfig from main schemas
        if not self.writer_config.layer_configs: # Corrected attribute name / This means None or empty list
            # <NEW LOGGING START>
            if self.writer_config.layer_configs is None:
                self.logger.info("DxfWriterConfig.layer_configs is None. Skipping layer creation from config.")
            elif len(self.writer_config.layer_configs) == 0: # Explicitly check for empty list
                self.logger.warning("DxfWriterConfig.layer_configs is an EMPTY LIST. No layers will be created from config.")
            # <NEW LOGGING END>
            else: # Should not happen if `not self.writer_config.layer_configs` is true and it's not None or empty
                 self.logger.info("No layer configurations provided in DxfWriterConfig (unusual state for 'not layer_configs'). Skipping layer creation.")
            return

        self.logger.debug(f"Creating {len(self.writer_config.layer_configs)} layers from DxfWriterConfig.")
        for layer_conf in self.writer_config.layer_configs: # Corrected attribute name
            s_layer_name = sanitize_layer_name(layer_conf.name)
            if not doc.layers.has_entry(s_layer_name):
                self.logger.debug(f"Creating layer: {s_layer_name}")
                dxf_layer = doc.layers.new(s_layer_name)
                if layer_conf.color: # Access color from DxfLayerConfig
                    if layer_conf.color.rgb is not None: # Added True Color support for layers
                        try:
                            dxf_layer.true_color = ezdxf.rgb2int(layer_conf.color.rgb)
                        except Exception as e_tc:
                            self.logger.warning(f"Layer '{s_layer_name}': Invalid RGB true color {layer_conf.color.rgb}. Error: {e_tc}")
                            if layer_conf.color.aci is not None: # Fallback to ACI if true color fails
                                dxf_layer.color = layer_conf.color.aci
                    elif layer_conf.color.aci is not None:
                        dxf_layer.color = layer_conf.color.aci
                if layer_conf.lineweight is not None:
                    dxf_layer.lineweight = layer_conf.lineweight
                if layer_conf.linetype:
                    dxf_layer.linetype = layer_conf.linetype
                dxf_layer.is_plotted = layer_conf.plot_flag # Corrected attribute name
                dxf_layer.is_frozen = layer_conf.is_frozen
                dxf_layer.is_off = layer_conf.is_off
                dxf_layer.is_locked = layer_conf.is_locked

            else:
                self.logger.debug(f"Layer {s_layer_name} already exists. Skipping creation.")
        self.logger.info("Finished creating layers from DxfWriterConfig.")

    async def _create_linetypes_from_config(self, doc: Drawing) -> None:
        """Creates linetypes in the DXF document based on the configuration."""
        if not self.writer_config.linetypes:
            self.logger.info("No linetype configurations provided. Skipping linetype creation.")
            return

        self.logger.debug(f"Creating {len(self.writer_config.linetypes)} linetypes.")
        for lt_conf in self.writer_config.linetypes:
            if not doc.linetypes.has_entry(lt_conf.name):
                self.logger.debug(f"Creating linetype: {lt_conf.name} with pattern {lt_conf.pattern}")
                try:
                    # Description is optional, pattern is a list of numbers
                    doc.linetypes.new(
                        name=lt_conf.name,
                        description=lt_conf.description or "",
                        pattern=lt_conf.pattern, # e.g., [0.5, -0.25, 0, -0.25]
                        length=sum(abs(p) for p in lt_conf.pattern) # Total length of one pattern sequence
                    )
                except Exception as e:
                    self.logger.error(f"Failed to create linetype {lt_conf.name}: {e}", exc_info=True)
            else:
                self.logger.debug(f"Linetype {lt_conf.name} already exists. Skipping creation.")
        self.logger.info("Finished creating linetypes.")

    async def _create_text_styles_from_config(self, doc: Drawing) -> None:
        """Creates text styles in the DXF document based on the configuration."""
        if not self.writer_config.text_styles:
            self.logger.info("No text style configurations provided. Skipping text style creation.")
            return

        self.logger.debug(f"Creating {len(self.writer_config.text_styles)} text styles.")
        for ts_conf in self.writer_config.text_styles:
            if not doc.styles.has_entry(ts_conf.name):
                self.logger.debug(f"Creating text style: {ts_conf.name} with font {ts_conf.font_file}")
                try:
                    doc.styles.new(
                        name=ts_conf.name,
                        dxfattribs={
                            "font": ts_conf.font_file, # Font filename (e.g., "arial.ttf")
                            "width_factor": ts_conf.width_factor or 1.0,
                            # Other attributes like 'height' (fixed height), 'oblique' (obliquing angle)
                        }
                    )
                    # Note: 'height' for a text style makes it a fixed-height style.
                    # Typically, MTEXT/TEXT entities define their own height.
                except Exception as e:
                    self.logger.error(f"Failed to create text style {ts_conf.name}: {e}", exc_info=True)
            else:
                self.logger.debug(f"Text style {ts_conf.name} already exists. Skipping creation.")
        self.logger.info("Finished creating text styles.")

    async def _create_block_definitions_from_config(
        self,
        doc: Drawing
        # entities_by_layer_config: Dict[str, Tuple[DomainLayerConfig, AsyncIterator[AnyDxfEntity]]] # Removed
    ) -> None:
        """Creates block definitions in the DXF document from DxfWriterConfig."""
        configured_block_definitions = self.writer_config.block_definitions or []
        if not configured_block_definitions:
            self.logger.info("No explicit block definitions in DxfWriterConfig. Skipping block creation.")
            return

        self.logger.debug(f"Processing {len(configured_block_definitions)} configured block definitions.")
        for block_conf in configured_block_definitions:
            block_name = sanitize_layer_name(block_conf.name) # Sanitize block name too
            if doc.blocks.has_entry(block_name):
                self.logger.debug(f"Block definition {block_name} already exists. Skipping.")
                continue

            self.logger.info(f"Creating block definition: {block_name}")
            try:
                block_layout = doc.blocks.new(name=block_name, base_point=block_conf.base_point)

                for entity_conf in block_conf.entities:
                    dxfattribs: Dict[str, Any] = {}
                    # Ensure layer "0" is handled as a valid layer name for block entities
                    dxfattribs['layer'] = sanitize_layer_name(entity_conf.layer if entity_conf.layer is not None else "0")

                    if entity_conf.color:
                        if entity_conf.color.rgb is not None:
                            dxfattribs['true_color'] = ezdxf.rgb2int(entity_conf.color.rgb)
                        elif entity_conf.color.aci is not None:
                            dxfattribs['color'] = entity_conf.color.aci

                    if entity_conf.linetype:
                        dxfattribs['linetype'] = entity_conf.linetype
                    if entity_conf.lineweight is not None:
                        dxfattribs['lineweight'] = entity_conf.lineweight

                    self.logger.debug(f"Adding entity type {entity_conf.type} to block {block_name} with attribs {dxfattribs}")

                    if isinstance(entity_conf, BlockPointConfig):
                        block_layout.add_point(entity_conf.location, dxfattribs=dxfattribs)
                    elif isinstance(entity_conf, BlockLineConfig):
                        block_layout.add_line(entity_conf.start_point, entity_conf.end_point, dxfattribs=dxfattribs)
                    elif isinstance(entity_conf, BlockCircleConfig):
                        block_layout.add_circle(entity_conf.center, entity_conf.radius, dxfattribs=dxfattribs)
                    elif isinstance(entity_conf, BlockArcConfig):
                        block_layout.add_arc(entity_conf.center, entity_conf.radius,
                                           entity_conf.start_angle, entity_conf.end_angle, dxfattribs=dxfattribs)
                    elif isinstance(entity_conf, BlockPolylineConfig):
                        points_for_polyline = [(v[0], v[1], v[2] if len(v) > 2 and v[2] is not None else 0.0) for v in entity_conf.vertices]

                        poly_attribs = dxfattribs.copy()
                        # Removed flags from poly_attribs initially, will be set specifically for POLYLINE
                        # if entity_conf.is_closed:
                        # poly_attribs['flags'] = poly_attribs.get('flags', 0) | 1

                        # Determine if we should use LWPOLYLINE or POLYLINE (3D)
                        use_3d_polyline = False
                        if entity_conf.type == "POLYLINE":
                            use_3d_polyline = True
                        else: # type is LWPOLYLINE or not specified, check Z consistency
                            first_z = None
                            z_inconsistent = False
                            has_any_z = False
                            for p in points_for_polyline:
                                if p[2] is not None:
                                    has_any_z = True
                                    if first_z is None:
                                        first_z = p[2]
                                    elif p[2] != first_z:
                                        z_inconsistent = True
                                        break
                            if z_inconsistent:
                                self.logger.warning(f"Block '{block_name}', polyline entity: Vertices have inconsistent Z values. "
                                                    f"Using 3D POLYLINE as Z coordinates vary significantly.")
                                use_3d_polyline = True
                            elif not has_any_z: # All Z are None (effectively 0.0)
                                pass # LWPolyline is fine, elevation will be 0.0
                            elif first_z is not None and not z_inconsistent : # All Z are same and not None
                                poly_attribs['elevation'] = first_z # Set elevation for LWPOLYLINE

                        if use_3d_polyline:
                            self.logger.debug(f"Adding 3D POLYLINE to block {block_name}.")
                            if entity_conf.is_closed: # Set flags for 3D POLYLINE
                                poly_attribs['flags'] = poly_attribs.get('flags', 0) | ezdxf.const.POLYLINE_CLOSED
                            block_layout.add_polyline3d(points_for_polyline, dxfattribs=poly_attribs)
                        else:
                            # Prepare points for LWPOLYLINE (x,y only)
                            points_2d_for_lw = [(p[0], p[1]) for p in points_for_polyline]
                            # Elevation for LWPOLYLINE should be in poly_attribs if set
                            # Closed for LWPOLYLINE is a direct attribute in dxfattribs
                            if entity_conf.is_closed:
                                poly_attribs['closed'] = True
                            else: # Ensure it's not inadvertently set if not closed
                                poly_attribs.pop('closed', None)

                            self.logger.debug(f"Adding LWPOLYLINE to block {block_name} with attribs {poly_attribs}")
                            block_layout.add_lwpolyline(points_2d_for_lw, dxfattribs=poly_attribs)

                    elif isinstance(entity_conf, BlockTextConfig):
                        text_dxfattribs = dxfattribs.copy()
                        if entity_conf.style:
                            text_dxfattribs['style'] = entity_conf.style
                        if entity_conf.height is not None: # Height 0 is valid (fit to style)
                             text_dxfattribs['height'] = entity_conf.height

                        # MTEXT specific attributes
                        is_mtext = entity_conf.type == "MTEXT" or "\\n" in entity_conf.text_string # Basic check

                        if is_mtext:
                            if entity_conf.width is not None:
                                text_dxfattribs['width'] = entity_conf.width # MTEXT width
                            if entity_conf.attachment_point is not None:
                                text_dxfattribs['attachment_point'] = entity_conf.attachment_point
                            if entity_conf.rotation is not None: # ADDED MTEXT ROTATION
                                text_dxfattribs['rotation'] = math.radians(entity_conf.rotation) # DXF MTEXT rotation is in radians

                            mtext_obj = block_layout.add_mtext(entity_conf.text_string, dxfattribs=text_dxfattribs)
                            # For MTEXT, insertion point is set via dxf.insert, not align with set_pos
                            mtext_obj.dxf.insert = Vec3(entity_conf.insertion_point)
                        else: # TEXT
                            if entity_conf.rotation is not None:
                                text_dxfattribs['rotation'] = entity_conf.rotation # TEXT rotation is in degrees
                            text_obj = block_layout.add_text(entity_conf.text_string, dxfattribs=text_dxfattribs)
                            # For TEXT, insertion point and alignment point logic
                            # text_obj.set_pos(Vec3(entity_conf.insertion_point), align=None) # Old way
                            text_obj.dxf.insert = Vec3(entity_conf.insertion_point) # Set base insertion point
                            # If alignment is specified (halign/valign in dxfattribs), ezdxf handles it relative to insert.
                            # If specific align_point is needed for certain alignments, it would be:
                            # if text_obj.dxf.halign != 0 or text_obj.dxf.valign != 0:
                            #    text_obj.dxf.align_point = Vec3(entity_conf.insertion_point)
                    else:
                        self.logger.warning(f"Unsupported entity type '{entity_conf.type}' in block definition '{block_name}'. Skipping entity.")
            except Exception as e:
                self.logger.error(f"Failed to create block definition {block_name} or its entities: {e}", exc_info=True)

        self.logger.info("Finished processing configured block definitions.")
