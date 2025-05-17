from typing import List, Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
import ezdxf
from ezdxf.lldxf.const import DXFError

from dxfplanner.domain.models.geo_models import GeoFeature, AnyGeoGeometry
from dxfplanner.domain.interfaces import IValidationService, AnyStrPath
from dxfplanner.config.schemas import ProjectConfig
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.utils import convert_dxfplanner_geometry_to_shapely
from dxfplanner.core.exceptions import ConfigurationError

# Conditional import for shapely to avoid hard dependency if not used elsewhere,
# but for geometry validation, it's a strong candidate for direct import.
if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry

logger = get_logger(__name__)

class ValidationService(IValidationService):
    """Service for validating data (e.g., input geodata, configuration)."""

    async def validate_geofeature(self, feature: GeoFeature, rules: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Validates a single GeoFeature. Returns a list of validation error messages (empty if valid).
        Currently performs basic geometry checks (validity, emptiness) using Shapely.
        The 'rules' parameter is not yet used.
        """
        errors: List[str] = []
        feature_id = feature.id or '(unknown_id)'

        if rules:
            logger.info(f"'rules' parameter provided to validate_geofeature for feature {feature_id}, but rule-based validation is not yet implemented beyond basic geometry checks.")

        if feature.geometry is None:
            errors.append(f"Feature '{feature_id}' has no geometry.")
            return errors

        try:
            shapely_geom: Optional[BaseGeometry] = convert_dxfplanner_geometry_to_shapely(feature.geometry)
        except Exception as e:
            errors.append(f"Feature '{feature_id}': Error converting geometry to Shapely: {e}")
            return errors

        if shapely_geom is None:
            errors.append(f"Feature '{feature_id}': Geometry conversion to Shapely resulted in None.")
            return errors

        if not shapely_geom.is_valid:
            errors.append(f"Feature '{feature_id}': Geometry is not valid according to Shapely.")

        if shapely_geom.is_empty:
            errors.append(f"Feature '{feature_id}': Geometry is empty according to Shapely.")

        if errors:
            logger.debug(f"Validation errors for feature '{feature_id}': {errors}")
        return errors

    async def validate_config(self, config: ProjectConfig) -> None:
        """
        Validates the application configuration.
        Pydantic performs schema validation and type checking during ProjectConfig model instantiation.
        If ProjectConfig is successfully created and passed to this method,
        it has already passed Pydantic's validation.

        This method serves as a hook for future, more complex cross-configuration
        validation rules or business logic checks that go beyond Pydantic's capabilities.
        """
        # At this point, 'config' is a valid ProjectConfig instance according to Pydantic.
        logger.info(
            f"ProjectConfig validation: Pydantic schema and type validation already passed for "
            f"Project Name: '{config.project_name}'. No further custom cross-validation rules are currently implemented in this service."
        )

        # Example placeholder for future custom cross-validation:
        # if config.some_setting > 10 and config.another_setting < 5:
        #     raise ConfigurationError("Custom validation: some_setting and another_setting conflict.")
        pass

    async def validate_output_dxf(self, dxf_file_path: AnyStrPath) -> List[str]:
        """
        Validates an output DXF file by attempting to read it with ezdxf and running an audit.
        Returns a list of error messages if validation fails.
        """
        errors: List[str] = []
        file_path_str = str(dxf_file_path) # Ensure it's a string for ezdxf
        logger.info(f"Validating output DXF file: {file_path_str}")
        try:
            doc = ezdxf.readfile(file_path_str)
            logger.info(f"DXF file {file_path_str} loaded successfully by ezdxf (Header version: {doc.dxfversion}). Basic parsing validation passed.")

            # Perform a deeper audit of the DXF document structure
            logger.info(f"Performing ezdxf audit for {file_path_str}...")
            auditor = doc.audit()
            if auditor.has_errors:
                for error_msg_obj in auditor.errors: # auditor.errors contains error objects/messages
                    # Error objects might not be simple strings. Convert to string safely.
                    err_str = str(error_msg_obj) if error_msg_obj is not None else "Unknown audit error object"
                    errors.append(f"DXF Audit Error: {err_str}")
                logger.warning(f"DXF file {file_path_str} has {len(auditor.errors)} audit errors.")
            else:
                logger.info(f"DXF file {file_path_str} passed ezdxf audit with no errors.")

        except FileNotFoundError:
            error_msg = f"DXF validation failed: File not found at '{file_path_str}'."
            logger.error(error_msg)
            errors.append(error_msg)
        except DXFError as e: # Catch specific ezdxf errors (DXFStructureError, DXFVersionError, etc.)
            error_msg = f"DXF validation failed for '{file_path_str}': Invalid DXF structure or version - {e}."
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
        except Exception as e: # Catch any other unexpected errors during read
            error_msg = f"DXF validation failed for '{file_path_str}': Unexpected error during read - {e}."
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

        return errors
