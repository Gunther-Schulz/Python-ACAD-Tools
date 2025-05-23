"""Configuration validation schemas and utilities for robust config validation."""
import os
import re
from typing import Any, Dict, List, Optional, Union, Tuple, Type
from pathlib import Path

from pydantic import field_validator, model_validator, ValidationInfo, ConfigDict
from pydantic_core import ValidationError as PydanticValidationError

# Import for CRS validation
try:
    from pyproj import CRS
    from pyproj.exceptions import CRSError
    PYPROJ_AVAILABLE = True
except ImportError:
    CRS = None
    CRSError = Exception
    PYPROJ_AVAILABLE = False

# Import for color validation
try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False


class ConfigValidationError(Exception):
    """Custom exception for configuration validation errors."""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 config_file: Optional[str] = None, validation_errors: Optional[List[str]] = None):
        self.message = message
        self.field_name = field_name
        self.config_file = config_file
        self.validation_errors = validation_errors or []

        detailed_message = f"Configuration validation error"
        if config_file:
            detailed_message += f" in {config_file}"
        if field_name:
            detailed_message += f" for field '{field_name}'"
        detailed_message += f": {message}"

        if validation_errors:
            detailed_message += f"\nDetailed errors:\n" + "\n".join(f"  - {err}" for err in validation_errors)

        super().__init__(detailed_message)


class ValidationRegistry:
    """Registry for common validation functions and patterns."""

    # Valid file extensions for different data types
    VALID_EXTENSIONS = {
        'geojson': ['.geojson', '.json'],
        'shapefile': ['.shp'],
        'dxf': ['.dxf'],
        'yaml': ['.yaml', '.yml'],
        'linetype': ['.lin'],
        'font': ['.shx', '.ttf', '.otf'],
        'gpkg': ['.gpkg']  # Added GeoPackage support
    }

    # Valid CRS patterns
    CRS_PATTERNS = {
        'epsg': re.compile(r'^EPSG:\d+$', re.IGNORECASE),
        'proj4': re.compile(r'^\+proj='),
        'wkt': re.compile(r'^(GEOGCS|PROJCS|GEOCCS|COMPD_CS|VERT_CS|LOCAL_CS)\['),
    }

    # Valid ACI color range (AutoCAD Color Index)
    ACI_COLOR_RANGE = (0, 255)

    # Valid DXF versions
    VALID_DXF_VERSIONS = [
        'R12', 'R14', 'R2000', 'R2004', 'R2007', 'R2010', 'R2013', 'R2018', 'R2021'
    ]

    # Valid export formats
    VALID_EXPORT_FORMATS = ['dxf', 'shp', 'gpkg', 'all']

    # Valid geometry types
    VALID_GEOMETRY_TYPES = [
        'Point', 'LineString', 'Polygon', 'MultiPoint', 'MultiLineString', 'MultiPolygon'
    ]

    # Valid linetype patterns (common CAD linetypes)
    VALID_LINETYPES = [
        'Continuous', 'BYLAYER', 'BYBLOCK',
        'DASHED', 'DOTTED', 'DASHDOT', 'CENTER', 'PHANTOM',
        'HIDDEN', 'DIVIDE', 'BORDER', 'ACAD_ISO02W100',
        'ACAD_ISO03W100', 'ACAD_ISO04W100', 'ACAD_ISO05W100'
    ]


