from typing import Optional, List
from ezdxf.document import Drawing

from ..interfaces.dxf_resource_manager_interface import IDXFResourceManager
from ..interfaces.dxf_adapter_interface import IDXFAdapter
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.style_models import LayerStyleProperties, TextStyleProperties
from ..domain.exceptions import DXFProcessingError


class DXFResourceManagerService(IDXFResourceManager):
    """
    Service for managing DXF resources like linetypes and text styles
    within a DXF document, using an IDXFAdapter.
    """

    def __init__(
        self,
        dxf_adapter: IDXFAdapter,
        logger_service: ILoggingService,
    ):
        self._dxf_adapter = dxf_adapter
        self._logger = logger_service.get_logger(__name__)

    def ensure_linetype(
        self,
        drawing: Drawing,
        layer_props: Optional[LayerStyleProperties]
    ) -> None:
        if layer_props is None or layer_props.linetype is None:
            return

        linetype_name = layer_props.linetype
        if not linetype_name.strip():
            self._logger.warning(f"Linetype name '{linetype_name}' is invalid or effectively empty. Skipping.")
            return

        if linetype_name.upper() in ["BYLAYER", "BYBLOCK", "CONTINUOUS"]:
            return # These are standard and assumed to exist

        pattern_to_use: Optional[List[float]] = None
        description_to_use: str = f"Linetype {linetype_name}"

        if layer_props.linetype_pattern is not None:
            if isinstance(layer_props.linetype_pattern, list) and layer_props.linetype_pattern:  # Pattern is a non-empty list
                pattern_to_use = layer_props.linetype_pattern
                description_to_use = f"Custom linetype {linetype_name} from style pattern"
                self._logger.debug(f"Using linetype pattern for '{linetype_name}' from style definition.")
            else:  # Pattern is not a list or is an empty list
                self._logger.warning(
                    f"Linetype pattern for '{linetype_name}' is invalid (not a list or empty). "
                    "Proceeding with default/common linetype logic."
                )
                # pattern_to_use remains None, will trigger block below

        if pattern_to_use is None:  # Only if no valid custom pattern was found
            common_linetypes = {
                "DASHED": {"pattern": [1.2, -0.7], "description": "Dashed ----"},
                "DOTTED": {"pattern": [0.0, -0.2], "description": "Dotted . . ."},
                "DASHDOT": {"pattern": [1.0, -0.25, 0.0, -0.25], "description": "Dash dot --- . ---"},
                "CENTER": {"pattern": [1.25, -0.25, 0.25, -0.25], "description": "Center ____ _ ____"},
                "PHANTOM": {"pattern": [1.25, -0.25, 0.25, -0.25, 0.25, -0.25], "description": "Phantom ____ __ ____"}
            }
            if linetype_name.upper() in common_linetypes:
                linetype_def = common_linetypes[linetype_name.upper()]
                pattern_to_use = linetype_def["pattern"]
                description_to_use = linetype_def["description"]
                self._logger.debug(f"Using common linetype pattern for '{linetype_name}'.")
            else:
                self._logger.warning(f"Linetype '{linetype_name}' is not a predefined common type and has no pattern in style. Creating with a default dashed pattern.")
                pattern_to_use = [1.0, -0.5]  # Default pattern
                description_to_use = f"Custom linetype {linetype_name} (defaulted pattern)"

        if pattern_to_use is not None:
            try:
                self._dxf_adapter.create_linetype(
                    doc=drawing,
                    ltype_name=linetype_name,
                    pattern=pattern_to_use,
                    description=description_to_use
                )
                self._logger.info(f"Ensured/Created linetype '{linetype_name}' in DXF via adapter.")
            except DXFProcessingError as e:
                self._logger.error(f"Adapter failed to create/ensure linetype '{linetype_name}': {e}", exc_info=True)
            except Exception as e: # Broader catch for unexpected adapter issues
                self._logger.error(f"Unexpected error creating linetype '{linetype_name}' via adapter: {e}", exc_info=True)


    def ensure_text_style(
        self,
        drawing: Drawing,
        text_props: Optional[TextStyleProperties]
    ) -> Optional[str]:
        if text_props is None or text_props.font is None:
            return None

        font_face_name = text_props.font
        # Style name generation logic moved from StyleApplicatorService._ensure_dxf_text_style
        style_name_candidate = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in font_face_name)

        # MODIFIED: Check if original font_face_name was empty/whitespace, or if derived candidate is problematic
        if not font_face_name.strip() or not style_name_candidate.strip() or style_name_candidate.lower() == "none":
            self._logger.warning(f"Cannot derive a valid style name from font: '{font_face_name}'. Using default style.")
            return None

        style_name = f"Style_{style_name_candidate}"

        self._logger.debug(f"Ensuring text style '{style_name}' for font '{font_face_name}' via adapter.")
        try:
            self._dxf_adapter.create_text_style(
                doc=drawing,
                style_name=style_name,
                font_name=font_face_name
            )
            self._logger.info(f"Ensured/Created text style '{style_name}' for font '{font_face_name}' via adapter.")
            return style_name
        except DXFProcessingError as e:
            self._logger.error(f"Adapter failed to create text style '{style_name}' for font '{font_face_name}': {e}", exc_info=True)
            return None
        except Exception as e: # Broader catch
            self._logger.error(f"Unexpected error creating text style '{style_name}' for '{font_face_name}': {e}", exc_info=True)
            return None
