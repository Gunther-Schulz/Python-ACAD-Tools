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
import asyncio # For async file reading simulation if needed, or async operations

from dxfplanner.domain.models.geo_models import GeoFeature
from dxfplanner.domain.interfaces import IGeoDataReader, AnyStrPath
from dxfplanner.core.exceptions import GeoDataReadError, ConfigurationError
from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class CsvWktReader(IGeoDataReader):
    """
    A reader for CSV files containing Well-Known Text (WKT) geometries.
    """

    # No __init__ needed for now, dependencies passed via read_features kwargs if required by logic

    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncIterator[GeoFeature]:
        """
        Reads features from a CSV file with WKT geometry, performs CRS transformation,
        and yields GeoFeature objects.

        Args:
            source_path: Path to the CSV data source file.
            source_crs: Optional CRS of the source WKT data (e.g., "EPSG:4326").
                        Required if not inherently geographic (e.g., WGS84).
            target_crs: Optional target CRS to reproject features to during reading (e.g., "EPSG:25833").
            **kwargs: Must contain 'wkt_column' (str) and 'delimiter' (str).
                      Optionally can contain 'encoding' (str, defaults to utf-8).

        Yields:
            GeoFeature: An asynchronous iterator of geographic features.

        Raises:
            FileNotFoundError: If the CSV file specified is not found.
            PermissionError: If the file cannot be accessed.
            ConfigurationError: If required kwargs ('wkt_column', 'delimiter') are missing or CRS info is insufficient.
            csv.Error: For CSV parsing issues.
            shapely.errors.WKTReadingError: If WKT geometry is invalid.
            pyproj.exceptions.CRSError: If provided CRS strings are invalid.
            GeoDataReadError: For other general errors during reading or processing.
        """
        # --- Parameter Extraction and Validation ---
        if not source_path:
            raise ValueError("source_path must be provided.")
        file_path = Path(source_path)

        try:
            wkt_column = str(kwargs['wkt_column'])
            delimiter = str(kwargs['delimiter'])
        except KeyError as e:
            msg = f"Missing required keyword argument for CsvWktReader: {e}"
            logger.error(msg)
            raise ConfigurationError(msg) from e

        encoding = kwargs.get('encoding', 'utf-8')
        logger.info(
            f"Reading CSV+WKT features from: {file_path}, "
            f"wkt_col='{wkt_column}', delim='{delimiter}', "
            f"source_crs='{source_crs}', target_crs='{target_crs}', encoding='{encoding}'"
        )

        # --- CRS Setup ---
        source_crs_pyproj: Optional[CRS] = None
        target_crs_pyproj: Optional[CRS] = None
        transformer: Optional[Transformer] = None

        try:
            if source_crs:
                source_crs_pyproj = CRS.from_user_input(source_crs)
            else:
                # Attempt to default to WGS84 if no source CRS provided, common for basic WKT
                logger.warning(f"No source CRS provided for {file_path}. Assuming WGS84 (EPSG:4326).")
                source_crs_pyproj = CRS.from_epsg(4326)
                # If this assumption is wrong, reprojection will likely fail or be incorrect.
                # Consider raising ConfigurationError if source_crs is strictly required by workflow.

            if target_crs:
                target_crs_pyproj = CRS.from_user_input(target_crs)

            if source_crs_pyproj and target_crs_pyproj and source_crs_pyproj != target_crs_pyproj:
                logger.info(
                    f"Preparing transformation from CRS '{source_crs_pyproj.name}' "
                    f"(EPSG:{source_crs_pyproj.to_epsg() or 'N/A'}) to "
                    f"'{target_crs_pyproj.name}' (EPSG:{target_crs_pyproj.to_epsg() or 'N/A'})"
                )
                transformer = Transformer.from_crs(
                    source_crs_pyproj, target_crs_pyproj, always_xy=True
                )
            elif target_crs_pyproj and source_crs_pyproj == target_crs_pyproj:
                logger.info(f"Source and target CRS ('{target_crs}') are the same, no reprojection needed.")
            elif not target_crs:
                 logger.info("No target CRS provided, no reprojection will be performed.")

        except CRSError as e:
            msg = f"Invalid CRS specified ('{source_crs}' or '{target_crs}'): {e}"
            logger.error(msg)
            raise ConfigurationError(msg) from e # Raise as config error

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
                     logger.error(msg)
                     raise ConfigurationError(msg)

                row_count = 0
                processed_count = 0
                skipped_count = 0
                for row in reader:
                    row_count += 1
                    try:
                        wkt_string = row.get(wkt_column)
                        if not wkt_string:
                            # logger.warning(f"Row {row_count}: WKT string is missing or empty in column '{wkt_column}', skipping.")
                            skipped_count += 1
                            continue

                        # Parse WKT
                        geom = shape(wkt_string) # Use shape() for auto-detection; loads() is deprecated.

                        # Extract properties (all columns except WKT column)
                        properties = {k: v for k, v in row.items() if k != wkt_column}

                        # Reproject if necessary
                        if transformer:
                            geom = shapely_transform_op(transformer.transform, geom)

                        yield GeoFeature(geometry=geom, properties=properties)
                        processed_count += 1

                        # Potential await point for cooperative multitasking if parsing is very long
                        # await asyncio.sleep(0)

                    except WKTReadingError as e:
                        logger.error(f"Row {row_count}: Invalid WKT geometry in column '{wkt_column}': {e}. Skipping row. Content: '{wkt_string[:100]}...'")
                        skipped_count += 1
                    except GeometryTypeError as e:
                        logger.error(f"Row {row_count}: Unsupported geometry type from WKT in column '{wkt_column}': {e}. Skipping row.")
                        skipped_count += 1
                    except Exception as e:
                        logger.error(f"Row {row_count}: Unexpected error processing row: {e}. Skipping row.", exc_info=True)
                        skipped_count += 1

                logger.info(f"Finished reading {file_path}. Total rows: {row_count}, Processed: {processed_count}, Skipped: {skipped_count}.")

        except FileNotFoundError:
            logger.error(f"CSV file not found: {file_path}")
            raise # Re-raise specific error
        except PermissionError as e:
             logger.error(f"Permission denied accessing file: {file_path}: {e}")
             raise GeoDataReadError(f"Permission denied for {file_path}") from e
        except csv.Error as e:
            logger.error(f"CSV parsing error in {file_path}: {e}")
            raise GeoDataReadError(f"Failed to parse CSV {file_path}") from e
        except Exception as e:
            logger.error(f"Unexpected error reading CSV/WKT {file_path}: {e}", exc_info=True)
            raise GeoDataReadError(f"Failed to read CSV/WKT {file_path}: {e}") from e
