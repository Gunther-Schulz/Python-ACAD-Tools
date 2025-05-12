"""
Geometric operations like buffer, simplify, etc.
"""
from typing import AsyncIterator, List, Dict, Any, Optional

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation, IStyleService
from dxfplanner.config.schemas import (
    BufferOperationConfig, SimplifyOperationConfig, FieldMappingOperationConfig,
    ReprojectOperationConfig, CleanGeometryOperationConfig, ExplodeMultipartOperationConfig,
    IntersectionOperationConfig,
    MergeOperationConfig,
    DissolveOperationConfig,
    FilterByAttributeOperationConfig,
    LabelPlacementOperationConfig
)
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.utils import (
    make_valid_geometry,
    remove_islands_from_geometry,
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_dxfplanner_geometry,
    reproject_geometry,
    explode_multipart_geometry,
    GeoPoint # Added GeoPoint for label geometry
)
from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon, GeometryCollection, Point # Added Point for type check
from shapely.prepared import prep # For potential performance optimization
from shapely.errors import GEOSException # General shapely errors
from shapely.ops import unary_union # Explicit import for union
import asyncio
from dependency_injector import containers # For type hinting container
from collections import defaultdict # Added for grouping features

try:
    import asteval
except ImportError:
    asteval = None # Flag that the library is missing

# Forward declaration for type hinting the container within its own module scope if needed elsewhere
# Although likely not needed just for operations.py if container is only passed in init.
# class MainContainer(containers.DeclarativeContainer): pass

logger = get_logger(__name__)

# Shapely join and cap style integer constants
# (Normally imported from shapely.geometry.enums if available, or defined if using older shapely)
# For shapely < 2.0, these might be directly shapely.geometry.JOIN_STYLE values
# For shapely >= 2.0, they are attributes of an enum.
# Let's assume direct integer values for broader compatibility or define them.
SHAPELY_JOIN_STYLE = {
    'ROUND': 1,
    'MITRE': 2,
    'BEVEL': 3
}
SHAPELY_CAP_STYLE = {
    'ROUND': 1,
    'FLAT': 2, # aka BUTT
    'SQUARE': 3
}

class BufferOperation(IOperation[BufferOperationConfig]):
    """Performs a buffer operation on geographic features."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: BufferOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the buffer operation.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: The configuration for the buffer operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting buffered GeoFeature objects.
        """
        logger.info(f"Executing BufferOperation for source_layer: '{config.source_layer}' with distance: {config.distance}, output: '{config.output_layer_name}'")

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(f"Could not convert DXFPlanner geometry to Shapely for feature. Attributes: {feature.attributes}")
                continue

            if config.make_valid_pre_buffer:
                shapely_geom = make_valid_geometry(shapely_geom)
                if shapely_geom is None or shapely_geom.is_empty:
                    logger.warning(f"Geometry became None/empty after pre-buffer validation. Attributes: {feature.attributes}")
                    continue

            current_buffer_distance = config.distance
            if config.distance_field and config.distance_field in feature.attributes:
                try:
                    current_buffer_distance = float(feature.attributes[config.distance_field])
                    logger.debug(f"Using distance_field '{config.distance_field}' with value: {current_buffer_distance}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse distance_field '{config.distance_field}' value '{feature.attributes[config.distance_field]}' as float: {e}. Using default: {config.distance}")
                    current_buffer_distance = config.distance

            # Get Shapely join/cap style integer values
            s_join_style = SHAPELY_JOIN_STYLE.get(config.join_style, SHAPELY_JOIN_STYLE['ROUND'])
            s_cap_style = SHAPELY_CAP_STYLE.get(config.cap_style, SHAPELY_CAP_STYLE['ROUND'])

            try:
                # Perform the buffer operation
                buffered_s_geom = shapely_geom.buffer(
                    current_buffer_distance,
                    resolution=config.resolution,
                    join_style=s_join_style,
                    cap_style=s_cap_style,
                    mitre_limit=config.mitre_limit
                    # single_sided=config.single_sided # If/when supported and added to config
                )
            except Exception as e_buffer:
                logger.error(f"Error during Shapely buffer operation for feature: {e_buffer}. Attributes: {feature.attributes}", exc_info=True)
                continue # Skip this feature

            if buffered_s_geom is None or buffered_s_geom.is_empty:
                logger.debug(f"Buffer result is None or empty for feature. Attributes: {feature.attributes}")
                continue

            # Island handling (applies to Polygons/MultiPolygons primarily)
            # skip_islands means preserve_islands = False
            # preserve_islands means preserve_islands = True
            # If neither is True, default is effectively preserve_islands = True (or rather, no specific island removal)
            # The remove_islands_from_geometry function handles the logic based on its preserve_islands flag.
            # We call it if either skip_islands is true (meaning preserve_islands=false) or preserve_islands is true.
            if config.skip_islands or config.preserve_islands:
                # If skip_islands is True, then preserve_islands for the function must be False.
                # If skip_islands is False but preserve_islands is True, then preserve_islands for the function is True.
                should_preserve_for_func = config.preserve_islands and not config.skip_islands
                buffered_s_geom = remove_islands_from_geometry(buffered_s_geom, preserve_islands=should_preserve_for_func)
                if buffered_s_geom is None or buffered_s_geom.is_empty:
                    logger.debug(f"Geometry became None/empty after island processing. Attributes: {feature.attributes}")
                    continue

            if config.make_valid_post_buffer:
                buffered_s_geom = make_valid_geometry(buffered_s_geom)
                if buffered_s_geom is None or buffered_s_geom.is_empty:
                    logger.warning(f"Geometry became None/empty after post-buffer validation. Attributes: {feature.attributes}")
                    continue

            # Handle potential MultiGeometries from buffer result
            geoms_to_yield = []
            if isinstance(buffered_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"Buffer result is a MultiGeometry ({buffered_s_geom.geom_type}) with {len(buffered_s_geom.geoms)} parts. Processing parts.")
                for part_geom in buffered_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty: continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else: # Single geometry
                converted_single = convert_shapely_to_dxfplanner_geometry(buffered_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from buffer result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                # Preserve original attributes and CRS
                # TODO: Consider how attributes should be handled/modified after buffer, if at all by this operation
                new_feature_attributes = feature.attributes.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_feature_attributes, crs=feature.crs)

        logger.info(f"BufferOperation completed for source_layer: '{config.source_layer}'")


