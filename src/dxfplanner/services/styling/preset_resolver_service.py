from typing import Optional
from logging import Logger
# import logging # Remove import for standard logger

from dxfplanner.config.schemas import ProjectConfig, StyleObjectConfig
from dxfplanner.services.styling.styling_utils import merge_style_components

# # Temporary logger for debugging this specific issue
# TEMP_DEBUG_LOGGER = logging.getLogger("PresetResolverService_DEBUG")
# TEMP_DEBUG_LOGGER.setLevel(logging.DEBUG)
# if not TEMP_DEBUG_LOGGER.hasHandlers():
#     handler = logging.StreamHandler()
#     formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
#     handler.setFormatter(formatter)
#     TEMP_DEBUG_LOGGER.addHandler(handler)

class PresetResolverServiceError(Exception):
    """Custom exception for PresetResolverService errors."""
    pass

class PresetResolverService:
    """
    Service responsible for resolving style presets and merging them with inline definitions.
    """
    def __init__(self, project_config: ProjectConfig, logger: Logger):
        self.project_config = project_config
        self.logger = logger
        # self.debug_logger = TEMP_DEBUG_LOGGER # Remove temp logger

    def resolve_preset_and_inline(
        self,
        preset_name: Optional[str],
        inline_definition: Optional[StyleObjectConfig],
        context_name: Optional[str] = "UnknownContext"
    ) -> StyleObjectConfig:
        """
        Resolves a style by potentially fetching a preset and merging it with an inline definition.

        Args:
            preset_name: The name of the style preset to fetch from project_config.
            inline_definition: An inline StyleObjectConfig to be merged.
            context_name: A descriptive name for the context this style is being resolved for (for logging).

        Returns:
            A resolved StyleObjectConfig. If no preset is found and no inline definition
            is provided, a default (empty) StyleObjectConfig is returned.
        """
        log_prefix = f"PresetResolver for '{context_name}': "
        base_from_preset: Optional[StyleObjectConfig] = None

        if preset_name:
            preset = self.project_config.style_presets.get(preset_name)
            if preset:
                base_from_preset = preset
                self.logger.debug(f"{log_prefix}Found preset '{preset_name}'.")
            else:
                self.logger.warning(f"{log_prefix}Style preset '{preset_name}' not found.")

        resolved_style = merge_style_components(
            model_cls=StyleObjectConfig,
            base=base_from_preset,
            override=inline_definition
        )

        # Original detailed logging (can be restored if needed, or simplified further)
        if not preset_name and not inline_definition:
            self.logger.debug(f"{log_prefix}No preset name or inline definition provided. Resolved: {resolved_style.model_dump_json(indent=2)}")
        elif preset_name and not base_from_preset and not inline_definition:
            self.logger.debug(f"{log_prefix}Preset '{preset_name}' not found, and no inline definition. Resolved: {resolved_style.model_dump_json(indent=2)}")
        elif preset_name and not base_from_preset and inline_definition:
            self.logger.debug(f"{log_prefix}Preset '{preset_name}' not found. Using only inline. Resolved: {resolved_style.model_dump_json(indent=2)}")
        elif preset_name and base_from_preset and not inline_definition:
             self.logger.debug(f"{log_prefix}Using preset '{preset_name}' as is. Resolved: {resolved_style.model_dump_json(indent=2)}")
        elif preset_name and base_from_preset and inline_definition:
            self.logger.debug(f"{log_prefix}Merged preset '{preset_name}' with inline. Resolved: {resolved_style.model_dump_json(indent=2)}")
        elif not preset_name and inline_definition:
            self.logger.debug(f"{log_prefix}No preset name. Using only inline. Resolved: {resolved_style.model_dump_json(indent=2)}")

        return resolved_style
