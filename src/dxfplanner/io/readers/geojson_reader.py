"""
GeoJSON data reader implementation.
"""
import json # For potential malformed JSON errors, though fiona might catch first
from pathlib import Path
from typing import AsyncIterator, Optional, Any

import fiona
from fiona.errors import FionaError, DriverError
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry import shape
from shapely.errors import GeometryTypeError
from shapely.ops import transform as shapely_transform_op

from dxfplanner.config import AppConfig, GeoJsonSourceConfig
from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IGeoDataReader
from dxfplanner.core.exceptions import GeoDataReadError
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class GeoJsonReader(IGeoDataReader[GeoJsonSourceConfig]):
    """
    A reader for GeoJSON files.
    """

    def __init__(self, app_config: AppConfig):
        """
        Initializes the GeoJsonReader.

        Args:
            app_config: The application configuration.
        """
        self.app_config = app_config

    async def read_features(
        self, source_config: GeoJsonSourceConfig, target_crs_epsg: int
    ) -> AsyncIterator[GeoFeature]:
        """
        Reads features from a GeoJSON file, performs CRS transformation, and yields GeoFeature objects.

        Args:
            source_config: Configuration for the GeoJSON data source.
            target_crs_epsg: The EPSG code of the target coordinate reference system.

        Yields:
            GeoFeature: An asynchronous iterator of geographic features.

        Raises:
            FileNotFoundError: If the GeoJSON file specified in source_config is not found.
            fiona.errors.DriverError: If there is an error opening or reading the GeoJSON file.
            ValueError: If the source CRS cannot be determined or is invalid.
        """
        file_path = source_config.file_path
        logger.info(
            f"Reading GeoJSON features from: {file_path}, targeting EPSG:{target_crs_epsg}"
        )

        try:
            with fiona.open(file_path, "r") as collection:
                source_crs_str = source_config.source_crs
                if not source_crs_str:
                    if hasattr(collection, 'crs_wkt') and collection.crs_wkt:
                        source_crs_str = collection.crs_wkt
                        logger.info(
                            f"Source CRS from GeoJSON file (WKT): {source_crs_str}"
                        )
                    elif hasattr(collection, 'crs') and collection.crs:
                         # Attempt to get a string representation if crs is a dict or other object
                        if isinstance(collection.crs, dict) and 'init' in collection.crs:
                            source_crs_str = collection.crs['init'] # e.g., "epsg:4326"
                        elif hasattr(collection.crs, 'to_string'):
                             source_crs_str = collection.crs.to_string()
                        else:
                            logger.warning(f"Could not determine string CRS from collection.crs object: {collection.crs}")
                            source_crs_str = None # Fallback

                        if source_crs_str:
                             logger.info(
                                f"Source CRS from GeoJSON file (parsed): {source_crs_str}"
                            )
                        else:
                            msg = f"Source CRS not defined in config or determinable from GeoJSON file: {file_path}"
                            logger.error(msg)
                            raise ValueError(msg)
                    else:
                        msg = f"Source CRS not defined in config or GeoJSON file: {file_path}"
                        logger.error(msg)
                        raise ValueError(msg)

                source_crs_pyproj = CRS.from_user_input(source_crs_str)
                target_crs_pyproj = CRS.from_epsg(target_crs_epsg)

                transformer = None
                if source_crs_pyproj != target_crs_pyproj:
                    logger.info(
                        f"Transforming from CRS '{source_crs_pyproj.name}' (EPSG:{source_crs_pyproj.to_epsg() or 'N/A'}) to '{target_crs_pyproj.name}' (EPSG:{target_crs_pyproj.to_epsg() or 'N/A'})"
                    )
                    transformer = Transformer.from_crs(
                        source_crs_pyproj, target_crs_pyproj, always_xy=True
                    )

                for i, feature in enumerate(collection):
                    try:
                        geom = shape(feature["geometry"])
                        properties = feature.get("properties", {})

                        if transformer:
                            # Use shapely.ops.transform for robust geometry transformation
                            geom = shapely_transform_op(transformer.transform, geom)

                        yield GeoFeature(
                            geometry=geom,
                            properties=properties,
                        )
                    except Exception as e:
                        logger.error(
                            f"Error processing feature {i} from {file_path}: {e}",
                            exc_info=True,
                        )
                        continue # Skip problematic feature
        except FileNotFoundError:
            logger.error(f"GeoJSON file not found: {file_path}")
            raise
        except fiona.errors.DriverError as e:
            logger.error(f"Fiona driver error reading {file_path}: {e}")
            raise
        except ValueError as e: # Catch CRS value errors
            logger.error(f"CRS related error for {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error reading GeoJSON {file_path}: {e}", exc_info=True
            )
            raise
