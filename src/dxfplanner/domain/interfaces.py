from typing import Protocol, List, Dict, Any, AsyncIterator, Optional, TypeVar, Tuple, Union
from pathlib import Path
from pydantic import BaseModel # Added for PlacedLabel

# Import domain models to be used in interface definitions
from .models.common import Coordinate, Color, BoundingBox as BoundingBoxModel
from .models.geo_models import GeoFeature #, PointGeo, PolylineGeo, PolygonGeo (GeoFeature contains these)
from .models.dxf_models import DxfEntity, DxfLayer, AnyDxfEntity # Added AnyDxfEntity explicitly
from ..config.schemas import (
    ProjectConfig, # ADDED ProjectConfig
    LayerConfig, BaseOperationConfig, LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig, HatchPropertiesConfig, StyleObjectConfig, # Added StyleObjectConfig
    LabelPlacementOperationConfig, # Added LabelPlacementOperationConfig
    LayerStyleConfig # Added LayerStyleConfig
)
from ..config.style_schemas import LabelingConfig # Added LabelingConfig

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

    # --- Legend Generation Support Methods ---

    async def clear_legend_content(
        self,
        doc: Any, # ezdxf.document.Drawing
        msp: Any, # ezdxf.layouts.Modelspace
        legend_id: str
    ) -> None:
        """Removes entities associated with a specific legend ID."""
        ...

    async def get_entities_bbox(
        self,
        entities: List[Any]
    ) -> Optional[BoundingBoxModel]:
        """Calculates and returns the bounding box of a list of DXF entities."""
        ...

    async def translate_entities(
        self,
        entities: List[Any],
        dx: float, dy: float, dz: float
    ) -> None:
        """Translates a list of DXF entities by a given vector."""
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

    async def validate_config(self, config: ProjectConfig) -> None: # UPDATED from Any to ProjectConfig
        """Validates the application configuration."""
        ...

    async def validate_output_dxf(self, dxf_file_path: AnyStrPath) -> List[str]:
        """Validates the output DXF file."""
        ...

# --- Label Placement Service Model & Interface ---
class PlacedLabel(BaseModel):
    """Represents a label that has been placed, with its text, position, and rotation."""
    text: str
    position: Coordinate
    rotation: float # Degrees

class ILabelPlacementService(Protocol):
    """Interface for advanced label placement considering features and avoiding collisions."""

    async def place_labels_for_features(
        self,
        features: AsyncIterator[GeoFeature],
        layer_name: str,
        config: LabelingConfig,
        text_style_properties: TextStylePropertiesConfig,
        # TODO: Consider adding parameters for existing_placed_labels and avoidance_geometries
        # if iterative placement or external avoidance areas are needed.
    ) -> AsyncIterator[PlacedLabel]:
        """
        Calculates optimal placements for labels for a stream of geographic features.

        Args:
            features: An asynchronous iterator of GeoFeature objects to be labeled.
            layer_name: The name of the layer these features belong to, for context.
            config: Configuration specific to this label placement task (LabelingConfig).
            text_style_properties: The resolved text style properties for the labels.

        Yields:
            PlacedLabel: An asynchronous iterator of PlacedLabel objects.
        """
        if False: # pragma: no cover
            yield
        ...

# --- Orchestration & Pipeline Service Interfaces ---

