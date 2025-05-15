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

    async def read_features(
        self,
        source_path: AnyStrPath,
        source_crs: Optional[str] = None,
        target_crs: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncIterator[GeoFeature]:
        """
        Reads features from a GeoJSON file, performs CRS transformation, and yields GeoFeature objects.

        Args:
            source_path: Path to the geodata source file or resource.
            source_crs: Optional CRS of the source data (e.g., "EPSG:4326"). If None,
                        attempts to read from file or use config.default_source_crs.
            target_crs: Optional target CRS to reproject features to during reading (e.g., "EPSG:25833").
            **kwargs: Additional keyword arguments (currently logged if present).

        Yields:
            GeoFeature: An asynchronous iterator of geographic features.

        Raises:
            FileNotFoundError: If the GeoJSON file specified in source_config is not found.
            fiona.errors.DriverError: If there is an error opening or reading the GeoJSON file.
            pyproj.exceptions.CRSError: If provided CRS strings are invalid.
            GeoDataReadError: For general errors during reading or processing.
            ConfigurationError: If CRS information is missing and cannot be determined.
        """
        if not source_path:
            raise ValueError("source_path must be provided.")
        file_path = Path(source_path)

        self.logger.info(
            f"Reading GeoJSON features from: {file_path}, source_crs='{source_crs}', target_crs='{target_crs}'"
        )

        if kwargs:
            self.logger.warning(f"GeoJsonReader received unused kwargs: {kwargs}")

        try:
            # Determine encoding for fiona.open
            fiona_encoding = self.config.encoding_override if self.config.encoding_override else None

            with fiona.open(file_path, "r", encoding=fiona_encoding) as collection:
                source_crs_str_resolved = source_crs
                if not source_crs_str_resolved:
                    # Try from config first if not directly provided
                    source_crs_str_resolved = self.config.default_source_crs
                    if source_crs_str_resolved:
                        self.logger.info(f"Using Source CRS from configuration: {source_crs_str_resolved}")

                if not source_crs_str_resolved: # If still not resolved, try from file
                    if hasattr(collection, 'crs_wkt') and collection.crs_wkt:
                        source_crs_str_resolved = collection.crs_wkt
                        self.logger.info(
                            f"Using Source CRS from GeoJSON file (WKT): {source_crs_str_resolved}"
                        )
                    elif hasattr(collection, 'crs') and collection.crs:
                        if isinstance(collection.crs, dict) and 'init' in collection.crs:
                            source_crs_str_resolved = collection.crs['init']
                        elif hasattr(collection.crs, 'to_string'):
                            source_crs_str_resolved = collection.crs.to_string()
                        else:
                            msg = f"Could not determine string CRS from collection.crs object: {collection.crs}"
                            self.logger.warning(msg)
                            source_crs_str_resolved = None

                        if source_crs_str_resolved:
                            self.logger.info(
                                f"Using Source CRS from GeoJSON file (parsed): {source_crs_str_resolved}"
                            )
                        else:
                            msg = f"Source CRS not defined in config or determinable from GeoJSON file: {file_path}"
                            self.logger.error(msg)
                            raise ConfigurationError(msg)
                    else:
                        msg = f"Source CRS not provided and cannot be determined from GeoJSON file: {file_path}"
                        self.logger.error(msg)
                        raise ConfigurationError(msg)

                source_crs_pyproj = CRS.from_user_input(source_crs_str_resolved)

                target_crs_pyproj = None
                if target_crs:
                    target_crs_pyproj = CRS.from_user_input(target_crs)
                else:
                    self.logger.info("No target CRS provided, no reprojection will be performed.")

                transformer = None
                if target_crs_pyproj and source_crs_pyproj != target_crs_pyproj:
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

                for i, feature in enumerate(collection):
                    try:
                        if "geometry" not in feature or feature["geometry"] is None:
                            self.logger.warning(f"Feature {i} from {file_path} lacks geometry, skipping.")
                            continue
                        if "properties" not in feature:
                            self.logger.warning(f"Feature {i} from {file_path} lacks properties, using empty dict.")

                        geom_shapely = shape(feature["geometry"])
                        properties = feature.get("properties", {})

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
                            self.logger.warning(f"Feature {i} from {file_path}: Unsupported Shapely geometry type '{geom_shapely.geom_type}' encountered. Skipping feature.")
                            continue

                        yield GeoFeature(
                            geometry=geo_model_geometry,
                            properties=properties,
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error processing feature {i} from {file_path}: {e}",
                            exc_info=True,
                        )
                        continue
        except FileNotFoundError:
            self.logger.error(f"GeoJSON file not found: {file_path}")
            raise
        except fiona.errors.DriverError as e:
            self.logger.error(f"Fiona driver error reading {file_path}: {e}")
            raise
        except CRSError as e:
            self.logger.error(f"Invalid CRS provided for {file_path}: {e}")
            raise
        except (ConfigurationError, ValueError) as e:
            self.logger.error(f"Configuration or value error for {file_path}: {e}")
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error reading GeoJSON {file_path}: {e}", exc_info=True
            )
            raise GeoDataReadError(f"Failed to read GeoJSON {file_path}: {e}") from e
