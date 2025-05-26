"""Configuration validation schemas and utilities for robust config validation."""
import os
import re
from typing import Any, Dict, List, Optional, Union, Tuple, Type
from pathlib import Path
from urllib.parse import urlparse

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

# Import for geometry validation
try:
    from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
    from shapely.validation import explain_validity
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

from ..interfaces.config_validation_interface import IConfigValidation
from ..interfaces.path_resolver_interface import IPathResolver
from .exceptions import ConfigValidationError


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
        'gpkg': ['.gpkg'],  # Added GeoPackage support
        'csv': ['.csv'],
        'xlsx': ['.xlsx', '.xls'],
        'kml': ['.kml'],
        'gml': ['.gml']
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

    # Valid geom layer settings (comprehensive list from OLDAPP analysis)
    VALID_GEOM_LAYER_KEYS = {
        'name', 'geojsonFile', 'shapeFile', 'dxfLayer', 'style', 'labelColumn',
        'selectByProperties', 'updateDxf', 'operations', 'description', 'source',
        'lastUpdated', 'type', 'sourceLayer', 'outputShapeFile', 'close',
        'linetypeScale', 'linetypeGeneration', 'viewports', 'attributes',
        'bluntAngles', 'label', 'applyHatch', 'plot', 'saveToLagefaktor'
    }

    # Valid style types and their properties
    VALID_STYLE_TYPES = {
        'layer': {
            'color', 'linetype', 'lineweight', 'plot', 'locked', 'frozen',
            'is_on', 'transparency', 'linetypeScale', 'close'
        },
        'hatch': {
            'pattern', 'scale', 'color', 'transparency', 'individual_hatches',
            'layers', 'lineweight'
        },
        'text': {
            'color', 'height', 'font', 'maxWidth', 'attachmentPoint',
            'flowDirection', 'lineSpacingStyle', 'lineSpacingFactor',
            'bgFill', 'bgFillColor', 'bgFillScale', 'underline', 'overline',
            'strikeThrough', 'obliqueAngle', 'rotation', 'paragraph'
        }
    }

    # Valid operation types
    VALID_OPERATION_TYPES = {
        'buffer', 'intersection', 'union', 'difference', 'simplify', 'transform',
        'filter', 'merge', 'clip', 'dissolve', 'envelope', 'bounding_box',
        'rotate', 'scale', 'translate', 'offset_curve', 'symmetric_difference',
        'connect_points', 'create_circles', 'copy', 'filterByIntersection',
        'simpleLabel', 'wmts', 'wms', 'contour'
    }

    # Valid text attachment points
    VALID_TEXT_ATTACHMENT_POINTS = {
        'TOP_LEFT', 'TOP_CENTER', 'TOP_RIGHT',
        'MIDDLE_LEFT', 'MIDDLE_CENTER', 'MIDDLE_RIGHT',
        'BOTTOM_LEFT', 'BOTTOM_CENTER', 'BOTTOM_RIGHT'
    }

    # Valid flow directions
    VALID_FLOW_DIRECTIONS = {'LEFT_TO_RIGHT', 'TOP_TO_BOTTOM', 'BY_STYLE'}

    # Valid line spacing styles
    VALID_LINE_SPACING_STYLES = {'AT_LEAST', 'EXACT'}

    # Valid cap styles for buffer operations
    VALID_CAP_STYLES = {'round', 'flat', 'square'}

    # Valid join styles for buffer operations
    VALID_JOIN_STYLES = {'round', 'mitre', 'bevel'}

    # Valid spatial predicates for filter operations
    VALID_SPATIAL_PREDICATES = {
        'intersects', 'contains', 'within', 'touches', 'crosses', 'overlaps',
        'disjoint', 'equals', 'covers', 'covered_by'
    }

    # Performance warning thresholds
    PERFORMANCE_THRESHOLDS = {
        'max_buffer_distance': 10000.0,  # meters
        'max_file_size_mb': 100.0,
        'max_features_warning': 50000,
        'max_operation_chain_length': 10
    }

    # Common column name patterns for validation
    COMMON_COLUMN_PATTERNS = {
        'id': ['id', 'fid', 'objectid', 'gid', 'uid'],
        'name': ['name', 'label', 'title', 'description'],
        'area': ['area', 'area_m2', 'area_sqm', 'surface'],
        'length': ['length', 'length_m', 'perimeter'],
        'elevation': ['elevation', 'height', 'z', 'elev', 'alt']
    }