# Interface for the main orchestration service
# Renamed from IDxfOrchestrator to IDxfGenerationService for consistency
# class IDxfOrchestrator(Protocol): # OLD NAME - TO BE REMOVED/REPLACED
class IDxfGenerationService(Protocol): # NEW NAME
    """Interface for the main service orchestrating the DXF generation pipeline."""

    async def generate_dxf_from_source(
        self,
        output_dxf_path: AnyStrPath,
        # target_crs: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        Orchestrates the full workflow: read geodata, transform, write DXF.

        Args:
            output_dxf_path: Path for the generated DXF file.
            # target_crs: Optional target CRS for the DXF output. # Commented out as DxfGenerationService doesn't use it.
            **kwargs: Further options passed down to readers, transformers, writers.
        """
        ...

# NEW: Interface for the Pipeline Service
class IPipelineService(Protocol):
    """Interface for the service that executes the main processing pipeline."""

    async def run_pipeline(
        self,
        output_dxf_path: str,
        **kwargs: Any
    ) -> None:
        """
        Runs the configured processing pipeline for all layers and generates DXF output.

        Args:
            output_dxf_path: The path to the output DXF file.
            **kwargs: Additional keyword arguments if pipeline needs them directly.
        """
        ...

# NEW: Interface for the Layer Processor Service
class ILayerProcessorService(Protocol):
    """Interface for the service that processes a single layer configuration."""

    async def process_layer(
        self,
        layer_config: LayerConfig,
    ) -> AsyncIterator[AnyDxfEntity]:
        """
        Processes a single layer configuration.

        Args:
            layer_config: The configuration for the layer to process.

        Yields:
            AnyDxfEntity: An asynchronous iterator of DXF entities generated for this layer.
        """
        if False: # pragma: no cover
            yield
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

# --- Legend Generation Interface ---

class ILegendGenerator(Protocol):
    """Interface for generating legends in a DXF document."""

    async def generate_legends(
        self,
        doc: Any, # ezdxf.document.Drawing
        msp: Any, # ezdxf.layouts.Modelspace
        # Configuration for legends will be injected via __init__ using AppConfig
        **kwargs: Any # For additional future options
    ) -> None:
        """
        Generates legends and adds them to the provided DXF document modelspace.

        Args:
            doc: The ezdxf Drawing document object.
            msp: The ezdxf Modelspace object where legend entities will be added.
            **kwargs: Additional keyword arguments for specific generation options.
        """
        ...

# --- Style Service Interface ---
class IStyleService(Protocol):
    """Interface for resolving and providing style configurations."""

    def get_resolved_style_object(
        self,
        preset_name: Optional[str] = None,
        inline_definition: Optional[StyleObjectConfig] = None,
        override_definition: Optional[StyleObjectConfig] = None,
        context_name: Optional[str] = None # For logging, e.g., layer name
    ) -> StyleObjectConfig:
        """
        Resolves a style object from a preset, inline definition, and optional overrides.
        The precedence is: inline_definition, then (preset + override_definition), then preset_name.
        An empty StyleObjectConfig with default component properties is returned if no definitive style information is found.
        """
        ...

    def get_layer_display_properties(
        self,
        layer_config: LayerConfig
    ) -> LayerDisplayPropertiesConfig:
        """
        Resolves and returns the final LayerDisplayPropertiesConfig for a given LayerConfig,
        considering presets, inline styles, and overrides defined in LayerConfig.
        Uses get_resolved_style_object internally.
        """
        ...

    def get_text_style_properties(
        self,
        # Reference to a style (preset name or inline object) or use layer_config's style
        style_reference: Optional[Union[str, StyleObjectConfig, TextStylePropertiesConfig]] = None,
        layer_config_fallback: Optional[LayerConfig] = None
    ) -> TextStylePropertiesConfig:
        """
        Resolves and returns TextStylePropertiesConfig.
        If style_reference (preset name, StyleObjectConfig, or direct TextStylePropertiesConfig) is given, it's prioritized.
        If style_reference is a preset name or StyleObjectConfig, text_props are extracted.
        If style_reference is None or doesn't yield text_props, and layer_config_fallback is provided,
        it attempts to find text_props within the style resolved from layer_config_fallback.
        Returns a TextStylePropertiesConfig with default values if no specific properties are found.
        """
        ...

    def get_hatch_properties(
        self,
        # Reference to a style (preset name or inline object) or use layer_config's style
        style_reference: Optional[Union[str, StyleObjectConfig, HatchPropertiesConfig]] = None,
        layer_config_fallback: Optional[LayerConfig] = None
    ) -> HatchPropertiesConfig:
        """
        Resolves and returns HatchPropertiesConfig.
        If style_reference (preset name, StyleObjectConfig, or direct HatchPropertiesConfig) is given, it's prioritized.
        If style_reference is a preset name or StyleObjectConfig, hatch_props are extracted.
        If style_reference is None or doesn't yield hatch_props, and layer_config_fallback is provided,
        it attempts to find hatch_props within the style resolved from layer_config_fallback.
        Returns a HatchPropertiesConfig with default values if no specific properties are found.
        """
        ...

    def get_resolved_style_for_label_operation(
        self, config: LabelPlacementOperationConfig
    ) -> TextStylePropertiesConfig:
        """
        Resolves the TextStylePropertiesConfig for labels based on LabelPlacementOperationConfig.
        Considers text_style_preset_name and text_style_inline within config.label_settings.
        """
        ...

    def get_resolved_feature_style(self, geo_feature: GeoFeature, layer_config: LayerConfig) -> StyleObjectConfig:
        """
        Resolves the StyleObjectConfig for a given GeoFeature based on the LayerConfig,
        applying feature-specific style rules.
        """
        ...

# --- DXF Writer Component Service Interfaces ---

class IDxfResourceSetupService(Protocol):
    """Interface for setting up DXF document resources (layers, styles, blocks)."""

    async def setup_document_resources(
        self,
        doc: Any, # ezdxf.document.Drawing
        app_config: Any, # AppConfig
        entities_by_layer_config: Dict[str, Tuple[LayerConfig, AsyncIterator[AnyDxfEntity]]] # For block defs
    ) -> None:
        """
        Sets up layers, text styles, linetypes, and block definitions in the DXF document.
        """
        ...

class IDxfEntityConverterService(Protocol):
    """Interface for converting DxfEntity domain models to ezdxf entities."""

    async def add_dxf_entity_to_modelspace(
        self,
        msp: Any, # ezdxf.layouts.Modelspace
        doc: Any, # ezdxf.document.Drawing (for resources like text styles)
        dxf_entity_model: AnyDxfEntity,
        layer_style_config: LayerStyleConfig # For applying styles
    ) -> Optional[Any]: # Returns the created ezdxf entity or None
        """
        Converts a DxfEntity domain model to an ezdxf entity and adds it to modelspace.
        Applies common styling.
        """
        ...

class IDxfViewportSetupService(Protocol):
    """Interface for setting up DXF document viewports and initial views."""

    async def setup_drawing_view(
        self,
        doc: Any, # ezdxf.document.Drawing
        msp: Any, # ezdxf.layouts.Modelspace
        entities_flat_list: List[AnyDxfEntity], # All DXF domain models to consider for extents
        app_config: Any # AppConfig for view settings
    ) -> None:
        """
        Sets up the main viewport and initial view of the DXF drawing.
        """
        ...
