from typing import Optional, List, Union, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
from enum import Enum
from .common_schemas import CRSModel

class DataSourceType(str, Enum):
    SHAPEFILE = "SHAPEFILE"
    GEOJSON = "GEOJSON"
    CSV_WKT = "CSV_WKT"
    # TODO: Add more as they are supported e.g. GEOPACKAGE = "GEOPACKAGE"

class BaseReaderConfig(BaseModel):
    """Base configuration for all data readers."""
    type: DataSourceType
    path: str
    crs: Optional[CRSModel] = Field(default=None, description="Source CRS. If not provided, attempts to infer or assumes project CRS.")
    encoding: str = Field(default="utf-8", description="File encoding.")
    attributes_to_include: Optional[List[str]] = Field(default=None, description="List of attribute fields to include. None means all.")
    attributes_to_exclude: Optional[List[str]] = Field(default=None, description="List of attribute fields to exclude. Applied after inclusion.")
    attribute_mapping: Optional[Dict[str, str]] = Field(default=None, description="Mapping of source attribute names to desired names, e.g., {'OLD_NAME': 'new_name'}")

class ShapefileSourceConfig(BaseReaderConfig):
    type: Literal[DataSourceType.SHAPEFILE] = DataSourceType.SHAPEFILE
    # Specific Shapefile options can be added here if needed

class GeoJSONSourceConfig(BaseReaderConfig):
    type: Literal[DataSourceType.GEOJSON] = DataSourceType.GEOJSON
    # Specific GeoJSON options can be added here if needed

class CsvWktReaderConfig(BaseReaderConfig):
    type: Literal[DataSourceType.CSV_WKT] = DataSourceType.CSV_WKT
    wkt_column: str = Field(default="wkt", description="Name of the column containing WKT geometry.")
    delimiter: str = Field(default=",", description="CSV delimiter.")
    # `crs` and `encoding` are inherited from BaseReaderConfig

AnySourceConfig = Union[
    ShapefileSourceConfig,
    GeoJSONSourceConfig,
    CsvWktReaderConfig,
]
