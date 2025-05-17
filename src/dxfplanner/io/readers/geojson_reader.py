"""
GeoJSON data reader implementation.
"""
import json # For potential malformed JSON errors, though fiona might catch first
from pathlib import Path
from typing import AsyncIterator, Optional, Any, Iterator, Dict, Tuple # Added Iterator, Dict, Tuple
import asyncio # ADDED
from functools import partial # ADDED
from typing import cast

import os # DEBUGGING EnvError
print(f"[geojson_reader.py] TOP LEVEL - Initial GDAL_DATA: {os.environ.get('GDAL_DATA')}") # DEBUGGING EnvError
print(f"[geojson_reader.py] TOP LEVEL - Initial PROJ_LIB: {os.environ.get('PROJ_LIB')}") # DEBUGGING EnvError

import fiona
from fiona.errors import FionaError, DriverError
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry import shape
from shapely.errors import GeometryTypeError
from shapely.ops import transform as shapely_transform_op

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import PointGeo, PolylineGeo, PolygonGeo
from dxfplanner.domain.interfaces import IGeoDataReader, AnyStrPath
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError
from dxfplanner.config.schemas import GeoJSONSourceConfig

_SENTINEL = object() # Sentinel to signal end of iteration from thread

class GeoJsonReader(IGeoDataReader):
    """
    A reader for GeoJSON files.
    """
    def __init__(self, config: GeoJSONSourceConfig, logger: Any):
        self.config = config
        self.logger = logger
        # DEBUGGING EnvError
        logger.debug(f"[GeoJsonReader __init__] GDAL_DATA: {os.environ.get('GDAL_DATA')}")
        logger.debug(f"[GeoJsonReader __init__] PROJ_LIB: {os.environ.get('PROJ_LIB')}")

    def _blocking_read_features_sync_generator(
        self,
        source_path: AnyStrPath, # Keep original type for consistency with existing logic
        source_crs: Optional[str],
        target_crs: Optional[str],
        **kwargs: Any
    ) -> Iterator[GeoFeature]: # Changed to Iterator
        """
        Synchronous generator that performs the actual Fiona I/O and feature processing.
        This method will be run in a separate thread.
        """
        # DEBUGGING EnvError
        self.logger.info(f"[_blocking_read_features_sync_generator] ENTRY GDAL_DATA: {os.environ.get('GDAL_DATA')}")
        self.logger.info(f"[_blocking_read_features_sync_generator] ENTRY PROJ_LIB: {os.environ.get('PROJ_LIB')}")

        if not source_path:
            raise ValueError("source_path must be provided.")
        file_path = Path(source_path)

        self.logger.info(
            f"GeoJsonReader (sync): Reading features from: {file_path}, source_crs='{source_crs}', target_crs='{target_crs}'"
        )

        if kwargs: # Original kwargs handling
            self.logger.warning(f"GeoJsonReader (sync) received unused kwargs: {kwargs}")

        try:
            fiona_encoding = self.config.encoding if self.config.encoding else None
            self.logger.debug(f"GeoJsonReader (sync): Effective Fiona encoding: {fiona_encoding if fiona_encoding else 'Fiona default'}")

            # DEBUGGING EnvError
            self.logger.info(f"[_blocking_read_features_sync_generator] PRE-FIONA.OPEN GDAL_DATA: {os.environ.get('GDAL_DATA')}")
            self.logger.info(f"[_blocking_read_features_sync_generator] PRE-FIONA.OPEN PROJ_LIB: {os.environ.get('PROJ_LIB')}")

            with fiona.open(
                file_path,
                mode='r',
                encoding=fiona_encoding # Pass the potentially None encoding to Fiona
            ) as source_collection:
                # CRS Handling:
                # Priority: self.config.crs (from BaseReaderConfig) > file's detected CRS.

                source_crs_str_from_config = self.config.crs.value if self.config.crs else None

                fiona_file_crs_obj = source_collection.crs
                fiona_file_crs_str = str(fiona_file_crs_obj) if fiona_file_crs_obj else None

                self.logger.debug(f"GeoJsonReader (sync): Configured CRS: {source_crs_str_from_config}, File's detected CRS: {fiona_file_crs_str}")

                source_crs_str_resolved: Optional[str] = None
                if source_crs_str_from_config:
                    source_crs_str_resolved = source_crs_str_from_config
                    if fiona_file_crs_str and fiona_file_crs_str.lower() != source_crs_str_from_config.lower():
                        self.logger.warning(
                            f"GeoJsonReader (sync): Configured CRS '{source_crs_str_from_config}' "
                            f"differs from file's CRS '{fiona_file_crs_str}'. Using configured CRS."
                        )
                elif fiona_file_crs_str:
                    source_crs_str_resolved = fiona_file_crs_str
                # If neither is present, source_crs_str_resolved remains None

                self.logger.debug(f"GeoJsonReader (sync): Effective source CRS for features: {source_crs_str_resolved}")

                target_crs_str = target_crs

                transformer: Optional[Transformer] = None # Initialize transformer to None
                if source_crs_str_resolved and target_crs_str and source_crs_str_resolved.lower() != target_crs_str.lower():
                    self.logger.info(f"GeoJsonReader (sync): Reprojecting from {source_crs_str_resolved} to {target_crs_str}")
                    transformer = Transformer.from_crs(source_crs_str_resolved, target_crs_str, always_xy=True)

                for i, feature in enumerate(source_collection):
                    try:
                        if "geometry" not in feature or feature["geometry"] is None:
                            self.logger.warning(f"GeoJsonReader (sync): Feature {i} from {file_path} lacks geometry, skipping.")
                            continue
                        if "properties" not in feature:
                            self.logger.warning(f"GeoJsonReader (sync): Feature {i} from {file_path} lacks properties, using empty dict.")

                        geom_shapely = shape(feature["geometry"])
                        properties = feature.get("properties", {})

                        if transformer:
                            geom_shapely = shapely_transform_op(transformer.transform, geom_shapely)

                        geo_model_geometry: Any
                        geom_type = geom_shapely.geom_type
                        if geom_type == 'Point':
                            geo_model_geometry = PointGeo(coordinates=Coordinate(x=geom_shapely.x, y=geom_shapely.y, z=geom_shapely.z if geom_shapely.has_z else None))
                        elif geom_type == 'LineString':
                            coords_list = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 and geom_shapely.has_z else None) for c in geom_shapely.coords]
                            geo_model_geometry = PolylineGeo(coordinates=coords_list)
                        elif geom_type == 'Polygon':
                            exterior_coords = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 and geom_shapely.has_z else None) for c in geom_shapely.exterior.coords]
                            interiors_coords_list = []
                            for interior in geom_shapely.interiors:
                                interiors_coords_list.append([Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 and geom_shapely.has_z else None) for c in interior.coords])
                            geo_model_geometry = PolygonGeo(coordinates=[exterior_coords] + interiors_coords_list)
                        else:
                            self.logger.warning(f"GeoJsonReader (sync): Feature {i} from {file_path}: Unsupported Shapely geometry type '{geom_type}'. Skipping feature.")
                            continue

                        yield GeoFeature(
                            geometry=geo_model_geometry,
                            properties=properties,
                        )
                    except Exception as e_feat:
                        self.logger.error(
                            f"GeoJsonReader (sync): Error processing feature {i} from {file_path}: {e_feat}",
                            exc_info=True,
                        )
                        continue # Skip feature on error

        except FileNotFoundError:
            self.logger.error(f"GeoJsonReader (sync): File not found: {file_path}")
            raise GeoDataReadError(f"GeoJSON file not found: {file_path}") from None # Use from None for cleaner trace
        except fiona.errors.DriverError as e_fiona_driver:
            self.logger.error(f"GeoJsonReader (sync): Fiona driver error reading {file_path}: {e_fiona_driver}")
            raise GeoDataReadError(f"Fiona driver error for {file_path}: {e_fiona_driver}") from e_fiona_driver
        except CRSError as e_crs:
            self.logger.error(f"GeoJsonReader (sync): Invalid CRS provided for {file_path}: {e_crs}")
            raise GeoDataReadError(f"Invalid CRS for {file_path}: {e_crs}") from e_crs
        except (ConfigurationError, ValueError) as e_config_val:
            self.logger.error(f"GeoJsonReader (sync): Configuration or value error for {file_path}: {e_config_val}")
            raise # Re-raise specific app errors
        except Exception as e_general_sync:
            self.logger.error(f"GeoJsonReader (sync): Unexpected error reading GeoJSON {file_path}: {e_general_sync}", exc_info=True)
            raise GeoDataReadError(f"Failed to read GeoJSON {file_path} in sync generator: {e_general_sync}") from e_general_sync


    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncIterator[GeoFeature]:
        self.logger.info(f"GeoJsonReader: Queuing read for '{source_path}'. SourceCRS: {source_crs}, TargetCRS: {target_crs}")

        sync_gen_iterator = self._blocking_read_features_sync_generator(
            source_path=source_path,
            source_crs=source_crs,
            target_crs=target_crs,
            **kwargs
        )

        loop = asyncio.get_running_loop()
        active_task_count = 0

        def _get_next_item(it):
            try:
                return next(it)
            except StopIteration:
                return _SENTINEL # Return sentinel instead of raising StopIteration

        while True:
            try:
                feature_or_sentinel = await loop.run_in_executor(None, _get_next_item, sync_gen_iterator) # NEW

                if feature_or_sentinel is _SENTINEL:
                    if active_task_count == 0:
                        self.logger.info(f"GeoJsonReader: Threaded generator for '{source_path}' yielded no features or completed immediately.")
                    else:
                        self.logger.info(f"GeoJsonReader: Threaded generator for '{source_path}' completed after {active_task_count} features.")
                    break

                feature = cast(GeoFeature, feature_or_sentinel) # We expect a GeoFeature if not sentinel
                active_task_count += 1
                yield feature
            except GeoDataReadError as e_gd_read: # Catch specific errors from _blocking_read...
                self.logger.error(f"GeoJsonReader: GeoDataReadError from threaded generator for '{source_path}': {e_gd_read.args[0] if e_gd_read.args else str(e_gd_read)}.", exc_info=False)
                raise
            except (ConfigurationError, ValueError) as e_app_err:
                self.logger.error(f"GeoJsonReader: App Error from threaded generator for '{source_path}': {e_app_err}.", exc_info=False)
                raise
            except Exception as e_thread:
                self.logger.error(f"GeoJsonReader: Unexpected error in threaded generator for '{source_path}': {e_thread}", exc_info=True)
                raise GeoDataReadError(f"Unexpected error processing GeoJSON '{source_path}' in thread: {e_thread}") from e_thread

        if active_task_count > 0:
            self.logger.info(f"GeoJsonReader: Async iteration for '{source_path}' successfully finished.")
        elif not loop.is_closed():
            self.logger.info(f"GeoJsonReader: Async iteration for '{source_path}' finished (no features yielded or all filtered).")
