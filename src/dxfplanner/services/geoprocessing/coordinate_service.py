import logging
from typing import List, Optional, Any, Dict, Tuple, Union

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.interfaces import ICoordinateService
from dxfplanner.core.exceptions import CoordinateTransformError
from dxfplanner.config.common_schemas import CoordinateServiceConfig # Changed import path

# Actual projection library
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError # Added ProjError

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

    def reproject_coordinate(self, coord: Coordinate, from_crs: str, to_crs: str) -> Coordinate:
        """Reprojects a single coordinate from a source CRS to a target CRS."""
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

    async def reproject_coordinates_batch(
        self, coords: List[Coordinate], from_crs: str, to_crs: str
    ) -> List[Coordinate]:
        """Reprojects a list of coordinates in batch."""
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
                # This part could be optimized further (e.g. asyncio.gather if truly async)
                # but for pyproj CPU-bound ops, sequential is often fine or needs thread pool.
                # For now, using the sync method sequentially.
                # loguru.logger.debug("Mixed Z presence in batch reprojection; reprojecting individually.")
                reprojected_coords = []
                for coord in coords:
                    reprojected_coords.append(self.reproject_coordinate(coord, from_crs, to_crs))
                return reprojected_coords

        except ProjError as e:
            raise CoordinateTransformError(
                f"Error transforming batch coordinates from CRS '{from_crs}' to '{to_crs}': {e}"
            )
        except Exception as e:
             raise CoordinateTransformError(
                f"Unexpected error transforming batch coordinates from CRS '{from_crs}' to '{to_crs}': {e}"
            )

    # Async helper removed as reproject_coordinate is sync and pyproj is CPU-bound.
    # If this service were to be truly async with external calls, that pattern would be useful.
