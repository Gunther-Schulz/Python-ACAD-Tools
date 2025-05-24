"""Project-related domain models following PROJECT_ARCHITECTURE.MD specification."""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum

from .common_types import CoordinateReferenceSystem


class ExportFormat(str, Enum):
    """Supported export formats."""
    DXF = "dxf"
    SHAPEFILE = "shp"
    GEOPACKAGE = "gpkg"
    ALL = "all"


class DXFVersion(str, Enum):
    """Supported DXF versions."""
    R12 = "R12"
    R2000 = "R2000"
    R2004 = "R2004"
    R2007 = "R2007"
    R2010 = "R2010"
    R2013 = "R2013"
    R2018 = "R2018"


class ProjectMainSettings(BaseModel):
    """Core project settings, typically from project.yaml."""
    model_config = ConfigDict(extra='ignore')

    crs: CoordinateReferenceSystem
    dxf_filename: str = Field(alias='dxfFilename')
    template: Optional[str] = None
    export_format: ExportFormat = Field(default=ExportFormat.DXF, alias='exportFormat')
    dxf_version: DXFVersion = Field(default=DXFVersion.R2010, alias='dxfVersion')
    style_presets_file: Optional[str] = Field(default="styles.yaml", alias='stylePresetsFile')
    shapefile_output_dir: Optional[str] = Field(None, alias='shapefileOutputDir')
    output_dxf_path: Optional[str] = Field(None, alias='outputDxfPath')
    output_geopackage_path: Optional[str] = Field(None, alias='outputGeopackagePath')


class LegendDefinition(BaseModel):
    """Definition for map legends."""
    model_config = ConfigDict(extra='ignore')

    name: str
    title: Optional[str] = None
    position: Optional[Dict[str, float]] = None
    style: Optional[str] = None


class GlobalProjectSettings(BaseModel):
    """Global project settings that apply across all projects."""
    model_config = ConfigDict(extra='ignore')

    default_crs: CoordinateReferenceSystem = "EPSG:4326"
    default_dxf_version: DXFVersion = DXFVersion.R2010
    default_export_format: ExportFormat = ExportFormat.DXF
    global_styles_enabled: bool = True
    validation_enabled: bool = True


class SpecificProjectConfig(BaseModel):
    """Complete configuration for a specific project."""
    model_config = ConfigDict(extra='ignore')

    main: ProjectMainSettings
    geom_layers: List['GeomLayerDefinition'] = Field(default_factory=list, alias='geomLayers')
    legends: List[LegendDefinition] = Field(default_factory=list)
    project_specific_styles: Optional[Dict[str, Any]] = Field(None, alias='projectSpecificStyles')

    # Additional project components (to be expanded)
    viewports: List[Dict[str, Any]] = Field(default_factory=list)
    block_inserts: List[Dict[str, Any]] = Field(default_factory=list, alias='blockInserts')
    text_inserts: List[Dict[str, Any]] = Field(default_factory=list, alias='textInserts')
    path_arrays: List[Dict[str, Any]] = Field(default_factory=list, alias='pathArrays')
    wmts_layers: List[Dict[str, Any]] = Field(default_factory=list, alias='wmtsLayers')
    wms_layers: List[Dict[str, Any]] = Field(default_factory=list, alias='wmsLayers')
    dxf_operations: Optional[Dict[str, Any]] = Field(None, alias='dxfOperations')


# Forward reference resolution
from .geometry_models import GeomLayerDefinition