class ConfigValidators:
    """Collection of reusable validation functions."""

    @staticmethod
    def validate_file_path(value: str, file_type: Optional[str] = None,
                          must_exist: bool = False, base_path: Optional[str] = None,
                          is_output_file: bool = False) -> str:
        """Validates file paths with optional existence and extension checking."""
        if not value or not isinstance(value, str):
            raise ValueError("File path must be a non-empty string")

        # Convert to Path object for better handling
        if base_path and not os.path.isabs(value):
            full_path = Path(base_path) / value
        else:
            full_path = Path(value)

        # Validate extension if file_type specified
        if file_type and file_type in ValidationRegistry.VALID_EXTENSIONS:
            valid_exts = ValidationRegistry.VALID_EXTENSIONS[file_type]
            if not any(str(full_path).lower().endswith(ext) for ext in valid_exts):
                raise ValueError(f"File must have one of these extensions: {valid_exts}")

        # Check existence if required
        if must_exist and not full_path.exists():
            raise ValueError(f"File does not exist: {full_path}")

        # Handle output file directory creation
        if is_output_file and full_path.parent != full_path:
            if not full_path.parent.exists():
                try:
                    # Create the output directory if it doesn't exist
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    # Log this directory creation if we had access to logger
                    # For now, this will be silent, but it's a valid action for output files
                except (PermissionError, OSError) as e:
                    raise ValueError(f"Cannot create output directory {full_path.parent}: {e}")

        # Check if parent directory exists (for non-output files)
        elif not must_exist and not is_output_file and full_path.parent != full_path:
            if not full_path.parent.exists():
                raise ValueError(f"Parent directory does not exist: {full_path.parent}")

        return str(value)  # Return original path format

    @staticmethod
    def validate_crs(value: str) -> str:
        """Validates Coordinate Reference System strings."""
        if not value or not isinstance(value, str):
            raise ValueError("CRS must be a non-empty string")

        # Check common patterns first (faster)
        if ValidationRegistry.CRS_PATTERNS['epsg'].match(value):
            # Extract EPSG code and validate range
            epsg_code = int(value.split(':')[1])
            if epsg_code < 1 or epsg_code > 32767:  # Reasonable EPSG range
                raise ValueError(f"EPSG code {epsg_code} is outside valid range (1-32767)")
            return value

        if ValidationRegistry.CRS_PATTERNS['proj4'].match(value):
            return value

        if ValidationRegistry.CRS_PATTERNS['wkt'].match(value):
            return value

        # If pyproj is available, try to parse it
        if PYPROJ_AVAILABLE:
            try:
                crs_obj = CRS.from_string(value)
                if not crs_obj.is_valid:
                    raise ValueError(f"Invalid CRS: {value}")
                return value
            except CRSError as e:
                raise ValueError(f"Invalid CRS '{value}': {e}")

        # Fallback: accept common CRS names
        common_crs = ['WGS84', 'NAD83', 'NAD27', 'ETRS89']
        if value.upper() in common_crs:
            return value

        raise ValueError(f"Unrecognized CRS format: {value}. Use EPSG:XXXX, PROJ4, or WKT format")

    @staticmethod
    def validate_aci_color(value: Union[str, int]) -> Union[str, int]:
        """Validates ACI color codes and color names."""
        if isinstance(value, int):
            min_aci, max_aci = ValidationRegistry.ACI_COLOR_RANGE
            if not (min_aci <= value <= max_aci):
                raise ValueError(f"ACI color code must be between {min_aci} and {max_aci}")
            return value

        if isinstance(value, str):
            # Allow color names (validated later against color map)
            if not value.strip():
                raise ValueError("Color name cannot be empty")
            return value.strip()

        raise ValueError("Color must be an integer (ACI code) or string (color name)")

    @staticmethod
    def validate_dxf_version(value: str) -> str:
        """Validates DXF version strings."""
        if value not in ValidationRegistry.VALID_DXF_VERSIONS:
            raise ValueError(f"Invalid DXF version '{value}'. Valid versions: {ValidationRegistry.VALID_DXF_VERSIONS}")
        return value

    @staticmethod
    def validate_export_format(value: str) -> str:
        """Validates export format strings."""
        if value not in ValidationRegistry.VALID_EXPORT_FORMATS:
            raise ValueError(f"Invalid export format '{value}'. Valid formats: {ValidationRegistry.VALID_EXPORT_FORMATS}")
        return value

    @staticmethod
    def validate_geometry_types(value: List[str]) -> List[str]:
        """Validates geometry type lists."""
        invalid_types = [gt for gt in value if gt not in ValidationRegistry.VALID_GEOMETRY_TYPES]
        if invalid_types:
            raise ValueError(f"Invalid geometry types: {invalid_types}. Valid types: {ValidationRegistry.VALID_GEOMETRY_TYPES}")
        return value

    @staticmethod
    def validate_linetype(value: str) -> str:
        """Validates linetype names."""
        if value not in ValidationRegistry.VALID_LINETYPES:
            # Allow custom linetypes but issue warning via logger if available
            if not re.match(r'^[A-Za-z0-9_-]+$', value):
                raise ValueError(f"Invalid linetype name '{value}'. Must contain only alphanumeric characters, underscores, and hyphens")
        return value

    @staticmethod
    def validate_positive_number(value: float, field_name: str = "value") -> float:
        """Validates that a number is positive."""
        if value <= 0:
            raise ValueError(f"{field_name} must be positive, got {value}")
        return value

    @staticmethod
    def validate_non_negative_number(value: float, field_name: str = "value") -> float:
        """Validates that a number is non-negative."""
        if value < 0:
            raise ValueError(f"{field_name} must be non-negative, got {value}")
        return value

    @staticmethod
    def validate_percentage(value: float, field_name: str = "percentage") -> float:
        """Validates percentage values (0.0 to 1.0)."""
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{field_name} must be between 0.0 and 1.0, got {value}")
        return value

    @staticmethod
    def validate_url(value: str) -> str:
        """Basic URL validation."""
        if not value.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return value


