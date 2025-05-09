from typing import AsyncIterator, Optional, List, Any, Dict, Tuple
from pathlib import Path

import ezdxf
from ezdxf.enums import InsertUnits # For setting drawing units
from ezdxf import colors as ezdxf_colors # For ACI color handling
from ezdxf import const as ezdxf_const # For MTEXT constants

from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfLayer, # DxfLayer might not be used directly if layers are from AppConfig
    DxfLine, DxfLWPolyline, DxfText, DxfMText, # Added DxfMText
    AnyDxfEntity, Coordinate
)
from dxfplanner.domain.interfaces import IDxfWriter, AnyStrPath
from dxfplanner.core.exceptions import DxfWriteError
from dxfplanner.config.schemas import AppConfig, ColorModel, LayerDisplayPropertiesConfig, TextStylePropertiesConfig # Added TextStylePropertiesConfig
from dxfplanner.services.style_service import StyleService, StyleObjectConfig # For resolving layer styles
from dxfplanner.core.logging_config import get_logger

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

    async def write_drawing(
        self,
        file_path: AnyStrPath,
        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]],
        **kwargs: Any
    ) -> None:
        """
        Writes DXF entities to a specified file path.
        Entities are grouped by their source LayerConfig for styling.
        """
        p_file_path = Path(file_path)
        if not p_file_path.suffix.lower() == ".dxf":
            raise DxfWriteError(f"Output file path must have a .dxf extension: {p_file_path}")

        try:
            doc = ezdxf.new(dxfversion=self._writer_config.target_dxf_version)
            msp = doc.modelspace()

            # Setup document properties and text styles
            self._setup_document_properties(doc)
            self._create_text_styles(doc)

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

                    if isinstance(entity_model, DxfLine):
                        dxf_entity = msp.add_line(
                            start=entity_model.start.to_tuple(),
                            end=entity_model.end.to_tuple(),
                            dxfattribs=entity_dxf_attribs
                        )
                        self._attach_writer_xdata(dxf_entity)
                    elif isinstance(entity_model, DxfLWPolyline):
                        # ezdxf LWPOLYLINE points are (x, y, [start_width, [end_width, [bulge]]])
                        # Our Coordinate model is (x,y,z). For now, just use x,y.
                        points = [(c.x, c.y) for c in entity_model.points]
                        dxf_entity = msp.add_lwpolyline(
                            points=points,
                            format='xy', # explicit for clarity
                            close=entity_model.is_closed,
                            dxfattribs=entity_dxf_attribs
                        )
                        self._attach_writer_xdata(dxf_entity)
                    elif isinstance(entity_model, DxfText):
                        # Basic text support. Style resolution and MTEXT will be more complex.
                        if hasattr(entity_model, 'style') and entity_model.style:
                             entity_dxf_attribs['style'] = entity_model.style
                        else: # Default to configured default style name
                             entity_dxf_attribs['style'] = self._writer_config.default_text_style_name

                        dxf_text_entity = msp.add_text(
                            text=entity_model.text_content,
                            height=entity_model.height,
                            dxfattribs=entity_dxf_attribs
                        )
                        # Ensure placement is set for TEXT, especially if alignment is involved
                        # DxfText model currently has rotation, but ezdxf add_text takes it in dxfattribs.
                        # For simplicity, current DxfText model has rotation, style. Writer uses them.
                        # Actual alignment (halign, valign) would need more fields in DxfText and mapping here.
                        dxf_text_entity.set_placement(
                            insert=entity_model.insertion_point.to_tuple(),
                            align=ezdxf_const.TEXT_ALIGN_LEFT # Defaulting, make configurable/part of DxfText model
                        )
                        if entity_model.rotation is not None and entity_model.rotation != 0.0 : # TEXT rotation
                            dxf_text_entity.dxf.rotation = entity_model.rotation

                        self._attach_writer_xdata(dxf_text_entity)
                    elif isinstance(entity_model, DxfMText):
                        mtext_attribs = entity_dxf_attribs.copy() # Start with generic entity attribs (layer, color)

                        mtext_attribs['insert'] = entity_model.insertion_point.to_tuple()
                        mtext_attribs['char_height'] = entity_model.char_height

                        if entity_model.style:
                            mtext_attribs['style'] = entity_model.style
                        else:
                            mtext_attribs['style'] = self._writer_config.default_text_style_name

                        if entity_model.width is not None: # MTEXT width of text box
                            mtext_attribs['width'] = entity_model.width
                        if entity_model.rotation is not None: # MTEXT rotation
                            mtext_attribs['rotation'] = entity_model.rotation

                        # Attachment point mapping
                        if entity_model.attachment_point:
                            ap_map = {
                                'TOP_LEFT': ezdxf_const.MTEXT_TOP_LEFT, 'TOP_CENTER': ezdxf_const.MTEXT_TOP_CENTER, 'TOP_RIGHT': ezdxf_const.MTEXT_TOP_RIGHT,
                                'MIDDLE_LEFT': ezdxf_const.MTEXT_MIDDLE_LEFT, 'MIDDLE_CENTER': ezdxf_const.MTEXT_MIDDLE_CENTER, 'MIDDLE_RIGHT': ezdxf_const.MTEXT_MIDDLE_RIGHT,
                                'BOTTOM_LEFT': ezdxf_const.MTEXT_BOTTOM_LEFT, 'BOTTOM_CENTER': ezdxf_const.MTEXT_BOTTOM_CENTER, 'BOTTOM_RIGHT': ezdxf_const.MTEXT_BOTTOM_RIGHT,
                            }
                            mtext_attribs['attachment_point'] = ap_map.get(entity_model.attachment_point)

                        # Flow direction mapping
                        if entity_model.flow_direction:
                            fd_map = {
                                'LEFT_TO_RIGHT': ezdxf_const.MTEXT_LEFT_TO_RIGHT,
                                'TOP_TO_BOTTOM': ezdxf_const.MTEXT_TOP_TO_BOTTOM,
                                'BY_STYLE': ezdxf_const.MTEXT_BY_STYLE
                            }
                            mtext_attribs['flow_direction'] = fd_map.get(entity_model.flow_direction)

                        # Line spacing style mapping
                        if entity_model.line_spacing_style:
                            lss_map = {
                                'AT_LEAST': ezdxf_const.MTEXT_AT_LEAST,
                                'EXACT': ezdxf_const.MTEXT_EXACT
                            }
                            mtext_attribs['line_spacing_style'] = lss_map.get(entity_model.line_spacing_style)

                        if entity_model.line_spacing_factor is not None:
                            mtext_attribs['line_spacing_factor'] = entity_model.line_spacing_factor

                        # Background fill - simple boolean for now
                        if entity_model.bg_fill_enabled is not None:
                            mtext_attribs['bg_fill'] = entity_model.bg_fill_enabled
                            if entity_model.bg_fill_enabled:
                                # By default, ezdxf uses current drawing background color for MASK
                                # and specific color for BG_FILL (non-mask).
                                # More complex bg color/scale/transparency can be added if DxfMText model supports it.
                                pass


                        dxf_mtext_entity = msp.add_mtext(text=entity_model.text_content, dxfattribs=mtext_attribs)
                        self._attach_writer_xdata(dxf_mtext_entity)
                    # Add other entity types (DxfCircle, DxfArc, DxfInsert) here
                    else:
                        logger.warning(f"Unsupported DxfEntity type: {type(entity_model)}. Skipping.")

            if self._writer_config.audit_on_save:
                try:
                    logger.debug("Performing DXF document audit before saving.")
                    doc.audit() # Audit the document
                except Exception as e:
                    logger.warning(f"Error during DXF document audit: {e}", exc_info=True)

            doc.saveas(p_file_path)
            logger.info(f"DXF file successfully written to: {p_file_path}")

        except ezdxf.DXFError as e:
            logger.error(f"ezdxf library error while writing to {p_file_path}: {e}", exc_info=True)
            raise DxfWriteError(f"ezdxf library error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error writing DXF file {p_file_path}: {e}", exc_info=True)
            raise DxfWriteError(f"Unexpected error writing DXF: {e}")
