"""
Geometric operations like buffer, simplify, etc.
"""
from typing import AsyncIterator, List, Dict, Any, Optional, Tuple

from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo
from dxfplanner.domain.interfaces import (
    IOperation,
    IStyleService,
    ILabelPlacementService
)
from dxfplanner.config.schemas import (
    BufferOperationConfig,
    SimplifyOperationConfig,
    FieldMappingOperationConfig,
    ReprojectOperationConfig,
    CleanGeometryOperationConfig,
    ExplodeMultipartOperationConfig,
    IntersectionOperationConfig,
    IntersectionAttributeOptionsConfig,
    IntersectionInputAttributeOptions,
    IntersectionOverlayAttributeOptions,
    IntersectionAttributeConflictResolution,
    MergeOperationConfig,
    DissolveOperationConfig,
    FilterByAttributeOperationConfig,
    FilterOperator,
    LogicalOperator,
    FilterByExtentOperationConfig,
    LabelPlacementOperationConfig,
    TextStylePropertiesConfig,
    ProjectConfig
)
from dxfplanner.core.logging_config import get_logger
from shapely.geometry import (
    MultiPoint,
    MultiLineString,
    MultiPolygon,
    GeometryCollection,
    box as shapely_box
)
from shapely.prepared import prep
from shapely.errors import GEOSException
from shapely.ops import unary_union
import asyncio
from dependency_injector import containers
from collections import defaultdict
from copy import deepcopy
from dxfplanner.geometry.utils import (
    make_valid_geometry,
    remove_islands_from_geometry,
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_anygeogeometry,
    reproject_geometry,
    explode_multipart_geometry
)
import types

logger = get_logger(__name__)