class CrossFieldValidator:
    """Handles validation that spans multiple fields within a model."""

    @staticmethod
    def validate_output_paths_consistency(values: Dict[str, Any]) -> Dict[str, Any]:
        """Validates that output paths are consistent with export format."""
        # Handle both camelCase (YAML) and snake_case (Python) field names
        export_format = values.get('export_format', values.get('exportFormat', 'dxf'))

        # Check for DXF output path (handle both field name formats)
        output_dxf = values.get('output_dxf_path') or values.get('outputDxfPath')

        # Check for shapefile output directory (handle both field name formats)
        output_shp_dir = values.get('shapefile_output_dir') or values.get('shapefileOutputDir')

        # Check for geopackage output path (handle both field name formats)
        output_gpkg = values.get('output_geopackage_path') or values.get('outputGeopackagePath')

        errors = []

        if export_format in ['dxf', 'all'] and not output_dxf:
            errors.append("output_dxf_path (outputDxfPath) is required when export_format includes 'dxf'")

        if export_format in ['shp', 'all'] and not output_shp_dir:
            errors.append("shapefile_output_dir (shapefileOutputDir) is required when export_format includes 'shp'")

        if export_format in ['gpkg', 'all'] and not output_gpkg:
            errors.append("output_geopackage_path (outputGeopackagePath) is required when export_format includes 'gpkg'")

        if errors:
            raise ValueError(f"Output path consistency errors: {'; '.join(errors)}")

        return values

    @staticmethod
    def validate_operation_layer_references(values: Dict[str, Any], available_layers: List[str]) -> Dict[str, Any]:
        """Validates that operation layer references point to existing layers."""
        operations = values.get('operations', [])
        if not operations:
            return values

        errors = []

        for i, operation in enumerate(operations):
            op_type = operation.get('type', 'unknown')

            # Check 'layer' field (single layer operations)
            if 'layer' in operation:
                layer_ref = operation['layer']
                if isinstance(layer_ref, str) and layer_ref not in available_layers:
                    errors.append(f"Operation {i} ({op_type}): layer '{layer_ref}' not found in available layers")
                elif isinstance(layer_ref, dict) and 'name' in layer_ref:
                    layer_name = layer_ref['name']
                    if layer_name not in available_layers:
                        errors.append(f"Operation {i} ({op_type}): layer '{layer_name}' not found in available layers")

            # Check 'layers' field (multi-layer operations)
            if 'layers' in operation:
                for j, layer_ref in enumerate(operation['layers']):
                    if isinstance(layer_ref, str) and layer_ref not in available_layers:
                        errors.append(f"Operation {i} ({op_type}): layers[{j}] '{layer_ref}' not found in available layers")
                    elif isinstance(layer_ref, dict) and 'name' in layer_ref:
                        layer_name = layer_ref['name']
                        if layer_name not in available_layers:
                            errors.append(f"Operation {i} ({op_type}): layers[{j}] '{layer_name}' not found in available layers")

        if errors:
            raise ValueError(f"Layer reference errors: {'; '.join(errors)}")

        return values


