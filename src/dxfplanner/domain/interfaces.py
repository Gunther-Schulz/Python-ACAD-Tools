from typing import Protocol, List, Dict, Any, AsyncIterator, Optional, TypeVar, Tuple, Union
from pathlib import Path
from pydantic import BaseModel # Added for PlacedLabel

# Import domain models to be used in interface definitions
from .models.common import Coordinate, Color, BoundingBox as BoundingBoxModel
from .models.geo_models import GeoFeature #, PointGeo, PolylineGeo, PolygonGeo (GeoFeature contains these)
from .models.dxf_models import DxfEntity, DxfLayer, AnyDxfEntity # Added AnyDxfEntity explicitly
from ..config.schemas import (
    LayerConfig, BaseOperationConfig, LayerDisplayPropertiesConfig,
    TextStylePropertiesConfig, HatchPropertiesConfig, StyleObjectConfig, # Added StyleObjectConfig
    LabelSettings, LabelPlacementOperationConfig # Added LabelPlacementOperationConfig
)

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

    async def ensure_layer_exists_with_properties(
        self,
        doc: Any,
        layer_name: str,
        properties: Optional[LayerDisplayPropertiesConfig] = None
    ) -> Any: # Returns the ezdxf layer object
        """Ensures a layer exists, creating or updating it with specified properties."""
        ...

    async def add_mtext_ez(
        self,
        doc: Any, msp: Any,
        text: str,
        insertion_point: Tuple[float, float],
        layer_name: str,
        style_config: TextStylePropertiesConfig,
        max_width: Optional[float] = None,
        legend_item_id: Optional[str] = None # For potential XDATA tagging
    ) -> Tuple[Optional[Any], float]: # Returns (ezdxf_entity | None, actual_height)
        """Adds an MTEXT entity with extended styling and returns the entity and its calculated height."""
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

    async def add_lwpolyline(
        self,
        doc: Any, msp: Any,
        points: List[Tuple[float, float]],
        layer_name: str,
        style_props: Optional[LayerDisplayPropertiesConfig],
        is_closed: bool = False,
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]: # Returns ezdxf_entity | None
        """Adds an LWPOLYLINE entity."""
        ...

    async def add_hatch(
        self,
        doc: Any, msp: Any,
        # Hatch paths often include bulge values, not just simple points for complex boundaries
        # For simplicity, current model is List[List[Tuple[float,float]] for outer/inner loops of vertices
        # Actual ezdxf might take PathEdge or similar for more complex hatch paths.
        paths: List[List[Tuple[float, float]]], # List of paths (loops of vertices)
        layer_name: str,
        hatch_props_config: HatchPropertiesConfig,
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]: # Returns ezdxf_entity | None
        """Adds a HATCH entity."""
        ...

    async def add_block_reference(
        self,
        doc: Any, msp: Any,
        block_name: str,
        insertion_point: Tuple[float, float],
        layer_name: str,
        scale_x: float = 1.0, # Changed to scale_x, scale_y, scale_z for ezdxf
        scale_y: float = 1.0,
        scale_z: float = 1.0,
        rotation: float = 0.0,
        style_props: Optional[LayerDisplayPropertiesConfig] = None, # For potential color override if block is BYBLOCK
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]: # Returns ezdxf_entity | None
        """Adds a BLOCK_REFERENCE (INSERT) entity."""
        ...

    async def add_line(
        self,
        doc: Any, msp: Any,
        start_point: Tuple[float, float],
        end_point: Tuple[float, float],
        layer_name: str,
        style_props: Optional[LayerDisplayPropertiesConfig],
        legend_item_id: Optional[str] = None
    ) -> Optional[Any]: # Returns ezdxf_entity | None
        """Adds a LINE entity."""
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
        config: LabelSettings, # Changed from LabelPlacementConfig
        text_style_properties: TextStylePropertiesConfig, # ADDED
        # TODO: Consider adding parameters for existing_placed_labels and avoidance_geometries
        # if iterative placement or external avoidance areas are needed.
    ) -> AsyncIterator[PlacedLabel]:
        """
        Calculates optimal placements for labels for a stream of geographic features.

        Args:
            features: An asynchronous iterator of GeoFeature objects to be labeled.
            layer_name: The name of the layer these features belong to, for context.
            config: Configuration specific to this label placement task (LabelSettings).
            text_style_properties: The resolved text style properties for the labels. # ADDED

        Yields:
            PlacedLabel: An asynchronous iterator of PlacedLabel objects.
        """
        if False: # pragma: no cover
            yield
        ...

# Interface for the main orchestration service
class IDxfOrchestrator(Protocol):
    """Interface for the main service orchestrating the DXF generation pipeline."""

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
