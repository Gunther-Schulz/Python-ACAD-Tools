"""
Geometric operations like buffer, simplify, etc.
"""
from typing import AsyncIterator, List, Dict, Any

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.schemas import (
    BufferOperationConfig, SimplifyOperationConfig, FieldMappingOperationConfig,
    ReprojectOperationConfig, CleanGeometryOperationConfig, ExplodeMultipartOperationConfig,
    IntersectionOperationConfig
)
from dxfplanner.core.logging_config import get_logger
from dxfplanner.geometry.utils import (
    make_valid_geometry,
    remove_islands_from_geometry,
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_dxfplanner_geometry,
    reproject_geometry,
    explode_multipart_geometry
)
from shapely.geometry import MultiPoint, MultiLineString, MultiPolygon, GeometryCollection # For checking buffer result type
from shapely.prepared import prep # For potential performance optimization
from shapely.errors import GEOSException # General shapely errors
from shapely.ops import unary_union # Explicit import for union
import asyncio
from dependency_injector import containers # For type hinting container

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