class ConfigValidationService:
    """Service for comprehensive configuration validation."""

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path
        self.validation_errors: List[str] = []

    def validate_project_config(self, config_data: Dict[str, Any],
                              config_file: Optional[str] = None) -> Dict[str, Any]:
        """Validates a complete project configuration."""
        self.validation_errors = []

        try:
            # Validate main project settings
            if 'main' in config_data:
                self._validate_main_settings(config_data['main'])

            # Validate geometry layers
            if 'geomLayers' in config_data or 'geom_layers' in config_data:
                geom_layers = config_data.get('geomLayers', config_data.get('geom_layers', []))
                layer_names = self._validate_geometry_layers(geom_layers)

                # Cross-validate operations against available layers
                for layer in geom_layers:
                    if 'operations' in layer:
                        try:
                            CrossFieldValidator.validate_operation_layer_references(
                                {'operations': layer['operations']}, layer_names
                            )
                        except ValueError as e:
                            self.validation_errors.append(f"Layer '{layer.get('name', '?')}': {e}")

            # Validate legends
            if 'legends' in config_data:
                self._validate_legends(config_data['legends'])

            # Final validation
            if self.validation_errors:
                raise ConfigValidationError(
                    f"Configuration validation failed with {len(self.validation_errors)} errors",
                    config_file=config_file,
                    validation_errors=self.validation_errors
                )

            return config_data

        except Exception as e:
            if isinstance(e, ConfigValidationError):
                raise
            raise ConfigValidationError(f"Unexpected validation error: {e}", config_file=config_file)

    def _validate_main_settings(self, main_data: Dict[str, Any]) -> None:
        """Validates main project settings."""
        # Validate CRS
        if 'crs' in main_data:
            try:
                ConfigValidators.validate_crs(main_data['crs'])
            except ValueError as e:
                self.validation_errors.append(f"main.crs: {e}")

        # Validate DXF filename
        if 'dxfFilename' in main_data or 'dxf_filename' in main_data:
            dxf_filename = main_data.get('dxfFilename', main_data.get('dxf_filename'))
            try:
                ConfigValidators.validate_file_path(dxf_filename, 'dxf', base_path=self.base_path)
            except ValueError as e:
                self.validation_errors.append(f"main.dxf_filename: {e}")

        # Validate DXF version
        if 'dxfVersion' in main_data or 'dxf_version' in main_data:
            dxf_version = main_data.get('dxfVersion', main_data.get('dxf_version'))
            try:
                ConfigValidators.validate_dxf_version(dxf_version)
            except ValueError as e:
                self.validation_errors.append(f"main.dxf_version: {e}")

        # Validate export format
        if 'exportFormat' in main_data or 'export_format' in main_data:
            export_format = main_data.get('exportFormat', main_data.get('export_format'))
            try:
                ConfigValidators.validate_export_format(export_format)
            except ValueError as e:
                self.validation_errors.append(f"main.export_format: {e}")

        # Cross-field validation for output paths
        try:
            CrossFieldValidator.validate_output_paths_consistency(main_data)
        except ValueError as e:
            self.validation_errors.append(f"main settings: {e}")

    def _validate_geometry_layers(self, layers_data: List[Dict[str, Any]]) -> List[str]:
        """Validates geometry layer definitions and returns layer names."""
        layer_names = []

        for i, layer in enumerate(layers_data):
            layer_name = layer.get('name', f'layer_{i}')
            layer_names.append(layer_name)

            # Validate data sources
            sources = [
                ('geojsonFile', 'geojson'),
                ('shapeFile', 'shapefile'),
                ('dxfLayer', None)  # DXF layer is just a string reference
            ]

            source_count = 0
            for source_key, file_type in sources:
                if source_key in layer or source_key.lower().replace('file', '_file') in layer:
                    source_count += 1
                    if file_type:  # File-based source
                        file_path = layer.get(source_key, layer.get(source_key.lower().replace('file', '_file')))
                        try:
                            ConfigValidators.validate_file_path(file_path, file_type, base_path=self.base_path)
                        except ValueError as e:
                            self.validation_errors.append(f"layer '{layer_name}' {source_key}: {e}")

            if source_count == 0:
                self.validation_errors.append(f"layer '{layer_name}': no valid data source specified")
            elif source_count > 1:
                self.validation_errors.append(f"layer '{layer_name}': multiple data sources specified (only one allowed)")

            # Validate operations
            if 'operations' in layer:
                self._validate_operations(layer['operations'], f"layer '{layer_name}'")

        # Check for duplicate layer names
        duplicates = [name for name in layer_names if layer_names.count(name) > 1]
        if duplicates:
            self.validation_errors.append(f"Duplicate layer names found: {list(set(duplicates))}")

        return layer_names

    def _validate_operations(self, operations: List[Dict[str, Any]], context: str) -> None:
        """Validates operation definitions."""
        for i, operation in enumerate(operations):
            op_context = f"{context} operation[{i}]"

            # Validate operation type
            if 'type' not in operation:
                self.validation_errors.append(f"{op_context}: missing 'type' field")
                continue

            op_type = operation['type']

            # Type-specific validation
            if op_type == 'buffer':
                if 'distance' not in operation and 'distanceField' not in operation:
                    self.validation_errors.append(f"{op_context}: buffer operation requires 'distance' or 'distanceField'")

                if 'distance' in operation:
                    try:
                        ConfigValidators.validate_non_negative_number(operation['distance'], 'buffer distance')
                    except ValueError as e:
                        self.validation_errors.append(f"{op_context}: {e}")

            elif op_type in ['translate', 'scale', 'rotate']:
                # Validate transformation parameters
                if op_type == 'translate':
                    for param in ['dx', 'dy']:
                        if param in operation and not isinstance(operation[param], (int, float)):
                            self.validation_errors.append(f"{op_context}: {param} must be a number")

                elif op_type == 'scale':
                    for param in ['xfact', 'yfact']:
                        if param in operation:
                            try:
                                ConfigValidators.validate_positive_number(operation[param], f'scale {param}')
                            except ValueError as e:
                                self.validation_errors.append(f"{op_context}: {e}")

                elif op_type == 'rotate':
                    if 'angle' not in operation:
                        self.validation_errors.append(f"{op_context}: rotate operation requires 'angle' field")

    def _validate_legends(self, legends_data: List[Dict[str, Any]]) -> None:
        """Validates legend definitions."""
        for i, legend in enumerate(legends_data):
            legend_context = f"legend[{i}]"

            # Validate required fields
            if 'name' not in legend:
                self.validation_errors.append(f"{legend_context}: missing 'name' field")

            if 'position' not in legend:
                self.validation_errors.append(f"{legend_context}: missing 'position' field")
            else:
                # Validate position coordinates
                position = legend['position']
                if not isinstance(position, (list, tuple)) or len(position) != 2:
                    self.validation_errors.append(f"{legend_context}: position must be [x, y] coordinates")
                else:
                    try:
                        x, y = position
                        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                            self.validation_errors.append(f"{legend_context}: position coordinates must be numbers")
                    except (ValueError, TypeError):
                        self.validation_errors.append(f"{legend_context}: invalid position format")

            # Validate legend items
            if 'items' in legend:
                if not isinstance(legend['items'], list):
                    self.validation_errors.append(f"{legend_context}: 'items' must be a list")
                else:
                    for j, item in enumerate(legend['items']):
                        if not isinstance(item, dict) or 'text' not in item:
                            self.validation_errors.append(f"{legend_context} item[{j}]: must have 'text' field")


def validate_config_with_schema(config_data: Dict[str, Any],
                               config_type: str,
                               config_file: Optional[str] = None,
                               base_path: Optional[str] = None) -> Dict[str, Any]:
    """Main entry point for configuration validation."""
    validator = ConfigValidationService(base_path=base_path)

    if config_type == 'project':
        return validator.validate_project_config(config_data, config_file)
    else:
        raise ValueError(f"Unknown configuration type: {config_type}")