SHAPELY_JOIN_STYLE = types.MappingProxyType({
    'ROUND': 1,
    'MITRE': 2,
    'BEVEL': 3
})
SHAPELY_CAP_STYLE = types.MappingProxyType({
    'ROUND': 1,
    'FLAT': 2,
    'SQUARE': 3
})


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
        logger.info(
            f"Executing BufferOperation for source_layer: '{config.source_layer}' "
            f"with distance: {config.distance}, output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(
                    f"Skipping feature with no geometry. Attributes: {feature.attributes}"
                )
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(
                    f"Could not convert DXFPlanner geometry to Shapely for feature. "
                    f"Attributes: {feature.attributes}"
                )
                continue

            if config.make_valid_pre_buffer:
                shapely_geom = make_valid_geometry(shapely_geom)
                if shapely_geom is None or shapely_geom.is_empty:
                    logger.warning(
                        f"Geometry became None/empty after pre-buffer validation. "
                        f"Attributes: {feature.attributes}"
                    )
                    continue

            current_buffer_distance = config.distance
            if config.distance_field and config.distance_field in feature.attributes:
                try:
                    current_buffer_distance = float(feature.attributes[config.distance_field])
                    logger.debug(
                        f"Using distance_field '{config.distance_field}' with value: {current_buffer_distance}"
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Could not parse distance_field '{config.distance_field}' value "
                        f"'{feature.attributes[config.distance_field]}' as float: {e}. "
                        f"Using default: {config.distance}"
                    )
                    current_buffer_distance = config.distance

            s_join_style = SHAPELY_JOIN_STYLE.get(
                config.join_style, SHAPELY_JOIN_STYLE['ROUND']
            )
            s_cap_style = SHAPELY_CAP_STYLE.get(
                config.cap_style, SHAPELY_CAP_STYLE['ROUND']
            )

            try:
                buffered_s_geom = shapely_geom.buffer(
                    current_buffer_distance,
                    resolution=config.resolution,
                    join_style=s_join_style,
                    cap_style=s_cap_style,
                    mitre_limit=config.mitre_limit
                )
            except Exception as e_buffer:
                logger.error(
                    f"Error during Shapely buffer operation for feature: {e_buffer}. "
                    f"Attributes: {feature.attributes}",
                    exc_info=True
                )
                continue

            if buffered_s_geom is None or buffered_s_geom.is_empty:
                logger.debug(f"Buffer result is None or empty for feature. Attributes: {feature.attributes}")
                continue

            if config.skip_islands or config.preserve_islands:
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

            geoms_to_yield = []
            if isinstance(buffered_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"Buffer result is a MultiGeometry ({buffered_s_geom.geom_type}) with {len(buffered_s_geom.geoms)} parts. Processing parts.")
                for part_geom in buffered_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty:
                        continue
                    converted_part = convert_shapely_to_anygeogeometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_anygeogeometry(buffered_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from buffer result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
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
            config: The configuration for the simplify operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting simplified GeoFeature objects.
        """
        logger.info(
            f"Executing SimplifyOperation for source_layer: '{config.source_layer}' "
            f"with tolerance: {config.tolerance}, output: '{config.output_layer_name}'"
        )

        async for feature in features:
            if feature.geometry is None:
                logger.debug(f"Simplify: Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                logger.warning(f"Simplify: Could not convert or got empty Shapely geometry. Attrs: {feature.attributes}")
                continue

            try:
                simplified_s_geom = shapely_geom.simplify(config.tolerance, preserve_topology=config.preserve_topology)
            except Exception as e_simplify:
                logger.error(
                    f"Simplify: Error during Shapely simplify operation: {e_simplify}. Attrs: {feature.attributes}",
                    exc_info=True
                )
                continue

            if simplified_s_geom is None or simplified_s_geom.is_empty:
                logger.debug(f"Simplify: Result is None or empty. Attrs: {feature.attributes}")
                continue

            # Ensure valid geometry after simplification if configured (though simplify usually preserves validity)
            if config.make_valid_post_simplify:
                simplified_s_geom = make_valid_geometry(simplified_s_geom)
                if simplified_s_geom is None or simplified_s_geom.is_empty:
                    logger.warning(f"Simplify: Geometry became None/empty after post-simplify validation. Attrs: {feature.attributes}")
                continue

            geoms_to_yield = []
            if isinstance(simplified_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                for part_geom in simplified_s_geom.geoms:
                    if part_geom and not part_geom.is_empty:
                        converted_part = convert_shapely_to_anygeogeometry(part_geom)
                        if converted_part:
                            geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_anygeogeometry(simplified_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"Simplify: No valid DXFPlanner geometries from simplification. Attrs: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_feature_attributes = feature.attributes.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_feature_attributes, crs=feature.crs)

        logger.info(f"SimplifyOperation completed for source_layer: '{config.source_layer}'")


class FieldMappingOperation(IOperation[FieldMappingOperationConfig]):
    """Maps feature attributes based on a provided configuration."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: FieldMappingOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the field mapping operation.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: The configuration for field mapping.

        Yields:
            GeoFeature: GeoFeatures with remapped attributes.
        """
        logger.info(
            f"Executing FieldMappingOperation for source_layer: '{config.source_layer}', "
            f"output: '{config.output_layer_name}'"
        )

        async for feature in features:
            new_attributes: Dict[str, Any] = {}
            original_attributes = feature.attributes or {}

            # Apply field map
            for old_field, new_field_or_spec in config.mapping.items():
                if old_field in original_attributes:
                    if isinstance(new_field_or_spec, str): # Simple rename
                        new_attributes[new_field_or_spec] = original_attributes[old_field]
                    elif isinstance(new_field_or_spec, dict): # More complex mapping (e.g. with default or type)
                        # For now, assume it's a dict like {"new_name": "field_name", "default": val}
                        # Placeholder for more complex logic if FieldMapSpecification becomes more detailed
                        target_field_name = new_field_or_spec.get("new_name", old_field) # Default to old_field if new_name not specified
                        new_attributes[target_field_name] = original_attributes[old_field]
                        # TODO: Handle "default" value from spec if old_field not in original_attributes
                        # TODO: Handle type conversion from spec
                # else: old_field not in attributes, handled by copy_unmapped or implicitly dropped

            # Handle unmapped fields
            if config.drop_unmapped_fields:
                # If drop_unmapped_fields is true, new_attributes (which only contains mapped fields so far) is final.
                # No action needed here as unmapped fields are implicitly not carried over.
                pass
            elif config.copy_unmapped_fields: # drop_unmapped_fields is False and copy_unmapped_fields is True
                for old_field, old_value in original_attributes.items():
                    if old_field not in config.mapping: # Changed from config.field_map
                        if old_field not in new_attributes:
                            new_attributes[old_field] = old_value
            # If drop_unmapped_fields is False and copy_unmapped_fields is False,
            # unmapped fields are implicitly dropped (same outcome as drop_unmapped_fields=True).

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
                logger.debug(f"Reproject: Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            source_crs_str = feature.crs
            if not source_crs_str:
                logger.warning(f"Reproject: Feature has no source CRS defined. Cannot reproject. Attributes: {feature.attributes}")
                # Potentially yield original feature if config.allow_passthrough_if_no_source_crs, or skip
                continue

            if source_crs_str.lower() == target_crs_str.lower():
                logger.debug(f"Reproject: Feature CRS '{source_crs_str}' matches target CRS '{target_crs_str}'. Yielding original feature.")
                yield feature
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty:
                logger.warning(f"Reproject: Could not convert or got empty Shapely geometry. Attrs: {feature.attributes}")
                continue

            try:
                reprojected_s_geom = reproject_geometry(shapely_geom, source_crs_str, target_crs_str)
            except Exception as e_reproject:
                logger.error(
                    f"Reproject: Error during Shapely reproject_geometry: {e_reproject}. Attrs: {feature.attributes}",
                    exc_info=True
                )
                continue

            if reprojected_s_geom is None or reprojected_s_geom.is_empty:
                logger.warning(f"Reproject: Result is None or empty. Source CRS: {source_crs_str}, Target CRS: {target_crs_str}. Attrs: {feature.attributes}")
                continue

            geoms_to_yield = []
            if isinstance(reprojected_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                for part_geom in reprojected_s_geom.geoms:
                    if part_geom and not part_geom.is_empty:
                        converted_part = convert_shapely_to_anygeogeometry(part_geom)
                        if converted_part:
                            geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_anygeogeometry(reprojected_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"Reproject: No valid DXFPlanner geometries from reprojected result. Attrs: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_attributes = feature.attributes.copy() # Preserve original attributes
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_attributes, crs=target_crs_str) # CRITICAL: Update CRS to target_crs_str

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
                logger.debug(f"CleanGeometry: Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty: # Check for empty too
                logger.warning(f"CleanGeometry: Could not convert or got empty Shapely geometry. Attrs: {feature.attributes}")
                continue

            try:
                cleaned_s_geom = make_valid_geometry(shapely_geom)
            except Exception as e_clean:
                logger.error(
                    f"CleanGeometry: Error during make_valid_geometry: {e_clean}. Attrs: {feature.attributes}",
                    exc_info=True
                )
                continue

            if cleaned_s_geom is None or cleaned_s_geom.is_empty:
                logger.warning(f"CleanGeometry: Geometry became None or empty after cleaning (make_valid). Original type: {shapely_geom.geom_type if shapely_geom else 'N/A'}. Attrs: {feature.attributes}")
                continue

            geoms_to_yield = []
            if isinstance(cleaned_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                for part_geom in cleaned_s_geom.geoms:
                    if part_geom and not part_geom.is_empty:
                        converted_part = convert_shapely_to_anygeogeometry(part_geom)
                        if converted_part:
                            geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_anygeogeometry(cleaned_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"CleanGeometry: No valid DXFPlanner geometries from cleaned result. Attrs: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_attributes = feature.attributes.copy()
                yield GeoFeature(geometry=new_dxf_geom, attributes=new_attributes, crs=feature.crs) # Preserve original CRS

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
        Single part geometries are passed through unchanged by explode_multipart_geometry.

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
                logger.debug(f"Explode: Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None or shapely_geom.is_empty: # Check for empty too
                logger.warning(f"Explode: Could not convert or got empty Shapely geometry. Attrs: {feature.attributes}")
                continue

            part_count = 0
            try:
                # explode_multipart_geometry itself handles single geoms by yielding them directly
                for single_part_s_geom in explode_multipart_geometry(shapely_geom):
                    if single_part_s_geom is None or single_part_s_geom.is_empty:
                        continue

                    # It's good practice to ensure parts are valid, though explode itself doesn't guarantee validity of parts
                    # For now, we assume explode_multipart_geometry yields reasonable parts or rely on a subsequent Clean op.
                    # valid_part_s_geom = make_valid_geometry(single_part_s_geom)
                    # if valid_part_s_geom is None or valid_part_s_geom.is_empty:
                    #    logger.debug(f"Explode: A part became None/empty after make_valid. Original part type: {single_part_s_geom.geom_type}")
                    #    continue
                    # new_dxf_geom_part = convert_shapely_to_dxfplanner_geometry(valid_part_s_geom)

                    new_dxf_geom_part = convert_shapely_to_anygeogeometry(single_part_s_geom)

                    if new_dxf_geom_part:
                        part_count += 1
                        # Each part gets a copy of the original attributes and CRS
                        new_attributes = feature.attributes.copy()
                        yield GeoFeature(geometry=new_dxf_geom_part, attributes=new_attributes, crs=feature.crs)
                    else:
                        logger.warning(f"Explode: Could not convert exploded Shapely part back to DXFPlanner geometry. Part type: {single_part_s_geom.geom_type if single_part_s_geom else 'N/A'}")
            except Exception as e_explode:
                logger.error(
                    f"Explode: Error during explode_multipart_geometry or processing parts: {e_explode}. Attrs: {feature.attributes}",
                    exc_info=True
                )
                continue # Skip this feature on error

            if part_count == 0:
                logger.debug(f"Explode: No parts yielded for feature. Original type: {shapely_geom.geom_type if shapely_geom else 'N/A'}. Attrs: {feature.attributes}")

        logger.info(f"ExplodeMultipartOperation completed for source_layer: '{config.source_layer}'")


class IntersectionOperation(IOperation[IntersectionOperationConfig]):
    """Performs an intersection operation between the input features and features from other specified layers."""

    def __init__(self, di_container: containers.DeclarativeContainer):
        """
        Initializes the IntersectionOperation.

        Args:
            di_container: The application's dependency injection container to resolve readers/layers.
        """
        self._container = di_container
        self._project_config: ProjectConfig = self._container.project_config()

    async def _load_overlay_features(self, layer_names: List[str], primary_op_crs: Optional[str]) -> Tuple[List[GeoFeature], Optional[str]]:
        """
        Loads all features from the specified overlay layers.
        Tries to reproject them to primary_op_crs if provided and different.
        Returns the list of features and the CRS they are in (hopefully primary_op_crs or their original if primary_op_crs was None).
        """
        overlay_features: List[GeoFeature] = []

        # Determine a consistent CRS for loading overlay features.
        # If primary_op_crs (from the main input stream) is known, use that.
        # Otherwise, fall back to project's default target CRS if defined.
        # If neither, features are loaded in their native or reader-defined CRS.
        target_crs_for_overlays_load = primary_op_crs
        final_overlay_crs = primary_op_crs

        if not target_crs_for_overlays_load and self._project_config.services and self._project_config.services.coordinate:
            target_crs_for_overlays_load = self._project_config.services.coordinate.default_target_crs
            final_overlay_crs = target_crs_for_overlays_load # If we use default_target_crs, that's what they'll be in
            if target_crs_for_overlays_load:
                logger.info(f"Intersection: No primary operation CRS provided for overlays, using project default target CRS for loading: {target_crs_for_overlays_load}")


            for layer_name in layer_names:
                layer_config = next((lc for lc in self._project_config.layers if lc.name == layer_name), None)
                if not layer_config or not layer_config.source:
                    logger.warning(f"Intersection: Overlay layer '{layer_name}' not found in config or has no source. Skipping.")
                    continue

                try:
                    reader = self._container.resolve_reader(layer_config.source.type)
                    reader_kwargs = layer_config.source.model_dump(exclude={'type', 'crs', 'path'})

                    current_source_crs = layer_config.source.crs
                    # No fallback to project_config.services.coordinate.default_source_crs here, reader should handle if None

                    logger.info(f"Intersection: Loading overlay layer '{layer_name}' (SourceCRS: {current_source_crs}, TargetCRS for load: {target_crs_for_overlays_load or 'Reader-defined/Native'})...")

                    async for feature in reader.read_features(
                        source_path=layer_config.source.path,
                        source_crs=current_source_crs,
                        target_crs=target_crs_for_overlays_load, # Pass the determined target_crs_for_overlays_load
                        **reader_kwargs
                    ):
                        if feature.geometry:
                            # Ensure attributes exists, even if empty
                            if feature.attributes is None:
                                feature.attributes = {}
                            overlay_features.append(feature)
                            # After read_features, feature.crs should be target_crs_for_overlays_load if it was provided and reprojection occurred.
                            # If target_crs_for_overlays_load was None, feature.crs is whatever the reader set (native or its own default).
                            # We need to track the actual CRS of the loaded overlay features if primary_op_crs was initially None.
                            if final_overlay_crs is None and feature.crs: # First feature with a CRS sets the benchmark if no primary_op_crs
                                final_overlay_crs = feature.crs
                                logger.info(f"Intersection: Overlay features from '{layer_name}' determined to be in CRS '{final_overlay_crs}' (used as benchmark).")
                            elif final_overlay_crs and feature.crs and final_overlay_crs.lower() != feature.crs.lower():
                                logger.warning(f"Intersection: Overlay layer '{layer_name}' feature loaded in CRS '{feature.crs}', but expected/benchmark CRS is '{final_overlay_crs}'. This could lead to issues.")


                    logger.info(f"Intersection: Loaded {len(overlay_features)} features from overlay layer '{layer_name}'. Features should now be in CRS: {final_overlay_crs or 'Varies/Unknown'}.")

                except Exception as e:
                    logger.error(f"Intersection: Failed to load overlay layer '{layer_name}': {e}", exc_info=True)
                    continue
            return overlay_features, final_overlay_crs

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: IntersectionOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        logger.info(f"Executing IntersectionOperation for source_layer: '{config.source_layer}' to intersect with layer: '{config.overlay_layer_name}', output: '{config.output_layer_name}'")

        first_input_feature_list = []
        try:
            first_input_feature = await features.__anext__()
            first_input_feature_list.append(first_input_feature)
        except StopAsyncIteration:
            logger.warning("Intersection: Input feature stream is empty. Yielding no results.")
            return

        async def prepend_first_feature_stream(first_feat_list, rest_of_features):
            if first_feat_list:
                yield first_feat_list[0]
            async for feat in rest_of_features:
                yield feat

        processed_features_stream = prepend_first_feature_stream(first_input_feature_list, features)

        primary_op_crs = first_input_feature_list[0].crs if first_input_feature_list and first_input_feature_list[0].crs else None
        if primary_op_crs:
            logger.info(f"Intersection: Determined primary operation CRS from first input feature: {primary_op_crs}")
        else:
            logger.info("Intersection: Could not determine primary operation CRS from first input feature. Overlay loading will use project defaults or native CRSs.")

        overlay_features, intersection_crs = await self._load_overlay_features([config.overlay_layer_name], primary_op_crs)

        if not overlay_features:
            logger.warning(f"Intersection: No valid overlay features loaded from '{config.overlay_layer_name}'. Operation will yield no results.")
            return

        if not intersection_crs:
            logger.warning("IntersectionOperation: Could not determine a consistent CRS for overlay features. CRS consistency for intersection relies on input features matching. This might lead to incorrect results if CRSs are diverse.")

        valid_overlay_s_geoms = []
        for feat in overlay_features:
            current_feat_attributes = feat.attributes if feat.attributes is not None else {}
            s_geom = convert_dxfplanner_geometry_to_shapely(feat.geometry)
            if s_geom and not s_geom.is_empty:
                s_geom = make_valid_geometry(s_geom)
                if s_geom and not s_geom.is_empty:
                    valid_overlay_s_geoms.append(s_geom)
                else:
                    logger.debug(f"Overlay feature geometry became invalid/empty after make_valid. Attributes: {current_feat_attributes}")
            else:
                logger.debug(f"Overlay feature geometry is None or empty before make_valid. Attributes: {current_feat_attributes}")

        if not valid_overlay_s_geoms:
            logger.warning("Intersection: No valid overlay geometries to perform intersection after conversion/validation.")
            return

        try:
            combined_overlay_geom = unary_union(valid_overlay_s_geoms)
            combined_overlay_geom = make_valid_geometry(combined_overlay_geom)
        except Exception as e_union:
            logger.error(f"Intersection: Failed to compute union of overlay geometries: {e_union}", exc_info=True)
            return

        if not combined_overlay_geom or combined_overlay_geom.is_empty:
            logger.warning("Intersection: Combined overlay geometry is empty or invalid after union/validation.")
            return

        prepared_combined_overlay = prep(combined_overlay_geom)
        logger.info(f"Intersection: Prepared combined overlay geometry from '{config.overlay_layer_name}'. Type: {combined_overlay_geom.geom_type}. Assumed CRS for intersection: {intersection_crs or 'Varies/Unknown'}")

        processed_count = 0
        yielded_count = 0

        attr_options = config.attribute_options or IntersectionAttributeOptionsConfig()
        input_opts = attr_options.input_options
        overlay_opts = attr_options.overlay_options
        conflict_res = attr_options.conflict_resolution

        async for feature in processed_features_stream:
            processed_count += 1
            original_input_attributes = feature.attributes if feature.attributes is not None else {}

            if feature.geometry is None:
                logger.debug(f"Skipping input feature with no geometry. Attributes: {original_input_attributes}")
                continue

            input_s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if input_s_geom is None or input_s_geom.is_empty:
                logger.debug(f"Input feature geometry is None or empty after conversion. Attributes: {original_input_attributes}")
                continue
            input_s_geom = make_valid_geometry(input_s_geom)
            if input_s_geom is None or input_s_geom.is_empty:
                logger.debug(f"Input feature geometry became invalid/empty after make_valid. Attributes: {original_input_attributes}")
                continue

            current_input_crs = feature.crs
            reprojected_input_s_geom = input_s_geom
            output_feature_crs = feature.crs

            if intersection_crs and current_input_crs and current_input_crs.lower() != intersection_crs.lower():
                logger.debug(f"Reprojecting input feature from CRS '{current_input_crs}' to '{intersection_crs}' for intersection.")
                try:
                    reprojected_input_s_geom = reproject_geometry(input_s_geom, current_input_crs, intersection_crs)
                    if reprojected_input_s_geom is None or reprojected_input_s_geom.is_empty:
                        logger.warning(f"Input feature geometry became None/empty after reprojection from '{current_input_crs}' to '{intersection_crs}'. Attributes: {original_input_attributes}")
                        continue
                    output_feature_crs = intersection_crs
                except Exception as e_reproject_main:
                    logger.error(f"Error reprojecting input feature from '{current_input_crs}' to '{intersection_crs}': {e_reproject_main}. Attributes: {original_input_attributes}", exc_info=True)
                    continue
            elif not current_input_crs and intersection_crs:
                logger.warning(f"Input feature has no CRS, but intersection CRS ('{intersection_crs}') is set. Assuming input is already in target CRS. Attributes: {original_input_attributes}")
                output_feature_crs = intersection_crs
            elif not intersection_crs and current_input_crs:
                logger.warning(f"Intersection CRS is not consistently determined from overlays, but input feature has CRS '{current_input_crs}'. Intersection will assume this CRS. Attributes: {original_input_attributes}")
                output_feature_crs = current_input_crs
            elif not intersection_crs and not current_input_crs:
                logger.warning(f"Neither a consistent intersection_crs nor input feature CRS is set. Assuming all data is in a consistent, unknown CRS. Attributes: {original_input_attributes}")
                output_feature_crs = None

            intersected_s_geom = None
            try:
                if prepared_combined_overlay.intersects(reprojected_input_s_geom):
                    intersected_s_geom = reprojected_input_s_geom.intersection(combined_overlay_geom)
                    if intersected_s_geom:
                        intersected_s_geom = make_valid_geometry(intersected_s_geom)
            except GEOSException as e_geos:
                logger.error(f"GEOSException during intersection for feature: {e_geos}. Attributes: {original_input_attributes}", exc_info=True)
                continue
            except Exception as e_general_intersect:
                logger.error(f"Unexpected error during intersection processing for feature: {e_general_intersect}. Attributes: {original_input_attributes}", exc_info=True)
                continue

            if intersected_s_geom is None or intersected_s_geom.is_empty:
                continue

            final_attributes: Dict[str, Any] = {}

            if input_opts.keep_attributes == "all":
                for k, v in original_input_attributes.items():
                    new_key = f"{input_opts.prefix or ''}{k}"
                    final_attributes[new_key] = v
            elif isinstance(input_opts.keep_attributes, list):
                for k in input_opts.keep_attributes:
                    if k in original_input_attributes:
                        new_key = f"{input_opts.prefix or ''}{k}"
                        final_attributes[new_key] = original_input_attributes[k]

            if overlay_opts and overlay_opts.add_attributes:
                for k_overlay, v_overlay in overlay_opts.add_attributes.items():
                    new_key_overlay = f"{overlay_opts.prefix or ''}{k_overlay}"
                    if new_key_overlay in final_attributes:
                        if conflict_res == IntersectionAttributeConflictResolution.PREFER_OVERLAY:
                            final_attributes[new_key_overlay] = v_overlay
                        elif conflict_res == IntersectionAttributeConflictResolution.PREFER_INPUT:
                            pass
            else:
                final_attributes[new_key_overlay] = v_overlay

            geoms_to_yield = []
            converted_geometry_parts = convert_shapely_to_anygeogeometry(intersected_s_geom)
            if isinstance(converted_geometry_parts, list):
                for part_geom in converted_geometry_parts:
                    if part_geom:
                        geoms_to_yield.append(part_geom)
            elif converted_geometry_parts:
                geoms_to_yield.append(converted_geometry_parts)

            for new_dxf_geom_part in geoms_to_yield:
                yield GeoFeature(geometry=new_dxf_geom_part, attributes=deepcopy(final_attributes), crs=output_feature_crs)
                yielded_count += 1

        logger.info(f"IntersectionOperation completed for source_layer: '{config.source_layer}'. Processed: {processed_count}, Yielded: {yielded_count}.")


class MergeOperation(IOperation[MergeOperationConfig]):
    """
    Merges features from a single input stream into one or fewer features
    by performing a unary union of their geometries.
    """

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: MergeOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the merge operation. Collects all geometries from the input stream,
        performs a unary union, and yields the resulting feature(s).
        Attributes and CRS from the first feature encountered are used for the output.

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for the merge operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting merged GeoFeature objects.
                       Typically yields one feature, or multiple if the union results
                       in a GeometryCollection of differing simple types that are then exploded by conversion.
        """
        log_prefix = f"MergeOperation (source_layer: '{config.source_layer}', output: '{config.output_layer_name}')"
        logger.info(f"{log_prefix}: Executing...")

        shapely_geoms_to_merge: List[Any] = [] # Using Any for Shapely geometries
        first_feature_attributes: Optional[Dict[str, Any]] = None
        first_feature_crs: Optional[str] = None
        input_feature_count = 0

        async for feature in features:
            input_feature_count += 1
            if input_feature_count == 1: # Capture attributes and CRS from the first feature
                first_feature_attributes = feature.attributes.copy() if feature.attributes else {}
                first_feature_crs = feature.crs

            if feature.geometry:
                s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
                if s_geom and not s_geom.is_empty:
                    # It's good practice to validate before union, though unary_union can handle some invalid cases
                    valid_s_geom = make_valid_geometry(s_geom)
                    if valid_s_geom and not valid_s_geom.is_empty:
                        shapely_geoms_to_merge.append(valid_s_geom)
                    else:
                        logger.debug(f"{log_prefix}: Input geometry became None/empty after make_valid. Attrs: {feature.attributes}")
                else:
                    logger.debug(f"{log_prefix}: Input geometry is None/empty after conversion. Attrs: {feature.attributes}")
            # Consider asyncio.sleep(0) if this loop becomes very dense without I/O
            # await asyncio.sleep(0) # Removed as per prior similar cases unless proven necessary

        if not shapely_geoms_to_merge:
            logger.info(f"{log_prefix}: No valid geometries found in {input_feature_count} input features to merge. Yielding nothing.")
            return

        logger.info(f"{log_prefix}: Collected {len(shapely_geoms_to_merge)} valid geometries from {input_feature_count} input features for merging.")

        merged_s_geom = None
        try:
            # unary_union can take a list of Shapely geometries
            merged_s_geom = unary_union(shapely_geoms_to_merge)
            if merged_s_geom is None or merged_s_geom.is_empty:
                logger.warning(f"{log_prefix}: Unary union resulted in an empty or invalid geometry.")
                return

            # Validate after union as well
            merged_s_geom = make_valid_geometry(merged_s_geom)
            if merged_s_geom is None or merged_s_geom.is_empty:
                logger.warning(f"{log_prefix}: Merged geometry became empty or invalid after validation.")
                return

        except GEOSException as e_geos_union:
            logger.error(f"{log_prefix}: GEOSException during unary_union operation: {e_geos_union}", exc_info=True)
            return
        except Exception as e_union_general:
            logger.error(f"{log_prefix}: Unexpected error during unary_union or post-validation: {e_union_general}", exc_info=True)
            return


        result_attributes = first_feature_attributes if first_feature_attributes is not None else {}
        # result_crs is already set to first_feature_crs

        geoms_to_yield = []
        # convert_shapely_to_dxfplanner_geometry can return a list if it explodes a GeometryCollection
        # However, for Merge, we typically expect a single (potentially multipart) geometry.
        # If unary_union results in a GeometryCollection of mixed types, convert_shapely... will handle it by yielding parts.

        converted_geoms = convert_shapely_to_anygeogeometry(merged_s_geom)
        if isinstance(converted_geoms, list):
            geoms_to_yield.extend(converted_geoms)
        elif converted_geoms: # Single geometry
            geoms_to_yield.append(converted_geoms)


        if not geoms_to_yield:
            logger.warning(f"{log_prefix}: No valid DXFPlanner geometries could be converted from the merged result.")
            return

        yielded_count = 0
        for new_dxf_geom in geoms_to_yield:
            if new_dxf_geom: # Ensure the geometry itself isn't None
                yield GeoFeature(geometry=new_dxf_geom, attributes=result_attributes, crs=first_feature_crs)
            yielded_count += 1

        logger.info(f"{log_prefix}: Completed. Yielded {yielded_count} feature(s) from merged geometry.")

class DissolveOperation(IOperation[DissolveOperationConfig]):
    """Dissolves features based on a specified attribute field."""

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: DissolveOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        log_prefix = f"DissolveOperation (source: '{config.source_layer}', field: '{config.dissolve_by_field}', output: '{config.output_layer_name}')"
        logger.info(f"{log_prefix}: Starting dissolve.")

        grouped_features_data: Dict[Any, Dict[str, Any]] = defaultdict(lambda: {"geoms": [], "first_feature_attrs": None, "first_feature_crs": None})

        input_feature_count = 0
        async for feature in features:
            input_feature_count += 1
            current_attributes = feature.attributes if feature.attributes else {}
            group_key_value: Any = config.group_for_missing_key # Default for missing field or None value

            if config.dissolve_by_field:
                if config.dissolve_by_field in current_attributes:
                    val = current_attributes[config.dissolve_by_field]
                    group_key_value = val if val is not None else config.group_for_missing_key # Use specific value if not None
                # else: stays group_for_missing_key
            else: # No dissolve_by_field, all features go into a single conceptual group
                group_key_value = "__all_features_dissolve_group__"

            group_data = grouped_features_data[group_key_value]

            if group_data["first_feature_attrs"] is None: # First feature in this group
                group_data["first_feature_attrs"] = current_attributes.copy()
                group_data["first_feature_crs"] = feature.crs

            if feature.geometry:
                s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
                if s_geom and not s_geom.is_empty:
                    valid_s_geom = make_valid_geometry(s_geom)
                    if valid_s_geom and not valid_s_geom.is_empty:
                        group_data["geoms"].append(valid_s_geom)

        if input_feature_count == 0:
            logger.info(f"{log_prefix}: No features provided to dissolve.")
            return

        logger.debug(f"{log_prefix}: Features grouped into {len(grouped_features_data)} groups by field '{config.dissolve_by_field or 'N/A (all features)'}'.")

        dissolved_feature_count = 0
        for group_key, data_for_group in grouped_features_data.items():
            shapely_geoms_to_union = data_for_group["geoms"]
            first_attrs_in_group = data_for_group["first_feature_attrs"]
            crs_for_group = data_for_group["first_feature_crs"]

            if not shapely_geoms_to_union:
                logger.warning(f"{log_prefix}: No valid geometries to union for group '{group_key}'. Skipping group.")
                continue

            try:
                dissolved_s_geom = unary_union(shapely_geoms_to_union)
                if dissolved_s_geom is None or dissolved_s_geom.is_empty:
                    logger.warning(f"{log_prefix}: Unary union resulted in an empty geometry for group '{group_key}'.")
                    continue

                dissolved_s_geom = make_valid_geometry(dissolved_s_geom)
                if dissolved_s_geom is None or dissolved_s_geom.is_empty:
                    logger.warning(f"{log_prefix}: Dissolved geometry became empty after final make_valid for group '{group_key}'.")
                    continue

                # Attributes for the new dissolved feature:
                # Start with attributes of the first feature in the group.
                # Then, if dissolving by field, ensure that field has the group_key value.
                new_attributes = first_attrs_in_group.copy() if first_attrs_in_group else {}
                if config.dissolve_by_field:
                    actual_key_to_store = group_key if group_key != config.group_for_missing_key else None
                    new_attributes[config.dissolve_by_field] = actual_key_to_store

                # TODO: Implement attribute aggregation from config.attribute_aggregation_rules if provided

                # Convert back to DxfPlanner geometry/geometries
                # convert_shapely_to_dxfplanner_geometry can return a list (e.g. for GeometryCollection)
                final_dxf_geoms = convert_shapely_to_anygeogeometry(dissolved_s_geom)

                geoms_to_yield_for_group = []
                if isinstance(final_dxf_geoms, list):
                    geoms_to_yield_for_group.extend(g for g in final_dxf_geoms if g)
                elif final_dxf_geoms:
                    geoms_to_yield_for_group.append(final_dxf_geoms)

                if not geoms_to_yield_for_group:
                    logger.warning(f"{log_prefix}: Failed to convert dissolved Shapely geometry back to DxfPlannerGeometry for group '{group_key}'.")
                    continue

                for result_geom_part in geoms_to_yield_for_group:
                    yield GeoFeature(
                        geometry=result_geom_part,
                        attributes=new_attributes, # All parts of a dissolved group get same attrs
                        crs=crs_for_group
                    )
                    dissolved_feature_count +=1
                logger.debug(f"{log_prefix}: Successfully dissolved group '{group_key}'. Result type: {dissolved_s_geom.geom_type if dissolved_s_geom else 'N/A'}. Yielded {len(geoms_to_yield_for_group)} DXF geometry part(s).")

            except GEOSException as e_geos_dissolve:
                logger.error(f"{log_prefix}: GEOSException during unary_union or post-processing for group '{group_key}': {e_geos_dissolve}", exc_info=True)
            except Exception as e_dissolve_general:
                logger.error(f"{log_prefix}: Error processing group '{group_key}': {e_dissolve_general}", exc_info=True)

        logger.info(f"{log_prefix}: Completed. Produced {dissolved_feature_count} dissolved feature parts from {len(grouped_features_data)} groups.")


class FilterByAttributeOperation(IOperation[FilterByAttributeOperationConfig]):
    """Filters features based on attribute values matching specified criteria."""

    def __init__(self, logger_param: Optional[Any] = None):
        self.logger = logger_param if logger_param else logger

    def _evaluate_condition(self, feature_value: Any, condition_value: Any, operator: FilterOperator) -> bool:
        """Evaluates a single filter condition."""
        # Handle cases where feature_value might be None (attribute does not exist or is null)
        if operator == FilterOperator.IS_NULL:
            return feature_value is None
        if operator == FilterOperator.IS_NOT_NULL:
            return feature_value is not None

        if feature_value is None: # For other operators, if feature_value is None, it typically doesn't match unless IS_NULL was used
            return False

        try:
            # Ensure consistent type for comparison, default to string comparison if types are tricky
            # For numeric comparisons, explicitly cast AFTER checking if they can be numbers

            if operator in [FilterOperator.GREATER_THAN, FilterOperator.LESS_THAN,
                            FilterOperator.GREATER_THAN_OR_EQUAL_TO, FilterOperator.LESS_THAN_OR_EQUAL_TO]:
                # Attempt numeric conversion; if it fails, this condition part is false for these ops
                try:
                    num_feature_value = float(feature_value)
                    num_condition_value = float(condition_value)
                except (ValueError, TypeError):
                    self.logger.debug(f"Cannot convert to float for numeric comparison. Feature: '{feature_value}', Condition: '{condition_value}'. Operator: {operator}.")
                    return False # Cannot perform numeric comparison

                if operator == FilterOperator.GREATER_THAN: return num_feature_value > num_condition_value
                if operator == FilterOperator.LESS_THAN: return num_feature_value < num_condition_value
                if operator == FilterOperator.GREATER_THAN_OR_EQUAL_TO: return num_feature_value >= num_condition_value
                if operator == FilterOperator.LESS_THAN_OR_EQUAL_TO: return num_feature_value <= num_condition_value

            # String-based comparisons
            str_feature_value = str(feature_value)
            str_condition_value = str(condition_value)

            if operator == FilterOperator.EQUALS: return str_feature_value == str_condition_value
            if operator == FilterOperator.NOT_EQUALS: return str_feature_value != str_condition_value
            if operator == FilterOperator.CONTAINS: return str_condition_value in str_feature_value
            if operator == FilterOperator.NOT_CONTAINS: return str_condition_value not in str_feature_value
            if operator == FilterOperator.STARTS_WITH: return str_feature_value.startswith(str_condition_value)
            if operator == FilterOperator.ENDS_WITH: return str_feature_value.endswith(str_condition_value)

            if operator == FilterOperator.IN or operator == FilterOperator.NOT_IN:
                if not isinstance(condition_value, list):
                    self.logger.warning(f"{operator} operator expects a list for condition_value, got {type(condition_value)}. Returning False.")
                    return False

                # Convert list items to string for comparison, similar to how feature_value is treated
                condition_value_str_list = [str(v) for v in condition_value]
                if operator == FilterOperator.IN: return str_feature_value in condition_value_str_list
                if operator == FilterOperator.NOT_IN: return str_feature_value not in condition_value_str_list

        except (ValueError, TypeError) as e: # Catch broad errors during conversion/comparison
            self.logger.debug(f"Error during comparison: {e}. Feature value: '{feature_value}', Condition value: '{condition_value}', Operator: {operator}. Returning False.")
            return False

        self.logger.warning(f"Unknown or unhandled operator: {operator} in _evaluate_condition. Returning False.")
        return False

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: FilterByAttributeOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        """
        Executes the filter operation based on a list of conditions and a logical operator.
        """
        log_prefix = f"FilterByAttributeOperation (source_layer: '{config.source_layer}', output: '{config.output_layer_name}')"
        self.logger.info(f"{log_prefix}: Executing with {len(config.conditions)} condition(s) and operator '{config.logical_operator}'.")

        if not config.conditions:
            self.logger.warning(f"{log_prefix}: No filter conditions provided. Yielding all features.")
            async for feature_no_cond in features:
                yield feature_no_cond
            self.logger.info(f"{log_prefix}: Completed (no conditions, all features yielded).")
            return

        yielded_count = 0
        processed_count = 0

        async for feature in features:
            processed_count += 1
            # Use feature.attributes, ensuring it's a dict even if None originally
            current_attributes = feature.attributes if feature.attributes is not None else {}

            results_per_condition = []
            for condition_config in config.conditions: # Renamed for clarity
                feature_value = current_attributes.get(condition_config.attribute) # Use .get() for safety
                condition_match = self._evaluate_condition(feature_value, condition_config.value, condition_config.operator)
                results_per_condition.append(condition_match)
                self.logger.debug(f"Filter Eval: Attr '{condition_config.attribute}', FeatVal '{feature_value}', Op '{condition_config.operator}', CondVal '{condition_config.value}', Match: {condition_match}")


            final_match = False
            if not results_per_condition: # Should not happen if config.conditions is not empty due to check above
                self.logger.warning(f"{log_prefix}: No condition results evaluated for a feature, though conditions exist. Defaulting to no match. Attrs: {current_attributes}")
                final_match = False
            elif config.logical_operator == LogicalOperator.AND:
                final_match = all(results_per_condition)
            elif config.logical_operator == LogicalOperator.OR:
                final_match = any(results_per_condition)
            else: # Should be caught by Pydantic schema for LogicalOperator, but defensive
                self.logger.error(f"{log_prefix}: Unknown logical operator: {config.logical_operator}. Defaulting to no match.")
                final_match = False

            if final_match:
                yield feature
                yielded_count += 1
            else:
                self.logger.debug(f"{log_prefix}: Feature did not match combined conditions. Results: {results_per_condition}. Attrs: {current_attributes}")


        self.logger.info(f"{log_prefix}: Completed. Processed: {processed_count}, Yielded: {yielded_count}.")

class LabelPlacementOperation(IOperation[LabelPlacementOperationConfig]):
    """Performs label placement by utilizing an ILabelPlacementService."""

    def __init__(self, label_placement_service: ILabelPlacementService, style_service: IStyleService, logger_param: Optional[Any] = None):
        self.label_placement_service = label_placement_service
        self.style_service = style_service
        self.logger = logger_param if logger_param else logger

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: LabelPlacementOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        log_prefix = f"LabelPlacementOperation (source: '{config.source_layer}', output: '{config.output_label_layer_name}')"
        self.logger.info(f"{log_prefix}: Delegating to LabelPlacementService.")

        # Determine a contextual layer name for logging/service calls if source_layer is not in op config
        # This could happen if the LabelPlacementOperation is implicitly added by LayerProcessorService
        # and is operating on the output of a previous operation.
        # In such cases, config.source_layer might be None.
        # Using output_label_layer_name as a fallback for context, or a generic default.
        contextual_layer_name_for_service = config.source_layer or config.output_label_layer_name or "unknown_source_for_labeling"

        label_settings = config.label_settings # This is LabelSettingsConfig

        # Resolve text style properties using the style_service for the *operation as a whole*.
        # The StyleService should provide the correct TextStylePropertiesConfig based on the operation's config
        # (which might point to a named style or have inline properties).
        text_style_props_for_service_call: Optional[TextStylePropertiesConfig] = None
        try:
            text_style_props_for_service_call = self.style_service.get_resolved_style_for_label_operation(
                operation_config=config # Pass the full LabelPlacementOperationConfig
            )
            self.logger.debug(f"{log_prefix}: Resolved text style: {text_style_props_for_service_call.model_dump_json(indent=2, exclude_unset=True) if text_style_props_for_service_call else 'None'}")
        except Exception as e_style_resolve:
            self.logger.error(f"{log_prefix}: Error resolving text style: {e_style_resolve}", exc_info=True)
            # Fallback to a default config to allow processing to continue, though labels might not be styled as expected.
            text_style_props_for_service_call = TextStylePropertiesConfig() # Default instance

        # The LabelPlacementService is responsible for generating PlacedLabel objects
        # which contain position, text, and rotation.
        # It takes the features, the LabelSettingsConfig, and the resolved TextStylePropertiesConfig.
        placed_label_data_stream = self.label_placement_service.place_labels_for_features(
            features=features,
            layer_name=contextual_layer_name_for_service, # For context within the service
            config=label_settings,
            text_style_properties=text_style_props_for_service_call # Pass the resolved style
        )

        yielded_count = 0
        async for placed_label in placed_label_data_stream: # placed_label is PlacedLabel model
            # Create a PointGeo for the label's geometry
            label_geometry = PointGeo(coordinates=placed_label.position)

            # Attributes for the GeoFeature representing the label:
            # It's important that the DXF writer can recognize this as a label.
            # We store the text itself, rotation, and the *actual text style properties* used for placement.
            label_attributes: Dict[str, Any] = {
                "__geometry_type__": "LABEL",  # Hint for DXF writer
                "label_text": placed_label.text,
                "label_rotation": placed_label.rotation,
                # Store the resolved text style properties directly in the attributes
                # so the DXF writer has all info needed to create the MTEXT/TEXT entity.
                "text_style_properties": text_style_props_for_service_call.model_dump(exclude_unset=True) if text_style_props_for_service_call else {}
            }

            # Labels typically don't have a CRS or inherit from the features they label,
            # but for consistency, if the first input feature had a CRS, we could assign it.
            # For now, setting to None as their coordinates are usually in the same space
            # as the features they were derived from (which should be consistent by this point).
            yield GeoFeature(geometry=label_geometry, attributes=label_attributes, crs=None)
            yielded_count += 1
            # await asyncio.sleep(0) # Usually not needed here as service call is main async point

        self.logger.info(f"{log_prefix}: Completed. Yielded {yielded_count} label features.")

class FilterByExtentOperation(IOperation[FilterByExtentOperationConfig]):
    """Filters features based on their spatial relationship with a specified extent."""

    def __init__(self, logger_param: Optional[Any] = None):
        self.logger = logger_param if logger_param else logger

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: FilterByExtentOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        log_prefix = (
            f"FilterByExtentOperation (source_layer: '{config.source_layer}', "
            f"output: '{config.output_layer_name}')"
        )
        self.logger.info(f"{log_prefix}: Executing. Extent: ({config.extent.min_x}, {config.extent.min_y}) to ({config.extent.max_x}, {config.extent.max_y}), Extent CRS: {config.extent.crs}")

        try:
            # Create a Shapely polygon from the configuration's extent
            extent_polygon = shapely_box(
                config.extent.min_x, config.extent.min_y,
                config.extent.max_x, config.extent.max_y
            )
            if extent_polygon.is_empty:
                self.logger.error(f"{log_prefix}: Defined extent resulted in an empty polygon. No features will pass.")
                return
            prepared_extent_polygon = prep(extent_polygon)
        except Exception as e_extent:
            self.logger.error(f"{log_prefix}: Failed to create or prepare extent polygon: {e_extent}. Aborting operation.", exc_info=True)
            return

        processed_count = 0
        yielded_count = 0

        async for feature in features:
            processed_count += 1
            if feature.geometry is None:
                self.logger.debug(f"{log_prefix}: Skipping feature with no geometry. Attributes: {feature.attributes}")
                continue

            feature_s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if feature_s_geom is None or feature_s_geom.is_empty:
                self.logger.debug(f"{log_prefix}: Feature geometry is None or empty after Shapely conversion. Attributes: {feature.attributes}")
                continue

            # Make valid to ensure intersection checks are reliable
            feature_s_geom = make_valid_geometry(feature_s_geom)
            if feature_s_geom is None or feature_s_geom.is_empty:
                self.logger.debug(f"{log_prefix}: Feature geometry became None/empty after make_valid. Attributes: {feature.attributes}")
                continue

            feature_crs = feature.crs
            extent_crs = config.extent.crs
            geom_to_check = feature_s_geom

            if feature_crs and extent_crs and feature_crs.lower() != extent_crs.lower():
                self.logger.debug(f"{log_prefix}: Reprojecting feature from CRS '{feature_crs}' to extent CRS '{extent_crs}'.")
                try:
                    geom_to_check = reproject_geometry(feature_s_geom, feature_crs, extent_crs)
                    if geom_to_check is None or geom_to_check.is_empty:
                        self.logger.warning(f"{log_prefix}: Feature geometry became None/empty after reprojection from '{feature_crs}' to '{extent_crs}'. Attrs: {feature.attributes}")
                        continue
                except Exception as e_reproject:
                    self.logger.error(f"{log_prefix}: Error reprojecting feature geometry from '{feature_crs}' to '{extent_crs}': {e_reproject}. Skipping feature. Attrs: {feature.attributes}", exc_info=True)
                    continue
            elif feature_crs and not extent_crs:
                self.logger.debug(f"{log_prefix}: Extent has no CRS. Assuming extent is in feature CRS '{feature_crs}'.")
            elif not feature_crs and extent_crs:
                self.logger.debug(f"{log_prefix}: Feature has no CRS. Assuming feature is in extent CRS '{extent_crs}'.")
            elif not feature_crs and not extent_crs:
                self.logger.debug(f"{log_prefix}: Neither feature nor extent has CRS. Assuming same unknown CRS.")


            # Perform the intersection check (defaulting to 'intersects' mode)
            # TODO: Implement other modes (contains, within) if config.mode is added/uncommented
            try:
                if prepared_extent_polygon.intersects(geom_to_check):
                    # Yield the original feature (with its original geometry and CRS)
                    yield feature
                    yielded_count += 1
                # else: self.logger.debug(f"{log_prefix}: Feature does not intersect extent. Geom type: {geom_to_check.geom_type}")
            except GEOSException as e_geos:
                self.logger.error(f"{log_prefix}: GEOSException during spatial predicate check: {e_geos}. Attrs: {feature.attributes}", exc_info=True)
            except Exception as e_intersect:
                self.logger.error(f"{log_prefix}: Unexpected error during spatial predicate check: {e_intersect}. Attrs: {feature.attributes}", exc_info=True)

        self.logger.info(f"{log_prefix}: Completed. Processed: {processed_count}, Yielded: {yielded_count}.")
