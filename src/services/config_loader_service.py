"""Concrete implementation of the IConfigLoader interface."""
import os
import yaml # PyYAML
from typing import Type, TypeVar, List, Dict, Optional
from pydantic import BaseModel, ValidationError

from ..interfaces.config_loader_interface import IConfigLoader
from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.path_resolver_interface import IPathResolver
from ..domain.config_models import (
    AppConfig,
    StyleConfig,
    ColorConfig, # Represents the structure { "colors": List[AciColorMappingItem] }
    AciColorMappingItem, # For direct parsing if aci_colors.yaml is a list
    GlobalProjectSettings,
    SpecificProjectConfig,
    ProjectMainSettings,
    GeomLayerDefinition,
    LegendDefinition,
    # ... import other specific models needed by SpecificProjectConfig
    # WmtsLayerProjectDefinition, WmsLayerProjectDefinition, DxfOperationsConfig etc.
)
from ..domain.exceptions import ConfigError
from ..domain.config_validation import (
    validate_config_with_schema,
    ConfigValidationError,
    ConfigValidationService,
    CrossFieldValidator
)


_T = TypeVar("_T", bound=BaseModel)

class ConfigLoaderService(IConfigLoader):
    """Loads application and project configurations from YAML files and environment variables."""

    def __init__(self, logger_service: ILoggingService, app_config: Optional[AppConfig] = None, path_resolver: Optional[IPathResolver] = None):
        """Initialize with required injected dependencies following strict DI principles."""
        self._logger = logger_service.get_logger(__name__)
        self._app_config: Optional[AppConfig] = app_config
        self._path_resolver: Optional[IPathResolver] = path_resolver
        self._aci_color_mappings: Optional[List[AciColorMappingItem]] = None

    def _resolve_path_if_needed(self, file_path: str, project_name: Optional[str] = None, projects_root_dir: Optional[str] = None) -> str:
        """Resolve path aliases if path resolver is available and path is an alias reference."""
        if not self._path_resolver or not file_path.startswith('@'):
            return file_path

        if not project_name or not projects_root_dir:
            self._logger.warning(f"Cannot resolve path alias '{file_path}' without project context")
            return file_path

        try:
            # We need to load the project's path aliases to create the context
            project_dir = os.path.join(projects_root_dir, project_name)
            project_yaml_path = os.path.join(project_dir, "project.yaml")

            if os.path.exists(project_yaml_path):
                with open(project_yaml_path, 'r', encoding='utf-8') as f:
                    project_data = yaml.safe_load(f)

                if 'pathAliases' in project_data:
                    from ..domain.path_models import ProjectPathAliases, PathResolutionContext
                    aliases = ProjectPathAliases(aliases=project_data['pathAliases'])
                    context = self._path_resolver.create_context(project_name, project_dir, aliases)
                    resolved_path = self._path_resolver.resolve_path(file_path, context)
                    self._logger.debug(f"Resolved path alias '{file_path}' to '{resolved_path}'")
                    return resolved_path

            self._logger.warning(f"Could not resolve path alias '{file_path}' - no pathAliases found in project config")
            return file_path

        except Exception as e:
            self._logger.warning(f"Failed to resolve path alias '{file_path}': {e}")
            return file_path

    def _load_yaml_file(self, file_path: str, model_class: Type[_T],
                        validate_config: bool = True, config_type: Optional[str] = None) -> _T:
        """Helper to load a YAML file and parse it into a Pydantic model."""
        self._logger.debug(f"Attempting to load YAML file: {file_path} into model {model_class.__name__}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:  # Added explicit UTF-8 encoding
                data = yaml.safe_load(f)
            if data is None: # Handle empty YAML file
                self._logger.warning(f"YAML file is empty: {file_path}")
                # Depending on model_class, an empty dict might be valid for models with all optional fields
                # or if default_factory is used. For stricter cases, this could be an error.
                # For now, assume an empty dict might be processable by Pydantic (e.g. for StyleConfig)
                data = {}

            # Apply configuration validation if requested
            if validate_config and config_type:
                try:
                    base_path = os.path.dirname(file_path) if os.path.isabs(file_path) else None
                    data = validate_config_with_schema(
                        data,
                        config_type,
                        config_file=file_path,
                        base_path=base_path
                    )
                    self._logger.debug(f"Configuration validation passed for {file_path}")
                except ConfigValidationError as e:
                    self._logger.error(f"Configuration validation failed for {file_path}: {e}")
                    raise ConfigError(f"Configuration validation failed for {file_path}: {e}") from e

            return model_class.model_validate(data)
        except FileNotFoundError:
            self._logger.error(f"Configuration file not found: {file_path}")
            raise ConfigError(f"Configuration file not found: {file_path}") from None
        except UnicodeDecodeError as e:
            self._logger.error(f"Encoding error reading file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"Encoding error reading file {file_path}. Expected UTF-8: {e}") from e
        except yaml.YAMLError as e:
            self._logger.error(f"Error parsing YAML file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"Error parsing YAML file {file_path}: {e}") from e
        except ValidationError as e:
            self._logger.error(f"Validation error for {model_class.__name__} from file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"Validation error for {model_class.__name__} from file {file_path}: {e}") from e
        except IOError as e:
            self._logger.error(f"IOError reading file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"IOError reading file {file_path}: {e}") from e

    def _load_yaml_list_file(self, file_path: str, item_model_class: Type[_T]) -> List[_T]:
        """Helper to load a YAML file containing a list of items into Pydantic models."""
        self._logger.debug(f"Attempting to load YAML list file: {file_path} into List[{item_model_class.__name__}]")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:  # Added explicit UTF-8 encoding
                data = yaml.safe_load(f)
            if not isinstance(data, list):
                err_msg = f"YAML file {file_path} does not contain a list as expected."
                self._logger.error(err_msg)
                raise ConfigError(err_msg)
            return [item_model_class.model_validate(item) for item in data]
        except FileNotFoundError:
            self._logger.error(f"Configuration file not found: {file_path}")
            raise ConfigError(f"Configuration file not found: {file_path}") from None
        except UnicodeDecodeError as e:
            self._logger.error(f"Encoding error reading file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"Encoding error reading file {file_path}. Expected UTF-8: {e}") from e
        except yaml.YAMLError as e:
            self._logger.error(f"Error parsing YAML file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"Error parsing YAML file {file_path}: {e}") from e
        except ValidationError as e:
            self._logger.error(f"Validation error for List[{item_model_class.__name__}] from {file_path}: {e}", exc_info=True)
            raise ConfigError(f"Validation error for List[{item_model_class.__name__}] from {file_path}: {e}") from e
        except IOError as e:
            self._logger.error(f"IOError reading file {file_path}: {e}", exc_info=True)
            raise ConfigError(f"IOError reading file {file_path}: {e}") from e

    def get_app_config(self) -> AppConfig:
        """Loads AppConfig using pydantic-settings (from .env, env vars)."""
        if self._app_config is None:
            self._logger.debug("Loading AppConfig for the first time.")
            try:
                self._app_config = AppConfig()
                # Log some key app config values for diagnostics if needed, be careful with secrets
                self._logger.info(f"AppConfig loaded. Projects root: {self._app_config.projects_root_dir}")
            except ValidationError as e:
                self._logger.error(f"Validation error loading AppConfig: {e}", exc_info=True)
                raise ConfigError(f"Validation error loading AppConfig: {e}") from e
            except Exception as e: # Catch any other Pydantic-settings loading issues
                self._logger.error(f"Failed to load AppConfig: {e}", exc_info=True)
                raise ConfigError(f"Failed to load AppConfig: {e}") from e
        return self._app_config

    def load_global_styles(self, styles_file_path: str, project_name: Optional[str] = None, projects_root_dir: Optional[str] = None) -> StyleConfig:
        """Loads global styles.yaml with optional path alias resolution."""
        resolved_path = self._resolve_path_if_needed(styles_file_path, project_name, projects_root_dir)
        return self._load_yaml_file(resolved_path, StyleConfig)

    def load_aci_colors(self, aci_colors_file_path: str) -> ColorConfig:
        """Loads aci_colors.yaml. File structure is a plain list of ACI color items."""
        self._logger.debug(f"Attempting to load ACI colors from: {aci_colors_file_path}")
        list_of_items = self._load_yaml_list_file(aci_colors_file_path, AciColorMappingItem)
        return ColorConfig(colors=list_of_items)

    def load_global_project_settings(self, global_projects_file_path: str) -> GlobalProjectSettings:
        """Loads the global projects.yaml (or similar)."""
        # This file might contain GlobalProjectSettings directly or be a dict from which it's extracted.
        # AppConfig has `global_settings: GlobalProjectSettings`. If this file *is* the content for that,
        # then the structure loaded by pydantic-settings for AppConfig handles it.
        # This method is for loading it if it's a *separate* file not managed by AppConfig directly.
        # For now, assume it maps directly to GlobalProjectSettings model.
        return self._load_yaml_file(global_projects_file_path, GlobalProjectSettings)

    def load_specific_project_config(
        self,
        project_name: str,
        projects_root_dir: str, # This should ideally come from AppConfig
        project_yaml_name: str = "project.yaml",
        geom_layers_yaml_name: str = "geom_layers.yaml",
        legends_yaml_name: str = "legends.yaml",
        project_specific_styles_yaml_name: Optional[str] = None
    ) -> SpecificProjectConfig:
        """Loads all configuration for a specific project."""
        self._logger.info(f"Loading configuration for project: {project_name}")
        project_dir = os.path.join(projects_root_dir, project_name)

        if not os.path.isdir(project_dir):
            self._logger.error(f"Project directory not found: {project_dir}")
            raise ConfigError(f"Project directory not found: {project_dir}")

        try:
            # Main project settings - validate with schema
            main_settings_path = os.path.join(project_dir, project_yaml_name)

            # Load the full YAML file first
            with open(main_settings_path, 'r', encoding='utf-8') as f:
                full_project_data = yaml.safe_load(f)

            # Load path aliases for later use in SpecificProjectConfig
            # Path resolution during validation is handled by the validation service
            # creating a PathResolutionContext from the full project data
            if 'pathAliases' in full_project_data:
                from ..domain.path_models import ProjectPathAliases
                try:
                    path_aliases_data = ProjectPathAliases(aliases=full_project_data['pathAliases'])
                    self._logger.debug(f"Loaded {len(path_aliases_data.aliases)} path aliases for project '{project_name}'")
                except Exception as e:
                    self._logger.error(f"Failed to load path aliases for project '{project_name}': {e}")
                    path_aliases_data = None
            else:
                path_aliases_data = None

            # Extract the 'main' section for ProjectMainSettings
            if 'main' not in full_project_data:
                raise ConfigError(f"Missing 'main' section in project configuration: {main_settings_path}")

            main_data = full_project_data['main']

            # Validate the main section with schema if requested
            if True:  # validate_config is True
                try:
                    main_data = validate_config_with_schema(
                        {'main': main_data},  # Wrap for validation
                        'project',
                        config_file=main_settings_path,
                        base_path=project_dir,
                        path_resolver=self._path_resolver
                    )['main']  # Extract main section after validation
                    self._logger.debug(f"Configuration validation passed for {main_settings_path}")
                except ConfigValidationError as e:
                    self._logger.error(f"Configuration validation failed for {main_settings_path}: {e}")
                    raise ConfigError(f"Configuration validation failed for {main_settings_path}: {e}") from e

            # Create the ProjectMainSettings model from the main section
            main_settings = ProjectMainSettings.model_validate(main_data)

            # Geometry Layers - load and validate comprehensively
            geom_layers_path = os.path.join(project_dir, geom_layers_yaml_name)

            # Load raw YAML data for comprehensive validation
            with open(geom_layers_path, 'r', encoding='utf-8') as f:
                geom_layers_raw = yaml.safe_load(f)

            # Apply comprehensive validation including style preset checking, file existence, etc.
            validator = ConfigValidationService(base_path=project_dir, path_resolver=self._path_resolver)

            try:
                # Handle both list format (direct array) and dict format (with geomLayers key)
                if isinstance(geom_layers_raw, list):
                    geom_layers_list = geom_layers_raw
                elif isinstance(geom_layers_raw, dict) and 'geomLayers' in geom_layers_raw:
                    geom_layers_list = geom_layers_raw['geomLayers']
                else:
                    raise ConfigError(f"Invalid geom_layers.yaml format. Expected list or dict with 'geomLayers' key.")

                # Validate the complete geom layers configuration
                # Pass the full project configuration including pathAliases for proper path resolution
                validation_config = {
                    'geomLayers': geom_layers_list,
                    'pathAliases': full_project_data.get('pathAliases', {}),
                    'main': full_project_data.get('main', {})
                }
                validated_geom_config = validator.validate_project_config(
                    validation_config,
                    config_file=geom_layers_path
                )

                # Log validation warnings if any
                warnings = validator.validation_warnings
                if warnings:
                    self._logger.warning(f"Geometry layers validation warnings for project '{project_name}':")
                    for warning in warnings:
                        self._logger.warning(f"  - {warning}")

                self._logger.debug(f"Comprehensive geometry layers validation passed for {geom_layers_path}")

            except ConfigValidationError as e:
                self._logger.error(f"Comprehensive geometry layers validation failed for {geom_layers_path}: {e}")
                if hasattr(e, 'validation_errors') and e.validation_errors:
                    for error in e.validation_errors:
                        self._logger.error(f"  - {error}")
                raise ConfigError(f"Geometry layers validation failed for project '{project_name}': {e}") from e

            # Now load into Pydantic models (this will also validate structure)
            geom_layers_data = self._load_yaml_list_file(geom_layers_path, GeomLayerDefinition)

            # Legends
            legends_path = os.path.join(project_dir, legends_yaml_name)
            # legends.yaml might be a list or a dict if it contains multiple named legends.
            # Assuming a list for now as per List[LegendDefinition] in SpecificProjectConfig
            # If it can be a dict of named legends, the model or loading needs adjustment.
            # For now, if `legends.yaml` itself *is* the list:
            legends_data: List[LegendDefinition] = []
            if os.path.exists(legends_path):
                 legends_data = self._load_yaml_list_file(legends_path, LegendDefinition)
            else:
                self._logger.warning(f"Legends file not found for project {project_name}: {legends_path}. Proceeding with empty legends list.")

            # Project-specific styles (optional)
            project_styles_data: Optional[Dict[str, Any]] = None # Corresponds to StyleConfig.styles
            if project_specific_styles_yaml_name:
                project_styles_path = os.path.join(project_dir, project_specific_styles_yaml_name)
                if os.path.exists(project_styles_path):
                    # StyleConfig model expects {"styles": {...}}. So load StyleConfig then extract .styles
                    loaded_proj_style_config = self._load_yaml_file(project_styles_path, StyleConfig)
                    project_styles_data = loaded_proj_style_config.styles
                else:
                    self._logger.warning(f"Project specific styles file specified but not found: {project_styles_path}")

            # TODO: Load other parts of SpecificProjectConfig as models are finalized
            # (viewports, block_inserts, text_inserts, path_arrays, wmts_layers, wms_layers, dxf_operations)
            # For now, they will use their default_factory (empty lists) if not explicitly loaded.

            project_config = SpecificProjectConfig(
                main=main_settings,
                geomLayers=geom_layers_data, # Alias used in Pydantic model
                legends=legends_data,
                project_specific_styles=project_styles_data, # Alias used in Pydantic model
                pathAliases=path_aliases_data,  # Use the correct alias name
                # Initialize other fields as they are loaded
                # viewports=[], blockInserts=[], textInserts=[], pathArrays=[],
                # wmtsLayers=[], wmsLayers=[], dxfOperations=None
            )

            self._logger.info(f"Successfully loaded configuration for project '{project_name}' with {len(geom_layers_data)} layers")
            return project_config

        except ConfigValidationError as e:
            self._logger.error(f"Configuration validation failed for project '{project_name}': {e}")
            raise ConfigError(f"Configuration validation failed for project '{project_name}': {e}") from e
        except Exception as e:
            self._logger.error(f"Failed to load project configuration for '{project_name}': {e}", exc_info=True)
            raise ConfigError(f"Failed to load project configuration for '{project_name}': {e}") from e

    def get_aci_color_mappings(self) -> List[AciColorMappingItem]:
        """Returns the loaded ACI color mappings."""
        if self._aci_color_mappings is None:
            # Try to load ACI colors if app_config is available
            if self._app_config:
                try:
                    color_config = self.load_aci_colors(self._app_config.aci_colors_file)
                    self._aci_color_mappings = color_config.colors
                    self._logger.info(f"Loaded {len(self._aci_color_mappings)} ACI color mappings")
                except Exception as e:
                    self._logger.warning(f"Failed to load ACI color mappings: {e}")
                    self._aci_color_mappings = []
            else:
                self._logger.warning("ACI color mappings have not been loaded and no app_config available.")
                self._aci_color_mappings = []
        return self._aci_color_mappings
