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
    AnyDxfEntity, Coordinate, DxfInsert, # Added DxfInsert
    DxfArc, DxfCircle, DxfPolyline
)
from dxfplanner.domain.interfaces import IDxfWriter, AnyStrPath
from dxfplanner.core.exceptions import DxfWriteError
from dxfplanner.config.schemas import AppConfig, ColorModel, LayerDisplayPropertiesConfig, TextStylePropertiesConfig, HatchPropertiesConfig # Added HatchPropertiesConfig
from dxfplanner.services.style_service import StyleService, StyleObjectConfig # For resolving layer styles
from dxfplanner.core.logging_config import get_logger
from dxfplanner.services.attribute_mapping_service import AttributeMappingService
from dxfplanner.services.coordinate_service import CoordinateService
from dxfplanner.domain.models.common import (\
    DXFAttribs,\
    ColorModel,\
    AnyGeometry,\
)
from dxfplanner.domain.models.geo_models import (\
    GeoFeature,\
    PointGeo,\
    PolylineGeo,\
    PolygonGeo,\
    MultiPointGeo,\
    MultiPolylineGeo,\
    MultiPolygonGeo,\
    GeometryCollectionGeo,\
    AnyGeoGeometry\
)
from dxfplanner.config.schemas import (\
    DxfWriterConfig,\
    LayerConfig,\
    OperationsConfig,\
    StyleObjectConfig, LayerDisplayPropertiesConfig, TextStylePropertiesConfig, HatchPropertiesConfig \
)

# Need BoundingBoxModel from domain models for return type
from dxfplanner.domain.models.common import BoundingBox as BoundingBoxModel

logger = get_logger(__name__)

