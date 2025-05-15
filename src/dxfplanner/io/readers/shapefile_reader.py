from typing import AsyncIterator, Optional, Any
from pathlib import Path

# External libraries
import fiona
from fiona.errors import DriverError, FionaValueError, CRSError as FionaCRSError
from shapely.geometry import shape as shapely_shape

# DXFPlanner imports
from dxfplanner.config.schemas import ShapefileReaderConfig # Updated import
from dxfplanner.domain.models.geo_models import GeoFeature # Base model for output
from dxfplanner.domain.models.common import Coordinate # Used by geometry utils
from dxfplanner.domain.interfaces import IGeoDataReader, AnyStrPath # Adhering to interface
from dxfplanner.core.exceptions import GeoDataReadError
from dxfplanner.geometry.utils import reproject_geometry, convert_shapely_to_anygeogeometry # Utilities
# from dxfplanner.core.logging_config import get_logger # Removed

# logger = get_logger(__name__) # Removed module logger

class ShapefileReader(IGeoDataReader):
    """Reads geodata from Shapefile format."""

    def __init__(self, config: ShapefileReaderConfig, logger: Any): # Updated __init__
        self.config = config
        self.logger = logger
        # self.default_encoding = app_config.io.readers.shapefile.default_encoding # Removed

    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None,
        # Specific to ShapefileSourceConfig, passed via kwargs from LayerProcessor
        encoding: Optional[str] = None, # This parameter can override config
        **kwargs: Any
    ) -> AsyncIterator[GeoFeature]:
        """
        Reads geographic features from a Shapefile.

        Args:
            source_path: Path to the .shp file.
            source_crs: Optional CRS of the source data (e.g., "EPSG:4326"). If None, tries to use .prj file.
            target_crs: Optional target CRS to reproject features to during reading (e.g., "EPSG:3857").
            encoding: Optional encoding for the shapefile's DBF. Defaults to app_config.
            **kwargs: Catches other potential args from LayerConfig.source if any.
        """
        p_source_path = Path(source_path)
        self.logger.info(f"Reading Shapefile: {p_source_path}, Source CRS hint: {source_crs}, Target CRS: {target_crs}") # Use self.logger

        if not p_source_path.exists() or not p_source_path.is_file():
            raise GeoDataReadError(f"Shapefile not found or is not a file: {p_source_path}")
        if not p_source_path.suffix.lower() == ".shp":
            raise GeoDataReadError(f"Specified path is not a .shp file: {p_source_path}")

        actual_encoding = encoding if encoding is not None else self.config.encoding # Use self.config.encoding

        try:
            with fiona.open(p_source_path, 'r', encoding=actual_encoding) as collection:
                # Determine authoritative source CRS for features from this file
                authoritative_source_crs: Optional[str] = None
                try:
                    # Fiona's collection.crs is a dict like {'init': 'epsg:4326'} or a WKT string
                    # We need to robustly convert it to an EPSG string if possible for consistency,
                    # or use the WKT string directly if pyproj can handle it.
                    # For simplicity with reproject_geometry, aim for "EPSG:XXXX" strings.
                    if collection.crs:
                        if isinstance(collection.crs, dict) and collection.crs.get('init'):
                            authoritative_source_crs = str(collection.crs['init']).upper() # e.g. EPSG:4326
                        elif isinstance(collection.crs, str): # WKT string
                            authoritative_source_crs = collection.crs
                        else: # Unrecognized crs format from fiona
                            self.logger.warning(f"Fiona returned CRS in unrecognized format: {collection.crs}. Using provided source_crs hint if available.") # Use self.logger

                    if source_crs: # Parameter takes precedence or fills if file had none
                        if authoritative_source_crs and authoritative_source_crs.lower() != source_crs.lower():
                            self.logger.warning(f"Provided source_crs '{source_crs}' differs from file\'s detected CRS '{authoritative_source_crs}'. Using '{source_crs}'.") # Use self.logger
                        authoritative_source_crs = source_crs.upper()

                    # New: Use config.default_source_crs as a fallback if still not determined
                    if not authoritative_source_crs and self.config.default_source_crs:
                        authoritative_source_crs = self.config.default_source_crs
                        self.logger.info(f"Using default_source_crs from config: {authoritative_source_crs}") # Use self.logger

                    if not authoritative_source_crs:
                         self.logger.warning(f"Could not determine source CRS for {p_source_path}. Reprojection to target_crs might fail or be inaccurate.") # Use self.logger

                except FionaCRSError as e_crs_fiona:
                    self.logger.warning(f"Fiona CRSError when accessing collection.crs for {p_source_path}: {e_crs_fiona}. Using provided source_crs hint: {source_crs}") # Use self.logger
                    if source_crs:
                        authoritative_source_crs = source_crs.upper()
                    # New: Use config.default_source_crs as a fallback
                    elif self.config.default_source_crs:
                        authoritative_source_crs = self.config.default_source_crs
                        self.logger.info(f"Using default_source_crs from config after FionaCRSError: {authoritative_source_crs}") # Use self.logger
                    else:
                        self.logger.error(f"No source CRS could be determined for {p_source_path}. Cannot proceed reliably.") # Use self.logger
                        raise GeoDataReadError(f"Missing source CRS for {p_source_path}") from e_crs_fiona

                self.logger.info(f"Reading features from {p_source_path}. Authoritative Source CRS: {authoritative_source_crs}, Target CRS: {target_crs}, Encoding: {actual_encoding}") # Use self.logger

                for i, record in enumerate(collection):
                    try:
                        shapely_geom_orig = shapely_shape(record['geometry'])
                        if shapely_geom_orig is None or shapely_geom_orig.is_empty:
                            self.logger.debug(f"Skipping feature {i} with null or empty geometry.") # Use self.logger
                            continue

                        properties = dict(record['properties'])
                        feature_id = record.get('id') # fiona records might have 'id' or not

                        current_s_geom = shapely_geom_orig
                        current_crs = authoritative_source_crs

                        # On-the-fly reprojection if target_crs is specified and different
                        if target_crs and authoritative_source_crs and target_crs.lower() != authoritative_source_crs.lower():
                            reprojected_s_geom = reproject_geometry(shapely_geom_orig, authoritative_source_crs, target_crs)
                            if reprojected_s_geom:
                                current_s_geom = reprojected_s_geom
                                current_crs = target_crs
                                self.logger.debug(f"Feature {i} reprojected from {authoritative_source_crs} to {target_crs}") # Use self.logger
                            else:
                                self.logger.warning(f"Failed to reproject feature {i} from {authoritative_source_crs} to {target_crs}. Using original geometry and CRS.") # Use self.logger

                        # Convert Shapely geometry to AnyGeoGeometry model
                        geo_model_geom = convert_shapely_to_anygeogeometry(current_s_geom)

                        if geo_model_geom:
                            yield GeoFeature(
                                geometry=geo_model_geom,
                                properties=properties,
                                id=str(feature_id) if feature_id is not None else f"fid_{i}", # Ensure an ID
                                crs=current_crs # This should be the CRS of geo_model_geom
                            )
                        else:
                            self.logger.warning(f"Could not convert geometry for feature {i} to AnyGeoGeometry model. Shapely type: {current_s_geom.geom_type if current_s_geom else 'None'}") # Use self.logger

                    except Exception as e_feat:
                        self.logger.error(f"Error processing feature {i} from {p_source_path}: {e_feat}", exc_info=True) # Use self.logger
                        # Optionally, could yield a GeoFeature with error information or skip

        except DriverError as e_driver:
            raise GeoDataReadError(f"Fiona DriverError for {p_source_path}: {e_driver}") from e_driver
        except FionaValueError as e_val:
            raise GeoDataReadError(f"Fiona ValueError for {p_source_path} (often path or encoding issue): {e_val}") from e_val
        except FileNotFoundError: # Should be caught by p_source_path.exists() but as safeguard
             raise GeoDataReadError(f"Shapefile not found: {p_source_path}")
        except Exception as e_general:
            raise GeoDataReadError(f"Unexpected error reading shapefile {p_source_path}: {e_general}") from e_general
