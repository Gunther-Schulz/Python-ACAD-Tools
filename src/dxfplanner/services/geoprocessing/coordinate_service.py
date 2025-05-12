from typing import List, Optional, Any, Dict, Tuple

# Import required geometry types if needed for transform_geometry
from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.models.geo_models import PointGeo, PolylineGeo, PolygonGeo, GeometryCollection, AnyGeoGeometry # Need these for type checking
from dxfplanner.domain.interfaces import ICoordinateService
from dxfplanner.core.exceptions import CoordinateTransformError
from dxfplanner.config.schemas import CoordinateServiceConfig # For config injection

# Actual projection library
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError # Added ProjError
from pyproj.geometry import transform as pyproj_transform_geometry # For geometry transformation

from dxfplanner.core.logging_config import get_logger

logger = get_logger(__name__)

class CoordinateTransformService(ICoordinateService):
    """Service for performing coordinate reference system transformations."""

    def __init__(self, config: Optional[CoordinateServiceConfig] = None):
        self.config = config # Store config if provided, though not used in this basic impl
        # For caching transformers if desired later:
        self._transformers: Dict[Tuple[str, str], Transformer] = {}

    def _get_transformer(self, from_crs_str: str, to_crs_str: str) -> Transformer:
        """Helper to get or create a pyproj.Transformer. Caches transformers."""
        if not from_crs_str or not to_crs_str:
            raise CoordinateTransformError("Source and target CRS must be provided.")

        cache_key = (from_crs_str, to_crs_str)
        if cache_key not in self._transformers:
            try:
                source_crs = CRS.from_user_input(from_crs_str)
                target_crs = CRS.from_user_input(to_crs_str)
                self._transformers[cache_key] = Transformer.from_crs(
                    crs_from=source_crs, crs_to=target_crs, always_xy=True
                )
            except CRSError as e:
                raise CoordinateTransformError(f"Failed to create transformer from CRS '{from_crs_str}' to '{to_crs_str}': {e}")
        return self._transformers[cache_key]

    def transform_coordinate(self, coord: Coordinate, from_crs: str, to_crs: str) -> Coordinate:
        """Transforms a single coordinate from a source CRS to a target CRS."""
        if from_crs.lower() == to_crs.lower(): # Case-insensitive comparison for CRS strings
            return coord

        transformer = self._get_transformer(from_crs, to_crs)
        try:
            if coord.z is not None:
                x_new, y_new, z_new = transformer.transform(coord.x, coord.y, coord.z)
                return Coordinate(x=x_new, y=y_new, z=z_new)
            else:
                x_new, y_new = transformer.transform(coord.x, coord.y)
                return Coordinate(x=x_new, y=y_new)
        except ProjError as e: # Catch specific projection error
            raise CoordinateTransformError(
                f"Error transforming coordinate {coord} from CRS '{from_crs}' to '{to_crs}': {e}"
            )
        except Exception as e: # Catch any other unexpected errors during transform
            raise CoordinateTransformError(
                f"Unexpected error transforming coordinate {coord} from CRS '{from_crs}' to '{to_crs}': {e}"
            )

    async def transform_coordinates_batch(
        self, coords: List[Coordinate], from_crs: str, to_crs: str
    ) -> List[Coordinate]:
        """Transforms a list of coordinates in batch."""
        if not coords:
            return []
        if from_crs.lower() == to_crs.lower(): # Case-insensitive comparison
            return coords

        transformer = self._get_transformer(from_crs, to_crs)

        # Check for consistent Z presence
        has_z_values = [c.z is not None for c in coords]
        all_have_z = all(has_z_values)
        none_have_z = not any(has_z_values)

        xs = [c.x for c in coords]
        ys = [c.y for c in coords]

        try:
            if all_have_z:
                zs = [c.z for c in coords] # mypy needs this defined in this scope
                new_xs, new_ys, new_zs = transformer.transform(xs, ys, zs)
                return [Coordinate(x=nx, y=ny, z=nz) for nx, ny, nz in zip(new_xs, new_ys, new_zs)]
            elif none_have_z:
                new_xs, new_ys = transformer.transform(xs, ys)
                return [Coordinate(x=nx, y=ny) for nx, ny in zip(new_xs, new_ys)]
            else: # Mixed Z presence
                # Fallback to individual reprojection for mixed Z cases
                # Using the sync method sequentially.
                # logger.debug("Mixed Z presence in batch reprojection; reprojecting individually.")
                reprojected_coords = []
                for coord in coords:
                    reprojected_coords.append(self.transform_coordinate(coord, from_crs, to_crs))
                return reprojected_coords

        except ProjError as e:
            raise CoordinateTransformError(
                f"Error transforming batch coordinates from CRS '{from_crs}' to '{to_crs}': {e}"
            )
        except Exception as e:
             raise CoordinateTransformError(
                f"Unexpected error transforming batch coordinates from CRS '{from_crs}' to '{to_crs}': {e}"
            )

    # New method implementation
    async def transform_geometry(
        self,
        geometry: AnyGeoGeometry, # Use the specific type alias
        from_crs: str,
        to_crs: str
    ) -> AnyGeoGeometry:
        """Transforms the coordinates of a given geometry object using pyproj."""
        if from_crs.lower() == to_crs.lower():
            return geometry

        transformer = self._get_transformer(from_crs, to_crs)

        # Helper function to transform coordinates within the geometry structures
        def _transform_coords(coords: List[Coordinate]) -> List[Coordinate]:
            # Use the existing batch transform logic (non-async for now)
            # NOTE: This currently calls the *async* batch method sequentially inside a sync helper.
            # This is NOT ideal for performance if this method is called frequently.
            # A better approach would involve making this entire method sync or using
            # a proper async approach for batching if pyproj offered async transforms.
            # For simplicity here, we accept the sequential async call.

            # TODO: Revisit performance/async pattern if this becomes a bottleneck.
            # Simplest sync adaptation:
            if not coords: return []
            has_z = [c.z is not None for c in coords]
            all_z = all(has_z)
            no_z = not any(has_z)
            xs = [c.x for c in coords]
            ys = [c.y for c in coords]
            if all_z:
                zs = [c.z for c in coords]
                new_xs, new_ys, new_zs = transformer.transform(xs, ys, zs)
                return [Coordinate(x=nx, y=ny, z=nz) for nx, ny, nz in zip(new_xs, new_ys, new_zs)]
            elif no_z:
                new_xs, new_ys = transformer.transform(xs, ys)
                return [Coordinate(x=nx, y=ny) for nx, ny in zip(new_xs, new_ys)]
            else: # Mixed Z: transform individually
                return [self.transform_coordinate(c, from_crs, to_crs) for c in coords]

        try:
            if isinstance(geometry, PointGeo):
                new_coord = _transform_coords([geometry.coordinate])[0]
                return PointGeo(coordinate=new_coord)
            elif isinstance(geometry, PolylineGeo):
                new_coords = _transform_coords(geometry.coordinates)
                return PolylineGeo(coordinates=new_coords)
            elif isinstance(geometry, PolygonGeo):
                new_exterior = _transform_coords(geometry.exterior_ring)
                new_interiors = [_transform_coords(interior) for interior in geometry.interior_rings]
                return PolygonGeo(exterior_ring=new_exterior, interior_rings=new_interiors)
            elif isinstance(geometry, GeometryCollection):
                # Recursively transform geometries in the collection
                # Note: this recursive call is sync within an async method.
                transformed_geoms = [
                    # Awaiting here would require making _transform_coords and this method fully async
                    # which complicates the pyproj sync usage. Keeping it sync for now.
                    await self.transform_geometry(geom, from_crs, to_crs)
                    for geom in geometry.geometries
                ]
                return GeometryCollection(geometries=transformed_geoms)
            else:
                # Handle other geometry types if they exist (e.g., MultiPoint, MultiPolyline, MultiPolygon)
                # For now, raise an error for unhandled types.
                logger.warning(f"Unhandled geometry type for transformation: {type(geometry)}")
                raise NotImplementedError(f"Transformation for {type(geometry)} not implemented.")

        except (ProjError, CoordinateTransformError) as e:
            logger.error(f"Error transforming geometry from {from_crs} to {to_crs}: {e}", exc_info=True)
            raise CoordinateTransformError(f"Failed to transform geometry: {e}")
        except Exception as e:
            logger.error(f"Unexpected error transforming geometry: {e}", exc_info=True)
            raise CoordinateTransformError(f"Unexpected error during geometry transformation: {e}")