class ConfigValidators:
    """Collection of reusable validation functions."""

    @staticmethod
    def validate_file_path(value: str, file_type: Optional[str] = None,
                          must_exist: bool = False, base_path: Optional[str] = None,
                          is_output_file: bool = False,
                          path_resolver: Optional[IPathResolver] = None,
                          project_context = None) -> str:
        """Validates file paths with optional existence and extension checking."""
        if not value or not isinstance(value, str):
            raise ValueError("File path must be a non-empty string")

        # Handle path alias resolution if available
        resolved_path = value
        was_alias_resolved = False
        if path_resolver and project_context and value.startswith('@'):
            try:
                resolved_path = path_resolver.resolve_path(value, project_context)
                was_alias_resolved = True
            except Exception as e:
                raise ValueError(f"Failed to resolve path alias '{value}': {e}")

        # Convert to Path object for better handling
        # If path was resolved from alias, use it directly as it's already properly resolved
        if was_alias_resolved or os.path.isabs(resolved_path):
            full_path = Path(resolved_path)
        elif base_path:
            full_path = Path(base_path) / resolved_path
        else:
            full_path = Path(resolved_path)

        # Validate extension if file_type specified - use resolved path for extension check
        if file_type and file_type in ValidationRegistry.VALID_EXTENSIONS:
            valid_exts = ValidationRegistry.VALID_EXTENSIONS[file_type]
            # Check extension on the resolved path, not the original alias
            if not any(str(full_path).lower().endswith(ext) for ext in valid_exts):
                raise ValueError(f"File must have one of these extensions: {valid_exts}")

        # Check existence if required
        if must_exist and not full_path.exists():
            raise ValueError(f"File does not exist: {full_path}")

        # Check file size for performance warnings
        if must_exist and full_path.exists() and full_path.is_file():
            file_size_mb = full_path.stat().st_size / (1024 * 1024)
            if file_size_mb > ValidationRegistry.PERFORMANCE_THRESHOLDS['max_file_size_mb']:
                raise ValueError(f"File size ({file_size_mb:.1f}MB) exceeds recommended maximum ({ValidationRegistry.PERFORMANCE_THRESHOLDS['max_file_size_mb']}MB)")

        # Handle output file directory creation
        if is_output_file and full_path.parent != full_path:
            if not full_path.parent.exists():
                try:
                    # Create the output directory if it doesn't exist
                    full_path.parent.mkdir(parents=True, exist_ok=True)
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
        """Validates linetype strings."""
        if value not in ValidationRegistry.VALID_LINETYPES:
            # Check for ACAD ISO pattern
            acad_pattern = r'^ACAD_ISO\d{2}W100$'
            if not re.match(acad_pattern, value):
                raise ValueError(f"Invalid linetype '{value}'. Valid linetypes: {ValidationRegistry.VALID_LINETYPES} or ACAD_ISOxxW100 pattern")
        return value

    @staticmethod
    def validate_positive_number(value: float, field_name: str = "value") -> float:
        """Validates positive numbers."""
        if value <= 0:
            raise ValueError(f"{field_name} must be positive, got {value}")
        return value

    @staticmethod
    def validate_non_negative_number(value: float, field_name: str = "value") -> float:
        """Validates non-negative numbers."""
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
        """Validates URL strings."""
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL format: {value}")
        return value

    @staticmethod
    def validate_column_name(value: str, available_columns: Optional[List[str]] = None) -> str:
        """Validates column names and suggests alternatives if not found."""
        if not value or not isinstance(value, str):
            raise ValueError("Column name must be a non-empty string")

        if available_columns and value not in available_columns:
            # Try case-insensitive match
            case_insensitive_matches = [col for col in available_columns if col.lower() == value.lower()]
            if case_insensitive_matches:
                raise ValueError(f"Column '{value}' not found. Did you mean '{case_insensitive_matches[0]}'? (case mismatch)")

            # Try fuzzy matching
            suggestion = ConfigValidators.suggest_closest_match(value, set(available_columns))
            if suggestion:
                raise ValueError(f"Column '{value}' not found. Did you mean '{suggestion}'?")
            else:
                raise ValueError(f"Column '{value}' not found. Available columns: {available_columns}")

        return value

    @staticmethod
    def validate_text_attachment_point(value: str) -> str:
        """Validates text attachment point values."""
        if value.upper() not in ValidationRegistry.VALID_TEXT_ATTACHMENT_POINTS:
            raise ValueError(f"Invalid attachment point '{value}'. Valid values: {ValidationRegistry.VALID_TEXT_ATTACHMENT_POINTS}")
        return value.upper()

    @staticmethod
    def validate_flow_direction(value: str) -> str:
        """Validates text flow direction values."""
        if value.upper() not in ValidationRegistry.VALID_FLOW_DIRECTIONS:
            raise ValueError(f"Invalid flow direction '{value}'. Valid values: {ValidationRegistry.VALID_FLOW_DIRECTIONS}")
        return value.upper()

    @staticmethod
    def validate_line_spacing_style(value: str) -> str:
        """Validates line spacing style values."""
        if value.upper() not in ValidationRegistry.VALID_LINE_SPACING_STYLES:
            raise ValueError(f"Invalid line spacing style '{value}'. Valid values: {ValidationRegistry.VALID_LINE_SPACING_STYLES}")
        return value.upper()

    @staticmethod
    def validate_cap_style(value: str) -> str:
        """Validates cap style for buffer operations."""
        if value.lower() not in ValidationRegistry.VALID_CAP_STYLES:
            raise ValueError(f"Invalid cap style '{value}'. Valid values: {ValidationRegistry.VALID_CAP_STYLES}")
        return value.lower()

    @staticmethod
    def validate_join_style(value: str) -> str:
        """Validates join style for buffer operations."""
        if value.lower() not in ValidationRegistry.VALID_JOIN_STYLES:
            raise ValueError(f"Invalid join style '{value}'. Valid values: {ValidationRegistry.VALID_JOIN_STYLES}")
        return value.lower()

    @staticmethod
    def validate_spatial_predicate(value: str) -> str:
        """Validates spatial predicate for filter operations."""
        if value.lower() not in ValidationRegistry.VALID_SPATIAL_PREDICATES:
            raise ValueError(f"Invalid spatial predicate '{value}'. Valid values: {ValidationRegistry.VALID_SPATIAL_PREDICATES}")
        return value.lower()

    @staticmethod
    def validate_buffer_distance(value: float, field_name: str = "buffer distance") -> float:
        """Validates buffer distance with performance warnings."""
        if value < 0:
            raise ValueError(f"{field_name} cannot be negative, got {value}")

        max_distance = ValidationRegistry.PERFORMANCE_THRESHOLDS['max_buffer_distance']
        if value > max_distance:
            raise ValueError(f"{field_name} ({value}) exceeds recommended maximum ({max_distance}) - may cause performance issues")

        return value

    @staticmethod
    def validate_operation_chain_length(operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validates operation chain length for performance."""
        max_length = ValidationRegistry.PERFORMANCE_THRESHOLDS['max_operation_chain_length']
        if len(operations) > max_length:
            raise ValueError(f"Operation chain length ({len(operations)}) exceeds recommended maximum ({max_length}) - may cause performance issues")
        return operations

    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return ConfigValidators.levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    @staticmethod
    def suggest_closest_match(unknown_key: str, valid_keys: set, max_distance: int = 2) -> Optional[str]:
        """Suggest the closest valid key for an unknown key."""
        if not valid_keys:
            return None

        closest_match = min(valid_keys, key=lambda x: ConfigValidators.levenshtein_distance(unknown_key, x))
        distance = ConfigValidators.levenshtein_distance(unknown_key, closest_match)

        if distance <= max_distance:
            return closest_match
        return None


class CrossFieldValidator:
    """Validators that check relationships between multiple fields."""

    @staticmethod
    def validate_output_paths_consistency(values: Dict[str, Any]) -> Dict[str, Any]:
        """Validates consistency between export format and output paths."""
        export_format = values.get('exportFormat', values.get('export_format'))

        if export_format == 'dxf':
            # Check new DXF configuration structure
            dxf_config = values.get('dxf')
            if not dxf_config or not dxf_config.get('outputPath', dxf_config.get('output_path')):
                raise ValueError("DXF export format requires dxf.outputPath to be specified")
        elif export_format == 'shp':
            if not values.get('shapefileOutputDir', values.get('shapefile_output_dir')):
                raise ValueError("Shapefile export format requires shapefileOutputDir to be specified")
        elif export_format == 'gpkg':
            if not values.get('outputGeopackagePath', values.get('output_geopackage_path')):
                raise ValueError("GeoPackage export format requires outputGeopackagePath to be specified")
        elif export_format == 'all':
            # For 'all' format, at least one output path should be specified
            dxf_config = values.get('dxf')
            dxf_output = dxf_config.get('outputPath', dxf_config.get('output_path')) if dxf_config else None

            has_output = any([
                dxf_output,
                values.get('shapefileOutputDir', values.get('shapefile_output_dir')),
                values.get('outputGeopackagePath', values.get('output_geopackage_path'))
            ])
            if not has_output:
                raise ValueError("Export format 'all' requires at least one output path to be specified")

        return values

    @staticmethod
    def validate_operation_layer_references(values: Dict[str, Any], available_layers: List[str]) -> Dict[str, Any]:
        """Validates that operation layer references exist."""
        operations = values.get('operations', [])

        for i, operation in enumerate(operations):
            if isinstance(operation, dict):
                # Check 'layers' field
                if 'layers' in operation:
                    layers = operation['layers']
                    if isinstance(layers, list):
                        for layer_ref in layers:
                            if isinstance(layer_ref, str) and layer_ref not in available_layers:
                                raise ValueError(f"Operation {i+1} references unknown layer: '{layer_ref}'")
                            elif isinstance(layer_ref, dict) and 'name' in layer_ref:
                                layer_name = layer_ref['name']
                                if layer_name not in available_layers:
                                    raise ValueError(f"Operation {i+1} references unknown layer: '{layer_name}'")

                # Check other layer reference fields
                layer_ref_fields = ['sourceLayer', 'overlay_layer', 'overlayLayer', 'layer']
                for field in layer_ref_fields:
                    if field in operation:
                        layer_ref = operation[field]
                        if isinstance(layer_ref, str) and layer_ref not in available_layers:
                            raise ValueError(f"Operation {i+1} field '{field}' references unknown layer: '{layer_ref}'")

        return values

    @staticmethod
    def validate_operation_dependencies(operations: List[Dict[str, Any]], layer_name: str) -> List[Dict[str, Any]]:
        """Validates operation dependencies and logical consistency."""
        for i, operation in enumerate(operations):
            op_type = operation.get('type')

            # Check for circular dependencies
            if 'layers' in operation:
                layers = operation['layers']
                if isinstance(layers, list) and layer_name in layers:
                    raise ValueError(f"Operation {i+1} creates circular dependency: layer '{layer_name}' references itself")

            # Check operation-specific dependencies
            if op_type in ['difference', 'intersection', 'union', 'symmetric_difference']:
                if 'overlay_layer' in operation or 'overlayLayer' in operation:
                    overlay = operation.get('overlay_layer', operation.get('overlayLayer'))
                    if overlay == layer_name:
                        raise ValueError(f"Operation {i+1}: overlay layer cannot be the same as the target layer")

        return operations

    @staticmethod
    def validate_style_consistency(style_config: Dict[str, Any], layer_name: str) -> Dict[str, Any]:
        """Validates style configuration consistency."""
        if isinstance(style_config, dict):
            # Check for conflicting style properties
            if 'layer' in style_config:
                layer_style = style_config['layer']
                if isinstance(layer_style, dict):
                    # Check for logical conflicts
                    if layer_style.get('frozen') and layer_style.get('plot'):
                        raise ValueError(f"Layer '{layer_name}': frozen layers should not be set to plot")

                    if layer_style.get('locked') and 'color' in layer_style:
                        # This is a warning, not an error
                        pass  # Could add to warnings list

        return style_config


class ConfigValidationService(IConfigValidation):
    """Service for comprehensive configuration validation."""

    def __init__(self, base_path: Optional[str] = None, path_resolver: Optional[IPathResolver] = None):
        self.base_path = base_path
        self.path_resolver = path_resolver
        self._validation_errors: List[str] = []
        self._validation_warnings: List[str] = []

    @property
    def validation_errors(self) -> List[str]:
        """Get the list of validation errors from the last validation run."""
        return self._validation_errors

    @property
    def validation_warnings(self) -> List[str]:
        """Get the list of validation warnings from the last validation run."""
        return self._validation_warnings

    def validate_project_config(self, config_data: Dict[str, Any],
                              config_file: Optional[str] = None) -> Dict[str, Any]:
        """Validates a complete project configuration."""
        self._validation_errors = []
        self._validation_warnings = []

        try:
            # Validate main project settings
            if 'main' in config_data:
                self._validate_main_settings(config_data['main'])

            # Validate geometry layers
            if 'geomLayers' in config_data or 'geom_layers' in config_data:
                geom_layers = config_data.get('geomLayers', config_data.get('geom_layers', []))
                layer_names = self._validate_geometry_layers(geom_layers, config_data)

                # Cross-validate operations against available layers
                for layer in geom_layers:
                    if 'operations' in layer:
                        try:
                            CrossFieldValidator.validate_operation_layer_references(
                                {'operations': layer['operations']}, layer_names
                            )
                            CrossFieldValidator.validate_operation_dependencies(
                                layer['operations'], layer.get('name', 'unknown')
                            )
                        except ValueError as e:
                            self._validation_errors.append(f"Layer '{layer.get('name', '?')}': {e}")

            # Validate legends
            if 'legends' in config_data:
                self._validate_legends(config_data['legends'])

            # Validate path aliases
            if 'pathAliases' in config_data:
                self._validate_path_aliases(config_data['pathAliases'])

            # Final validation
            if self._validation_errors:
                raise ConfigValidationError(
                    f"Configuration validation failed with {len(self._validation_errors)} errors",
                    config_file=config_file,
                    validation_errors=self._validation_errors
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
                self._validation_errors.append(f"main.crs: {e}")

        # Validate DXF configuration
        if 'dxf' in main_data:
            self._validate_dxf_config(main_data['dxf'])

        # Validate DXF version
        if 'dxfVersion' in main_data or 'dxf_version' in main_data:
            dxf_version = main_data.get('dxfVersion', main_data.get('dxf_version'))
            try:
                ConfigValidators.validate_dxf_version(dxf_version)
            except ValueError as e:
                self._validation_errors.append(f"main.dxf_version: {e}")

        # Validate export format
        if 'exportFormat' in main_data or 'export_format' in main_data:
            export_format = main_data.get('exportFormat', main_data.get('export_format'))
            try:
                ConfigValidators.validate_export_format(export_format)
            except ValueError as e:
                self._validation_errors.append(f"main.export_format: {e}")

        # Cross-field validation for output paths
        try:
            CrossFieldValidator.validate_output_paths_consistency(main_data)
        except ValueError as e:
            self._validation_errors.append(f"main settings: {e}")

        # Validate memory and performance settings
        if 'maxMemoryMb' in main_data or 'max_memory_mb' in main_data:
            max_memory = main_data.get('maxMemoryMb', main_data.get('max_memory_mb'))
            if isinstance(max_memory, (int, float)) and max_memory < 512:
                self._validation_warnings.append("main.max_memory_mb: Memory limit below 512MB may cause performance issues")

    def _validate_dxf_config(self, dxf_config: Dict[str, Any]) -> None:
        """Validates DXF configuration structure and consistency."""
        # Validate required output path
        if 'outputPath' not in dxf_config and 'output_path' not in dxf_config:
            self._validation_errors.append("dxf configuration: outputPath is required")
        else:
            output_path = dxf_config.get('outputPath', dxf_config.get('output_path'))
            try:
                ConfigValidators.validate_file_path(
                    output_path, 'dxf',
                    is_output_file=True,
                    base_path=self.base_path
                )
            except ValueError as e:
                self._validation_errors.append(f"dxf.outputPath: {e}")

        # Validate template path if provided
        if 'templatePath' in dxf_config or 'template_path' in dxf_config:
            template_path = dxf_config.get('templatePath', dxf_config.get('template_path'))
            try:
                ConfigValidators.validate_file_path(
                    template_path, 'dxf',
                    must_exist=True,
                    base_path=self.base_path
                )
            except ValueError as e:
                self._validation_errors.append(f"dxf.templatePath: {e}")

        # Validate input path if provided
        if 'inputPath' in dxf_config or 'input_path' in dxf_config:
            input_path = dxf_config.get('inputPath', dxf_config.get('input_path'))
            try:
                ConfigValidators.validate_file_path(
                    input_path, 'dxf',
                    must_exist=False,  # Don't require existence - orchestrator handles this
                    base_path=self.base_path
                )
            except ValueError as e:
                self._validation_errors.append(f"dxf.inputPath: {e}")

        # Validate mode if provided
        if 'mode' in dxf_config:
            mode = dxf_config['mode']
            valid_modes = ['create', 'update', 'template']
            if mode not in valid_modes:
                self._validation_errors.append(f"dxf.mode: '{mode}' is not valid. Must be one of: {valid_modes}")

        # Validate mode-specific requirements
        mode = dxf_config.get('mode', 'update')
        if mode == 'template':
            if 'templatePath' not in dxf_config and 'template_path' not in dxf_config:
                self._validation_errors.append("dxf configuration: templatePath is required when mode is 'template'")

    def _validate_geometry_layers(self, layers_data: List[Dict[str, Any]],
                                 full_config: Dict[str, Any]) -> List[str]:
        """Validates geometry layer definitions and returns layer names."""
        layer_names = []

        # Load available styles for validation
        available_styles = self._load_available_styles(full_config)

        for i, layer in enumerate(layers_data):
            layer_name = layer.get('name', f'layer_{i}')
            layer_names.append(layer_name)

            # Validate unknown keys with suggestions
            self._validate_layer_keys(layer, layer_name)

            # Validate data sources with file existence checking
            self._validate_layer_data_sources(layer, layer_name, full_config)

            # Validate style references
            self._validate_layer_style(layer, layer_name, available_styles)

            # Validate operations
            if 'operations' in layer:
                self._validate_operations(layer['operations'], f"layer '{layer_name}'")

            # Validate column references
            self._validate_layer_column_references(layer, layer_name)

            # Validate layer-specific settings
            self._validate_layer_specific_settings(layer, layer_name)

        # Check for duplicate layer names
        duplicates = [name for name in layer_names if layer_names.count(name) > 1]
        if duplicates:
            self._validation_errors.append(f"Duplicate layer names found: {list(set(duplicates))}")

        return layer_names

    def _validate_layer_keys(self, layer: Dict[str, Any], layer_name: str) -> None:
        """Validate layer keys and suggest corrections for typos."""
        unknown_keys = set(layer.keys()) - ValidationRegistry.VALID_GEOM_LAYER_KEYS

        if unknown_keys:
            for unknown_key in unknown_keys:
                suggestion = ConfigValidators.suggest_closest_match(
                    unknown_key, ValidationRegistry.VALID_GEOM_LAYER_KEYS
                )
                if suggestion:
                    self._validation_warnings.append(
                        f"Layer '{layer_name}': Unknown key '{unknown_key}'. Did you mean '{suggestion}'?"
                    )
                else:
                    self._validation_warnings.append(
                        f"Layer '{layer_name}': Unknown key '{unknown_key}'"
                    )

    def _validate_layer_data_sources(self, layer: Dict[str, Any], layer_name: str,
                                   full_config: Dict[str, Any]) -> None:
        """Validate layer data sources with file existence checking."""
        sources = [
            ('geojsonFile', 'geojson'),
            ('shapeFile', 'shapefile'),
            ('dxfLayer', None)  # DXF layer is just a string reference
        ]

        source_count = 0
        project_context = self._create_project_context(full_config)

        for source_key, file_type in sources:
            if source_key in layer or source_key.lower().replace('file', '_file') in layer:
                source_count += 1
                if file_type:  # File-based source
                    file_path = layer.get(source_key, layer.get(source_key.lower().replace('file', '_file')))
                    try:
                        ConfigValidators.validate_file_path(
                            file_path, file_type,
                            must_exist=True,  # Check file existence
                            base_path=self.base_path,
                            path_resolver=self.path_resolver,
                            project_context=project_context
                        )
                    except ValueError as e:
                        # Create more user-friendly error message for missing files
                        error_msg = str(e)
                        if "File does not exist" in error_msg:
                            self._validation_errors.append(
                                f"Layer '{layer_name}' {source_key}: File does not exist: {file_path}"
                            )
                        else:
                            self._validation_errors.append(f"Layer '{layer_name}' {source_key}: {e}")

        if source_count == 0:
            # Check if this is an operations-only layer
            if 'operations' not in layer:
                self._validation_errors.append(f"Layer '{layer_name}': no valid data source specified")
        elif source_count > 1:
            self._validation_errors.append(f"Layer '{layer_name}': multiple data sources specified (only one allowed)")

    def _validate_layer_style(self, layer: Dict[str, Any], layer_name: str,
                            available_styles: Dict[str, Any]) -> None:
        """Validate layer style references and inline styles."""
        if 'style' not in layer:
            return

        style = layer['style']

        if isinstance(style, str):
            # Style preset reference
            if style not in available_styles:
                suggestion = ConfigValidators.suggest_closest_match(style, set(available_styles.keys()))
                if suggestion:
                    self._validation_errors.append(
                        f"Layer '{layer_name}': Style preset '{style}' not found. Did you mean '{suggestion}'?"
                    )
                else:
                    self._validation_errors.append(
                        f"Layer '{layer_name}': Style preset '{style}' not found"
                    )

        elif isinstance(style, dict):
            # Inline style or style with preset
            if 'preset' in style:
                preset_name = style['preset']
                if preset_name not in available_styles:
                    suggestion = ConfigValidators.suggest_closest_match(preset_name, set(available_styles.keys()))
                    if suggestion:
                        self._validation_errors.append(
                            f"Layer '{layer_name}': Style preset '{preset_name}' not found. Did you mean '{suggestion}'?"
                        )
                    else:
                        self._validation_errors.append(
                            f"Layer '{layer_name}': Style preset '{preset_name}' not found"
                        )

            # Validate inline style structure
            self._validate_inline_style(style, layer_name)

            # Validate style consistency
            try:
                CrossFieldValidator.validate_style_consistency(style, layer_name)
            except ValueError as e:
                self._validation_errors.append(f"Layer '{layer_name}': {e}")

    def _validate_inline_style(self, style: Dict[str, Any], layer_name: str) -> None:
        """Validate inline style structure and properties."""
        for style_type, style_props in style.items():
            if style_type in ['preset']:  # Skip non-style keys
                continue

            if style_type not in ValidationRegistry.VALID_STYLE_TYPES:
                suggestion = ConfigValidators.suggest_closest_match(
                    style_type, set(ValidationRegistry.VALID_STYLE_TYPES.keys())
                )
                if suggestion:
                    self._validation_warnings.append(
                        f"Layer '{layer_name}': Unknown style type '{style_type}'. Did you mean '{suggestion}'?"
                    )
                else:
                    self._validation_warnings.append(
                        f"Layer '{layer_name}': Unknown style type '{style_type}'"
                    )
                continue

            if isinstance(style_props, dict):
                valid_props = ValidationRegistry.VALID_STYLE_TYPES[style_type]
                unknown_props = set(style_props.keys()) - valid_props

                for unknown_prop in unknown_props:
                    suggestion = ConfigValidators.suggest_closest_match(unknown_prop, valid_props)
                    if suggestion:
                        self._validation_warnings.append(
                            f"Layer '{layer_name}' {style_type} style: Unknown property '{unknown_prop}'. Did you mean '{suggestion}'?"
                        )
                    else:
                        self._validation_warnings.append(
                            f"Layer '{layer_name}' {style_type} style: Unknown property '{unknown_prop}'"
                        )

                # Validate specific style properties
                self._validate_style_properties(style_props, style_type, layer_name)

    def _validate_style_properties(self, style_props: Dict[str, Any], style_type: str, layer_name: str) -> None:
        """Validate specific style property values."""
        if style_type == 'text':
            # Validate text-specific properties
            if 'attachmentPoint' in style_props:
                try:
                    ConfigValidators.validate_text_attachment_point(style_props['attachmentPoint'])
                except ValueError as e:
                    self._validation_errors.append(f"Layer '{layer_name}' text style: {e}")

            if 'flowDirection' in style_props:
                try:
                    ConfigValidators.validate_flow_direction(style_props['flowDirection'])
                except ValueError as e:
                    self._validation_errors.append(f"Layer '{layer_name}' text style: {e}")

            if 'lineSpacingStyle' in style_props:
                try:
                    ConfigValidators.validate_line_spacing_style(style_props['lineSpacingStyle'])
                except ValueError as e:
                    self._validation_errors.append(f"Layer '{layer_name}' text style: {e}")

            if 'height' in style_props:
                try:
                    ConfigValidators.validate_positive_number(style_props['height'], 'text height')
                except ValueError as e:
                    self._validation_errors.append(f"Layer '{layer_name}' text style: {e}")

        elif style_type == 'layer':
            # Validate layer-specific properties
            if 'linetype' in style_props:
                try:
                    ConfigValidators.validate_linetype(style_props['linetype'])
                except ValueError as e:
                    self._validation_errors.append(f"Layer '{layer_name}' layer style: {e}")

            if 'transparency' in style_props:
                try:
                    ConfigValidators.validate_percentage(style_props['transparency'], 'transparency')
                except ValueError as e:
                    self._validation_errors.append(f"Layer '{layer_name}' layer style: {e}")

    def _validate_layer_column_references(self, layer: Dict[str, Any], layer_name: str) -> None:
        """Validate column references in layer configuration."""
        # Note: We can't validate against actual file columns here since we don't load the files
        # But we can validate the column name format and common patterns

        column_fields = ['labelColumn', 'label_column', 'label']
        for field in column_fields:
            if field in layer:
                column_name = layer[field]
                if not isinstance(column_name, str) or not column_name.strip():
                    self._validation_errors.append(f"Layer '{layer_name}': {field} must be a non-empty string")

        # Validate selectByProperties column references
        if 'selectByProperties' in layer:
            select_props = layer['selectByProperties']
            if isinstance(select_props, dict):
                for prop_name, prop_value in select_props.items():
                    if not isinstance(prop_name, str) or not prop_name.strip():
                        self._validation_errors.append(f"Layer '{layer_name}': selectByProperties property name must be a non-empty string")

    def _validate_layer_specific_settings(self, layer: Dict[str, Any], layer_name: str) -> None:
        """Validate layer-specific settings and configurations."""
        # Validate boolean settings
        boolean_fields = ['updateDxf', 'close', 'plot', 'applyHatch']
        for field in boolean_fields:
            if field in layer and not isinstance(layer[field], bool):
                self._validation_warnings.append(f"Layer '{layer_name}': {field} should be a boolean value")

        # Validate numeric settings
        if 'linetypeScale' in layer:
            try:
                ConfigValidators.validate_positive_number(layer['linetypeScale'], 'linetypeScale')
            except ValueError as e:
                self._validation_errors.append(f"Layer '{layer_name}': {e}")

    def _validate_operations(self, operations: List[Dict[str, Any]], context: str) -> None:
        """Validates operation definitions."""
        # Validate operation chain length
        try:
            ConfigValidators.validate_operation_chain_length(operations)
        except ValueError as e:
            self._validation_warnings.append(f"{context}: {e}")

        for i, operation in enumerate(operations):
            op_context = f"{context} operation[{i}]"

            # Validate operation type
            if 'type' not in operation:
                self._validation_errors.append(f"{op_context}: missing 'type' field")
                continue

            op_type = operation['type']

            # Check if operation type is valid
            if op_type not in ValidationRegistry.VALID_OPERATION_TYPES:
                suggestion = ConfigValidators.suggest_closest_match(
                    op_type, ValidationRegistry.VALID_OPERATION_TYPES
                )
                if suggestion:
                    self._validation_errors.append(
                        f"{op_context}: Unknown operation type '{op_type}'. Did you mean '{suggestion}'?"
                    )
                else:
                    self._validation_errors.append(
                        f"{op_context}: Unknown operation type '{op_type}'"
                    )
                continue

            # Type-specific validation
            self._validate_operation_parameters(operation, op_context)

    def _validate_operation_parameters(self, operation: Dict[str, Any], op_context: str) -> None:
        """Validate operation-specific parameters."""
        op_type = operation['type']

        if op_type == 'buffer':
            if 'distance' not in operation and 'distanceField' not in operation:
                self._validation_errors.append(f"{op_context}: buffer operation requires 'distance' or 'distanceField'")

            if 'distance' in operation:
                try:
                    ConfigValidators.validate_buffer_distance(operation['distance'], 'buffer distance')
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: {e}")

            # Validate buffer-specific parameters
            if 'cap_style' in operation:
                try:
                    ConfigValidators.validate_cap_style(operation['cap_style'])
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: {e}")

            if 'join_style' in operation:
                try:
                    ConfigValidators.validate_join_style(operation['join_style'])
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: {e}")

            if 'resolution' in operation:
                try:
                    ConfigValidators.validate_positive_number(operation['resolution'], 'buffer resolution')
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: {e}")

        elif op_type in ['translate', 'scale', 'rotate']:
            # Validate transformation parameters
            if op_type == 'translate':
                for param in ['dx', 'dy']:
                    if param in operation and not isinstance(operation[param], (int, float)):
                        self._validation_errors.append(f"{op_context}: {param} must be a number")

            elif op_type == 'scale':
                for param in ['xfact', 'yfact', 'scale_x', 'scale_y']:
                    if param in operation:
                        try:
                            ConfigValidators.validate_positive_number(operation[param], f'scale {param}')
                        except ValueError as e:
                            self._validation_errors.append(f"{op_context}: {e}")

            elif op_type == 'rotate':
                if 'angle' not in operation:
                    self._validation_errors.append(f"{op_context}: rotate operation requires 'angle' field")

        elif op_type == 'filter':
            if 'spatial_predicate' in operation:
                try:
                    ConfigValidators.validate_spatial_predicate(operation['spatial_predicate'])
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: {e}")

        elif op_type == 'transform':
            if 'target_crs' in operation:
                try:
                    ConfigValidators.validate_crs(operation['target_crs'])
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: target_crs {e}")

            if 'source_crs' in operation:
                try:
                    ConfigValidators.validate_crs(operation['source_crs'])
                except ValueError as e:
                    self._validation_errors.append(f"{op_context}: source_crs {e}")

        elif op_type in ['difference', 'intersection', 'union', 'symmetric_difference']:
            if 'layers' not in operation and 'overlay_layer' not in operation and 'overlayLayer' not in operation:
                self._validation_errors.append(f"{op_context}: {op_type} operation requires 'layers' or 'overlay_layer' field")

    def _validate_legends(self, legends_data: List[Dict[str, Any]]) -> None:
        """Validates legend definitions."""
        for i, legend in enumerate(legends_data):
            legend_context = f"legend[{i}]"

            # Validate required fields
            if 'name' not in legend:
                self._validation_errors.append(f"{legend_context}: missing 'name' field")

            if 'position' not in legend:
                self._validation_errors.append(f"{legend_context}: missing 'position' field")
            else:
                # Validate position coordinates
                position = legend['position']
                if not isinstance(position, (list, tuple)) or len(position) != 2:
                    self._validation_errors.append(f"{legend_context}: position must be [x, y] coordinates")
                else:
                    try:
                        x, y = position
                        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                            self._validation_errors.append(f"{legend_context}: position coordinates must be numbers")
                    except (ValueError, TypeError):
                        self._validation_errors.append(f"{legend_context}: invalid position format")

            # Validate legend items
            if 'items' in legend:
                if not isinstance(legend['items'], list):
                    self._validation_errors.append(f"{legend_context}: 'items' must be a list")
                else:
                    for j, item in enumerate(legend['items']):
                        if not isinstance(item, dict) or 'text' not in item:
                            self._validation_errors.append(f"{legend_context} item[{j}]: must have 'text' field")

    def _validate_path_aliases(self, path_aliases: Dict[str, Any]) -> None:
        """Validate path alias definitions."""
        if not isinstance(path_aliases, dict):
            self._validation_errors.append("pathAliases must be a dictionary")
            return

        # Check for circular references and invalid paths
        for alias_name, alias_path in path_aliases.items():
            if not isinstance(alias_name, str) or not alias_name.strip():
                self._validation_errors.append("Path alias names must be non-empty strings")
                continue

            if isinstance(alias_path, str):
                # Simple alias - only warn about '..' if it appears to be unsafe
                if '..' in alias_path:
                    # Check if this is a legitimate relative path within project structure
                    if self._is_legitimate_relative_path(alias_path):
                        # This is a legitimate project structure path, no warning needed
                        pass
                    else:
                        self._validation_warnings.append(f"Path alias '{alias_name}' contains '..' which may be a security risk")
            elif isinstance(alias_path, dict):
                # Nested alias structure - will be flattened
                self._validate_nested_path_aliases(alias_path, alias_name)
            else:
                self._validation_errors.append(f"Path alias '{alias_name}' must be a string or dictionary")

    def _validate_nested_path_aliases(self, nested_aliases: Dict[str, Any], parent_name: str) -> None:
        """Validate nested path alias structures."""
        for key, value in nested_aliases.items():
            full_name = f"{parent_name}.{key}"

            if isinstance(value, str):
                if '..' in value:
                    # Check if this is a legitimate relative path within project structure
                    if self._is_legitimate_relative_path(value):
                        # This is a legitimate project structure path, no warning needed
                        pass
                    else:
                        self._validation_warnings.append(f"Path alias '{full_name}' contains '..' which may be a security risk")
            elif isinstance(value, dict):
                self._validate_nested_path_aliases(value, full_name)
            else:
                self._validation_errors.append(f"Path alias '{full_name}' must be a string or dictionary")

    def _is_legitimate_relative_path(self, path: str) -> bool:
        """Check if a path with '..' is a legitimate relative path within project structure."""
        # Allow paths that go up to access shared project data
        # These patterns are common in well-structured projects:
        # - "../../data/file.geojson" (accessing shared data)
        # - "../../external_data/file.geojson" (accessing external data)
        # - "../../reference_files/file.geojson" (accessing reference files)
        # - "../templates/styles" (accessing shared templates)

        # Normalize the path to check for legitimate patterns
        normalized_path = path.replace('\\', '/').lower()

        # Allow common project structure patterns
        legitimate_patterns = [
            '../../data/',
            '../../external_data/',
            '../../reference_files/',
            '../templates/',
            '../../styles.',
            '../../test_data.',
            '../../road_network.',
        ]

        # Check if the path starts with any legitimate pattern
        for pattern in legitimate_patterns:
            if normalized_path.startswith(pattern):
                return True

        # Also allow simple relative paths that don't go too far up
        # Count the number of '../' sequences
        parent_dir_count = normalized_path.count('../')
        if parent_dir_count <= 2:  # Allow up to 2 levels up
            return True

        return False

    def _load_available_styles(self, full_config: Dict[str, Any]) -> Dict[str, Any]:
        """Load available styles from the configuration context."""
        available_styles = {}

        # Check if styles are embedded in the config
        if 'styles' in full_config:
            available_styles.update(full_config['styles'])

        # Load from external style files using path resolver
        if 'main' in full_config and 'stylePresetsFile' in full_config['main']:
            style_file_path = full_config['main']['stylePresetsFile']

            # Resolve path alias if needed
            if self.path_resolver and style_file_path.startswith('@'):
                try:
                    project_context = self._create_project_context(full_config)
                    resolved_path = self.path_resolver.resolve_path(style_file_path, project_context)

                    # Use resolved path directly since path resolver returns absolute paths
                    full_path = Path(resolved_path)

                    if full_path.exists():
                        import yaml
                        with open(full_path, 'r', encoding='utf-8') as f:
                            style_data = yaml.safe_load(f)
                            if isinstance(style_data, dict) and 'styles' in style_data:
                                available_styles.update(style_data['styles'])
                except Exception as e:
                    # Log error but don't fail validation
                    self._validation_warnings.append(f"Failed to load style file '{style_file_path}': {e}")

        return available_styles

    def _create_project_context(self, full_config: Dict[str, Any]):
        """Create project context for path resolution."""
        from ..domain.path_models import ProjectPathAliases, PathResolutionContext

        # Extract path aliases from config
        path_aliases_data = full_config.get('pathAliases', {})

        # Create ProjectPathAliases object
        project_aliases = ProjectPathAliases(aliases=path_aliases_data)

        # Extract project name from base_path if available, otherwise use fallback
        project_name = "unknown_project"
        if self.base_path:
            # Extract project name from base_path (e.g., "projects/test_project" -> "test_project")
            base_path_parts = Path(self.base_path).parts
            if len(base_path_parts) >= 2 and base_path_parts[-2] == "projects":
                project_name = base_path_parts[-1]

        # Create PathResolutionContext
        # Convert base_path to absolute path to prevent double directory issues
        absolute_project_root = os.path.abspath(self.base_path) if self.base_path else os.path.abspath(".")

        context = PathResolutionContext(
            project_name=project_name,
            project_root=absolute_project_root,
            aliases=project_aliases
        )
        return context


def validate_config_with_schema(config_data: Dict[str, Any],
                               config_type: str,
                               config_file: Optional[str] = None,
                               base_path: Optional[str] = None,
                               path_resolver: Optional[IPathResolver] = None) -> Dict[str, Any]:
    """Main entry point for configuration validation."""
    validator = ConfigValidationService(base_path=base_path, path_resolver=path_resolver)

    if config_type == 'project':
        return validator.validate_project_config(config_data, config_file)
    else:
        raise ValueError(f"Unknown configuration type: {config_type}")