class DxfWriter(IDxfWriter):
    """Writes DXF entities to a .dxf file using ezdxf library."""

    def __init__(
        self,
        config: DxfWriterConfig,
        app_config: AppConfig,
        coord_service: CoordinateService,
        attr_mapping_service: AttributeMappingService,
        style_service: StyleService,
        geometry_transformer: IGeometryTransformer
    ):
        self.config = config
        self.app_config = app_config
        self.coord_service = coord_service
        self.attr_mapping_service = attr_mapping_service
        self.style_service = style_service
        self.geometry_transformer = geometry_transformer
        self.logger = get_logger(__name__)
        self.doc: Optional[ezdxf.document.Drawing] = None
        self.msp: Optional[ezdxf.layouts.Modelspace] = None

    def _attach_writer_xdata(self, entity: ezdxf.entity.DXFEntity) -> None:
        """Attaches standard XDATA to an entity to identify it as writer-processed."""
        app_id = self.config.xdata_application_name
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
        if self.config.document_properties:
            for key, value in self.config.document_properties.items():
                header_var_name = f"${key.upper()}"
                try:
                    doc.header[header_var_name] = value
                    logger.debug(f"Set DXF header variable: {header_var_name} = {value}")
                except Exception as e:
                    logger.warning(f"Failed to set DXF header variable {header_var_name} to {value}: {e}")

        # Ensure drawing units are set (example, can be part of document_properties)
        # Defaulting to millimeters if not specified in document_properties
        if "$INSUNITS" not in doc.header and ("INSUNITS" not in (self.config.document_properties or {})):
             doc.header['$INSUNITS'] = InsertUnits.Millimeters # Default to Millimeters
             logger.debug(f"Set default DXF header variable: $INSUNITS = {InsertUnits.Millimeters}")


    def _create_text_styles(self, doc: ezdxf.document.Drawing) -> None:
        """Creates text styles in the DXF document from configuration."""
        if self.config.defined_text_styles:
            for style_name, style_config in self.config.defined_text_styles.items():
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
        app_id = self.config.xdata_application_name

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
            if self.config.template_file:
                p_template_path = Path(self.config.template_file)
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
                    logger.warning(f"Template file '{self.config.template_file}' not found or is not a file. Proceeding to create a new DXF.")
            else:
                logger.info("No template file configured. Proceeding to create a new DXF.")

        if doc is None or msp is None:
            logger.info(f"Creating a new DXF document for version {self.config.target_dxf_version}.")
            doc = ezdxf.new(dxfversion=self.config.target_dxf_version)
            msp = doc.modelspace()

        return doc, msp

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

        try:
            doc, msp = await self._get_or_create_document(p_output_path)

            self._setup_document_properties(doc)
            self._create_text_styles(doc)
            await self._setup_drawing_resources() # Call to setup self.doc, self.msp, and configured layers

            # NEW ENTITY PROCESSING LOOP:
            # Replaces the call to _process_and_add_entities
            for layer_name, (layer_cfg, entity_iter) in entities_by_layer_config.items():
                if not layer_cfg.enabled:
                    self.logger.debug(f"Skipping disabled layer: {layer_cfg.name}")
                    continue

                self.logger.debug(f"Processing entities for layer: {layer_cfg.name}")
                async for entity_model in entity_iter:
                    await self._add_dxf_entity_to_msp(entity_model) # This uses self.doc and self.msp

            if self.config.audit_on_save:
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
        if not self.config.xdata_application_name:
            logger.warning("XDATA application name not configured. Cannot clear legend content by XDATA.")
            return

        entities_to_delete = []
        # Construct the expected prefix for XDATA legend item tags for this specific legend_id
        # This matches the prefixing strategy in LegendGenerationService
        expected_xdata_tag_prefix = f"legend_{legend_id}_"
        app_id = self.config.xdata_application_name

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
                'style': style_config.font or self.config.default_text_style_name,
                'char_height': style_config.height or self.config.default_text_height or 1.0,
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
            if legend_item_id and self.config.xdata_application_name:
                mtext_entity.set_xdata(self.config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])

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
            if legend_item_id and self.config.xdata_application_name:
                lwpolyline.set_xdata(self.config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
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

            # Set hatch style (Normal, Outer, Ignore)
            hatch_style_map = {
                'NORMAL': ezdxf_const.HATCH_STYLE_NORMAL,
                'OUTERMOST': ezdxf_const.HATCH_STYLE_OUTERMOST,
                'IGNORE': ezdxf_const.HATCH_STYLE_IGNORE,
            }
            hatch.dxf.hatch_style = hatch_style_map.get(hatch_props_config.style.upper(), ezdxf_const.HATCH_STYLE_NORMAL)

            hatch.dxf.associative = hatch_props_config.associative

            self._attach_writer_xdata(hatch)
            if legend_item_id and self.config.xdata_application_name:
                hatch.set_xdata(self.config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
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
            if legend_item_id and self.config.xdata_application_name:
                block_ref.set_xdata(self.config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
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
            if legend_item_id and self.config.xdata_application_name:
                line.set_xdata(self.config.xdata_application_name, [(1000, "legend_item"), (1000, legend_item_id)])
            return line
        except Exception as e:
            logger.error(f"Error adding LINE: {e}", exc_info=True)
            return None

    async def _setup_drawing_resources(self):
        """Setup resources like text styles, linetypes in the DXF document using StyleService."""
        if not self.doc:
            self.logger.error("DXF document not initialized for resource setup.")
            return

        self.logger.info("Setting up DXF document resources (text styles, linetypes)...")

        # Use StyleService to get all unique TextStylePropertiesConfig from all layer styles and presets
        all_text_styles_props: List[TextStylePropertiesConfig] = self.style_service.get_all_defined_text_style_properties()

        for ts_props in all_text_styles_props:
            style_name = ts_props.font_name_or_style_preset # This is the DXF text style name
            if style_name and style_name not in self.doc.styles:
                try:
                    # ezdxf uses font (filename like 'arial.ttf') for new styles, not abstract name like 'Arial' directly for definition
                    # TextStylePropertiesConfig.font field should ideally carry the TTF font name or path.
                    # For now, we assume font_name_or_style_preset *is* the font file if creating.
                    # This needs refinement based on how TextStylePropertiesConfig.font is populated.
                    # If font is just a name like "Arial", ezdxf needs a font mapping or it might not find it.
                    font_for_ezdxf = ts_props.font_filename or style_name # Prefer specific font_filename if available

                    self.doc.styles.new(
                        name=style_name,
                        dxfattribs={
                            'font': font_for_ezdxf, # This is the TTF name, e.g., 'arial.ttf'
                            'width': ts_props.width_factor if ts_props.width_factor is not None else 1.0, # ezdxf uses 'width' for width_factor
                            'oblique': ts_props.oblique_angle if ts_props.oblique_angle is not None else 0.0,
                            # height is not part of style, it's on TEXT/MTEXT entity
                        }
                    )
                    self.logger.info(f"Created TEXTSTYLE '{style_name}' with font '{font_for_ezdxf}'.")
                except Exception as e:
                    self.logger.error(f"Failed to create TEXTSTYLE '{style_name}' with font '{font_for_ezdxf}': {e}", exc_info=True)
            elif style_name in self.doc.styles:
                 self.logger.debug(f"TEXTSTYLE '{style_name}' already exists in document.")

        # Setup Linetypes (complex linetypes might need definition from .lin file or dict)
        all_linetypes_props: List[LayerDisplayPropertiesConfig] = self.style_service.get_all_defined_layer_display_properties()
        unique_linetypes = set()
        for ld_props in all_linetypes_props:
            if ld_props.linetype and ld_props.linetype.upper() not in ["BYLAYER", "BYBLOCK", "CONTINUOUS"]:
                unique_linetypes.add(ld_props.linetype)

        for lt_name in unique_linetypes:
            if lt_name not in self.doc.linetypes:
                # This only loads standard linetypes or those in acad.lin.
                # Complex linetypes from custom files need self.doc.linetypes.load_linetypes(filename)
                try:
                    self.doc.linetypes.add_simple_line_pattern(lt_name, [0.0]) # Placeholder, this doesn't really define it
                    self.logger.warning(f"Linetype '{lt_name}' not found. Added as a placeholder simple pattern. For complex linetypes, ensure they are defined in a loaded .lin file or standard set.")
                    # A better approach would be to load from a specified .lin file in config
                    # Or have detailed patterns in StyleService/schemas.
                except Exception as e:
                     self.logger.error(f"Failed to add placeholder for linetype '{lt_name}': {e}")

    async def _add_dxf_entity_to_msp(self, dxf_entity_model: AnyDxfEntity):
        """Adds a single DXF entity (from Pydantic model) to the modelspace."""
        if not self.msp:
            self.logger.error("Modelspace not available. Cannot add DXF entity.")
            return

        if isinstance(dxf_entity_model, DxfLWPolyline):
            await self._add_dxf_lwpolyline(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfMText):
            await self._add_dxf_mtext(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfHatch):
            await self._add_dxf_hatch(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfLine):
            await self._add_dxf_line(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfCircle):
            await self._add_dxf_circle(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfArc):
            await self._add_dxf_arc(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfPolyline): # Added DxfPolyline (heavy)
            await self._add_dxf_polyline(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfText): # Simple DxfText (less common than MText now)
            await self._add_dxf_text(dxf_entity_model)
        elif isinstance(dxf_entity_model, DxfInsert): # Block insertions
             await self._add_dxf_insert(dxf_entity_model)
        else:
            self.logger.warning(f"Unsupported DxfEntity model type for direct addition: {type(dxf_entity_model).__name__}. Skipping.")

    def _apply_common_dxf_attributes(self, ezdxf_entity, model: AnyDxfEntity):
        """Applies common DXF attributes from the Pydantic model to the ezdxf entity."""
        if model.layer: ezdxf_entity.dxf.layer = model.layer
        if model.color_256 is not None: ezdxf_entity.dxf.color = model.color_256
        if model.linetype: ezdxf_entity.dxf.linetype = model.linetype
        if model.lineweight is not None: ezdxf_entity.dxf.lineweight = model.lineweight # e.g. 25 for 0.25mm

        # True Color (RGB)
        if model.true_color:
            ezdxf_entity.rgb = model.true_color # Sets true color
            if model.color_256 is None: # If ACI not set, ensure ezdxf uses true color by default
                 ezdxf_entity.dxf.color = ezdxf.const.BYLAYER # Or some default that allows true_color to dominate if ACI is not specifically set.
                                                          # Often, setting rgb implies ACI might be ignored or set to BYLAYER/BYBLOCK.
                                                          # Test behavior with CAD.

        # Linetype Scale
        if model.linetype_scale is not None and model.linetype_scale > 0:
            ezdxf_entity.dxf.ltscale = model.linetype_scale

        # Transparency
        # ezdxf uses specific ways to set transparency, often via a "Transparency" object or direct alpha
        if model.explicit_transparency is not None:
            # For ezdxf, transparency is often 1.0 - alpha (0.0 = opaque, 1.0 = fully transparent in model)
            # ezdxf alpha is 0 = fully transparent, 255 = opaque.
            # So, transparency value needs conversion if model.explicit_transparency is 0-1 (0=opaque, 1=transparent)
            # If model.explicit_transparency is alpha (0=opaque, 1=transparent as per DXF spec for CEALPHA)

            # Assuming model.explicit_transparency is 0.0 (opaque) to 1.0 (fully transparent)
            # DXF Alpha (as used by ezdxf for entity.transparency) is integer 0 (fully transparent) to 255 (opaque)
            # Or it can be a specific DXF constant like ezdxf.const.TRANSPARENCY_BYLAYER
            # Let's map 0.0-1.0 (model) to 0-255 alpha for ezdxf, where 0.0 model = 255 ezdxf (opaque)

            # Correct mapping: alpha_ezdxf = (1.0 - model_transparency) * 255
            # Example: model_transparency = 0.0 (opaque) -> alpha_ezdxf = (1.0 - 0.0) * 255 = 255 (opaque)
            #          model_transparency = 1.0 (transparent) -> alpha_ezdxf = (1.0 - 1.0) * 255 = 0 (transparent)
            #          model_transparency = 0.5 (semi) -> alpha_ezdxf = (1.0 - 0.5) * 255 = 127.5 -> 127 or 128

            alpha_value_for_ezdxf = int((1.0 - model.explicit_transparency) * 255)
            alpha_value_for_ezdxf = max(0, min(255, alpha_value_for_ezdxf)) # Clamp

            try:
                ezdxf_entity.transparency = alpha_value_for_ezdxf # This sets entity transparency if supported by entity type
                self.logger.debug(f"Set entity transparency for {type(ezdxf_entity).__name__} to model val {model.explicit_transparency} (ezdxf alpha: {alpha_value_for_ezdxf})")
            except AttributeError:
                self.logger.warning(f"Entity type {type(ezdxf_entity).__name__} may not directly support .transparency attribute. Style via layer if needed.")
            except Exception as e:
                 self.logger.error(f"Error setting transparency for {type(ezdxf_entity).__name__}: {e}")


    async def _add_dxf_line(self, model: DxfLine):
        if not self.msp: return
        line = self.msp.add_line(
            start=(model.start.x, model.start.y, model.start.z or 0.0),
            end=(model.end.x, model.end.y, model.end.z or 0.0),
        )
        self._apply_common_dxf_attributes(line, model)
        self.logger.debug(f"Added DxfLine to layer {model.layer}")

    async def _add_dxf_lwpolyline(self, model: DxfLWPolyline):
        if not self.msp: return
        # For LWPOLYLINE, points are (x, y, [start_width, [end_width, [bulge]]])
        # Current DxfLWPolyline model.points are just Coordinates.
        # Assuming simple LWPOLYLINE without width/bulge for now. Z is ignored by LWPOLYLINE.
        points_xy = [(p.x, p.y) for p in model.points]
        if not points_xy:
            self.logger.warning(f"LWPolyline for layer {model.layer} has no points. Skipping.")
            return

        lwpolyline = self.msp.add_lwpolyline(
            points=points_xy,
            format='xy', # Explicitly stating format
            close=model.is_closed,
            dxfattribs=model.dxfattribs
        )
        self._apply_common_dxf_attributes(lwpolyline, model)
        self.logger.debug(f"Added DxfLWPolyline to layer {model.layer} with {len(points_xy)} points.")

    async def _add_dxf_polyline(self, model: DxfPolyline): # New method for DxfPolyline (heavy)
        if not self.msp:
            self.logger.error("Modelspace not available. Cannot add DxfPolyline.")
            return

        points_3d = [(p.x, p.y, p.z or 0.0) for p in model.points]
        if len(points_3d) < 2: # A polyline needs at least two points
            self.logger.warning(
                f"DxfPolyline for layer {model.layer or 'Default'} has insufficient points ({len(points_3d)}). Skipping."
            )
            return

        polyline = self.msp.add_polyline3d(
            points=points_3d,
            close=model.is_closed,
            # dxfattribs can be used for thickness, elevation if DxfPolyline model has them directly
            # and _apply_common_dxf_attributes doesn't cover them or needs specific handling for POLYLINE
        )
        self._apply_common_dxf_attributes(polyline, model)
        # Note: POLYLINE entity specific attributes like default start/end width, vertex-specific widths,
        # or curve-fit/spline-fit vertices are not handled by this basic implementation.
        self.logger.debug(f"Added DxfPolyline to layer {model.layer or 'Default'} with {len(points_3d)} points.")

    async def _add_dxf_circle(self, model: DxfCircle): # New method for DxfCircle
        if not self.msp:
            self.logger.error("Modelspace not available. Cannot add DxfCircle.")
            return

        center_3d = (model.center.x, model.center.y, model.center.z or 0.0)

        if model.radius <= 0:
            self.logger.warning(
                f"DxfCircle for layer {model.layer or 'Default'} has invalid radius ({model.radius}). Skipping."
            )
            return

        circle = self.msp.add_circle(
            center=center_3d,
            radius=model.radius,
        )
        self._apply_common_dxf_attributes(circle, model)
        # Note: CIRCLE thickness can be applied via common attributes if model.thickness is populated
        self.logger.debug(f"Added DxfCircle to layer {model.layer or 'Default'} with radius {model.radius}.")

    async def _add_dxf_arc(self, model: DxfArc): # New method for DxfArc
        if not self.msp:
            self.logger.error("Modelspace not available. Cannot add DxfArc.")
            return

        center_3d = (model.center.x, model.center.y, model.center.z or 0.0)

        if model.radius <= 0:
            self.logger.warning(
                f"DxfArc for layer {model.layer or 'Default'} has invalid radius ({model.radius}). Skipping."
            )
            return

        arc = self.msp.add_arc(
            center=center_3d,
            radius=model.radius,
            start_angle=model.start_angle,
            end_angle=model.end_angle,
        )
        self._apply_common_dxf_attributes(arc, model)
        # Note: ARC thickness can be applied via common attributes if model.thickness is populated
        self.logger.debug(f"Added DxfArc to layer {model.layer or 'Default'} with radius {model.radius}.")

    async def _add_dxf_mtext(self, model: DxfMText):
        if not self.msp: return
        mtext_attribs = {
            'char_height': model.char_height,
            'width': model.width if model.width is not None and model.width > 0 else None, # MTEXT width attribute
            'rotation': model.rotation or 0.0,
            'style': model.style or "Standard",
            'attachment_point': self._map_mtext_attachment_point(model.attachment_point),
            # Flow direction, line spacing style/factor are more complex, often embedded in MTEXT codes or require specific handling
        }
        # Filter out None values from mtext_attribs as ezdxf prefers missing keys over None for some defaults
        mtext_attribs = {k: v for k, v in mtext_attribs.items() if v is not None}

        # MTEXT content with potential formatting codes (from paragraph_props, etc.)
        # This part needs a robust MTEXT code generator based on TextStylePropertiesConfig.paragraph_props
        # For now, using model.text_content directly.
        final_text_content = model.text_content

        # Example: if model has paragraph properties leading to formatting codes
        # if model.paragraph_props and model.paragraph_props.alignment == 'CENTER':
        #     final_text_content = f"\\{{\\qc}}{final_text_content}" # Simplified example

        mtext = self.msp.add_mtext(
            text=final_text_content,
            dxfattribs=mtext_attribs
        )
        mtext.dxf.insert = (model.insertion_point.x, model.insertion_point.y, model.insertion_point.z or 0.0)

        # Apply common DXF attributes (layer, color, linetype, etc.)
        self._apply_common_dxf_attributes(mtext, model)

        # Background fill handling (if DxfMText model carries these from TextStylePropertiesConfig.bg_fill_properties)
        if model.bg_fill_enabled and hasattr(model, 'bg_fill_properties') and model.bg_fill_properties: # Assuming bg_fill_properties is on DxfMText model if needed
            bg_props = model.bg_fill_properties
            bg_fill_flags = ezdxf.const.MTEXT_BG_FILL
            if bg_props.use_drawing_bg_color:
                bg_fill_flags |= ezdxf.const.MTEXT_BG_COLOR_Window_BG

            bg_color_for_ezdxf = None
            if bg_props.color: # If a specific color is set for BG
                # Convert bg_props.color (ColorModel) to ACI or TrueColor for ezdxf
                # This assumes bg_props.color can be an ACI int, an RGB tuple, or a name string
                # This is a simplified example of color conversion here
                if isinstance(bg_props.color, int): # ACI
                    bg_color_for_ezdxf = bg_props.color
                elif isinstance(bg_props.color, tuple): # RGB
                     # ezdxf might need true color for BG fill differently, or it might pick up entity's true color.
                     # For now, let's assume if RGB, it might need to be entity's main true_color if not ACI.
                     # This is complex. CAD behavior for BG fill color (ACI vs RGB) needs checking.
                     # Setting specific BG color might override main entity color for the BG box.
                     # Most robust: use ACI if available.
                     pass # RGB for BG fill needs careful mapping to ezdxf
                elif isinstance(bg_props.color, str):
                    # Try to convert named color to ACI or use default
                    pass

            mtext.set_bg_fill(
                color=bg_color_for_ezdxf, # ezdxf color index or None for default (often window bg or black/white)
                scale=bg_props.scale_factor if bg_props.scale_factor else 1.5, # Default border offset factor
                flags=bg_fill_flags,
                # ezdxf fill_true_color for specific RGB bg color,
                # fill_transparency for bg transparency
            )
            self.logger.debug(f"Applied background fill to MTEXT on layer {model.layer}")

        self.logger.debug(f"Added DxfMText to layer {model.layer}: '{model.text_content[:30]}...'")

    def _map_mtext_attachment_point(self, model_ap: Optional[str]) -> Optional[int]:
        if not model_ap: return None
        mapping = {
            'TOP_LEFT': ezdxf.const.MTEXT_TOP_LEFT, 'TOP_CENTER': ezdxf.const.MTEXT_TOP_CENTER, 'TOP_RIGHT': ezdxf.const.MTEXT_TOP_RIGHT,
            'MIDDLE_LEFT': ezdxf.const.MTEXT_MIDDLE_LEFT, 'MIDDLE_CENTER': ezdxf.const.MTEXT_MIDDLE_CENTER, 'MIDDLE_RIGHT': ezdxf.const.MTEXT_MIDDLE_RIGHT,
            'BOTTOM_LEFT': ezdxf.const.MTEXT_BOTTOM_LEFT, 'BOTTOM_CENTER': ezdxf.const.MTEXT_BOTTOM_CENTER, 'BOTTOM_RIGHT': ezdxf.const.MTEXT_BOTTOM_RIGHT,
        }
        return mapping.get(model_ap.upper())

    async def _add_dxf_text(self, model: DxfText): # For simple TEXT entities
        if not self.msp: return
        text_attribs = {
            'height': model.height,
            'rotation': model.rotation or 0.0,
            'style': model.style or "Standard",
            # halign, valign from model if DxfText model includes them
        }
        # Filter Nones
        text_attribs = {k:v for k,v in text_attribs.items() if v is not None}

        text_entity = self.msp.add_text(
            text=model.text_content,
            dxfattribs=text_attribs
        )
        text_entity.dxf.insert = (model.insertion_point.x, model.insertion_point.y, model.insertion_point.z or 0.0)
        self._apply_common_dxf_attributes(text_entity, model)
        self.logger.debug(f"Added DxfText to layer {model.layer}: '{model.text_content[:30]}...'")


    async def _add_dxf_insert(self, model: DxfInsert):
        if not self.msp: return
        # Ensure block definition exists, or ezdxf will error.
        # StyleService could potentially be used to check/create block defs if they were also part of style config.
        # For now, assume block definition exists in the template or is pre-created.
        if model.block_name not in self.doc.blocks:
            self.logger.error(f"Block definition '{model.block_name}' not found in DXF document. Cannot add INSERT entity for layer '{model.layer}'.")
            # Optionally, create a placeholder block:
            # self.doc.blocks.new(name=model.block_name)
            # self.logger.warning(f"Created placeholder empty block definition for '{model.block_name}'.")
            return

        insert_attribs = {
            'name': model.block_name,
            'insert': (model.insertion_point.x, model.insertion_point.y, model.insertion_point.z or 0.0),
            'xscale': model.x_scale,
            'yscale': model.y_scale,
            'zscale': model.z_scale,
            'rotation': model.rotation,
            # columns, rows, col_spacing, row_spacing for MINSERT if DxfInsert model supports them
        }
        # Filter Nones
        insert_attribs = {k:v for k,v in insert_attribs.items() if v is not None}

        insert = self.msp.add_blockref(**insert_attribs)
        self._apply_common_dxf_attributes(insert, model) # Applies layer, color, etc. to the INSERT entity

        # If model.attributes (list of DxfAttribute models) exists, create and attach attributes here
        # for attrib_model in model.attributes:
        #     insert.add_attrib(tag=attrib_model.tag, text=attrib_model.text_content, ...)
        #     # Style attributes if DxfAttribute model has style fields

        self.logger.debug(f"Added DxfInsert (block '{model.block_name}') to layer {model.layer}")

    # ... (keep _convert_color_model_to_aci, _create_layers_from_config, _ensure_layer_exists, _process_features_by_layer as is, unless StyleService impacts them)
    # _convert_color_model_to_aci might become less critical if GeometryTransformerImpl provides resolved ACI/RGB on DxfEntity models.
    # However, it might still be useful for layer color definitions.

    # Update _create_layers_from_config to potentially use StyleService for default layer properties if LayerConfig is minimal
    async def _create_layers_from_config(self):
        # ... (existing layer creation logic) ...
        # If LayerConfig only has name, style_preset_name, StyleService could provide defaults.
        # For now, assume LayerConfig is comprehensive enough or ezdxf defaults are fine.
        pass # No change from previous plan here for now. StyleService is mainly for entities.

    # _ensure_layer_exists might also use StyleService if layer props beyond name/color need setup from style preset.
    def _ensure_layer_exists(self, layer_name: str, dxf_attribs: Optional[Dict[str, Any]] = None):
        # ... (existing logic) ...
        # If dxf_attribs are not provided, and we want to style layer from a preset via StyleService:
        # if not dxf_attribs and self.style_service:
        #     # This needs a way to map a layer_name to a potential StyleObjectConfig in StyleService
        #     # (e.g. if LayerConfig had a style_preset_name, get that preset's layer_props)
        #     pass
        if layer_name not in self.doc.layers:
            # ... create layer ...
            # Apply detailed props if available (color, linetype, lineweight, transparency)
            # from a StyleObjectConfig.layer_props associated with this layer_name.
            # This is where StyleService could help define layers more richly if not just by name.
            pass # No change from previous plan here for now.

    async def _process_and_add_entities(self, doc, msp, entities_by_layer_config):
        # This method is effectively replaced by _add_dxf_entity_to_msp and its helpers.
        # The loop in write_features now calls _add_dxf_entity_to_msp.
        # If _process_and_add_entities still exists, it should be removed or refactored
        # to delegate to _add_dxf_entity_to_msp.
        # Given the new structure, it's cleaner to remove/replace it.
        # If _map_feature_to_dxf_attributes existed, it's also largely superseded by
        # GeometryTransformerImpl populating DxfEntity models and _apply_common_dxf_attributes here.
        pass
