from typing import Protocol, List, Dict, Any, AsyncIterator, Optional, TypeVar, Tuple
from pathlib import Path

# Import domain models to be used in interface definitions
from .models.common import Coordinate, Color, BoundingBox
from .models.geo_models import GeoFeature #, PointGeo, PolylineGeo, PolygonGeo (GeoFeature contains these)
from .models.dxf_models import DxfEntity, DxfLayer, AnyDxfEntity # Added AnyDxfEntity explicitly
from ..config.schemas import LayerConfig, BaseOperationConfig # Added BaseOperationConfig

# Generic type for path-like objects, often used for file paths
AnyStrPath = TypeVar("AnyStrPath", str, Path)

# --- Data Reader Interfaces ---

class IGeoDataReader(Protocol):
    """Interface for reading geodata from various sources."""

    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None, # Optional target CRS for on-the-fly reprojection by reader
        **kwargs: Any # For additional reader-specific options
    ) -> AsyncIterator[GeoFeature]:
        """
        Reads geographic features from a given source.

        Args:
            source_path: Path to the geodata source file or resource.
            source_crs: Optional CRS of the source data (e.g., "EPSG:4326").
            target_crs: Optional target CRS to reproject features to during reading.
            **kwargs: Additional keyword arguments for specific reader implementations.

        Yields:
            GeoFeature: An asynchronous iterator of GeoFeature objects.
        """
        # This is a protocol, so the implementation is in concrete classes.
        # The `...` indicates that the body is not defined here.
        # For an async generator, we'd expect `yield` in the implementation.
        # To make the protocol checker happy with an async generator method:
        if False: # pragma: no cover
            yield
        ...

# --- Data Writer Interfaces ---

class IDxfWriter(Protocol):
    """Interface for writing DXF entities to a file."""

    async def write_drawing(
        self,
        file_path: AnyStrPath,
        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]],
        # layers: Optional[List[DxfLayer]] = None, # Superseded by LayerConfig driven creation
        # target_dxf_version: Optional[str] = None, # Now part of DxfWriterConfig
        **kwargs: Any # For additional writer-specific options
    ) -> None:
        """
        Writes DXF entities to a specified file path.

        Args:
            file_path: The path to the output DXF file.
            entities_by_layer_config: A dictionary where keys are layer names (strings)
                                      and values are tuples containing the LayerConfig
                                      for that layer and an async iterator of AnyDxfEntity
                                      objects belonging to that layer.
            **kwargs: Additional keyword arguments for specific writer implementations.
        """
        ...

# --- Geometry Processing & Transformation Interfaces ---

class IGeometryTransformer(Protocol):
    """Interface for transforming GeoFeatures into DXF entities."""

    async def transform_feature_to_dxf_entities(
        self,
        feature: GeoFeature,
        # target_crs: Optional[str] = None, # Target CRS for coordinate transformation -- REMOVED
        # layer_mapping_config: Optional[Dict[str, Any]] = None, # Config for layer assignment
        # attribute_mapping_config: Optional[Dict[str, Any]] = None # Config for attribute to DXF prop mapping
        **kwargs: Any
    ) -> AsyncIterator[DxfEntity]:
        """
        Transforms a single GeoFeature into one or more DxfEntity objects.
        This may involve coordinate transformation, geometry simplification,
        and mapping attributes to DXF properties (like layer, color, text content).

        Args:
            feature: The GeoFeature object to transform.
            # target_crs: The target coordinate reference system for the DXF entities. -- REMOVED
            **kwargs: Additional arguments for transformation logic.

        Yields:
            DxfEntity: An asynchronous iterator of resulting DxfEntity objects.
        """
        if False: # pragma: no cover
            yield
        ...

# --- Core Service Interfaces (abstractions for application logic) ---

class ICoordinateService(Protocol):
    """Interface for coordinate reference system operations."""

    def reproject_coordinate(self, coord: Coordinate, from_crs: str, to_crs: str) -> Coordinate:
        """Reprojects a single coordinate from a source CRS to a target CRS."""
        ...

    async def reproject_coordinates_batch(self, coords: List[Coordinate], from_crs: str, to_crs: str) -> List[Coordinate]:
        """Reprojects a list of coordinates in batch."""
        ...

    # Could also add methods for reprojecting entire geometries (GeoFeature) if needed here
    # or keep that responsibility within IGeometryTransformer or a dedicated geometry service.

class IAttributeMapper(Protocol):
    """Interface for mapping GeoFeature attributes to DXF entity properties."""

    def get_dxf_layer_for_feature(self, feature: GeoFeature) -> str:
        """Determines the DXF layer name for a given GeoFeature based on its attributes and mapping rules."""
        ...

    def get_dxf_properties_for_feature(self, feature: GeoFeature) -> Dict[str, Any]:
        """
        Determines DXF visual properties (e.g., color, linetype, text style, text content)
        for a GeoFeature based on its attributes and mapping rules.

        Returns:
            A dictionary of DXF properties (e.g., {"color_256": 1, "text_content": "foo"}).
        """
        ...

class IValidationService(Protocol):
    """Interface for validating data (e.g., input geodata, configuration)."""

    async def validate_geofeature(self, feature: GeoFeature, rules: Optional[Dict[str, Any]] = None) -> List[str]:
        """Validates a single GeoFeature. Returns a list of validation error messages (empty if valid)."""
        ...

    # async def validate_config(self, config_data: Dict[str, Any], schema: Any) -> List[str]:
    #     """Validates configuration data against a schema."""
    #     ...

# Interface for the main orchestration service
class IDxfGenerationService(Protocol):
    """Interface for the main service orchestrating DXF generation."""

    async def generate_dxf_from_source(
        self,
        # source_geodata_path: AnyStrPath, # Removed
        output_dxf_path: AnyStrPath,
        # source_crs: Optional[str] = None, # Removed
        target_crs: Optional[str] = None,
        # specific_reader_options: Optional[Dict[str, Any]] = None,
        # specific_writer_options: Optional[Dict[str, Any]] = None,
        # specific_transformer_options: Optional[Dict[str, Any]] = None
        **kwargs: Any # Catch-all for future or less common options
    ) -> None:
        """
        Orchestrates the full workflow: read geodata, transform, write DXF.

        Args:
            output_dxf_path: Path for the generated DXF file.
            target_crs: Optional target CRS for the DXF output.
            **kwargs: Further options passed down to readers, transformers, writers.
        """
        ...

# --- Data Processing Operation Interface ---

TOperationConfig = TypeVar('TOperationConfig', bound='BaseOperationConfig')

class IOperation(Protocol[TOperationConfig]):
    """Interface for a single data processing operation."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: TOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the operation on a stream of geographic features.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: The specific configuration for this operation instance.

        Yields:
            GeoFeature: An asynchronous iterator of resulting GeoFeature objects.
        """
        if False: # pragma: no cover
            yield
        ...
