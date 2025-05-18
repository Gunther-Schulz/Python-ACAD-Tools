from logging import Logger
from ezdxf.document import Drawing
from ezdxf.entities import Textstyle

from dxfplanner.config.style_schemas import TextStylePropertiesConfig

class DxfStyleDefinitionServiceError(Exception):
    """Custom exception for DxfStyleDefinitionService errors."""
    pass

class DxfStyleDefinitionService:
    """
    Service responsible for creating and managing STYLE table entries in an ezdxf document
    based on resolved TextStylePropertiesConfig objects.
    """

    def __init__(self, logger: Logger):
        self.logger = logger

    def ensure_text_style_in_dxf(
        self,
        doc: Drawing,
        style_name: str,
        text_props: TextStylePropertiesConfig
    ) -> None:
        """
        Ensures that a DXF STYLE table entry exists for the given style name and properties.
        If the style exists with the same font, it does nothing.
        If it exists with a different font, it logs a warning.
        If it does not exist, it creates it.

        Args:
            doc: The ezdxf Drawing document.
            style_name: The name of the STYLE entry (e.g., "StandardLegend").
            text_props: The resolved text style properties.
        """
        font_to_use = text_props.resolved_font_filename
        log_prefix = f"DXF STYLE '{style_name}': "

        if not font_to_use:
            self.logger.warning(
                f"{log_prefix}Cannot create. No font file was resolved in text_props. "
                f"Input text_props.font_name_or_style_preset was '{text_props.font_name_or_style_preset}'."
            )
            return

        if doc.styles.has_entry(style_name):
            existing_style: Textstyle = doc.styles.get(style_name)
            if existing_style.dxf.font.lower() == font_to_use.lower():
                self.logger.debug(
                    f"{log_prefix}Already exists in DXF with the same font '{font_to_use}'. Skipping creation."
                )
                return
            else:
                self.logger.warning(
                    f"{log_prefix}Already exists in DXF but with a DIFFERENT font "
                    f"('{existing_style.dxf.font}' vs desired '{font_to_use}'). "
                    f"The existing style will NOT be overwritten."
                )
                return

        self.logger.info(f"{log_prefix}Creating new entry using font '{font_to_use}'.")

        dxfattribs = {"font": font_to_use}

        # Standard practice is often height=0.0 in STYLE, actual height on TEXT entity.
        # If text_props.height is consistently set for specific STYLEs, this can be re-evaluated.
        dxfattribs["height"] = 0.0

        if text_props.width_factor is not None:
            dxfattribs["width"] = text_props.width_factor

        if text_props.oblique_angle is not None: # degrees
            dxfattribs["oblique"] = text_props.oblique_angle

        try:
            doc.styles.new(name=style_name, dxfattribs=dxfattribs)
            self.logger.info(f"{log_prefix}Successfully created with attributes: {dxfattribs}")
        except Exception as e:
            self.logger.error(f"{log_prefix}Failed to create STYLE entry in DXF. Error: {e}. Attributes: {dxfattribs}")
            # Optionally, raise a DxfStyleDefinitionServiceError(e)
