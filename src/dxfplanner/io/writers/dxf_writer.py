from typing import AsyncIterator, Optional, List, Any, Dict, Tuple
from pathlib import Path

import ezdxf
from ezdxf.enums import InsertUnits # For setting drawing units
from ezdxf import colors as ezdxf_colors # For ACI color handling
from ezdxf import const as ezdxf_const # For MTEXT constants

from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfLayer, # DxfLayer might not be used directly if layers are from AppConfig
    DxfLine, DxfLWPolyline, DxfText, DxfMText, # Added DxfMText
    DxfHatch, DxfHatchPath, # Added DxfHatch and DxfHatchPath
    AnyDxfEntity, Coordinate,
    DxfArc, DxfCircle, DxfPolyline, DxfInsert # Added Arc, Circle, Polyline, Insert
)
from dxfplanner.domain.interfaces import IDxfWriter, AnyStrPath
from dxfplanner.core.exceptions import DxfWriteError
from dxfplanner.config.schemas import AppConfig, ColorModel, LayerDisplayPropertiesConfig, TextStylePropertiesConfig, HatchPropertiesConfig # Added HatchPropertiesConfig
from dxfplanner.services.style_service import StyleService, StyleObjectConfig # For resolving layer styles
from dxfplanner.core.logging_config import get_logger

# Need BoundingBoxModel from domain models for return type
from dxfplanner.domain.models.common import BoundingBox as BoundingBoxModel

logger = get_logger(__name__)

