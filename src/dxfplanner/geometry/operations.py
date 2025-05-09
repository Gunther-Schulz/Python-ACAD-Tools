"""
Geometric operations like buffer, simplify, etc.
"""
from typing import AsyncIterator

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IOperation
from dxfplanner.config.schemas import BufferOperationConfig, SimplifyOperationConfig, FieldMappingOperationConfig, ReprojectOperationConfig, CleanGeometryOperationConfig, ExplodeMultipartOperationConfig
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
