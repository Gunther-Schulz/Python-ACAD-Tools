from logging import Logger
from ezdxf.document import Drawing
from ezdxf.entities import Textstyle
from typing import Optional

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
        # Determine the font string to use for DXF STYLE entry or comparison
        font_for_dxf_style: Optional[str] = None
        if text_props.resolved_font_filename:
            font_for_dxf_style = text_props.resolved_font_filename
        elif text_props.font_name_or_style_preset:
            # Use font_name_or_style_preset if no specific file was resolved.
            # This could be "Arial.ttf" (if font provider was configured but didn't find it, though unlikely here)
            # or a generic name like "TXT" or "SIMPLEX" or the style_name itself like "StandardLegend"
            font_for_dxf_style = text_props.font_name_or_style_preset
        # If both are None, font_for_dxf_style remains None, ezdxf will use its default (e.g., TXT.shx)

        log_prefix = f"DXF STYLE '{style_name}': "

        if doc.styles.has_entry(style_name):
            existing_style: Textstyle = doc.styles.get(style_name)
            # Compare with the determined font_for_dxf_style
            # If font_for_dxf_style is None, means we intend to use ezdxf default.
            # If existing_style.dxf.font is also a default (e.g. "txt"), consider them compatible.
            existing_font_lower = existing_style.dxf.font.lower() if existing_style.dxf.font else ""
            desired_font_lower = font_for_dxf_style.lower() if font_for_dxf_style else ""

            if font_for_dxf_style is None and existing_style.dxf.font: # We want default, but existing has specific font
                 self.logger.debug(
                    f"{log_prefix}Already exists with font '{existing_style.dxf.font}'. Desired: ezdxf default. Assuming compatible."
                ) # Or, could warn if strict matching of "no font" is needed. For now, accept.
                 return
            elif font_for_dxf_style and existing_font_lower == desired_font_lower:
                self.logger.debug(
                    f"{log_prefix}Already exists in DXF with the same font '{font_for_dxf_style}'. Skipping creation."
                )
                return
            elif font_for_dxf_style is None and not existing_style.dxf.font: # Both intend default
                self.logger.debug(
                    f"{log_prefix}Already exists and uses ezdxf default font. Desired: ezdxf default. Skipping creation."
                )
                return
            else: # Fonts differ, or one specifies and other is default
                self.logger.warning(
                    f"{log_prefix}Already exists in DXF but with a DIFFERENT font setup "
                    f"(Existing: '{existing_style.dxf.font}', Desired: '{font_for_dxf_style}'). "
                    f"The existing style will NOT be overwritten."
                )
                return

        log_msg_font_part = f"using font '{font_for_dxf_style}'" if font_for_dxf_style else "using ezdxf default font"
        self.logger.info(f"{log_prefix}Creating new entry {log_msg_font_part}.")

        dxfattribs = {}
        if font_for_dxf_style: # Only set dxf.font if we have one, otherwise ezdxf handles default
            dxfattribs["font"] = font_for_dxf_style

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