class DxfWriter(IDxfWriter):
    """Writes DXF entities to a .dxf file using ezdxf library."""

    def __init__(self, app_config: AppConfig, style_service: StyleService):
        self._app_config = app_config
        self._writer_config = app_config.io.writers.dxf
        self._style_service = style_service
        # For ezdxf < 0.17
        # ezdxf.options.set(template_dir=ezdxf.EZDXF_TEST_FILES)

    def _attach_writer_xdata(self, entity: ezdxf.entity.DXFEntity) -> None:
        """Attaches standard XDATA to an entity to identify it as writer-processed."""
        app_id = self._writer_config.xdata_application_name
        if not app_id:
            logger.debug("XDATA application name not configured. Skipping XDATA attachment.")
            return

        try:
            # Using a simple marker string for now. Can be extended with more data.
            xdata_content = [(1000, f"Processed by {app_id}")]
            entity.set_xdata(app_id, xdata_content)
            logger.debug(f"Attached XDATA to entity {entity.dxf.handle} with AppID '{app_id}'.")
        except AttributeError: # e.g. if entity does not have set_xdata or is not a valid DXFEntity type
            logger.warning(f"Could not attach XDATA to entity {entity}. It might not support XDATA.", exc_info=True)
        except Exception as e:
            logger.warning(f"Failed to attach XDATA to entity {entity}: {e}", exc_info=True)

    def _setup_document_properties(self, doc: ezdxf.document.Drawing) -> None:
        """Sets DXF header variables from configuration."""
        if self._writer_config.document_properties:
            for key, value in self._writer_config.document_properties.items():
                header_var_name = f"${key.upper()}"
                try:
                    doc.header[header_var_name] = value
                    logger.debug(f"Set DXF header variable: {header_var_name} = {value}")
                except Exception as e:
                    logger.warning(f"Failed to set DXF header variable {header_var_name} to {value}: {e}")

        # Ensure drawing units are set (example, can be part of document_properties)
        # Defaulting to millimeters if not specified in document_properties
        if "$INSUNITS" not in doc.header and ("INSUNITS" not in (self._writer_config.document_properties or {})):
             doc.header['$INSUNITS'] = InsertUnits.Millimeters # Default to Millimeters
             logger.debug(f"Set default DXF header variable: $INSUNITS = {InsertUnits.Millimeters}")


    def _create_text_styles(self, doc: ezdxf.document.Drawing) -> None:
        """Creates text styles in the DXF document from configuration."""
        if self._writer_config.defined_text_styles:
            for style_name, style_config in self._writer_config.defined_text_styles.items():
                if style_name not in doc.styles:
                    try:
                        style_attribs = {'font': style_config.font}
                        if style_config.height is not None and style_config.height > 0: # Fixed height for style
                            style_attribs['height'] = style_config.height
                        if style_config.width_factor is not None:
                            style_attribs['width'] = style_config.width_factor # DXF name for width factor
                        if style_config.oblique_angle is not None:
                            style_attribs['oblique'] = style_config.oblique_angle # DXF name for oblique angle

                        # Add other DXF TEXTSTYLE properties if defined in TextStylePropertiesConfig
                        # e.g. 'flags', 'big_font' (not currently in TextStylePropertiesConfig)

                        doc.styles.new(style_name, dxfattribs=style_attribs)
                        logger.info(f"Created text style '{style_name}' with font '{style_config.font}'.")
                    except Exception as e:
                        logger.warning(f"Could not create text style '{style_name}' with font '{style_config.font}': {e}")
                else:
                    logger.debug(f"Text style '{style_name}' already exists.")

    def _convert_color_model_to_aci(self, color_model: Optional[ColorModel]) -> Optional[int]:
        """Converts ColorModel to ACI. Returns None if conversion is not direct (e.g. RGB)."""
        if color_model is None:
            return None
        if isinstance(color_model, int): # Assumed ACI
            return color_model
        if isinstance(color_model, str):
            color_str = color_model.upper()
            if color_str == "BYLAYER":
                return 256
            if color_str == "BYBLOCK":
                return 0
            try:
                return ezdxf_colors.ACI[color_str]
            except KeyError:
                logger.warning(f"Cannot convert color name '{color_model}' to ACI. Using BYLAYER.")
                return 256 # Default to BYLAYER if name not found
        # RGB Tuple (e.g. (255,0,0)) would require true color support (entity.rgb)
        # or a nearest ACI color match, which is complex. For now, ACI only.
        if isinstance(color_model, tuple) and len(color_model) == 3:
             logger.warning(f"RGB color tuple {color_model} provided; true color not yet fully implemented for all ACI slots. Defaulting related ACI to None/BYLAYER.")
             return None # Let ezdxf handle this, likely becomes BYLAYER if .rgb not set

        logger.warning(f"Unhandled ColorModel type: {type(color_model)}. Defaulting to BYLAYER.")
        return 256

    async def _get_or_create_document(
        self, file_path: Path
    ) -> Tuple[ezdxf.document.Drawing, ezdxf.layouts.Modelspace]:
        """Handles loading an existing DXF, a template, or creating a new document."""
        doc: Optional[ezdxf.document.Drawing] = None
        msp: Optional[ezdxf.layouts.Modelspace] = None
        app_id = self._writer_config.xdata_application_name

        if file_path.exists() and file_path.is_file():
            logger.info(f"Output file {file_path} exists. Attempting to load and update.")
            try:
                doc = ezdxf.readfile(file_path)
                msp = doc.modelspace()
                logger.info(f"Successfully loaded existing DXF: {file_path}")

                if app_id:
                    entities_to_delete = []
                    for entity in msp.query('*'):
                        if entity.has_xdata(app_id):
                            xdata_content_list = entity.get_xdata(app_id)
                            if xdata_content_list and isinstance(xdata_content_list, list):
                                for xd_item in xdata_content_list:
                                    if xd_item.code == 1000 and xd_item.value == f"Processed by {app_id}":
                                        entities_to_delete.append(entity)
                                        break
                    if entities_to_delete:
                        logger.info(f"Found {len(entities_to_delete)} entities with XDATA AppID '{app_id}' to clear.")
                        for entity in entities_to_delete:
                            try:
                                msp.delete_entity(entity)
                            except Exception as e_del:
                                logger.warning(f"Failed to delete entity {entity.dxf.handle}: {e_del}")
                        logger.info(f"Finished clearing entities. {len(entities_to_delete)} entities removed.")
                    else:
                        logger.info(f"No entities found with XDATA AppID '{app_id}' to clear in {file_path}.")
                else:
                    logger.warning("XDATA application name not configured. Cannot clear previously managed entities.")

            except ezdxf.DXFStructureError as e_load:
                logger.error(f"Failed to load existing DXF file {file_path} due to structure error: {e_load}. Please check the file or remove it to create a new one.", exc_info=True)
                raise DxfWriteError(f"Corrupt existing DXF file: {file_path}. Error: {e_load}")
            except Exception as e_load_generic:
                logger.error(f"An unexpected error occurred while loading existing DXF file {file_path}: {e_load_generic}.", exc_info=True)
                raise DxfWriteError(f"Failed to load existing DXF file: {file_path}. Error: {e_load_generic}")
        else:
            logger.info(f"Output file {file_path} does not exist.")
            if self._writer_config.template_file:
                p_template_path = Path(self._writer_config.template_file)
                if p_template_path.exists() and p_template_path.is_file():
                    logger.info(f"Attempting to load from template file: {p_template_path}")
                    try:
                        doc = ezdxf.readfile(p_template_path)
                        msp = doc.modelspace()
                        logger.info(f"Successfully loaded DXF from template: {p_template_path}")
                    except ezdxf.DXFStructureError as e_tmpl_load:
                        logger.error(f"Failed to load template DXF {p_template_path} due to structure error: {e_tmpl_load}. Proceeding to create a new DXF.", exc_info=True)
                    except Exception as e_tmpl_load_generic:
                        logger.error(f"An unexpected error occurred while loading template DXF {p_template_path}: {e_tmpl_load_generic}. Proceeding to create a new DXF.", exc_info=True)
                else:
                    logger.warning(f"Template file '{self._writer_config.template_file}' not found or is not a file. Proceeding to create a new DXF.")
            else:
                logger.info("No template file configured. Proceeding to create a new DXF.")

        if doc is None or msp is None:
            logger.info(f"Creating a new DXF document for version {self._writer_config.target_dxf_version}.")
            doc = ezdxf.new(dxfversion=self._writer_config.target_dxf_version)
            msp = doc.modelspace()

        return doc, msp

    async def _process_and_add_entities(
        self,
        doc: ezdxf.document.Drawing,
        msp: ezdxf.layouts.Modelspace,
        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]]
    ) -> None:
        """Creates layers and processes all entities, adding them to the modelspace."""
        # Create layers from AppConfig LayerConfigs that are enabled
        active_layer_configs = {name: data[0] for name, data in entities_by_layer_config.items()}

        for layer_name, layer_cfg in active_layer_configs.items():
            if not layer_cfg.enabled:
                logger.debug(f"Skipping disabled layer: {layer_cfg.name}")
                continue

            resolved_style: StyleObjectConfig = self._style_service.get_resolved_layer_style(layer_cfg)
            layer_dxf_attrs: Dict[str, Any] = {"name": layer_cfg.name}

            if resolved_style.layer_props:
                lp_cfg: LayerDisplayPropertiesConfig = resolved_style.layer_props
                aci_color = self._convert_color_model_to_aci(lp_cfg.color)
                if aci_color is not None:
                    layer_dxf_attrs['color'] = aci_color
                if lp_cfg.linetype and lp_cfg.linetype.upper() != "BYLAYER":
                    layer_dxf_attrs['linetype'] = lp_cfg.linetype
                if lp_cfg.lineweight >= 0: # Valid ACI lineweights are 0-211 for mm * 100
                    layer_dxf_attrs['lineweight'] = lp_cfg.lineweight
                layer_dxf_attrs['plot'] = lp_cfg.plot
                # Transparency for layers: ezdxf Layer object has .transparency (0.0 to 1.0)
                # layer_object.transparency = lp_cfg.transparency (after layer creation)

            if layer_cfg.name not in doc.layers:
                logger.debug(f"Adding layer to DXF: {layer_cfg.name} with attribs {layer_dxf_attrs}")
                dxf_layer = doc.layers.add(**layer_dxf_attrs) # type: ignore
                if resolved_style.layer_props and hasattr(dxf_layer, 'transparency'): # ezdxf >= 0.17
                     dxf_layer.transparency = resolved_style.layer_props.transparency
            else:
                logger.warning(f"Layer {layer_cfg.name} already exists in DXF doc. Skipping re-creation.")

        # Placeholder for Text Style creation from AppConfig style_presets and LayerConfig label styles
        # This needs to happen before entities that might reference them are created.
        # Example: for name, style_obj_cfg in self._app_config.style_presets.items():
        # if style_obj_cfg.text_props: create_ezdxf_text_style(doc, name, style_obj_cfg.text_props)

        # Process entities for each layer
        for layer_name, (layer_cfg, entity_iter) in entities_by_layer_config.items():
            if not layer_cfg.enabled:
                continue

            logger.debug(f"Writing entities for layer: {layer_cfg.name}")
            async for entity_model in entity_iter:
                entity_dxf_attribs: Dict[str, Any] = {"layer": entity_model.layer}

                # Direct entity property overrides
                if entity_model.color_256 is not None:
                    entity_dxf_attribs['color'] = entity_model.color_256
                # Add other direct properties from DxfEntity if they exist (e.g., linetype)
                if entity_model.linetype and entity_model.linetype.upper() != "BYLAYER":
                    entity_dxf_attribs['linetype'] = entity_model.linetype

                # More advanced styling (e.g., applying resolved layer style if entity props are None)
                # will be part of a later enhancement phase.

                try:
                    added_entity = None # Track added entity for XDATA
                    if isinstance(entity_model, DxfLine):
                        added_entity = msp.add_line(
                            start=entity_model.start.to_tuple(),
                            end=entity_model.end.to_tuple(),
                            dxfattribs=entity_dxf_attribs
                        )
                    elif isinstance(entity_model, DxfLWPolyline):
                        # Convert points, handling potential tuple structure if needed by ezdxf
                        # Assuming ezdxf add_lwpolyline takes list of (x,y) or (x,y,z) tuples
                        points_tuples = [p.to_tuple() for p in entity_model.points]
                        added_entity = msp.add_lwpolyline(
                            points=points_tuples,
                            close=entity_model.is_closed,
                            dxfattribs=entity_dxf_attribs
                        )
                    elif isinstance(entity_model, DxfText):
                        # Assign text style from model or default
                        style = entity_model.style or self._writer_config.default_text_style_name
                        if style not in doc.styles:
                            logger.warning(f"Text style '{style}' not found in document. Using default.")
                            style = self._writer_config.default_text_style_name
                        entity_dxf_attribs['style'] = style
                        entity_dxf_attribs['height'] = entity_model.height
                        entity_dxf_attribs['rotation'] = entity_model.rotation

                        added_entity = msp.add_text(
                            text=entity_model.text_content,
                            dxfattribs=entity_dxf_attribs,
                        ).set_placement(entity_model.insertion_point.to_tuple()) # Use set_placement for TEXT
                    elif isinstance(entity_model, DxfMText):
                        style = entity_model.style or self._writer_config.default_text_style_name
                        if style not in doc.styles:
                            logger.warning(f"MText style '{style}' not found in document. Using default.")
                            style = self._writer_config.default_text_style_name
                        entity_dxf_attribs['style'] = style
                        entity_dxf_attribs['char_height'] = entity_model.char_height
                        entity_dxf_attribs['width'] = entity_model.width
                        entity_dxf_attribs['rotation'] = entity_model.rotation
                        # Add other MTEXT properties like attachment point, line spacing etc.
                        if entity_model.attachment_point:
                            entity_dxf_attribs['attachment_point'] = getattr(ezdxf_const.MTextAttachmentPoint, entity_model.attachment_point, None)
                        # Add flow_direction, line_spacing_style, line_spacing_factor if needed
                        added_entity = msp.add_mtext(
                            text=entity_model.text_content,
                            dxfattribs=entity_dxf_attribs,
                        ).set_placement(entity_model.insertion_point.to_tuple())
                    elif isinstance(entity_model, DxfHatch):
                        added_entity = msp.add_hatch(
                            color=entity_dxf_attribs.get('color', ezdxf_const.BYLAYER),
                            # style=getattr(ezdxf_const.HatchStyle, entity_model.hatch_style_enum, ezdxf_const.HatchStyle.NORMAL),
                            # associative=entity_model.associative
                            dxfattribs=entity_dxf_attribs # Pass layer etc.
                        )
                        if added_entity:
                            added_entity.set_pattern_fill(
                                name=entity_model.pattern_name,
                                scale=entity_model.pattern_scale,
                                angle=entity_model.pattern_angle,
                                color=entity_dxf_attribs.get('color', ezdxf_const.BYLAYER) # Pattern color often same as hatch boundary color
                            )
                            for path_model in entity_model.paths:
                                path_vertices = [v.to_tuple() for v in path_model.vertices]
                                # path_type default is polyline | external - adjust if needed
                                added_entity.paths.add_polyline_path(path_vertices, is_closed=path_model.is_closed)
                    elif isinstance(entity_model, DxfInsert):
                        added_entity = msp.add_blockref(
                            name=entity_model.block_name,
                            insert=entity_model.insertion_point.to_tuple(),
                            dxfattribs={
                                **entity_dxf_attribs, # includes layer, color
                                'xscale': entity_model.x_scale,
                                'yscale': entity_model.y_scale,
                                'zscale': entity_model.z_scale,
                                'rotation': entity_model.rotation,
                            }
                        )
                    # --- NEW ENTITY TYPES ---
                    elif isinstance(entity_model, DxfCircle):
                        added_entity = msp.add_circle(
                            center=entity_model.center.to_tuple(),
                            radius=entity_model.radius,
                            dxfattribs=entity_dxf_attribs
                        )
                    elif isinstance(entity_model, DxfArc):
                        added_entity = msp.add_arc(
                            center=entity_model.center.to_tuple(),
                            radius=entity_model.radius,
                            start_angle=entity_model.start_angle,
                            end_angle=entity_model.end_angle,
                            dxfattribs=entity_dxf_attribs
                        )
                    elif isinstance(entity_model, DxfPolyline): # Heavy Polyline (3D)
                        points_tuples = [p.to_tuple() for p in entity_model.points]
                        added_entity = msp.add_polyline3d(
                            points=points_tuples,
                            close=entity_model.is_closed,
                            dxfattribs=entity_dxf_attribs
                        )
                    else:
                        logger.warning(f"Unhandled DXF entity model type: {type(entity_model)} for layer '{layer_name}'. Skipping.")

                    if added_entity: # If entity was successfully created
                        self._attach_writer_xdata(added_entity)
                except Exception as e_add:
                    logger.error(f"Failed to add entity ({type(entity_model)}) to modelspace for layer '{layer_name}': {e_add}", exc_info=False)
                    # Continue to next entity

    async def write_drawing(
        self,
        file_path: AnyStrPath,
        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]],
        **kwargs: Any
    ) -> None:
        """
        Writes DXF entities to a specified file path.
        Entities are grouped by their source LayerConfig for styling.
        Implements iterative output: loads existing file, clears managed entities,
        or uses a template, before adding new entities.
        """
        p_output_path = Path(file_path)
        if not p_output_path.suffix.lower() == ".dxf":
            raise DxfWriteError(f"Output file path must have a .dxf extension: {p_output_path}")

        doc: Optional[ezdxf.document.Drawing] = None
        msp: Optional[ezdxf.layouts.Modelspace] = None
        # app_id = self._writer_config.xdata_application_name # Moved to _get_or_create_document

        try:
            # Logic for loading existing file, template, or creating new is moved to _get_or_create_document
            doc, msp = await self._get_or_create_document(p_output_path)

            # Ensure document is set up (these methods are idempotent or check existence)
            self._setup_document_properties(doc)
            self._create_text_styles(doc)

            # Create layers from AppConfig LayerConfigs that are enabled
            # active_layer_configs = {name: data[0] for name, data in entities_by_layer_config.items()} # MOVED

            # for layer_name, layer_cfg in active_layer_configs.items(): # MOVED
            #     if not layer_cfg.enabled: # MOVED
            #         logger.debug(f"Skipping disabled layer: {layer_cfg.name}") # MOVED
            #         continue # MOVED
            # # ... entire layer creation loop MOVED to _process_and_add_entities

            # Process entities for each layer # MOVED
            # for layer_name, (layer_cfg, entity_iter) in entities_by_layer_config.items(): # MOVED
            #     if not layer_cfg.enabled: # MOVED
            #         continue # MOVED
            # # ... entire entity processing loop MOVED to _process_and_add_entities

            await self._process_and_add_entities(doc, msp, entities_by_layer_config)

            if self._writer_config.audit_on_save:
                try:
                    logger.debug("Performing DXF document audit before saving.")
                    doc.audit() # Audit the document
                except Exception as e:
                    logger.warning(f"Error during DXF document audit: {e}", exc_info=True)

            doc.saveas(p_output_path)
            logger.info(f"DXF file successfully written to: {p_output_path}")

        except ezdxf.DXFError as e:
            logger.error(f"ezdxf library error while writing to {p_output_path}: {e}", exc_info=True)
            raise DxfWriteError(f"ezdxf library error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error writing DXF file {p_output_path}: {e}", exc_info=True)
            raise DxfWriteError(f"Unexpected error writing DXF: {e}")

    # --- Legend Generation Support Method Implementations ---

    async def clear_legend_content(
        self,
        doc: Any, # ezdxf.document.Drawing
        msp: Any, # ezdxf.layouts.Modelspace
        legend_id: str
    ) -> None:
        logger.debug(f"Attempting to clear legend content for legend_id: {legend_id}")
        if not self._writer_config.xdata_application_name:
            logger.warning("XDATA application name not configured. Cannot clear legend content by XDATA.")
            return

        entities_to_delete = []
        # Construct the expected prefix for XDATA legend item tags for this specific legend_id
        # This matches the prefixing strategy in LegendGenerationService
        expected_xdata_tag_prefix = f"legend_{legend_id}_"
        app_id = self._writer_config.xdata_application_name

        for entity in msp: # Iterate through all entities in modelspace
            try:
                if entity.has_xdata(app_id):
                    xdata = entity.get_xdata(app_id)
                    # XDATA for legend items is expected to be like:
                    # [(1000, "legend_item"), (1000, "legend_<legend_id>_actual_item_name")]
                    if len(xdata) >= 2 and xdata[0].code == 1000 and xdata[0].value == "legend_item":
                        if xdata[1].code == 1000 and isinstance(xdata[1].value, str) and xdata[1].value.startswith(expected_xdata_tag_prefix):
                            entities_to_delete.append(entity)
                            logger.debug(f"Marked entity {entity.dxf.handle} (type: {entity.dxftype()}) with XDATA value '{xdata[1].value}' for deletion.")
            except AttributeError: # Some entities might not have has_xdata (e.g., unsupported types)
                logger.debug(f"Entity {entity} does not support XDATA, skipping.")
                continue
            except Exception as e:
                logger.warning(f"Error processing entity {entity.dxf.handle if hasattr(entity, 'dxf') else entity} for XDATA: {e}")
                continue

        if entities_to_delete:
            logger.info(f"Found {len(entities_to_delete)} entities to delete for legend_id: {legend_id}")
            for entity in entities_to_delete:
                try:
                    msp.delete_entity(entity)
                    logger.debug(f"Successfully deleted entity {entity.dxf.handle}.")
                except Exception as e:
                    logger.warning(f"Failed to delete entity {entity.dxf.handle}: {e}")
        else:
            logger.info(f"No entities found with XDATA matching prefix '{expected_xdata_tag_prefix}' for legend_id: {legend_id}. No entities deleted.")

    async def ensure_layer_exists_with_properties(
        self,
        doc: Any,
        layer_name: str,
        properties: Optional[LayerDisplayPropertiesConfig] = None
    ) -> Any: # Returns the ezdxf layer object
        logger.debug(f"Ensuring layer '{layer_name}' exists.")
        try:
            if layer_name in doc.layers:
                layer = doc.layers.get(layer_name)
                logger.debug(f"Layer '{layer_name}' already exists. Updating properties if provided.")
            else:
                logger.debug(f"Layer '{layer_name}' does not exist. Creating.")
                layer = doc.layers.new(layer_name) # Use new() for consistency with ezdxf >=0.17

            if properties:
                dxf_attrs = {}
                aci_color = self._convert_color_model_to_aci(properties.color)
                if aci_color is not None: dxf_attrs['color'] = aci_color
                if properties.linetype and properties.linetype.upper() != "BYLAYER": dxf_attrs['linetype'] = properties.linetype
                if properties.lineweight >= 0: dxf_attrs['lineweight'] = properties.lineweight
                dxf_attrs['plot'] = properties.plot

                for key, value in dxf_attrs.items():
                    try:
                        setattr(layer.dxf, key, value)
                    except AttributeError:
                        logger.warning(f"Could not set DXF attribute '{key}' on layer '{layer_name}'.")

                if hasattr(layer, 'transparency'): # ezdxf >= 0.17
                    layer.transparency = properties.transparency
                logger.debug(f"Applied properties to layer '{layer_name}': {properties.model_dump_json(exclude_none=True)}")
            return layer
        except Exception as e:
            logger.error(f"Error ensuring layer '{layer_name}': {e}", exc_info=True)
            raise DxfWriteError(f"Error ensuring layer '{layer_name}': {e}")

    async def add_mtext_ez(
        self,
        doc: Any, msp: Any,
        text: str,
        insertion_point: Tuple[float, float],
        layer_name: str,
        style_config: TextStylePropertiesConfig,
        max_width: Optional[float] = None,
        legend_item_id: Optional[str] = None
    ) -> Tuple[Optional[Any], float]:
        logger.debug(f"Adding MTEXT to layer '{layer_name}': '{text[:30]}...'")
        try:
            dxfattribs = {
                'layer': layer_name,
                'style': style_config.font or self._writer_config.default_text_style_name,
                'char_height': style_config.height or self._writer_config.default_text_height or 1.0,
            }
            if max_width is not None and max_width > 0:
                dxfattribs['width'] = max_width
            elif style_config.max_width is not None and style_config.max_width > 0:
                 dxfattribs['width'] = style_config.max_width

            if style_config.rotation is not None:
                dxfattribs['rotation'] = style_config.rotation

            aci_color = self._convert_color_model_to_aci(style_config.color)
            if aci_color is not None:
                dxfattribs['color'] = aci_color
            elif style_config.color_rgb: # Expects (r,g,b) tuple
                # entity.rgb can be set after creation if aci_color is None
                pass

            # Attachment Point
            ap_map = {
                'TOP_LEFT': ezdxf_const.MTEXT_TOP_LEFT, 'TOP_CENTER': ezdxf_const.MTEXT_TOP_CENTER, 'TOP_RIGHT': ezdxf_const.MTEXT_TOP_RIGHT,
                'MIDDLE_LEFT': ezdxf_const.MTEXT_MIDDLE_LEFT, 'MIDDLE_CENTER': ezdxf_const.MTEXT_MIDDLE_CENTER, 'MIDDLE_RIGHT': ezdxf_const.MTEXT_MIDDLE_RIGHT,
                'BOTTOM_LEFT': ezdxf_const.MTEXT_BOTTOM_LEFT, 'BOTTOM_CENTER': ezdxf_const.MTEXT_BOTTOM_CENTER, 'BOTTOM_RIGHT': ezdxf_const.MTEXT_BOTTOM_RIGHT,
            }
            if style_config.attachment_point:
                dxfattribs['attachment_point'] = ap_map.get(style_config.attachment_point.upper(), ezdxf_const.MTEXT_TOP_LEFT)
            else:
                dxfattribs['attachment_point'] = ezdxf_const.MTEXT_TOP_LEFT # Default

            # Other MTEXT properties from TextStylePropertiesConfig
            if style_config.flow_direction:
                fd_map = {
                    'LEFT_TO_RIGHT': ezdxf_const.MTEXT_LEFT_TO_RIGHT,
                    'TOP_TO_BOTTOM': ezdxf_const.MTEXT_TOP_TO_BOTTOM,
                    'BY_STYLE': ezdxf_const.MTEXT_BY_STYLE
                }
                dxfattribs['flow_direction'] = fd_map.get(style_config.flow_direction.upper())
            if style_config.line_spacing_style:
                lss_map = {
                    'AT_LEAST': ezdxf_const.MTEXT_AT_LEAST,
                    'EXACT': ezdxf_const.MTEXT_EXACT
                }
                dxfattribs['line_spacing_style'] = lss_map.get(style_config.line_spacing_style.upper())
            if style_config.line_spacing_factor is not None:
                dxfattribs['line_spacing_factor'] = style_config.line_spacing_factor
            if style_config.bg_fill_enabled is not None:
                dxfattribs['bg_fill'] = style_config.bg_fill_enabled
                if style_config.bg_fill_color:
                    bg_aci_color = self._convert_color_model_to_aci(style_config.bg_fill_color)
                    if bg_aci_color is not None:
                         dxfattribs['bg_fill_color'] = bg_aci_color # For MASK type fill if supported by ezdxf version
                         # For true BG_FILL, need to check ezdxf docs for specific attribute (often combined with mask)
                    # dxfattribs['box_fill_scale'] = style_config.bg_fill_scale if style_config.bg_fill_scale is not None else 1.5

            # MTEXT content can include formatting codes. TextStylePropertiesConfig could expand to support this.
            # For now, raw text is passed.
            mtext_entity = msp.add_mtext(text, dxfattribs=dxfattribs)
            mtext_entity.set_location(insert=insertion_point) # Ensure location is set, attachment point handles alignment relative to this

            if style_config.color_rgb and aci_color is None: # Set RGB if ACI wasn't appropriate/set
                 mtext_entity.rgb = style_config.color_rgb
            if style_config.bg_fill_enabled and style_config.bg_fill_color_rgb and not dxfattribs.get('bg_fill_color'):
                # This is complex: MTEXT background fill color might need specific handling for true color
                # ezdxf might handle it via MASK with color or true background color. For now, log it.
                logger.debug("RGB background fill color for MTEXT requested, direct ezdxf handling depends on version/type of fill.")

            self._attach_writer_xdata(mtext_entity)
            if legend_item_id and self._writer_config.xdata_application_name:
                mtext_entity.set_xdata(self._writer_config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])

            # Calculate actual height - this is non-trivial for MTEXT due to wrapping and line spacing.
            # ezdxf's bbox calculation is the most reliable way.
            actual_height = 0.0
            try:
                bbox = ezdxf.bbox.extents([mtext_entity], fast=True) # fast=True for performance if precise curves not needed for text bbox
                if bbox.has_data:
                    actual_height = bbox.size.y
            except Exception as e:
                logger.warning(f"Could not calculate bounding box for MTEXT: {e}. Returning 0 height.")

            return mtext_entity, actual_height
        except Exception as e:
            logger.error(f"Error adding MTEXT: {e}", exc_info=True)
            return None, 0.0

    async def get_entities_bbox(
        self,
        entities: List[Any]
    ) -> Optional[BoundingBoxModel]:
        logger.debug(f"Calculating bounding box for {len(entities)} entities.")
        if not entities:
            return None
        try:
            # Filter out None entities that might result from failed creations
            valid_entities = [e for e in entities if e is not None and hasattr(e, 'dxf')]
            if not valid_entities:
                logger.debug("No valid entities provided to calculate bounding box.")
                return None

            ez_bbox = ezdxf.bbox.extents(valid_entities, fast=True)
            if ez_bbox.has_data:
                return BoundingBoxModel(
                    min_x=ez_bbox.extmin.x, min_y=ez_bbox.extmin.y, min_z=ez_bbox.extmin.z,
                    max_x=ez_bbox.extmax.x, max_y=ez_bbox.extmax.y, max_z=ez_bbox.extmax.z
                )
            return None
        except Exception as e:
            logger.error(f"Error calculating bounding box: {e}", exc_info=True)
            return None

    async def translate_entities(
        self,
        entities: List[Any],
        dx: float, dy: float, dz: float
    ) -> None:
        logger.debug(f"Translating {len(entities)} entities by ({dx}, {dy}, {dz}).")
        if not entities:
            return
        try:
            for entity in entities:
                if entity and hasattr(entity, 'translate'):
                    entity.translate(dx, dy, dz)
        except Exception as e:
            logger.error(f"Error translating entities: {e}", exc_info=True)
            # Not raising DxfWriteError here as it might be part of a larger operation

    async def add_lwpolyline(
        self,
        doc: Any, msp: Any,
        points: List[Tuple[float, float]],
        layer_name: str,
        style_props: Optional[LayerDisplayPropertiesConfig],
        is_closed: bool = False,
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]:
        logger.debug(f"Adding LWPOLYLINE to layer '{layer_name}' with {len(points)} points.")
        if not points or len(points) < 2:
            logger.warning("LWPOLYLINE requires at least 2 points. Skipping.")
            return None
        try:
            dxfattribs = {'layer': layer_name}
            entity_rgb: Optional[Tuple[int,int,int]] = None
            if style_props:
                aci_color = self._convert_color_model_to_aci(style_props.color)
                if aci_color is not None:
                    dxfattribs['color'] = aci_color
                elif isinstance(style_props.color, tuple) and len(style_props.color) == 3:
                    entity_rgb = style_props.color # type: ignore

                if style_props.linetype and style_props.linetype.upper() != "BYLAYER":
                    dxfattribs['linetype'] = style_props.linetype
                if style_props.lineweight >= 0:
                    dxfattribs['lineweight'] = style_props.lineweight
                # LWPOLYLINE does not directly have transparency attribute in DXF like HATCH.
                # Transparency is often handled by layer or CEALPHA (entity alpha).

            lwpolyline = msp.add_lwpolyline(points=points, close=is_closed, dxfattribs=dxfattribs)
            if entity_rgb and hasattr(lwpolyline, 'rgb'):
                lwpolyline.rgb = entity_rgb

            self._attach_writer_xdata(lwpolyline)
            if legend_item_id and self._writer_config.xdata_application_name:
                lwpolyline.set_xdata(self._writer_config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
            return lwpolyline
        except Exception as e:
            logger.error(f"Error adding LWPOLYLINE: {e}", exc_info=True)
            return None

    async def add_hatch(
        self,
        doc: Any, msp: Any,
        paths: List[List[Tuple[float, float]]],
        layer_name: str,
        hatch_props_config: HatchPropertiesConfig,
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]:
        logger.debug(f"Adding HATCH to layer '{layer_name}' with pattern '{hatch_props_config.pattern_name}'.")
        if not paths:
            logger.warning("HATCH requires at least one path. Skipping.")
            return None
        try:
            dxfattribs = {
                'layer': layer_name,
                'hatch_style': ezdxf_const.HATCH_STYLE_IGNORE # Default, can be overridden by config
            }
            entity_rgb: Optional[Tuple[int,int,int]] = None

            if hatch_props_config.color:
                aci_color = self._convert_color_model_to_aci(hatch_props_config.color)
                if aci_color is not None:
                    dxfattribs['color'] = aci_color
                elif isinstance(hatch_props_config.color, tuple) and len(hatch_props_config.color) == 3:
                    entity_rgb = hatch_props_config.color # type: ignore

            if hatch_props_config.style:
                style_map = {
                    "NORMAL": ezdxf_const.HATCH_STYLE_NORMAL,
                    "OUTERMOST": ezdxf_const.HATCH_STYLE_OUTERMOST,
                    "IGNORE": ezdxf_const.HATCH_STYLE_IGNORE
                }
                dxfattribs['hatch_style'] = style_map.get(hatch_props_config.style.upper(), ezdxf_const.HATCH_STYLE_IGNORE)

            hatch = msp.add_hatch(dxfattribs=dxfattribs)

            if entity_rgb and hasattr(hatch, 'rgb'):
                hatch.rgb = entity_rgb
            if hatch_props_config.transparency is not None and hasattr(hatch, 'transparency'):
                hatch.transparency = hatch_props_config.transparency

            hatch.set_pattern_fill(
                name=hatch_props_config.pattern_name or "SOLID",
                scale=hatch_props_config.scale or 1.0,
                angle=hatch_props_config.angle or 0.0
            )

            for path_vertices in paths:
                if len(path_vertices) > 1:
                    # Assuming simple polyline paths for now
                    hatch.paths.add_polyline_path(path_vertices, is_closed=True) # Legend swatches are typically closed
                else:
                    logger.warning("Skipping hatch path with less than 2 vertices.")

            self._attach_writer_xdata(hatch)
            if legend_item_id and self._writer_config.xdata_application_name:
                hatch.set_xdata(self._writer_config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
            return hatch
        except Exception as e:
            logger.error(f"Error adding HATCH: {e}", exc_info=True)
            return None

    async def add_block_reference(
        self,
        doc: Any, msp: Any,
        block_name: str,
        insertion_point: Tuple[float, float],
        layer_name: str,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        scale_z: float = 1.0,
        rotation: float = 0.0,
        style_props: Optional[LayerDisplayPropertiesConfig] = None,
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]:
        logger.debug(f"Adding BLOCK_REFERENCE for '{block_name}' to layer '{layer_name}'.")
        if block_name not in doc.blocks:
            logger.error(f"Block '{block_name}' not defined in document. Skipping block reference.")
            return None
        try:
            dxfattribs = {
                'layer': layer_name,
                'xscale': scale_x, 'yscale': scale_y, 'zscale': scale_z,
                'rotation': rotation
            }
            entity_rgb: Optional[Tuple[int,int,int]] = None
            if style_props and style_props.color: # For INSERT, color is only applied if entities in block are BYBLOCK
                aci_color = self._convert_color_model_to_aci(style_props.color)
                if aci_color is not None:
                    dxfattribs['color'] = aci_color # This sets the INSERT entity color
                elif isinstance(style_props.color, tuple) and len(style_props.color) == 3:
                    entity_rgb = style_props.color # type: ignore

            block_ref = msp.add_blockref(name=block_name, insert=insertion_point, dxfattribs=dxfattribs)
            if entity_rgb and hasattr(block_ref, 'rgb'): # Not standard for INSERT to have .rgb, but if ezdxf supports it
                block_ref.rgb = entity_rgb

            self._attach_writer_xdata(block_ref)
            if legend_item_id and self._writer_config.xdata_application_name:
                block_ref.set_xdata(self._writer_config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
            return block_ref
        except Exception as e:
            logger.error(f"Error adding BLOCK_REFERENCE: {e}", exc_info=True)
            return None

    async def add_line(
        self,
        doc: Any, msp: Any,
        start_point: Tuple[float, float],
        end_point: Tuple[float, float],
        layer_name: str,
        style_props: Optional[LayerDisplayPropertiesConfig],
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]:
        logger.debug(f"Adding LINE to layer '{layer_name}' from {start_point} to {end_point}.")
        try:
            dxfattribs = {'layer': layer_name}
            entity_rgb: Optional[Tuple[int,int,int]] = None
            if style_props:
                aci_color = self._convert_color_model_to_aci(style_props.color)
                if aci_color is not None:
                    dxfattribs['color'] = aci_color
                elif isinstance(style_props.color, tuple) and len(style_props.color) == 3:
                    entity_rgb = style_props.color # type: ignore

                if style_props.linetype and style_props.linetype.upper() != "BYLAYER":
                    dxfattribs['linetype'] = style_props.linetype
                if style_props.lineweight >= 0:
                    dxfattribs['lineweight'] = style_props.lineweight

            line = msp.add_line(start=start_point, end=end_point, dxfattribs=dxfattribs)
            if entity_rgb and hasattr(line, 'rgb'):
                line.rgb = entity_rgb

            self._attach_writer_xdata(line)
            if legend_item_id and self._writer_config.xdata_application_name:
                line.set_xdata(self._writer_config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
            return line
        except Exception as e:
            logger.error(f"Error adding LINE: {e}", exc_info=True)
            return None
