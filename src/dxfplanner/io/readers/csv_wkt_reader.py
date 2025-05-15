"""
CSV with Well-Known Text (WKT) data reader implementation.
"""
import csv
from pathlib import Path
from typing import AsyncIterator, Optional, Any, Dict

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry import shape
from shapely.errors import WKTReadingError, GeometryTypeError
from shapely.ops import transform as shapely_transform_op
# import asyncio # For async file reading simulation if needed, or async operations # Removed if not used

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.models.common import Coordinate # For conversion
from dxfplanner.domain.models.geo_models import PointGeo, PolylineGeo, PolygonGeo # For conversion
from dxfplanner.domain.interfaces import IGeoDataReader, AnyStrPath
from dxfplanner.config.schemas import CsvWktReaderConfig # Added config import
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError
# Removed: from dxfplanner.core.logging_config import get_logger
# logger = get_logger(__name__) # Will use injected logger

class CsvWktReader(IGeoDataReader):
    """
    A reader for CSV files containing Well-Known Text (WKT) geometries.
    """

    def __init__(self, config: CsvWktReaderConfig, logger: Any): # Added Any for logger type hint
        self.config = config
        self.logger = logger

    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None,
        # Removed **kwargs: Any
    ) -> AsyncIterator[GeoFeature]:
        """
        Reads features from a CSV file with WKT geometry, performs CRS transformation,
        and yields GeoFeature objects.

        Args:
            source_path: Path to the CSV data source file.
            source_crs: Optional CRS of the source WKT data (e.g., "EPSG:4326").
                        If not provided, config.default_source_crs will be used.
            target_crs: Optional target CRS to reproject features to during reading (e.g., "EPSG:25833").

        Yields:
            GeoFeature: An asynchronous iterator of geographic features.

        Raises:
            FileNotFoundError: If the CSV file specified is not found.
            PermissionError: If the file cannot be accessed.
            ConfigurationError: If CRS info is insufficient or config is invalid.
            csv.Error: For CSV parsing issues.
            shapely.errors.WKTReadingError: If WKT geometry is invalid.
            pyproj.exceptions.CRSError: If provided CRS strings are invalid.
            GeoDataReadError: For other general errors during reading or processing.
        """
        if not source_path:
            # This basic validation can remain, or be part of a higher level pre-check
            raise ValueError("source_path must be provided.")
        file_path = Path(source_path)

        # --- Configured parameters ---
        wkt_column = self.config.wkt_column
        delimiter = self.config.delimiter
        encoding = self.config.encoding
        effective_source_crs = source_crs if source_crs is not None else self.config.default_source_crs

        self.logger.info(
            f"Reading CSV+WKT features from: {file_path}, "
            f"wkt_col='{wkt_column}', delim='{delimiter}', "
            f"source_crs='{effective_source_crs}', target_crs='{target_crs}', encoding='{encoding}'"
        )

        # --- CRS Setup ---
        source_crs_pyproj: Optional[CRS] = None
        target_crs_pyproj: Optional[CRS] = None
        transformer: Optional[Transformer] = None

        try:
            if effective_source_crs:
                source_crs_pyproj = CRS.from_user_input(effective_source_crs)
            else:
                self.logger.warning(f"No source CRS provided for {file_path} (neither in call nor config). Assuming WGS84 (EPSG:4326).")
                source_crs_pyproj = CRS.from_epsg(4326) # Default assumption

            if target_crs:
                target_crs_pyproj = CRS.from_user_input(target_crs)

            if source_crs_pyproj and target_crs_pyproj and source_crs_pyproj != target_crs_pyproj:
                self.logger.info(
                    f"Preparing transformation from CRS '{source_crs_pyproj.name}' "
                    f"(EPSG:{source_crs_pyproj.to_epsg() or 'N/A'}) to "
                    f"'{target_crs_pyproj.name}' (EPSG:{target_crs_pyproj.to_epsg() or 'N/A'})"
                )
                transformer = Transformer.from_crs(
                    source_crs_pyproj, target_crs_pyproj, always_xy=True
                )
            elif target_crs_pyproj and source_crs_pyproj == target_crs_pyproj:
                self.logger.info(f"Source and target CRS ('{target_crs}') are the same, no reprojection needed.")
            elif not target_crs:
                 self.logger.info("No target CRS provided, no reprojection will be performed.")

        except CRSError as e:
            msg = f"Invalid CRS specified ('{effective_source_crs}' or '{target_crs}'): {e}"
            self.logger.error(msg)
            raise ConfigurationError(msg) from e

        # --- File Reading and Processing ---
        try:
            # Note: Using sync file open/read within async function.
            # For true async file I/O, libraries like aiofiles would be needed.
            # For CPU-bound CSV/WKT parsing, running in a thread pool executor might be better.
            # Sticking to sync-in-async for simplicity, matching GeoJsonReader pattern.
            with file_path.open('r', newline='', encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile, delimiter=delimiter)
                if wkt_column not in reader.fieldnames:
                     msg = f"WKT column '{wkt_column}' not found in CSV header: {reader.fieldnames}"
                     self.logger.error(msg)
                     raise ConfigurationError(msg)

                row_count = 0
                processed_count = 0
                skipped_count = 0
                for row in reader:
                    row_count += 1
                    try:
                        wkt_string = row.get(wkt_column)
                        if not wkt_string:
                            # self.logger.warning(f"Row {row_count}: WKT string is missing or empty in column '{wkt_column}', skipping.")
                            skipped_count += 1
                            continue

                        # Parse WKT
                        geom_shapely = shape(wkt_string) # Use shape() for auto-detection; loads() is deprecated.

                        # Extract properties (all columns except WKT column)
                        properties = {k: v for k, v in row.items() if k != wkt_column}

                        # Reproject if necessary
                        if transformer:
                            geom_shapely = shapely_transform_op(transformer.transform, geom_shapely)

                        # Convert Shapely geometry to domain model
                        geo_model_geometry: Any
                        if geom_shapely.geom_type == 'Point':
                            geo_model_geometry = PointGeo(coordinates=Coordinate(x=geom_shapely.x, y=geom_shapely.y, z=geom_shapely.z if geom_shapely.has_z else None))
                        elif geom_shapely.geom_type == 'LineString':
                            coords = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 and geom_shapely.has_z else None) for c in geom_shapely.coords]
                            geo_model_geometry = PolylineGeo(coordinates=coords)
                        elif geom_shapely.geom_type == 'Polygon':
                            exterior_coords = [Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 and geom_shapely.has_z else None) for c in geom_shapely.exterior.coords]
                            interiors_coords = []
                            for interior in geom_shapely.interiors:
                                interiors_coords.append([Coordinate(x=c[0], y=c[1], z=c[2] if len(c) > 2 and geom_shapely.has_z else None) for c in interior.coords])
                            geo_model_geometry = PolygonGeo(coordinates=[exterior_coords] + interiors_coords)
                        # TODO: Add support for MultiPoint, MultiLineString, MultiPolygon, GeometryCollection if needed
                        else:
                            self.logger.warning(f"Row {row_count}: Unsupported geometry type '{geom_shapely.geom_type}' encountered. Skipping feature.")
                            skipped_count += 1
                            continue

                        yield GeoFeature(geometry=geo_model_geometry, properties=properties)
                        processed_count += 1

                        # Potential await point for cooperative multitasking if parsing is very long
                        # await asyncio.sleep(0)

                    except WKTReadingError as e:
                        self.logger.error(f"Row {row_count}: Invalid WKT geometry in column '{wkt_column}': {e}. Skipping row. Content: '{wkt_string[:100]}...'")
                        skipped_count += 1
                    except GeometryTypeError as e:
                        self.logger.error(f"Row {row_count}: Unsupported geometry type from WKT in column '{wkt_column}': {e}. Skipping row.")
                        skipped_count += 1
                    except Exception as e:
                        self.logger.error(f"Row {row_count}: Unexpected error processing row: {e}. Skipping row.", exc_info=True)
                        skipped_count += 1

                self.logger.info(f"Finished reading {file_path}. Total rows: {row_count}, Processed: {processed_count}, Skipped: {skipped_count}.")

        except FileNotFoundError:
            self.logger.error(f"CSV file not found: {file_path}")
            raise # Re-raise specific error
        except PermissionError as e:
             self.logger.error(f"Permission denied accessing file: {file_path}: {e}")
             raise GeoDataReadError(f"Permission denied for {file_path}") from e
        except csv.Error as e:
            self.logger.error(f"CSV parsing error in {file_path}: {e}")
            raise GeoDataReadError(f"Failed to parse CSV {file_path}") from e
        except Exception as e:
            self.logger.error(f"Unexpected error reading CSV/WKT {file_path}: {e}", exc_info=True)
            raise GeoDataReadError(f"Failed to read CSV/WKT {file_path}: {e}") from e
