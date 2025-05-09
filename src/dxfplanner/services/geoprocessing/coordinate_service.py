from typing import List, Optional

from dxfplanner.domain.models.common import Coordinate
from dxfplanner.domain.interfaces import ICoordinateService
from dxfplanner.core.exceptions import CoordinateTransformError
# from dxfplanner.config.schemas import CoordinateServiceConfig # For config injection

# Placeholder for actual projection library
# import pyproj

class CoordinateTransformService(ICoordinateService):
    """Service for performing coordinate reference system transformations."""

    # def __init__(self, config: CoordinateServiceConfig):
    #     self.config = config
    #     # One could initialize pyproj.Transformer instances here if CRSs are fixed or known at init
    #     # self.transformers: Dict[Tuple[str, str], pyproj.Transformer] = {}

    def _get_transformer(self, from_crs: str, to_crs: str) -> Any: # -> pyproj.Transformer:
        """Helper to get or create a pyproj.Transformer. Caches transformers."""
        # if (from_crs, to_crs) not in self.transformers:
        #     try:
        #         self.transformers[(from_crs, to_crs)] = pyproj.Transformer.from_crs(
        #             crs_from=from_crs, crs_to=to_crs, always_xy=True
        #         )
        #     except pyproj.exceptions.CRSError as e:
        #         raise CoordinateTransformError(f"Failed to create transformer from CRS '{from_crs}' to '{to_crs}': {e}")
        # return self.transformers[(from_crs, to_crs)]
        raise NotImplementedError("_get_transformer requires pyproj and caching logic.")

    def reproject_coordinate(self, coord: Coordinate, from_crs: str, to_crs: str) -> Coordinate:
        """Reprojects a single coordinate from a source CRS to a target CRS."""
        if from_crs == to_crs:
            return coord

        # transformer = self._get_transformer(from_crs, to_crs)
        # try:
        #     if coord.z is not None:
        #         x_new, y_new, z_new = transformer.transform(coord.x, coord.y, coord.z)
        #         return Coordinate(x=x_new, y=y_new, z=z_new)
        #     else:
        #         x_new, y_new = transformer.transform(coord.x, coord.y)
        #         return Coordinate(x=x_new, y=y_new)
        # except pyproj.exceptions.ProjError as e:
        #     raise CoordinateTransformError(
        #         f"Error transforming coordinate {coord} from CRS '{from_crs}' to '{to_crs}': {e}"
        #     )
        raise NotImplementedError(
            "CoordinateTransformService.reproject_coordinate requires pyproj."
        )

    async def reproject_coordinates_batch(
        self, coords: List[Coordinate], from_crs: str, to_crs: str
    ) -> List[Coordinate]:
        """Reprojects a list of coordinates in batch."""
        if not coords:
            return []
        if from_crs == to_crs:
            return coords

        # transformer = self._get_transformer(from_crs, to_crs)
        # # pyproj can transform sequences of coordinates
        # # Prepare lists for transformation
        # xs = [c.x for c in coords]
        # ys = [c.y for c in coords]
        # zs = [c.z for c in coords if c.z is not None] # Handle optional Z

        # try:
        #     if len(zs) == len(coords): # All have Z
        #         new_xs, new_ys, new_zs = transformer.transform(xs, ys, zs)
        #         return [Coordinate(x=nx, y=ny, z=nz) for nx, ny, nz in zip(new_xs, new_ys, new_zs)]
        #     elif not zs: # None have Z
        #         new_xs, new_ys = transformer.transform(xs, ys)
        #         return [Coordinate(x=nx, y=ny) for nx, ny in zip(new_xs, new_ys)]
        #     else: # Mixed Z (transform individually or raise error for simplicity in batch)
        #         # For simplicity, this example will fall back to individual, or you could pad Nones for Z
        #         # This is a good candidate for an async task group if individual transforms are preferred
        #         # Or, ensure all inputs have consistent Z for batching with pyproj like this.
        #         # loguru.logger.warning("Mixed Z presence in batch reprojection; falling back to individual.")
        #         # return [self.reproject_coordinate(c, from_crs, to_crs) for c in coords] # Sync fallback
        #         # As an async method, we could gather async calls to reproject_coordinate
        #         # import asyncio
        #         # tasks = [self._reproject_single_coord_async(c, from_crs, to_crs) for c in coords] # needs an async helper
        #         # return await asyncio.gather(*tasks)
        #         raise CoordinateTransformError("Batch reprojection with mixed Z presence is not straightforwardly handled in this example; ensure all coordinates have Z or none do for batch mode, or implement individual async projection.")

        # except pyproj.exceptions.ProjError as e:
        #     raise CoordinateTransformError(
        #         f"Error transforming batch coordinates from CRS '{from_crs}' to '{to_crs}': {e}"
        #     )
        raise NotImplementedError(
            "CoordinateTransformService.reproject_coordinates_batch requires pyproj."
        )

    # async def _reproject_single_coord_async(self, coord: Coordinate, from_crs: str, to_crs: str) -> Coordinate:
    #     """Async helper for individual reprojection, can be used with asyncio.gather."""
    #     # This would be similar to reproject_coordinate but potentially wrapped if it involved
    #     # I/O or CPU-bound work that should be run in an executor for a truly async app.
    #     # For pyproj, which is C-based, running in a thread pool executor might be appropriate
    #     # for the async version if transformations are very numerous and CPU-intensive.
    #     # import asyncio
    #     # loop = asyncio.get_running_loop()
    #     # return await loop.run_in_executor(None, self.reproject_coordinate, coord, from_crs, to_crs)
    #     return self.reproject_coordinate(coord, from_crs, to_crs) # If reproject_coordinate is quick enough
