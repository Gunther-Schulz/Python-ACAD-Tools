"""Resource manager service for proper resource management and cleanup."""
import gc
import os
import tempfile
import weakref
from contextlib import contextmanager
from typing import Dict, List, Any, Optional, Generator
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..interfaces.logging_service_interface import ILoggingService
from ..interfaces.resource_manager_interface import IResourceManager
from ..domain.exceptions import ApplicationBaseException


class ResourceManagerService(IResourceManager):
    """Service for managing resources and ensuring proper cleanup following existing patterns."""

    def __init__(self, logger_service: ILoggingService):
        """Initialize with injected logger service following existing pattern."""
        self._logger = logger_service.get_logger(__name__)
        self._temporary_files: List[str] = []
        self._geodataframe_refs: List[weakref.ReferenceType] = []  # Store weak references instead of WeakSet
        self._memory_threshold_mb: float = 500.0  # MB threshold for memory management

    def register_geodataframe(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Register a GeoDataFrame for memory tracking following existing pattern."""
        if gdf is not None:
            # Create weak reference and store it
            weak_ref = weakref.ref(gdf)
            self._geodataframe_refs.append(weak_ref)

            # Clean up dead references periodically
            self._cleanup_dead_references()

            self._logger.debug(f"Registered GeoDataFrame with {len(gdf)} features for memory tracking")
        return gdf

    def create_temporary_file(self, suffix: str = ".tmp", prefix: str = "python_acad_") -> str:
        """Create a temporary file and register it for cleanup following existing pattern."""
        try:
            fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
            os.close(fd)  # Close the file descriptor, we just need the path

            self._temporary_files.append(temp_path)
            self._logger.debug(f"Created temporary file: {temp_path}")

            return temp_path
        except Exception as e:
            self._logger.error(f"Failed to create temporary file: {e}", exc_info=True)
            raise ApplicationBaseException(f"Failed to create temporary file: {e}") from e

    @contextmanager
    def temporary_file_context(self, suffix: str = ".tmp", prefix: str = "python_acad_") -> Generator[str, None, None]:
        """Context manager for temporary files with automatic cleanup following existing pattern."""
        temp_path = None
        try:
            temp_path = self.create_temporary_file(suffix=suffix, prefix=prefix)
            yield temp_path
        except Exception as e:
            self._logger.error(f"Error in temporary file context: {e}", exc_info=True)
            raise
        finally:
            if temp_path and temp_path in self._temporary_files:
                self._cleanup_temporary_file(temp_path)

    @contextmanager
    def memory_managed_operation(self, operation_name: str) -> Generator[None, None, None]:
        """Context manager for memory-managed operations following existing pattern."""
        initial_memory = self._get_memory_usage_mb()
        self._logger.debug(f"Starting {operation_name}, initial memory: {initial_memory:.1f} MB")

        try:
            yield
        except Exception as e:
            self._logger.error(f"Error in {operation_name}: {e}", exc_info=True)
            raise
        finally:
            # Force garbage collection and check memory
            gc.collect()
            final_memory = self._get_memory_usage_mb()

            self._logger.debug(f"Completed {operation_name}, final memory: {final_memory:.1f} MB")

            if final_memory > self._memory_threshold_mb:
                self._logger.warning(f"Memory usage ({final_memory:.1f} MB) exceeds threshold ({self._memory_threshold_mb} MB) after {operation_name}")
                self._attempt_memory_cleanup()

    def copy_geodataframe_safely(self, gdf: gpd.GeoDataFrame, operation_context: str = "unknown") -> gpd.GeoDataFrame:
        """Create a safe copy of GeoDataFrame following existing pattern."""
        try:
            if gdf is None or gdf.empty:
                return gdf

            # Create copy and register for tracking
            gdf_copy = gdf.copy()
            self.register_geodataframe(gdf_copy)

            self._logger.debug(f"Created safe copy of GeoDataFrame for {operation_context} with {len(gdf_copy)} features")
            return gdf_copy

        except Exception as e:
            self._logger.error(f"Failed to create safe copy of GeoDataFrame for {operation_context}: {e}", exc_info=True)
            raise ApplicationBaseException(f"Failed to create safe copy of GeoDataFrame for {operation_context}: {e}") from e

    def optimize_geodataframe_memory(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Optimize GeoDataFrame memory usage following existing pattern."""
        if gdf is None or gdf.empty:
            return gdf

        try:
            initial_memory = gdf.memory_usage(deep=True).sum() / (1024 * 1024)  # Convert to MB

            # Optimize data types
            for col in gdf.columns:
                if col != 'geometry':
                    if gdf[col].dtype == 'object':
                        # Try to convert object columns to categorical if beneficial
                        unique_ratio = gdf[col].nunique() / len(gdf)
                        if unique_ratio < 0.5:  # If less than 50% unique values
                            gdf[col] = gdf[col].astype('category')
                    elif gdf[col].dtype == 'float64':
                        # Downcast float64 to float32 if possible
                        if gdf[col].min() >= -3.4e38 and gdf[col].max() <= 3.4e38:
                            gdf[col] = pd.to_numeric(gdf[col], downcast='float')
                    elif gdf[col].dtype == 'int64':
                        # Downcast int64 to smaller integer types if possible
                        gdf[col] = pd.to_numeric(gdf[col], downcast='integer')

            final_memory = gdf.memory_usage(deep=True).sum() / (1024 * 1024)
            memory_saved = initial_memory - final_memory

            if memory_saved > 0.1:  # Only log if significant savings
                self._logger.debug(f"Optimized GeoDataFrame memory: {initial_memory:.1f} MB -> {final_memory:.1f} MB (saved {memory_saved:.1f} MB)")

            return gdf

        except Exception as e:
            self._logger.warning(f"Failed to optimize GeoDataFrame memory: {e}")
            return gdf  # Return original if optimization fails

    def cleanup_temporary_files(self) -> None:
        """Clean up all temporary files following existing pattern."""
        cleaned_count = 0
        for temp_path in self._temporary_files[:]:  # Create a copy to iterate over
            if self._cleanup_temporary_file(temp_path):
                cleaned_count += 1

        if cleaned_count > 0:
            self._logger.info(f"Cleaned up {cleaned_count} temporary files")

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get memory usage statistics following existing pattern."""
        try:
            current_memory = self._get_memory_usage_mb()

            # Clean up dead references and count live ones
            self._cleanup_dead_references()
            tracked_gdfs = len(self._geodataframe_refs)
            temp_files = len(self._temporary_files)

            return {
                'current_memory_mb': round(current_memory, 2),
                'memory_threshold_mb': self._memory_threshold_mb,
                'tracked_geodataframes': tracked_gdfs,
                'temporary_files': temp_files,
                'memory_threshold_exceeded': current_memory > self._memory_threshold_mb
            }
        except Exception as e:
            self._logger.warning(f"Failed to get memory statistics: {e}")
            return {'error': str(e)}

    def cleanup_all_resources(self) -> None:
        """Clean up all managed resources following existing pattern."""
        try:
            # Clean up temporary files
            self.cleanup_temporary_files()

            # Clear GeoDataFrame references
            gdf_count = len(self._geodataframe_refs)
            self._geodataframe_refs.clear()

            # Force garbage collection
            gc.collect()

            final_memory = self._get_memory_usage_mb()
            self._logger.info(f"Cleaned up all resources: {gdf_count} GeoDataFrames, final memory: {final_memory:.1f} MB")

        except Exception as e:
            self._logger.error(f"Error during resource cleanup: {e}", exc_info=True)

    def _cleanup_temporary_file(self, temp_path: str) -> bool:
        """Clean up a specific temporary file following existing pattern."""
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                self._logger.debug(f"Removed temporary file: {temp_path}")

            if temp_path in self._temporary_files:
                self._temporary_files.remove(temp_path)

            return True

        except Exception as e:
            self._logger.warning(f"Failed to remove temporary file {temp_path}: {e}")
            return False

    def _get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB following existing pattern."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except ImportError:
            # Fallback if psutil not available
            try:
                import resource
                return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB to MB on Linux
            except:
                return 0.0

    def _attempt_memory_cleanup(self) -> None:
        """Attempt to clean up memory following existing pattern."""
        try:
            initial_memory = self._get_memory_usage_mb()

            # Force garbage collection
            gc.collect()

            # Clean up temporary files
            self.cleanup_temporary_files()

            final_memory = self._get_memory_usage_mb()
            memory_freed = initial_memory - final_memory

            if memory_freed > 0.1:
                self._logger.info(f"Memory cleanup freed {memory_freed:.1f} MB")

        except Exception as e:
            self._logger.warning(f"Memory cleanup failed: {e}")

    def _cleanup_dead_references(self) -> None:
        """Clean up dead weak references following existing pattern."""
        # Filter out dead references
        live_refs = [ref for ref in self._geodataframe_refs if ref() is not None]
        removed_count = len(self._geodataframe_refs) - len(live_refs)
        self._geodataframe_refs = live_refs

        if removed_count > 0:
            self._logger.debug(f"Cleaned up {removed_count} dead GeoDataFrame references")

    def __del__(self):
        """Destructor to ensure cleanup following existing pattern."""
        try:
            self.cleanup_all_resources()
        except:
            pass  # Suppress errors in destructor
