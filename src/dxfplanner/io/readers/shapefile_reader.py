from typing import AsyncIterator, Optional, Any, Iterator, Dict, Tuple
from pathlib import Path

# External libraries
import fiona
from fiona.errors import DriverError, FionaValueError, CRSError as FionaCRSError
from shapely.geometry import shape as shapely_shape, mapping
from shapely.ops import transform as shapely_transform
from functools import partial
import asyncio
import pyproj

# DXFPlanner imports
from dxfplanner.config.schemas import ShapefileSourceConfig # Updated import
from dxfplanner.domain.models.geo_models import GeoFeature, PointGeo, PolylineGeo, PolygonGeo, MultiPointGeo, MultiPolylineGeo, MultiPolygonGeo, GeometryCollectionGeo # Ensure all are imported
from dxfplanner.domain.models.common import Coordinate # Used by geometry utils
from dxfplanner.domain.interfaces import IGeoDataReader, AnyStrPath # Adhering to interface
from dxfplanner.core.exceptions import GeoDataReadError
from dxfplanner.geometry.utils import reproject_geometry, convert_shapely_to_anygeogeometry # Utilities
# from dxfplanner.core.logging_config import get_logger # Removed

# logger = get_logger(__name__) # Removed module logger

class ShapefileReader(IGeoDataReader):
    """Reads geodata from Shapefile format."""

    DEFAULT_ENCODING = "utf-8" # Add default encoding if not present

    def __init__(self, config: ShapefileSourceConfig, logger: Any): # Updated __init__
        self.config = config
        self.logger = logger
        self.default_encoding = self.DEFAULT_ENCODING if config.encoding is None else config.encoding
        self.logger.info(f"ShapefileReader initialized with default_encoding: {self.default_encoding}")

    def _blocking_read_features_sync_generator(
        self,
        source_path_str: str,
        source_crs_str: Optional[str],
        target_crs_str: Optional[str],
        layer_name: Optional[str],
        attribute_filter: Optional[Dict[str, Any]],
        bbox_filter: Optional[Tuple[float, float, float, float]],
        max_features: Optional[int],
        encoding: Optional[str], # Specific encoding for this read
        **kwargs: Any
    ) -> Iterator[GeoFeature]: # Return type is Iterator
        """
        Synchronous generator that performs the actual Fiona I/O and feature processing.
        This method will be run in a separate thread.
        """
        try:
            fiona_source_crs_obj = None # For Fiona's crs parameter
            if source_crs_str:
                try:
                    # Fiona typically expects a dict like {'init': 'epsg:4326'} or a PROJ string.
                    # from_epsg returns a dict. pyproj.CRS can parse various inputs robustly.
                    # Let's try to create a pyproj.CRS object first for validation and then get WKT for Fiona.
                    parsed_crs = pyproj.CRS.from_string(source_crs_str)
                    fiona_source_crs_obj = parsed_crs.to_wkt(pretty=False) # Or use from_string directly if Fiona handles it
                    self.logger.debug(f"Parsed source_crs '{source_crs_str}' to WKT for Fiona: {fiona_source_crs_obj}")
                except Exception as e_crs_parse:
                    self.logger.warning(f"Could not parse source_crs '{source_crs_str}' using pyproj: {e_crs_parse}. Fiona will attempt to read from .prj file or use its default.", exc_info=True)

            actual_encoding_for_read = encoding if encoding else self.default_encoding
            self.logger.info(f"ShapefileReader (sync): Opening '{source_path_str}' with encoding '{actual_encoding_for_read}', layer '{layer_name}'. Fiona CRS obj: {fiona_source_crs_obj}, TargetCRS: {target_crs_str}")

            with fiona.open(
                source_path_str,
                'r',
                encoding=actual_encoding_for_read,
                crs=fiona_source_crs_obj, # Pass WKT or compatible dict; None if not determined
                layer=layer_name,
                bbox=bbox_filter
            ) as collection:
                # Determine the effective source CRS for geometry operations
                effective_s_crs_str = source_crs_str # User-provided CRS string has priority for intent
                if not effective_s_crs_str and collection.crs: # If user didn't provide, try from file
                    # collection.crs is a dict e.g. {'init': 'epsg:4326'} or PROJ.4 string
                    # Convert to a string representation that pyproj can use reliably
                    if isinstance(collection.crs, dict) and collection.crs.get('init'):
                         effective_s_crs_str = collection.crs.get('init')
                    elif isinstance(collection.crs, str): # Already a string
                         effective_s_crs_str = collection.crs
                    else: # Fallback to WKT if available and it's a string
                        effective_s_crs_str = collection.crs_wkt if isinstance(collection.crs_wkt, str) else None
                    if effective_s_crs_str:
                        self.logger.info(f"Effective source CRS determined from shapefile: {effective_s_crs_str}")
                    else:
                        self.logger.warning(f"Could not determine a string representation for source CRS from shapefile's .prj (crs: {collection.crs}, crs_wkt: {collection.crs_wkt}).")


                if not effective_s_crs_str and target_crs_str:
                    self.logger.warning(f"Target CRS '{target_crs_str}' is specified, but no source CRS could be determined for '{source_path_str}'. Reprojection will be skipped.")

                count = 0
                for record in collection:
                    if record is None or record.get("geometry") is None:
                        self.logger.debug("Skipping record with no geometry.")
                        continue

                    if attribute_filter:
                        match = True
                        for key, value in attribute_filter.items():
                            if record.get("properties", {}).get(key) != value:
                                match = False
                                break
                        if not match:
                            continue

                    shapely_geom = shapely_shape(record["geometry"])
                    current_feature_output_crs = effective_s_crs_str # CRS of shapely_geom before any reprojection

                    if target_crs_str and effective_s_crs_str and (target_crs_str.lower() != effective_s_crs_str.lower()):
                        try:
                            # pyproj.transform needs CRS objects
                            source_pyproj_crs = pyproj.CRS.from_string(effective_s_crs_str)
                            target_pyproj_crs = pyproj.CRS.from_string(target_crs_str)

                            project = partial(
                                pyproj.transform,
                                source_pyproj_crs,
                                target_pyproj_crs,
                                always_xy=True # Ensure (lon, lat) or (x,y) order
                            )
                            reprojected_geom = shapely_transform(project, shapely_geom)
                            shapely_geom = reprojected_geom
                            current_feature_output_crs = target_crs_str
                            self.logger.debug(f"Successfully reprojected geometry to {target_crs_str}")
                        except Exception as e_reproject:
                            self.logger.error(f"Error reprojecting geometry from '{effective_s_crs_str}' to '{target_crs_str}': {e_reproject}. Attributes: {record.get('properties')}", exc_info=True)
                            continue # Skip this feature
                    elif target_crs_str and not effective_s_crs_str:
                        # Warning already logged
                        pass

                    dxfplanner_geom = convert_shapely_to_anygeogeometry(shapely_geom)
                    if not dxfplanner_geom:
                        self.logger.warning(f"Could not convert Shapely geometry to DXFPlanner geometry for feature in {source_path_str}. Shapely type: {shapely_geom.geom_type if shapely_geom else 'None'}")
                        continue

                    properties = record.get("properties") if record.get("properties") is not None else {}

                    yield GeoFeature(
                        id=str(record.get("id", f"fid_{count}")), # Ensure ID is string, provide fallback
                        geometry=dxfplanner_geom,
                        properties=properties, # Use original properties
                        crs=current_feature_output_crs
                    )
                    count += 1
                    if max_features and count >= max_features:
                        self.logger.info(f"Reached max_features ({max_features}). Stopping.")
                        break
                self.logger.info(f"ShapefileReader (sync): Finished processing {count} features from '{source_path_str}'.")

        except FileNotFoundError:
            self.logger.error(f"Shapefile not found: {source_path_str}")
            raise GeoDataReadError(f"Shapefile not found: {source_path_str}")
        except fiona.errors.DriverError as e: # Catch specific Fiona errors
            self.logger.error(f"Fiona driver error reading {source_path_str}: {e}", exc_info=True)
            raise GeoDataReadError(f"Fiona driver error for {source_path_str}: {e}") from e
        except UnicodeDecodeError as e_decode:
            self.logger.error(f"Encoding error reading {source_path_str} with encoding {actual_encoding_for_read}: {e_decode}. Try specifying a different encoding.", exc_info=True)
            raise GeoDataReadError(f"Encoding error for {source_path_str}: {e_decode}") from e_decode
        except Exception as e_gen: # Catch-all for other unexpected errors during sync processing
            self.logger.error(f"Unexpected error in _blocking_read_features_sync_generator for {source_path_str}: {e_gen}", exc_info=True)
            raise GeoDataReadError(f"Unexpected error reading shapefile {source_path_str}: {e_gen}") from e_gen

    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None,
        layer_name: Optional[str] = None,
        attribute_filter: Optional[Dict[str, Any]] = None,
        bbox_filter: Optional[Tuple[float, float, float, float]] = None,
        max_features: Optional[int] = None,
        **kwargs: Any
    ) -> AsyncIterator[GeoFeature]:
        self.logger.info(f"ShapefileReader: Queuing read for '{source_path}'. SourceCRS: {source_crs}, TargetCRS: {target_crs}, MaxFeatures: {max_features}")
        source_path_str = str(source_path)
        # Get encoding specific to this read from kwargs, or fall back to instance default
        encoding_for_read = kwargs.get('encoding', self.default_encoding)


        sync_gen_iterator = self._blocking_read_features_sync_generator(
            source_path_str=source_path_str,
            source_crs_str=source_crs,
            target_crs_str=target_crs,
            layer_name=layer_name,
            attribute_filter=attribute_filter,
            bbox_filter=bbox_filter,
            max_features=max_features,
            encoding=encoding_for_read, # Pass specific encoding
            **kwargs
        )

        loop = asyncio.get_running_loop()
        active_task_count = 0 # Simple way to track if at least one item was processed

        while True:
            try:
                feature = await loop.run_in_executor(None, partial(next, sync_gen_iterator))
                active_task_count +=1
                yield feature
            except StopIteration:
                if active_task_count == 0: # Check if StopIteration was immediate (empty source or all filtered pre-yield)
                    self.logger.info(f"ShapefileReader: Threaded generator for '{source_path_str}' yielded no features (completed immediately).")
                else:
                    self.logger.info(f"ShapefileReader: Threaded generator for '{source_path_str}' completed after yielding {active_task_count} features.")
                break
            except GeoDataReadError as e_gd_read: # Catch specific error raised by sync_gen
                self.logger.error(f"ShapefileReader: GeoDataReadError from threaded generator for '{source_path_str}': {e_gd_read.args[0] if e_gd_read.args else str(e_gd_read)}.", exc_info=False) # Log only message
                raise # Re-raise it
            except Exception as e_thread:
                self.logger.error(f"ShapefileReader: Unexpected error in threaded generator execution for '{source_path_str}': {e_thread}", exc_info=True)
                raise GeoDataReadError(f"Unexpected error processing shapefile '{source_path_str}' in thread: {e_thread}") from e_thread

        if active_task_count > 0: # Log final completion only if some processing happened.
             self.logger.info(f"ShapefileReader: Asynchronous iteration for '{source_path_str}' successfully finished.")
        elif active_task_count == 0 and not loop.is_closed(): # if loop is closed, means something went wrong before.
             self.logger.info(f"ShapefileReader: Asynchronous iteration for '{source_path_str}' finished without yielding features (source might be empty or all filtered).")
