from typing import Protocol, Optional, List

# Forward reference for ezdxf.document.Drawing to avoid direct import in interface if not desired
# Or import directly if that's the project convention for interfaces needing external types.
from ezdxf.document import Drawing

from ..domain.style_models import LayerStyleProperties, TextStyleProperties


class IDXFResourceManager(Protocol):
    """
    Interface for services that manage DXF resources like linetypes and text styles
    within a DXF document.
    """

    def ensure_linetype(
        self,
        drawing: Drawing,
        layer_props: Optional[LayerStyleProperties]
    ) -> None:
        """
        Ensures that a linetype specified in LayerStyleProperties exists in the DXF drawing.
        If the linetype is not a standard one (BYLAYER, BYBLOCK, CONTINUOUS) and does not exist,
        it attempts to create it based on patterns defined in LayerStyleProperties or common defaults.

        Args:
            drawing: The ezdxf Drawing object.
            layer_props: LayerStyleProperties containing linetype name and optional pattern.
                         If None or linetype is None, the method does nothing.
        """
        ...

    def ensure_text_style(
        self,
        drawing: Drawing,
        text_props: Optional[TextStyleProperties]
    ) -> Optional[str]:
        """
        Ensures that a text style corresponding to the font in TextStyleProperties exists
        in the DXF drawing. If it doesn't exist, it attempts to create it.

        Args:
            drawing: The ezdxf Drawing object.
            text_props: TextStyleProperties containing the font information.
                        If None or font is None, the method does nothing and returns None.

        Returns:
            The name of the ensured/created DXF text style if successful, otherwise None.
        """
        ...
