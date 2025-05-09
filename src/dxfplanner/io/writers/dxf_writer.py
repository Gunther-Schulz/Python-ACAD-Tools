from typing import AsyncIterator, Optional, List, Any, Dict, Tuple
from pathlib import Path

import ezdxf
from ezdxf.enums import InsertUnits # For setting drawing units
from ezdxf import colors as ezdxf_colors # For ACI color handling

from dxfplanner.domain.models.dxf_models import (
    DxfEntity, DxfLayer, # DxfLayer might not be used directly if layers are from AppConfig
    DxfLine, DxfLWPolyline, DxfText, # Add other entities as supported
    AnyDxfEntity, Coordinate
)
from dxfplanner.domain.interfaces import IDxfWriter, AnyStrPath
from dxfplanner.core.exceptions import DxfWriteError
from dxfplanner.config.schemas import AppConfig, ColorModel, LayerDisplayPropertiesConfig # DxfWriterConfig is AppConfig.io.writers.dxf
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

            # TODO: Set up units from config, e.g., self._writer_config.drawing_units
            doc.header['$INSUNITS'] = InsertUnits.Millimeters # Default for now

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
                        msp.add_line(
                            start=entity_model.start.to_tuple(),
                            end=entity_model.end.to_tuple(),
                            dxfattribs=entity_dxf_attribs
                        )
                    elif isinstance(entity_model, DxfLWPolyline):
                        # ezdxf LWPOLYLINE points are (x, y, [start_width, [end_width, [bulge]]])
                        # Our Coordinate model is (x,y,z). For now, just use x,y.
                        points = [(c.x, c.y) for c in entity_model.points]
                        msp.add_lwpolyline(
                            points=points,
                            format='xy', # explicit for clarity
                            close=entity_model.is_closed,
                            dxfattribs=entity_dxf_attribs
                        )
                    elif isinstance(entity_model, DxfText):
                        # Basic text support. Style resolution and MTEXT will be more complex.
                        if hasattr(entity_model, 'style') and entity_model.style:
                             entity_dxf_attribs['style'] = entity_model.style
                        else: # Default to "Standard" or make configurable
                             entity_dxf_attribs['style'] = "Standard"
                        msp.add_text(
                            text=entity_model.text_content,
                            height=entity_model.height,
                            dxfattribs=entity_dxf_attribs
                        ).set_placement(
                            insert=entity_model.insertion_point.to_tuple()
                            # TODO: alignment, rotation from DxfText model if added
                        )
                    # Add other entity types (DxfMText, DxfCircle, DxfArc, DxfInsert) here
                    else:
                        logger.warning(f"Unsupported DxfEntity type: {type(entity_model)}. Skipping.")

            doc.saveas(p_file_path)
            logger.info(f"DXF file successfully written to: {p_file_path}")

        except ezdxf.DXFError as e:
            logger.error(f"ezdxf library error while writing to {p_file_path}: {e}", exc_info=True)
            raise DxfWriteError(f"ezdxf library error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error writing DXF file {p_file_path}: {e}", exc_info=True)
            raise DxfWriteError(f"Unexpected error writing DXF: {e}")
