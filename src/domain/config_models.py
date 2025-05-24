"""Application configuration models following PROJECT_ARCHITECTURE.MD specification."""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pydantic_settings import BaseSettings
from enum import Enum

from .common_types import CoordinateReferenceSystem
from .project_models import (
    ProjectMainSettings, LegendDefinition, GlobalProjectSettings,
    SpecificProjectConfig, ExportFormat, DXFVersion
)
from .style_models import (
    StyleConfig, NamedStyle, LayerStyleProperties, TextStyleProperties,
    HatchStyleProperties, AciColorMappingItem, ColorConfig, TextAttachmentPoint
)
from .geometry_models import (
    GeomLayerDefinition, AllOperationParams, BufferOperationParams,
    FilterOperationParams, TransformOperationParams, OperationType, GeometryType,
    TranslateOpParams, RotateOpParams, ScaleOpParams, BufferOpParams,
    DifferenceOpParams, IntersectionOpParams, UnionOpParams, SymmetricDifferenceOpParams,
    BoundingBoxOpParams, EnvelopeOpParams, OffsetCurveOpParams, CreateCirclesOpParams,
    ConnectPointsOpParams, ContourOpParams, WmtsOpParams, WmsOpParams
)


class AppConfig(BaseSettings):
    """Application configuration loaded from environment variables and .env files."""
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Core paths
    projects_root_dir: str = Field(default="projects", alias="PROJECTS_ROOT_DIR")
    global_styles_file: str = Field(default="styles.yaml", alias="GLOBAL_STYLES_FILE")
    aci_colors_file: str = Field(default="aci_colors.yaml", alias="ACI_COLORS_FILE")

    # Logging configuration
    log_level_console: str = Field(default="INFO", alias="LOG_LEVEL_CONSOLE")
    log_level_file: Optional[str] = Field(default="DEBUG", alias="LOG_LEVEL_FILE")
    log_file_path: Optional[str] = Field(default="logs/app.log", alias="LOG_FILE_PATH")

    # Processing configuration
    max_memory_mb: float = Field(default=1024.0, alias="MAX_MEMORY_MB")
    temp_dir: Optional[str] = Field(default=None, alias="TEMP_DIR")

    # Feature flags
    enable_validation: bool = Field(default=True, alias="ENABLE_VALIDATION")
    enable_memory_optimization: bool = Field(default=True, alias="ENABLE_MEMORY_OPTIMIZATION")
    enable_parallel_processing: bool = Field(default=False, alias="ENABLE_PARALLEL_PROCESSING")

    @field_validator('log_level_console', 'log_level_file')
    @classmethod
    def validate_log_levels(cls, v):
        """Validate log levels are valid."""
        if v is None:
            return v
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}, got {v}")
        return v.upper()


# Re-export all domain models for backward compatibility
__all__ = [
    # App configuration
    "AppConfig",

    # Project models
    "ProjectMainSettings",
    "LegendDefinition",
    "GlobalProjectSettings",
    "SpecificProjectConfig",
    "ExportFormat",
    "DXFVersion",

    # Style models
    "StyleConfig",
    "NamedStyle",
    "LayerStyleProperties",
    "TextStyleProperties",
    "HatchStyleProperties",
    "AciColorMappingItem",
    "ColorConfig",
    "TextAttachmentPoint",

    # Geometry models
    "GeomLayerDefinition",
    "AllOperationParams",
    "BufferOperationParams",
    "FilterOperationParams",
    "TransformOperationParams",
    "TranslateOpParams",
    "RotateOpParams",
    "ScaleOpParams",
    "BufferOpParams",
    "DifferenceOpParams",
    "IntersectionOpParams",
    "UnionOpParams",
    "SymmetricDifferenceOpParams",
    "BoundingBoxOpParams",
    "EnvelopeOpParams",
    "OffsetCurveOpParams",
    "CreateCirclesOpParams",
    "ConnectPointsOpParams",
    "ContourOpParams",
    "WmtsOpParams",
    "WmsOpParams",
    "OperationType",
    "GeometryType",

    # Common types
    "CoordinateReferenceSystem"
]
