"""Interface for configuration loading services."""
from typing import Protocol, Optional, Dict, List

from ..domain.config_models import (
    StyleConfig,
    ColorConfig, # Assuming aci_colors.yaml loads into a list represented by ColorConfig.colors
    SpecificProjectConfig,
    GlobalProjectSettings,
    AppConfig, # AppConfig might be loaded initially, or parts of it.
    AciColorMappingItem  # Added for get_aci_color_mappings method
)
from ..domain.exceptions import ConfigError


class IConfigLoader(Protocol):
    """Interface for loading various application and project configurations."""

    def get_app_config(self) -> AppConfig:
        """
        Loads the core application configuration (e.g., from .env, global defaults).
        Raises: ConfigError if loading fails.
        """
        ...

    def load_global_styles(self, styles_file_path: str) -> StyleConfig:
        """
        Loads the global styles configuration (e.g., styles.yaml).
        Args:
            styles_file_path: Path to the global styles YAML file.
        Returns:
            A StyleConfig object.
        Raises:
            ConfigError: If the style configuration cannot be loaded or parsed.
        """
        ...

    def load_aci_colors(self, aci_colors_file_path: str) -> ColorConfig:
        """
        Loads the ACI color mappings (e.g., aci_colors.yaml).
        Args:
            aci_colors_file_path: Path to the ACI colors YAML file.
        Returns:
            A ColorConfig object containing the list of ACI color mappings.
        Raises:
            ConfigError: If the color configuration cannot be loaded or parsed.
        """
        ...

    def get_aci_color_mappings(self) -> List[AciColorMappingItem]:
        """
        Gets ACI color mappings, loading them if not already cached.
        Returns:
            A list of AciColorMappingItem objects.
        Raises:
            ConfigError: If the color mappings cannot be loaded.
        """
        ...

    def load_global_project_settings(self, global_projects_file_path: str) -> GlobalProjectSettings:
        """
        Loads global project settings (e.g., from a root projects.yaml).
        Args:
            global_projects_file_path: Path to the global projects settings file.
        Returns:
            A GlobalProjectSettings object.
        Raises:
            ConfigError: If the settings cannot be loaded or parsed.
        """
        ...

    def load_specific_project_config(
        self,
        project_name: str,
        projects_root_dir: str,
        # Optional paths if they are not derivable or fixed relative to project_name/root_dir
        project_yaml_name: str = "project.yaml",
        geom_layers_yaml_name: str = "geom_layers.yaml",
        legends_yaml_name: str = "legends.yaml",
        # ... other specific config file names as needed
        project_specific_styles_yaml_name: Optional[str] = None # e.g. "styles.yaml" within project folder
    ) -> SpecificProjectConfig:
        """
        Loads all configuration files for a specific project by its name.
        This would typically involve reading multiple YAML files associated with the project
        (e.g., project.yaml, geom_layers.yaml, legends.yaml, potentially project-specific styles)
        and consolidating them into a SpecificProjectConfig object.

        Args:
            project_name: The name of the project to load.
            projects_root_dir: The root directory where all projects are stored.
            project_yaml_name: Name of the main project definition file.
            geom_layers_yaml_name: Name of the geometry layers definition file.
            legends_yaml_name: Name of the legends definition file.
            project_specific_styles_yaml_name: Optional name of a project-specific styles file.

        Returns:
            A SpecificProjectConfig object for the specified project.
        Raises:
            ConfigError: If any part of the project's configuration cannot be loaded or parsed,
                         or if the project is not found.
        """
        ...
