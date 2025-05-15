"""
Geometric operations like buffer, simplify, etc.
"""
from typing import AsyncIterator, List, Dict, Any, Optional

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
    MergeOperationConfig,
    DissolveOperationConfig,
    FilterByAttributeOperationConfig,
    LabelPlacementOperationConfig,
    TextStylePropertiesConfig,
    AppConfig
)
from dxfplanner.core.logging_config import get_logger
from shapely.geometry import (
    MultiPoint,
    MultiLineString,
    MultiPolygon,
    GeometryCollection
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
    convert_dxfplanner_geometry_to_shapely,
    convert_shapely_to_dxfplanner_geometry,
    reproject_geometry,
    explode_multipart_geometry,
    remove_islands_from_geometry
)
import types

try:
    import asteval
except ImportError:
    asteval = None

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
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_dxfplanner_geometry(buffered_s_geom)
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

            try:
                simplified_s_geom = shapely_geom.simplify(config.tolerance, preserve_topology=config.preserve_topology)
            except Exception as e_simplify:
                logger.error(f"Error during Shapely simplify operation for feature: {e_simplify}. Attributes: {feature.attributes}", exc_info=True)
                continue

            if simplified_s_geom is None or simplified_s_geom.is_empty:
                logger.debug(f"Simplify result is None or empty for feature. Attributes: {feature.attributes}")
                continue

            geoms_to_yield = []
            if isinstance(simplified_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"Simplify result is a MultiGeometry ({simplified_s_geom.geom_type}) with {len(simplified_s_geom.geoms)} parts. Processing parts.")
                for part_geom in simplified_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty:
                        continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else:
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
                logger.debug("Field map is empty. Passing through original attributes.")
                new_attributes = feature.attributes.copy()

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
                continue

            if source_crs_str.lower() == target_crs_str.lower():
                logger.debug(f"Feature CRS '{source_crs_str}' matches target CRS '{target_crs_str}'. Yielding original feature.")
                yield feature
                continue

            shapely_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if shapely_geom is None:
                logger.warning(f"Could not convert DXFPlanner geometry to Shapely for feature. Attributes: {feature.attributes}")
                continue

            reprojected_s_geom = reproject_geometry(shapely_geom, source_crs_str, target_crs_str)

            if reprojected_s_geom is None or reprojected_s_geom.is_empty:
                logger.warning(f"Reprojection result is None or empty for feature. Source CRS: {source_crs_str}, Target CRS: {target_crs_str}. Attributes: {feature.attributes}")
                continue

            geoms_to_yield = []
            if isinstance(reprojected_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"Reproject result is a MultiGeometry ({reprojected_s_geom.geom_type}) with {len(reprojected_s_geom.geoms)} parts. Processing parts.")
                for part_geom in reprojected_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty:
                        continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_dxfplanner_geometry(reprojected_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from reproject result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
                new_attributes = feature.attributes.copy()
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

            cleaned_s_geom = make_valid_geometry(shapely_geom)

            if cleaned_s_geom is None or cleaned_s_geom.is_empty:
                logger.warning(f"Geometry became None or empty after cleaning (make_valid). Original type: {shapely_geom.geom_type}. Attributes: {feature.attributes}")
                continue

            geoms_to_yield = []
            if isinstance(cleaned_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                logger.debug(f"CleanGeometry result is a MultiGeometry ({cleaned_s_geom.geom_type}) with {len(cleaned_s_geom.geoms)} parts. Processing parts.")
                for part_geom in cleaned_s_geom.geoms:
                    if part_geom is None or part_geom.is_empty:
                        continue
                    converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                    if converted_part:
                        geoms_to_yield.append(converted_part)
            else:
                converted_single = convert_shapely_to_dxfplanner_geometry(cleaned_s_geom)
                if converted_single:
                    geoms_to_yield.append(converted_single)

            if not geoms_to_yield:
                logger.debug(f"No valid DXFPlanner geometries could be converted from clean_geometry result. Attributes: {feature.attributes}")
                continue

            for new_dxf_geom in geoms_to_yield:
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
                    new_attributes = feature.attributes.copy()
                    yield GeoFeature(geometry=new_dxf_geom_part, attributes=new_attributes, crs=feature.crs)
                else:
                    logger.warning(f"Could not convert exploded Shapely part back to DXFPlanner geometry. Part type: {single_part_s_geom.geom_type}")

            if part_count == 0 and not (isinstance(shapely_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection))):
                logger.debug(f"Input geometry was likely already single-part and processed by explode_multipart_geometry. Original: {shapely_geom.geom_type}")
            elif part_count == 0:
                 logger.debug(f"No parts yielded after exploding geometry for feature. Original type: {shapely_geom.geom_type}. Attributes: {feature.attributes}")

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

    async def _load_overlay_features(self, layer_names: List[str]) -> List[GeoFeature]:
        """Loads all features from the specified overlay layers."""
        overlay_features: List[GeoFeature] = []
        app_config: AppConfig = self._container.config()

        target_crs_for_overlays = app_config.services.coordinate.default_target_crs
        # If no default target CRS in app_config, overlays will be loaded in their native CRSs
        # or reader's default. This might complicate the main 'execute' method's reprojection logic.
        # For now, assume target_crs_for_overlays will be consistently used by readers if not None.

        for layer_name in layer_names:
            layer_config = next((lc for lc in app_config.layers if lc.name == layer_name), None)
            if not layer_config or not layer_config.source:
                logger.warning(f"Intersection: Overlay layer '{layer_name}' not found in config or has no source. Skipping.")
                continue

            try:
                reader = self._container.resolve_reader(layer_config.source.type)

                # Prepare reader_kwargs, ensuring source_crs and target_crs are correctly passed
                reader_kwargs = layer_config.source.model_dump(exclude={'type', 'crs', 'path'}) # model_dump for safety

                current_source_crs = layer_config.source.crs
                if not current_source_crs: # If not defined on the source itself
                    current_source_crs = app_config.services.coordinate.default_source_crs
                    if current_source_crs:
                        logger.info(f"Using default app source CRS '{current_source_crs}' for overlay layer '{layer_name}'")
                    # else: Reader will attempt to determine or use its own default

                logger.info(f"Intersection: Loading overlay layer '{layer_name}' (SourceCRS: {current_source_crs}, TargetCRS for load: {target_crs_for_overlays})...")

                # Pass resolved source_crs and the common target_crs_for_overlays to the reader
                async for feature in reader.read_features(
                    source_path=layer_config.source.path,
                    source_crs=current_source_crs,
                    target_crs=target_crs_for_overlays,
                    **reader_kwargs
                 ):
                    if feature.geometry:
                        # Ensure feature.properties exists, even if empty
                        if feature.properties is None:
                            feature.properties = {}
                        overlay_features.append(feature)
                logger.info(f"Intersection: Loaded {len(overlay_features)} features from overlay layer '{layer_name}'. Features should now be in CRS: {target_crs_for_overlays if target_crs_for_overlays else 'reader_defined_output_crs'}.")

            except Exception as e:
                logger.error(f"Intersection: Failed to load overlay layer '{layer_name}': {e}", exc_info=True)
                continue
        return overlay_features

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: IntersectionOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        logger.info(f"Executing IntersectionOperation for input layers to intersect with: {config.input_layers}, output: '{config.output_layer_name}'")

        # Determine the common CRS for intersection (from overlay loading)
        app_config: AppConfig = self._container.config()
        intersection_crs = app_config.services.coordinate.default_target_crs
        if not intersection_crs:
            logger.warning("IntersectionOperation: No default_target_crs defined in app_config. CRS consistency for intersection relies on input features and overlay layers already matching or readers handling it. This might lead to incorrect results if CRSs are diverse and not explicitly handled by readers to a common target.")
            # If intersection_crs is None, we proceed assuming CRSs might match or are handled upstream.
            # This is a risky path. A robust implementation might require a common CRS to be enforced or defined.

        overlay_features = await self._load_overlay_features(config.input_layers)
        if not overlay_features:
            logger.warning("Intersection: No valid overlay features loaded. Operation will yield no results.")
            return

        valid_overlay_s_geoms = []
        # Assuming all features from _load_overlay_features are now in 'intersection_crs' if it was set.
        # If intersection_crs was None, their CRS could be varied, making unary_union potentially problematic.
        # For now, proceed with assumption that _load_overlay_features harmonized to intersection_crs if set.
        for feat in overlay_features:
            # Ensure properties exists
            current_feat_properties = feat.properties if feat.properties is not None else {}
            s_geom = convert_dxfplanner_geometry_to_shapely(feat.geometry)
            if s_geom and not s_geom.is_empty:
                 s_geom = make_valid_geometry(s_geom)
                 if s_geom and not s_geom.is_empty:
                     valid_overlay_s_geoms.append(s_geom)
                 else:
                    logger.debug(f"Overlay feature geometry became invalid/empty after make_valid. Properties: {current_feat_properties}")
            else:
                logger.debug(f"Overlay feature geometry is None or empty before make_valid. Properties: {current_feat_properties}")


        if not valid_overlay_s_geoms:
            logger.warning("Intersection: No valid overlay geometries to perform intersection.")
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
        logger.info(f"Intersection: Prepared combined overlay geometry for intersection. Type: {combined_overlay_geom.geom_type}. CRS assumed: {intersection_crs or 'Varies/Unknown'}")

        processed_count = 0
        yielded_count = 0
        async for feature in features:
            processed_count += 1
            # Ensure properties exists
            current_feature_properties = feature.properties if feature.properties is not None else {}
            if feature.geometry is None:
                logger.debug(f"Skipping input feature with no geometry. Properties: {current_feature_properties}")
                continue

            input_s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
            if input_s_geom is None or input_s_geom.is_empty:
                logger.debug(f"Input feature geometry is None or empty after conversion. Properties: {current_feature_properties}")
                continue

            input_s_geom = make_valid_geometry(input_s_geom)
            if input_s_geom is None or input_s_geom.is_empty:
                logger.debug(f"Input feature geometry became invalid/empty after make_valid. Properties: {current_feature_properties}")
                continue

            # Reproject input_s_geom if CRS differs and intersection_crs is known
            current_input_crs = feature.crs
            reprojected_input_s_geom = input_s_geom
            output_crs = feature.crs # Default to original feature's CRS

            if intersection_crs and current_input_crs and current_input_crs.lower() != intersection_crs.lower():
                logger.debug(f"Reprojecting input feature from CRS '{current_input_crs}' to '{intersection_crs}' for intersection.")
                try:
                    reprojected_input_s_geom = reproject_geometry(input_s_geom, current_input_crs, intersection_crs)
                    if reprojected_input_s_geom is None or reprojected_input_s_geom.is_empty:
                        logger.warning(f"Input feature geometry became None/empty after reprojection from '{current_input_crs}' to '{intersection_crs}'. Properties: {current_feature_properties}")
                        continue
                    # Update CRS for output feature later
                    output_crs = intersection_crs
                except Exception as e_reproject:
                    logger.error(f"Error reprojecting input feature from '{current_input_crs}' to '{intersection_crs}': {e_reproject}. Properties: {current_feature_properties}", exc_info=True)
                    continue
            elif not current_input_crs and intersection_crs:
                logger.warning(f"Input feature has no CRS, but intersection CRS ('{intersection_crs}') is set. Assuming input is already in target CRS. This may be incorrect. Properties: {current_feature_properties}")
                output_crs = intersection_crs # Assume output should be intersection_crs
            elif not intersection_crs and current_input_crs:
                logger.warning(f"Intersection CRS is not set, but input feature has CRS '{current_input_crs}'. Intersection will use this CRS. Overlay layers should match. Properties: {current_feature_properties}")
                # output_crs is already current_input_crs
            elif not intersection_crs and not current_input_crs:
                logger.warning(f"Neither intersection_crs nor input feature CRS is set. Assuming all data is in a consistent, unknown CRS. Properties: {current_feature_properties}")
                output_crs = None # CRS is unknown
            # else: CRSs match or intersection_crs is not set and we use input feature's current_input_crs, or both are None
            # output_crs correctly holds the intended CRS for the output based on these conditions.

            intersected_result = None
            try:
                if prepared_combined_overlay.intersects(reprojected_input_s_geom):
                    intersected_result = reprojected_input_s_geom.intersection(combined_overlay_geom)
                    intersected_result = make_valid_geometry(intersected_result)

            except GEOSException as e:
                logger.error(f"GEOSException during intersection for feature: {e}. Properties: {current_feature_properties}", exc_info=True)
                continue
            except Exception as e_general:
                logger.error(f"Unexpected error during intersection processing for feature: {e_general}. Properties: {current_feature_properties}", exc_info=True)
                continue

            if intersected_result is None or intersected_result.is_empty:
                continue

            geoms_to_yield = []
            if isinstance(intersected_result, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
                 for part_geom in intersected_result.geoms:
                     if part_geom is None or part_geom.is_empty:
                         continue
                     converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                     if converted_part:
                         geoms_to_yield.append(converted_part)
            else:
                 converted_single = convert_shapely_to_dxfplanner_geometry(intersected_result)
                 if converted_single:
                     geoms_to_yield.append(converted_single)

            for new_dxf_geom in geoms_to_yield:
                new_feature_properties = deepcopy(current_feature_properties) # Use deepcopy for safety
                yield GeoFeature(geometry=new_dxf_geom, properties=new_feature_properties, crs=output_crs) # Use determined output_crs
                yielded_count += 1

        logger.info(f"IntersectionOperation completed. Processed: {processed_count}, Yielded: {yielded_count}.")


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

        Args:
            features: An asynchronous iterator of GeoFeature objects to process.
            config: Configuration for the merge operation.

        Yields:
            GeoFeature: An asynchronous iterator of resulting merged GeoFeature objects.
                       Typically yields one feature, or multiple if the union results
                       in a GeometryCollection of differing simple types.
        """
        log_prefix = f"MergeOperation (source: '{config.source_layer}', output: '{config.output_layer_name}')"
        logger.info(f"{log_prefix}: Executing...")

        shapely_geoms_to_merge = []
        first_feature_for_attrs: Optional[GeoFeature] = None
        input_feature_count = 0

        async for feature in features:
            input_feature_count += 1
            if first_feature_for_attrs is None:
                first_feature_for_attrs = feature

            if feature.geometry:
                s_geom = convert_dxfplanner_geometry_to_shapely(feature.geometry)
                if s_geom and not s_geom.is_empty:
                    shapely_geoms_to_merge.append(s_geom)
            await asyncio.sleep(0)

        if not shapely_geoms_to_merge:
            logger.info(f"{log_prefix}: No valid geometries found in {input_feature_count} input features to merge. Yielding nothing.")
            return

        logger.info(f"{log_prefix}: Collected {len(shapely_geoms_to_merge)} valid geometries from {input_feature_count} input features for merging.")

        merged_s_geom = None
        try:
            merged_s_geom = unary_union(shapely_geoms_to_merge)
            if merged_s_geom is None or merged_s_geom.is_empty:
                logger.warning(f"{log_prefix}: Unary union resulted in an empty or invalid geometry.")
                return

            merged_s_geom = make_valid_geometry(merged_s_geom)
            if merged_s_geom is None or merged_s_geom.is_empty:
                logger.warning(f"{log_prefix}: Merged geometry became empty or invalid after validation.")
                return

        except GEOSException as e_union:
            logger.error(f"{log_prefix}: Error during unary_union operation: {e_union}", exc_info=True)
            return

        result_attributes = first_feature_for_attrs.attributes.copy() if first_feature_for_attrs else {}
        result_crs = first_feature_for_attrs.crs if first_feature_for_attrs else None

        geoms_to_yield = []
        if isinstance(merged_s_geom, (MultiPoint, MultiLineString, MultiPolygon, GeometryCollection)):
            logger.debug(f"{log_prefix}: Merged result is a MultiGeometry ({merged_s_geom.geom_type}) with {len(merged_s_geom.geoms)} parts.")
            for part_geom in merged_s_geom.geoms:
                if part_geom is None or part_geom.is_empty:
                    continue
                converted_part = convert_shapely_to_dxfplanner_geometry(part_geom)
                if converted_part:
                    geoms_to_yield.append(converted_part)
        elif merged_s_geom:
            converted_single = convert_shapely_to_dxfplanner_geometry(merged_s_geom)
            if converted_single:
                geoms_to_yield.append(converted_single)

        if not geoms_to_yield:
            logger.warning(f"{log_prefix}: No valid DXFPlanner geometries could be converted from the merged result.")
            return

        yielded_count = 0
        for new_dxf_geom in geoms_to_yield:
            yield GeoFeature(geometry=new_dxf_geom, attributes=result_attributes, crs=result_crs)
            yielded_count += 1

        logger.info(f"{log_prefix}: Completed. Yielded {yielded_count} feature(s) from merged geometry.")

class DissolveOperation(IOperation[DissolveOperationConfig]):
    """Dissolves features based on a specified attribute field."""

    def execute(
        self,
        features: List[GeoFeature],
        config: DissolveOperationConfig,
        **kwargs: Any
    ) -> List[GeoFeature]:
        if not features:
            logger.info("DissolveOperation: No features provided to dissolve.")
            return []

        logger.info(f"DissolveOperation: Starting dissolve. Field: '{config.dissolve_by_field}'. Total features: {len(features)}")

        grouped_features: Dict[Any, List[GeoFeature]] = defaultdict(list)

        if config.dissolve_by_field:
            for feature in features:
                key_value = feature.properties.get(config.dissolve_by_field)
                if key_value is None: # Handles missing key or explicit None value
                    group_key = config.group_for_missing_key
                else:
                    group_key = key_value
                    grouped_features[group_key].append(feature)
            logger.debug(f"DissolveOperation: Features grouped into {len(grouped_features)} groups by field '{config.dissolve_by_field}'.")
        else:
            # If no dissolve_by_field, all features go into a single group
            grouped_features["_ALL_FEATURES_"].extend(features)
            logger.debug("DissolveOperation: No dissolve field specified, grouping all features together.")

        dissolved_features: List[GeoFeature] = []
        for group_key, group_features in grouped_features.items():
            if not group_features:
                continue

            shapely_geoms_to_union = []
            for i, feature_to_convert in enumerate(group_features):
                try:
                    shapely_geom = convert_dxfplanner_geometry_to_shapely(feature_to_convert.geometry)
                    if shapely_geom and not shapely_geom.is_empty:
                        valid_geom = make_valid_geometry(shapely_geom)
                        if valid_geom and not valid_geom.is_empty:
                            shapely_geoms_to_union.append(valid_geom)
                        elif i == 0 : # If it's the first feature and it becomes invalid/empty, log it.
                            logger.warning(f"DissolveOperation: Geometry for feature ID '{feature_to_convert.id}' (group '{group_key}') became empty/invalid after make_valid_geometry. Original: {shapely_geom.wkt if shapely_geom else 'None'}")
                    elif i == 0:
                         logger.warning(f"DissolveOperation: Initial geometry for feature ID '{feature_to_convert.id}' (group '{group_key}') is empty or failed conversion. Original DxfPlannerGeom: {feature_to_convert.geometry}")
                except Exception as e:
                    logger.error(f"DissolveOperation: Error converting/validating geometry for feature ID '{feature_to_convert.id}' (group '{group_key}'): {e}", exc_info=True)
                    if i == 0: # If the first feature fails, we might not have attributes.
                        logger.warning(f"DissolveOperation: Skipping feature ID '{feature_to_convert.id}' due to conversion/validation error.")


            if not shapely_geoms_to_union:
                logger.warning(f"DissolveOperation: No valid geometries to union for group '{group_key}'. Skipping group.")
                continue

            try:
                # Perform the unary union
                dissolved_geometry_shapely = unary_union(shapely_geoms_to_union)
                if dissolved_geometry_shapely.is_empty:
                    logger.warning(f"DissolveOperation: Unary union resulted in an empty geometry for group '{group_key}'.")
                    continue

                # Convert back to GeoFeature
                # For simplicity, take properties and dxf_properties from the first feature in the group
                first_feature_in_group = group_features[0]
                new_properties = deepcopy(first_feature_in_group.properties)
                new_dxf_properties = deepcopy(first_feature_in_group.dxf_properties) if first_feature_in_group.dxf_properties else {}

                # Update properties to reflect the dissolve if desired (e.g., add group_key)
                if config.dissolve_by_field:
                    new_properties[config.dissolve_by_field] = group_key if group_key != config.group_for_missing_key else None


                # Ensure the geometry is valid after union as well
                dissolved_geometry_shapely = make_valid_geometry(dissolved_geometry_shapely)
                if dissolved_geometry_shapely.is_empty:
                    logger.warning(f"DissolveOperation: Dissolved geometry became empty after final make_valid for group '{group_key}'.")
                    continue


                dissolved_dxfplanner_geometry = convert_shapely_to_dxfplanner_geometry(dissolved_geometry_shapely)

                if dissolved_dxfplanner_geometry:
                    dissolved_feature = GeoFeature(
                        id=f"dissolved_{group_key}_{dissolved_features.__len__()}", # Generate a new ID
                        geometry=dissolved_dxfplanner_geometry,
                        properties=new_properties,
                        dxf_properties=new_dxf_properties,
                        crs=first_feature_in_group.crs # Preserve CRS from first feature
                    )
                    dissolved_features.append(dissolved_feature)
                    logger.debug(f"DissolveOperation: Successfully dissolved group '{group_key}' into new feature ID '{dissolved_feature.id}'. Result type: {dissolved_geometry_shapely.geom_type}")
                else:
                    logger.warning(f"DissolveOperation: Failed to convert dissolved Shapely geometry back to DxfPlannerGeometry for group '{group_key}'.")

            except Exception as e:
                logger.error(f"DissolveOperation: Error during unary_union or post-processing for group '{group_key}': {e}", exc_info=True)

        logger.info(f"DissolveOperation: Completed. Produced {len(dissolved_features)} dissolved features.")
        return dissolved_features

class FilterByAttributeOperation(IOperation[FilterByAttributeOperationConfig]):
    """Filters features based on an attribute expression using asteval."""

    def __init__(self):
        if asteval is None:
            logger.error("FilterByAttributeOperation: 'asteval' library not found. Filtering will be bypassed. Please install 'asteval'.")
            self._interpreter = None
        else:
            self._interpreter = asteval.Interpreter()

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
            async for feature_bypass in features:
                if not warning_logged_bypass: # Log bypass warning only once
                    logger.warning(f"{log_prefix}: Bypassing filter for all features as 'asteval' is not installed.")
                    warning_logged_bypass = True
                yield feature_bypass
            logger.info(f"{log_prefix}: Completed (bypassed due to missing asteval).")
            return

        expression = config.filter_expression
        if not expression:
            logger.warning(f"{log_prefix}: Filter expression is empty. Yielding all features as per current behavior (or consider raising error/yielding none).")
            async for feature_no_expr in features:
                yield feature_no_expr
            logger.info(f"{log_prefix}: Completed (empty expression, all features yielded).")
            return

        yielded_count = 0
        processed_count = 0

        async for feature in features:
            processed_count += 1

            current_properties = feature.properties if feature.properties else {}

            try:
                # Prepare symbol table for asteval
                self._interpreter.error = [] # Clear previous errors
                self._interpreter.symtable.clear()

                eval_scope = {'properties': current_properties}
                eval_scope['True'] = True
                eval_scope['False'] = False
                eval_scope['None'] = None
                # Add other safe builtins if necessary, e.g., math functions
                # For now, only properties and basic constants.

                self._interpreter.symtable.update(eval_scope)

                if self._interpreter.eval(expression): # Successfully parsed and evaluated
                    expression_value = self._interpreter.symtable.get('_result')
                    if bool(expression_value):
                        yield feature
                        yielded_count += 1
                else: # Evaluation failed (syntax error in expr, or runtime error during eval)
                    errors = self._interpreter.get_error()
                    error_messages = [err.get_error()[1] for err in errors] if errors else ["Unknown evaluation error"]
                    logger.warning(f"{log_prefix}: Error evaluating filter for feature (ID: {feature.id or 'N/A'}): {error_messages}. Expr: '{expression}'. Properties: {current_properties}")
                    # self._interpreter.error = [] # Ensure errors are cleared if not done by eval failure path automatically

            except Exception as e: # Catch any other Python exceptions during the process
                logger.error(f"{log_prefix}: Unexpected Python error during filter processing for feature (ID: {feature.id or 'N/A'}): {e}. Expr: '{expression}'. Properties: {current_properties}", exc_info=True)

        logger.info(f"{log_prefix}: Completed. Processed: {processed_count}, Yielded: {yielded_count}.")

class LabelPlacementOperation(IOperation[LabelPlacementOperationConfig]):
    """Performs label placement by utilizing an ILabelPlacementService."""

    def __init__(self, label_placement_service: ILabelPlacementService, style_service: IStyleService, logger_param: Any = None):
        self.label_placement_service = label_placement_service
        self.style_service = style_service
        self.logger = logger_param if logger_param else logger

    async def execute(
        self,
        features: AsyncIterator[GeoFeature],
        config: LabelPlacementOperationConfig
    ) -> AsyncIterator[GeoFeature]:
        self.logger.info(f"Executing LabelPlacementOperation for source: '{config.source_layer}', output: '{config.output_label_layer_name}'. Delegating to LabelPlacementService.")

        contextual_layer_name = config.source_layer if config.source_layer else "unknown_layer_for_labeling"
        label_settings = config.label_settings

        # Resolve text style properties using the style_service
        text_style_props_for_service_call: Optional[TextStylePropertiesConfig] = None
        try:
            # This call should return a valid TextStylePropertiesConfig, even if default
            text_style_props_for_service_call = self.style_service.get_resolved_style_for_label_operation(config)
            self.logger.debug(f"Resolved text style for LabelPlacementOperation (layer: {contextual_layer_name}): {text_style_props_for_service_call.model_dump_json(indent=2, exclude_unset=True)}")
        except Exception as e_style_resolve:
            self.logger.error(f"Error resolving text style in LabelPlacementOperation for layer '{contextual_layer_name}': {e_style_resolve}", exc_info=True)
            # Fallback to a default config if resolution fails catastrophically (should be rare)
            text_style_props_for_service_call = TextStylePropertiesConfig()

        placed_label_stream = self.label_placement_service.place_labels_for_features(
            features=features,
            layer_name=contextual_layer_name,
            config=label_settings,
            text_style_properties=text_style_props_for_service_call # PASSING THE RESOLVED STYLE
        )

        yielded_count = 0
        async for placed_label in placed_label_stream:
            label_geometry = PointGeo(coordinates=placed_label.position)

            # The text_style_props_for_feature for the GeoFeature attributes should be the same one passed to the service
            # No need to resolve it again here.
            label_attributes = {
                "__geometry_type__": "LABEL",
                "label_text": placed_label.text,
                "label_rotation": placed_label.rotation,
                "text_style_properties": text_style_props_for_service_call.model_dump(exclude_unset=True) if text_style_props_for_service_call else {},
            }

            yield GeoFeature(geometry=label_geometry, attributes=label_attributes, crs=None) # CRS for labels is typically not set or inherited
            yielded_count += 1
            await asyncio.sleep(0)

        self.logger.info(f"LabelPlacementOperation (via service) completed. Yielded {yielded_count} label features for layer '{contextual_layer_name}'.")