class SimplifyOperation(IOperation[SimplifyOperationConfig]):
    """Performs a simplify (e.g., Douglas-Peucker) operation on geographic features."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: SimplifyOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the simplify operation.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for the simplify operation, including tolerance.

        Yields:
            GeoFeature: An asynchronous iterator of resulting simplified GeoFeature objects.
        """
        logger.info(
            f"Executing SimplifyOperation for source_layer: '{config.source_layer}' "
            f"with tolerance: {config.tolerance}, preserve_topology: {config.preserve_topology}, output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(f"Could not convert DXFPlanner geometry to Shapely for feature. Attributes: {feature.attributes}")
                continue

            # Note: Simplification might not need pre-validation like buffer does,
            # as it inherently tries to reduce complexity. Invalid input might behave unpredictably though.
            # If issues arise, make_valid_geometry(shapely_geom) could be added here.

            try:
                simplified_s_geom = shapely_geom.simplify(config.tolerance, preserve_topology=config.preserve_topology)
            except Exception as e_simplify:
                logger.error(f"Error during Shapely simplify operation for feature: {e_simplify}. Attributes: {feature.attributes}", exc_info=True)
                continue # Skip this feature

            if simplified_s_geom is None or simplified_s_geom.is_empty:
                logger.debug(f"Simplify result is None or empty for feature. Attributes: {feature.attributes}")
                continue

            # Post-validation might be useful if simplify can produce invalid geometries
            # simplified_s_geom = make_valid_geometry(simplified_s_geom) # Optional, consider based on observed behavior
            # if simplified_s_geom is None or simplified_s_geom.is_empty:
            #     logger.warning(f"Geometry became None/empty after post-simplify validation. Attributes: {feature.attributes}")
            #     continue

            geoms_to_yield = []
            if isinstance(simplified_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"Simplify result is a MultiGeometry ({simplified_s_geom.geom_type}) with {len(simplified_s_geom.geoms)} parts. Processing parts.")
                for part_geom in simplified_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty: continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else: # Single geometry
                converted_single = convert_shapely_to_dxfplanner_geometry(simplified_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from simplify result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_feature_attributes = feature.attributes.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_feature_attributes, crs=feature.crs)

        logger.info(f"SimplifyOperation completed for source_layer: '{config.source_layer}'")


class FieldMappingOperation(IOperation[FieldMappingOperationConfig]):
    """Maps attributes of geographic features based on configuration."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: FieldMappingOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the field mapping operation.
        For each feature, it creates new attributes based on the field_map.
        The field_map is expected as {new_field_name: old_field_name}.
        If an old_field_name is not found in the feature's attributes, the new field will not be created.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for field mapping.

        Yields:
            GeoFeature: An asynchronous iterator of GeoFeature objects with mapped fields.
        """
        logger.info(
            f"Executing FieldMappingOperation for source_layer: '{config.source_layer}' "
            f"with map: {config.field_map}, output: '{config.output_layer_name}'"
        )

        async for feature in features:
            new_attributes = {}
            if config.field_map:
                for new_field_name, old_field_name in config.field_map.items():
                    if old_field_name in feature.attributes:
                        new_attributes[new_field_name] = feature.attributes[old_field_name]
                    else:
                        logger.debug(
                            f"Old field '{old_field_name}' not found in attributes for feature mapping to '{new_field_name}'. "
                            f"Skipping this mapping. Attributes: {feature.attributes}"
                        )
            else:
                # If field_map is empty, pass through original attributes
                logger.debug("Field map is empty. Passing through original attributes.")
                new_attributes = feature.attributes.copy()

            # Geometry and CRS are preserved
            yield GeoFeature(geometry=feature.geometry, attributes=new_attributes, crs=feature.crs)

        logger.info(f"FieldMappingOperation completed for source_layer: '{config.source_layer}'")


class ReprojectOperation(IOperation[ReprojectOperationConfig]):
    """Reprojects geographic features to a new CRS."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: ReprojectOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the reprojection operation.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for reprojection, including target_crs.

        Yields:
            GeoFeature: An asynchronous iterator of reprojected GeoFeature objects.
        """
        logger.info(
            f"Executing ReprojectOperation for source_layer: '{config.source_layer}' "
            f"to target_crs: {config.target_crs}, output: '{config.output_layer_name}'"
        )

        target_crs_str = config.target_crs

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            source_crs_str = feature.crs
            if not source_crs_str:
                logger.warning(f"Feature has no source CRS defined. Cannot reproject. Attributes: {feature.attributes}")
                # Optionally, could yield original feature if a mode for this is added to config
                continue

            if source_crs_str.lower() == target_crs_str.lower():
                logger.debug(f"Feature CRS '{source_crs_str}' matches target CRS '{target_crs_str}'. Yielding original feature.")
                yield feature # No reprojection needed
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(f"Could not convert DXFPlanner geometry to Shapely for feature. Attributes: {feature.attributes}")
                continue

            reprojected_s_geom = reproject_geometry(shapely_geom, source_crs_str, target_crs_str)

            if reprojected_s_geom is None or reprojected_s_geom.is_empty:
                logger.warning(f"Reprojection result is None or empty for feature. Source CRS: {source_crs_str}, Target CRS: {target_crs_str}. Attributes: {feature.attributes}")
                continue

            # Handle potential MultiGeometries from reprojection (though less common than buffer)
            geoms_to_yield = []
            if isinstance(reprojected_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"Reproject result is a MultiGeometry ({reprojected_s_geom.geom_type}) with {len(reprojected_s_geom.geoms)} parts. Processing parts.")
                for part_geom in reprojected_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty: continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else: # Single geometry
                converted_single = convert_shapely_to_dxfplanner_geometry(reprojected_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from reproject result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_attributes = feature.attributes.copy() # Preserve original attributes
                # Create new feature with reprojected geometry and updated CRS
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_attributes, crs=target_crs_str)

        logger.info(f"ReprojectOperation completed for source_layer: '{config.source_layer}'")


class CleanGeometryOperation(IOperation[CleanGeometryOperationConfig]):
    """Cleans geometries (e.g., fix invalid, remove small parts)."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: CleanGeometryOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the geometry cleaning operation.
        Currently, this primarily uses make_valid_geometry.
        Future enhancements could include removing small parts or other cleaning routines based on config.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for cleaning geometry.

        Yields:
            GeoFeature: An asynchronous iterator of cleaned GeoFeature objects.
        """
        logger.info(
            f"Executing CleanGeometryOperation for source_layer: '{config.source_layer}', output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(f"Could not convert DXFPlanner geometry to Shapely for feature. Attributes: {feature.attributes}")
                continue

            # Apply make_valid_geometry as the primary cleaning step
            cleaned_s_geom = make_valid_geometry(shapely_geom)

            if cleaned_s_geom is None or cleaned_s_geom.is_empty:
                logger.warning(f"Geometry became None or empty after cleaning (make_valid). Original type: {shapely_geom.geom_type}. Attributes: {feature.attributes}")
                continue

            # Handle potential MultiGeometries from cleaning (e.g., if make_valid splits a polygon)
            geoms_to_yield = []
            if isinstance(cleaned_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"CleanGeometry result is a MultiGeometry ({cleaned_s_geom.geom_type}) with {len(cleaned_s_geom.geoms)} parts. Processing parts.")
                for part_geom in cleaned_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty: continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else: # Single geometry
                converted_single = convert_shapely_to_dxfplanner_geometry(cleaned_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from clean_geometry result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                # Preserve original attributes and CRS
                new_attributes = feature.attributes.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_attributes, crs=feature.crs)

        logger.info(f"CleanGeometryOperation completed for source_layer: '{config.source_layer}'")


class ExplodeMultipartOperation(IOperation[ExplodeMultipartOperationConfig]):
    """Explodes multipart geometries into single part geometries."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: ExplodeMultipartOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the explode multipart geometry operation.
        Converts multipart geometries (MultiPoint, MultiLineString, MultiPolygon)
        into multiple features, each with a single part geometry.
        Single part geometries are passed through unchanged.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for exploding multipart geometries.

        Yields:
            GeoFeature: An asynchronous iterator of single part GeoFeature objects.
        """
        logger.info(
            f"Executing ExplodeMultipartOperation for source_layer: '{config.source_layer}', output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(f"Could not convert DXFPlanner geometry to Shapely for feature. Attributes: {feature.attributes}")
                continue

            part_count = 0
            for single_part_s_geom in explode_multipart_geometry(shapely_geom):
                if single_part_s_geom is None or single_part_s_geom.is_empty:
                    continue

                new_dxf_geom_part = convert_shapely_to_dxfplanner_geometry(single_part_s_geom)

                if new_dxf_geom_part:
                    part_count += 1
                    # Preserve original attributes and CRS for each new feature part
                    # TODO: Consider if attributes need modification (e.g., adding part index)
                    new_attributes = feature.attributes.copy()
                    yield GeoFeature(geometry=new_dxf_geom_part, attributes=new_attributes, crs=feature.crs)
                else:
                    logger.warning(f"Could not convert exploded Shapely part back to DXFPlanner geometry. Part type: {single_part_s_geom.geom_type}")

            if part_count == 0 and not (isinstance(shapely_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection))):
                # This case handles if the input was already a single simple geometry that wasn't yielded by the loop
                # (because explode_multipart_geometry yields single simple parts directly)
                # However, the loop `for single_part_s_geom in explode_multipart_geometry(shapely_geom):`
                # should yield the original simple geometry once if it was simple.
                # This block might be redundant if explode_multipart_geometry always yields at least one item for valid non-empty simple geoms.
                # Let's trace: if shapely_geom is Point, explode yields it once. Loop runs once. new_dxf_geom_part made. part_count = 1.
                # This path should ideally not be hit if input was valid and simple.
                # It acts as a safeguard if somehow a simple geometry was not processed by the loop.
                logger.debug(f"Input geometry was likely already single-part and processed by explode_multipart_geometry. Original: {shapely_geom.geom_type}")
            elif part_count == 0:
                 logger.debug(f"No parts yielded after exploding geometry for feature. Original type: {shapely_geom.geom_type}. Attributes: {feature.attributes}")

        logger.info(f"ExplodeMultipartOperation completed for source_layer: '{config.source_layer}'")


# --- Intersection Operation ---

class IntersectionOperation(IOperation[IntersectionOperationConfig]):
    """Performs an intersection operation between the input features and features from other specified layers."""

    def __init__(self, di_container: containers.DeclarativeContainer):
        """
        Initializes the IntersectionOperation.

        Args:
            di_container: The application's dependency injection container to resolve readers/layers.
        """
        self._container = di_container
        # Potential optimization: Cache resolved overlay layers if config doesn't change frequently
        # For simplicity, we resolve and load them inside execute() for now.

    async def _load_overlay_features(self, layer_names: List[str]) -> List[GeoFeature]:
        """Loads all features from the specified overlay layers.""" # noqa
        overlay_features: List[GeoFeature] = []
        app_config = self._container.config() # Get AppConfig from container

        for layer_name in layer_names:
            layer_config = next((lc for lc in app_config.layers if lc.name == layer_name), None)
            if not layer_config or not layer_config.source:
                logger.warning(f"Intersection: Overlay layer '{layer_name}' not found in config or has no source. Skipping.")
                continue

            try:
                reader = self._container.resolve_reader(layer_config.source.type)
                # Prepare kwargs for the reader based on source config
                # This logic might need refinement depending on how reader kwargs are handled globally # noqa
                reader_kwargs = layer_config.source.model_dump(exclude={'type'}) # Pass source config fields as kwargs # noqa
                if layer_config.source.crs:
                    reader_kwargs['source_crs'] = layer_config.source.crs
                else:
                    # Attempt to get default source CRS if defined globally
                    default_src_crs = app_config.services.coordinate.default_source_crs
                    if default_src_crs:
                         reader_kwargs['source_crs'] = default_src_crs
                         logger.info(f"Using default source CRS '{default_src_crs}' for overlay layer '{layer_name}'") # noqa
                    else:
                        # Rely on reader's internal CRS detection or default (e.g., CsvWktReader defaults to EPSG:4326 if none provided/found) # noqa
                         logger.warning(f"No explicit source CRS for overlay layer '{layer_name}'. Reader will attempt detection or use default.") # noqa

                # For intersection, we assume overlay layers are already in the target CRS of the main pipeline # noqa
                # or handle reprojection explicitly here if needed. For now, assume they match input features CRS. # noqa
                target_crs = app_config.services.coordinate.default_target_crs # Get pipeline target CRS # noqa

                logger.info(f"Intersection: Loading overlay layer '{layer_name}'...")
                async for feature in reader.read_features(
                    source_path=layer_config.source.path,
                    source_crs=reader_kwargs.get('source_crs'),
                    target_crs=target_crs, # Request features in target CRS
                    **reader_kwargs
                 ):
                    if feature.geometry: # Ensure geometry exists
                        overlay_features.append(feature)
                logger.info(f"Intersection: Loaded {len(overlay_features)} features from overlay layer '{layer_name}'.") # noqa

            except Exception as e:
                 logger.error(f"Intersection: Failed to load overlay layer '{layer_name}': {e}", exc_info=True) # noqa
                 # Decide whether to continue without this layer or raise an error
                 # For now, log and continue
                 continue
        return overlay_features

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: IntersectionOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the intersection operation.
        Intersects each input feature with the union of features from the overlay layers.
        Keeps attributes from the original input feature.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for the intersection operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting intersected GeoFeature objects.
        """
        logger.info(f"Executing IntersectionOperation for layers: {config.input_layers}, output: '{config.output_layer_name}'") # noqa

        # 1. Load all features from the overlay layers
        overlay_features = await self._load_overlay_features(config.input_layers)
        if not overlay_features:
            logger.warning("Intersection: No valid overlay features loaded. Operation will yield no results.") # noqa
            return # Use return for async generator stop

        # 2. Combine overlay geometries (union overlay geometries first) # noqa
        valid_overlay_s_geoms = []
        for feat in overlay_features:
            s_geom = convert_dxfplanner_geometry_to_shapely(feat.geometry)
            if s_geom and not s_geom.is_empty:
                 s_geom = make_valid_geometry(s_geom)
                 if s_geom and not s_geom.is_empty:
                     valid_overlay_s_geoms.append(s_geom)

        if not valid_overlay_s_geoms:
             logger.warning("Intersection: No valid overlay geometries to perform intersection.") # noqa
             # Decide if we should stop or continue processing input features (yielding originals?)
             # For intersection, if overlay is empty, result is empty. Stop.
             return

        try:
             combined_overlay_geom = unary_union(valid_overlay_s_geoms)
             combined_overlay_geom = make_valid_geometry(combined_overlay_geom)
        except Exception as e_union:
             logger.error(f"Intersection: Failed to compute union of overlay geometries: {e_union}", exc_info=True) # noqa
             # Cannot proceed without combined overlay geometry
             return

        if not combined_overlay_geom or combined_overlay_geom.is_empty:
             logger.warning("Intersection: Combined overlay geometry is empty or invalid after union/validation.") # noqa
             return

        prepared_combined_overlay = prep(combined_overlay_geom) # Prepare the combined geometry
        logger.info(f"Intersection: Prepared combined overlay geometry for intersection. Type: {combined_overlay_geom.geom_type}") # noqa

        # 3. Process input features stream
        processed_count = 0
        yielded_count = 0
        async for feature in features:
            processed_count += 1
            if feature.geometry is None:
                continue

            input_s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if input_s_geom is None or input_s_geom.is_empty:
                continue

            # Make input valid before intersection check
            input_s_geom = make_valid_geometry(input_s_geom)
            if input_s_geom is None or input_s_geom.is_empty:
                continue

            intersected_result = None
            try:
                # Use prepared geometry for faster check
                if prepared_combined_overlay.intersects(input_s_geom):
                    # Actual intersection
                    intersected_result = input_s_geom.intersection(combined_overlay_geom) # Use non-prepared for calculation # noqa
                    intersected_result = make_valid_geometry(intersected_result) # Validate result

            except GEOSException as e:
                 logger.error(f"Error during intersection operation for feature: {e}. Attributes: {feature.attributes}", exc_info=True) # noqa
                 continue # Skip this feature
            except Exception as e_general:
                 logger.error(f"Unexpected error during intersection processing for feature: {e_general}. Attributes: {feature.attributes}", exc_info=True) # noqa
                 continue # Skip this feature

            if intersected_result is None or intersected_result.is_empty:
                 continue # Skip if intersection is empty

            # Convert back to DXFPlanner geometry, handle MultiGeometries
            geoms_to_yield = []
            if isinstance(intersected_result, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)): # noqa
                 for part_geom in intersected_result.geoms:
                     if part_geom is None or part_geom.is_empty: continue
                     converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                     if converted_part:
                         geoms_to_yield.append(converted_part)
            else: # Single geometry
                 converted_single = convert_shapely_to_dxfplanner_geometry(intersected_result)
                 if converted_single:
                     geoms_to_yield.append(converted_single)

            # Yield new features with original attributes
            for new_dxf_geom in geoms_to_yield:
                 new_feature_attributes = feature.attributes.copy() # Keep original attributes
                 yield GeoFeature(geometry=new_dxf_geom, attributes=new_feature_attributes, crs=feature.crs)
                 yielded_count += 1

            # Optional: yield progress? await asyncio.sleep(0)?

        logger.info(f"IntersectionOperation completed. Processed: {processed_count}, Yielded: {yielded_count}.") # noqa


# --- ADDED PLACEHOLDERS START ---

class MergeOperation(IOperation[MergeOperationConfig]):
    """
    Merges features. Currently, with a single input stream, this acts as a
    pass-through operation, potentially renaming the conceptual output layer.
    A true multi-layer merge would require changes to the IOperation interface
    or a different mechanism for accessing multiple input sources.
    """

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: MergeOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the merge operation (currently pass-through).

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for the merge operation.

        Yields:
            GeoFeature: An asynchronous iterator of the input GeoFeature objects.
        """
        log_prefix = f"MergeOperation (source: '{config.source_layer}', output: '{config.output_layer_name}')"
        logger.info(f"{log_prefix}: Executing...")
        logger.warning(f"{log_prefix}: Currently implemented as a pass-through operation. Yielding input features unchanged.")

        yielded_count = 0
        async for feature in features:
            yield feature
            yielded_count += 1

        logger.info(f"{log_prefix}: Completed. Yielded {yielded_count} features (pass-through).")

class DissolveOperation(IOperation[DissolveOperationConfig]):
    """Dissolves features based on a common attribute value, merging their geometries."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: DissolveOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the dissolve operation. Groups features by the specified attribute,
        then merges the geometries within each group using unary_union.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration including the dissolve_by_attribute.

        Yields:
            GeoFeature: An asynchronous iterator of dissolved GeoFeature objects.
        """
        dissolve_attr = config.dissolve_by_attribute
        log_prefix = f"DissolveOperation (source: '{config.source_layer}', by: '{dissolve_attr}', output: '{config.output_layer_name}')"
        logger.info(f"{log_prefix}: Executing...")

        if not dissolve_attr:
            logger.warning(f"{log_prefix}: No dissolve_by_attribute specified. Dissolving all features into one (if any).")
            # Treat all features as belonging to a single group if no attribute is specified
            grouped_features: Dict[Optional[Any], List[GeoFeature]] = {None: []}
            async for feature in features:
                 grouped_features[None].append(feature)
        else:
            # Group features by the dissolve attribute value
            grouped_features: Dict[Any, List[GeoFeature]] = defaultdict(list)
            processed_count = 0
            async for feature in features:
                processed_count += 1
                if dissolve_attr in feature.attributes:
                    group_key = feature.attributes[dissolve_attr]
                    # Ensure group_key is hashable (e.g., convert lists/dicts to tuples/frozensets if needed, though unlikely for typical dissolve keys)
                    try:
                        hash(group_key)
                    except TypeError:
                         logger.warning(f"{log_prefix}: Attribute '{dissolve_attr}' value '{group_key}' (type: {type(group_key)}) is not hashable. Skipping feature.")
                         continue
                    grouped_features[group_key].append(feature)
                else:
                    logger.debug(f"{log_prefix}: Feature missing dissolve attribute '{dissolve_attr}'. Grouping under 'None'. Attributes: {feature.attributes}")
                    grouped_features[None].append(feature) # Group features missing the attribute together
            logger.info(f"{log_prefix}: Grouped {processed_count} features into {len(grouped_features)} groups.")

        # Process each group
        yielded_count = 0
        for group_key, features_in_group in grouped_features.items():
            if not features_in_group:
                continue

            # Get geometries and convert to Shapely
            shapely_geoms_in_group = []
            for feature in features_in_group:
                if feature.geometry:
                    s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
                    if s_geom and not s_geom.is_empty:
                        # Pre-validate before union? Optional, might help robustness.
                        s_geom = make_valid_geometry(s_geom)
                        if s_geom and not s_geom.is_empty:
                            shapely_geoms_in_group.append(s_geom)

            if not shapely_geoms_in_group:
                 logger.debug(f"{log_prefix}: Group '{group_key}' had no valid geometries to dissolve.")
                 continue

            # Perform unary union
            dissolved_s_geom = None
            try:
                dissolved_s_geom = unary_union(shapely_geoms_in_group)
                dissolved_s_geom = make_valid_geometry(dissolved_s_geom) # Validate result
            except Exception as e_union:
                 logger.error(f"{log_prefix}: Error dissolving geometries for group '{group_key}': {e_union}", exc_info=True)
                 continue # Skip this group on error

            if dissolved_s_geom is None or dissolved_s_geom.is_empty:
                 logger.debug(f"{log_prefix}: Dissolved geometry for group '{group_key}' is empty or invalid.")
                 continue

            # Convert back to DXFPlanner geometry, handle MultiGeometries
            geoms_to_yield = []
            if isinstance(dissolved_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                 for part_geom in dissolved_s_geom.geoms:
                     if part_geom is None or part_geom.is_empty: continue
                     converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                     if converted_part:
                         geoms_to_yield.append(converted_part)
            else: # Single geometry
                 converted_single = convert_shapely_to_dxfplanner_geometry(dissolved_s_geom)
                 if converted_single:
                     geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"{log_prefix}: No valid DXFPlanner geometries could be converted from dissolve result for group '{group_key}'.")
                continue

            # Use attributes from the first feature in the group
            # TODO: Implement attribute aggregation strategies if needed (e.g., sum, mean, list)
            first_feature = features_in_group[0]
            result_attributes = first_feature.attributes.copy()
            # Ensure the dissolve attribute reflects the group key (important if grouped by None)
            if dissolve_attr:
                 result_attributes[dissolve_attr] = group_key

            # Yield new dissolved features
            for new_dxf_geom in geoms_to_yield:
                 yield GeoFeature(geometry=new_dxf_geom, attributes=result_attributes, crs=first_feature.crs)
                 yielded_count += 1

        logger.info(f"{log_prefix}: Completed. Yielded {yielded_count} dissolved features.")

class FilterByAttributeOperation(IOperation[FilterByAttributeOperationConfig]):
    """Filters features based on an attribute expression using asteval."""

    def __init__(self): # Removed di_container as it's not used here
        if asteval is None:
            # Log the error but don't raise an exception during __init__.
            # The execute method will handle the missing library more gracefully.
            logger.error("FilterByAttributeOperation: 'asteval' library not found. Filtering will be bypassed. Please install 'asteval'.")
            self._interpreter = None
        else:
            self._interpreter = asteval.Interpreter()
            # Optional: Configure asteval interpreter further if needed (e.g., max_statements, custom functions)
            # self._interpreter.symtable['custom_func'] = lambda x: x * 2 # Example

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: FilterByAttributeOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the filter operation using asteval to evaluate the expression.
        """
        log_prefix = f"FilterByAttributeOperation (source: '{config.source_layer}', output: '{config.output_layer_name}', filter: '{config.filter_expression}')"
        logger.info(f"{log_prefix}: Executing...")

        if self._interpreter is None:
            logger.error(f"{log_prefix}: 'asteval' library not available. Bypassing filtering and yielding all features.")
            warning_logged_bypass = False
            async for feature_bypass in features: # Pass through if lib missing
                if not warning_logged_bypass:
                    logger.warning(f"{log_prefix}: Bypassing filter for all features as 'asteval' is not installed.")
                    warning_logged_bypass = True
                yield feature_bypass
            logger.info(f"{log_prefix}: Completed (bypassed).")
            return

        expression = config.filter_expression
        if not expression:
            logger.warning(f"{log_prefix}: Filter expression is empty. Yielding all features.")
            async for feature_no_expr in features:
                yield feature_no_expr
            logger.info(f"{log_prefix}: Completed (empty expression).")
            return

        yielded_count = 0
        processed_count = 0

        async for feature in features:
            processed_count += 1
            try:
                # Using a new interpreter instance per feature evaluation to ensure a clean symtable,
                # or clearing the existing one. For simplicity with potential async execution,
                # creating a new one might be safer if the interpreter is not thread/async-safe
                # or if complex state could persist. Asteval's Interpreter is generally reusable.
                # Let's clear the symtable of the shared instance.
                self._interpreter.symtable.clear()
                self._interpreter.symtable.update(feature.attributes)
                # Add common built-ins if not available by default in asteval's minimal set
                self._interpreter.symtable['True'] = True
                self._interpreter.symtable['False'] = False
                self._interpreter.symtable['None'] = None
                # Add other safe built-ins or math functions if needed e.g. self._interpreter.symtable['sqrt'] = math.sqrt

                result = self._interpreter.eval(expression)

                if self._interpreter.error:
                    # Log errors that occurred during evaluation for this feature
                    errors = self._interpreter.get_error() # Get all errors
                    self._interpreter.error = [] # Clear errors from the interpreter instance
                    for err in errors:
                        logger.warning(f"{log_prefix}: Error evaluating filter for feature (ID: {feature.attributes.get('id', 'N/A')}): {err.get_error()[1]}. Expr: '{expression}'. Attrs: {feature.attributes}")
                    continue # Skip feature on evaluation error

                if result: # Yield feature if expression evaluates to True
                    yield feature
                    yielded_count += 1

            except Exception as e:
                # This catches errors in the Python code itself, not asteval evaluation errors (handled above)
                logger.error(f"{log_prefix}: Unexpected Python error during filter processing for feature (ID: {feature.attributes.get('id', 'N/A')}): {e}. Expr: '{expression}'. Attrs: {feature.attributes}", exc_info=True)
                # Decide whether to skip feature or allow app to stop based on severity

        logger.info(f"{log_prefix}: Completed. Processed: {processed_count}, Yielded: {yielded_count}.")

# --- ADDED PLACEHOLDERS END ---

# --- ADDED LABEL PLACEMENT PLACEHOLDER START ---

class LabelPlacementOperation(IOperation[LabelPlacementOperationConfig]):
    """Performs label placement based on configuration."""
    # This operation might need access to the LabelPlacementService via DI later for full implementation,
    # especially for complex collision detection and placement rules.

    def __init__(self, style_service: IStyleService, logger_param: Any = None):
        self.style_service = style_service
        # If a base IOperation class had a logger, we'd pass it. For now, use module logger.
        self.logger = logger_param if logger_param else logger # Use injected logger if provided, else module logger

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: LabelPlacementOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        self.logger.info(f"Executing LabelPlacementOperation for source: '{config.source_layer}', output: '{config.output_label_layer_name}'.")

        # Resolve text style using the new method in StyleService
        try:
            label_text_style = self.style_service.get_resolved_style_for_label_operation(config)
            self.logger.info(f"Resolved label text style for LabelPlacementOperation: Font='{label_text_style.font}', Height='{label_text_style.height}'")
            # Further logging of other resolved style properties can be added if needed.
        except Exception as e:
            self.logger.error(f"Error resolving label style in LabelPlacementOperation: {e}", exc_info=True)
            # Decide if we should proceed without style or stop. For now, log and proceed.
            label_text_style = TextStylePropertiesConfig() # Use default if error

        # Determine label text source
        use_fixed_text = config.label_settings.fixed_label_text is not None
        label_attr = config.label_settings.label_attribute

        if not use_fixed_text and not label_attr:
            self.logger.error(f"LabelPlacementOperation requires either fixed_label_text or label_attribute in label_settings. Skipping.")
            return # Stop processing if no label source defined

        log_prefix = f"LabelPlacementOperation (source: '{config.source_layer}', output: '{config.output_label_layer_name}')"
        yielded_count = 0
        async for feature in features:
            label_text = ""
            if use_fixed_text:
                label_text = config.label_settings.fixed_label_text
            elif label_attr in feature.attributes:
                label_text = str(feature.attributes[label_attr]) # Ensure string
            else:
                 self.logger.debug(f"{log_prefix}: Feature missing label attribute '{label_attr}'. Skipping label for this feature. Attrs: {feature.attributes}")
                 continue # Skip if attribute missing

            if not label_text: # Skip if text is empty after resolving
                 self.logger.debug(f"{log_prefix}: Resolved label text is empty. Skipping label. Attrs: {feature.attributes}")
                 continue

            if feature.geometry is None:
                 logger.debug(f"{log_prefix}: Feature has no geometry to place label on. Skipping label. Attrs: {feature.attributes}")
                 continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                 logger.debug(f"{log_prefix}: Could not convert feature geometry to valid Shapely object. Skipping label. Attrs: {feature.attributes}")
                 continue

            # Calculate placement point (simple strategy)
            placement_s_point: Optional[Point] = None
            try:
                if isinstance(shapely_geom, Point):
                    placement_s_point = shapely_geom
                else:
                    # representative_point() is guaranteed to be within the geometry
                    placement_s_point = shapely_geom.representative_point()
            except Exception as e_place:
                 logger.error(f"{log_prefix}: Error calculating placement point: {e_place}. Skipping label. Attrs: {feature.attributes}", exc_info=True)
                 continue

            if placement_s_point is None or placement_s_point.is_empty:
                 logger.warning(f"{log_prefix}: Calculated placement point is invalid. Skipping label. Attrs: {feature.attributes}")
                 continue

            # Apply offsets (assuming CRS units for now)
            # TODO: Handle expression-based offsets if needed
            offset_x = 0.0
            offset_y = 0.0
            try:
                 offset_x = float(config.label_settings.offset_x)
                 offset_y = float(config.label_settings.offset_y)
            except ValueError:
                 logger.warning(f"{log_prefix}: Could not parse offsets ('{config.label_settings.offset_x}', '{config.label_settings.offset_y}') as float. Using 0.0.")
            except Exception as e_offset:
                 logger.error(f"{log_prefix}: Error processing offsets: {e_offset}. Using 0.0.", exc_info=True)

            final_x = placement_s_point.x + offset_x
            final_y = placement_s_point.y + offset_y

            # Convert final placement point back to GeoPoint
            label_geo_point = GeoPoint(x=final_x, y=final_y, z=placement_s_point.z if placement_s_point.has_z else 0.0)

            # Create attributes for the label feature
            label_attributes = {
                "__geometry_type__": "LABEL", # Special flag for DxfWriter
                "label_text": label_text,
                # Pass resolved style properties directly
                "text_style_properties": label_text_style.model_dump(exclude_unset=True),
                # Copy original attributes? Or just specific ones? For now, keep it clean.
                # **feature.attributes # Uncomment to copy original attributes
            }

            # Yield the label feature
            yield GeoFeature(geometry=label_geo_point, attributes=label_attributes, crs=feature.crs)
            yielded_count += 1

        logger.info(f"{log_prefix}: Completed. Yielded {yielded_count} label features.")

# --- ADDED LABEL PLACEMENT PLACEHOLDER END ---
