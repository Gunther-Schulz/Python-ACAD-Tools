"""
GeoJSON data reader implementation.
"""
import json # For potential malformed JSON errors, though fiona might catch first
from pathlib import Path
from typing import AsyncIterator, Optional, Any, Iterator, Dict, Tuple # Added Iterator, Dict, Tuple
import asyncio # ADDED
from functools import partial # ADDED

import fiona
from fiona.errors import FionaError, DriverError
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry import shape
from shapely.errors import GeometryTypeError
from shapely.ops import transform as shapely_transform_op

from dxfplanner.config import AppConfig, GeoJsonSourceConfig
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import PointGeo, PolylineGeo, PolygonGeo
from dxfplanner.domain.interfaces import IGeoDataReader, AnyStrPath
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError
from dxfplanner.config.schemas import GeoJsonReaderConfig

class GeoJsonReader(IGeoDataReader):
    """
    A reader for GeoJSON files.
    """
    def __init__(self, config: GeoJsonReaderConfig, logger: Any):
        self.config = config
        self.logger = logger

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
        if not source_path:
            raise ValueError("source_path must be provided.")
        file_path = Path(source_path)

        self.logger.info(
            f"GeoJsonReader (sync): Reading features from: {file_path}, source_crs='{source_crs}', target_crs='{target_crs}'"
        )

        if kwargs: # Original kwargs handling
            self.logger.warning(f"GeoJsonReader (sync) received unused kwargs: {kwargs}")

        try:
            fiona_encoding = self.config.encoding_override if self.config.encoding_override else None

            with fiona.open(file_path, "r", encoding=fiona_encoding) as collection:
                source_crs_str_resolved = source_crs
                if not source_crs_str_resolved:
                    source_crs_str_resolved = self.config.default_source_crs
                    if source_crs_str_resolved: self.logger.info(f"GeoJsonReader (sync): Using Source CRS from configuration: {source_crs_str_resolved}")

                if not source_crs_str_resolved: # If still not resolved, try from file
                    if hasattr(collection, 'crs_wkt') and collection.crs_wkt:
                        source_crs_str_resolved = collection.crs_wkt
                        self.logger.info(
                            f"GeoJsonReader (sync): Using Source CRS from GeoJSON file (WKT): {source_crs_str_resolved}"
                        )
                    elif hasattr(collection, 'crs') and collection.crs:
                        if isinstance(collection.crs, dict) and 'init' in collection.crs:
                            source_crs_str_resolved = collection.crs['init']
                        elif hasattr(collection.crs, 'to_string'): # For pyproj.CRS like objects
                            source_crs_str_resolved = collection.crs.to_string()
                        else:
                            self.logger.warning(f"GeoJsonReader (sync): Could not determine string CRS from collection.crs object: {collection.crs}")
                            source_crs_str_resolved = None # Explicitly set to None

                        if source_crs_str_resolved:
                            self.logger.info(
                                f"GeoJsonReader (sync): Using Source CRS from GeoJSON file (parsed): {source_crs_str_resolved}"
                            )
                        # No else needed here, if still None, next block handles it

                if not source_crs_str_resolved:
                    msg = f"GeoJsonReader (sync): Source CRS not provided and cannot be determined from GeoJSON file: {file_path}"
                    self.logger.error(msg)
                    raise ConfigurationError(msg)

                source_crs_pyproj = CRS.from_user_input(source_crs_str_resolved)

                target_crs_pyproj = None
                if target_crs:
                    target_crs_pyproj = CRS.from_user_input(target_crs)
                else:
                    self.logger.info("GeoJsonReader (sync): No target CRS provided, no reprojection will be performed.")

                transformer = None
                if target_crs_pyproj and source_crs_pyproj != target_crs_pyproj:
                    self.logger.info(
                        f"GeoJsonReader (sync): Preparing transformation from CRS '{source_crs_pyproj.name}' "
                        f"(EPSG:{source_crs_pyproj.to_epsg() or 'N/A'}) to "
                        f"'{target_crs_pyproj.name}' (EPSG:{target_crs_pyproj.to_epsg() or 'N/A'})"
                    )
                    transformer = Transformer.from_crs(
                        source_crs_pyproj, target_crs_pyproj, always_xy=True
                    )
                elif target_crs_pyproj and source_crs_pyproj == target_crs_pyproj:
                    self.logger.info(f"GeoJsonReader (sync): Source and target CRS ('{target_crs}') are the same, no reprojection needed.")

                for i, feature in enumerate(collection):
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

        while True:
            try:
                feature = await loop.run_in_executor(None, partial(next, sync_gen_iterator))
                active_task_count += 1
                yield feature
            except StopIteration:
                if active_task_count == 0:
                     self.logger.info(f"GeoJsonReader: Threaded generator for '{source_path}' yielded no features.")
                else:
                     self.logger.info(f"GeoJsonReader: Threaded generator for '{source_path}' completed after {active_task_count} features.")
                break
            except GeoDataReadError as e_gd_read:
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
