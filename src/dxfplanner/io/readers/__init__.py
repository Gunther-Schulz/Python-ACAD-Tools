# src/dxfplanner/io/readers/__init__.py

# Expose reader classes for easier import if desired, e.g.:
# from .shapefile_reader import ShapefileReader
from .geojson_reader import GeoJsonReader # To be created
# from .csv_wkt_reader import CsvWktReader # To be created

# Alternatively, a factory function could be defined here to return a reader based on file type or config.

# For now, keeping it simple. If ShapefileReader is the only one, direct import is fine too.
from .shapefile_reader import ShapefileReader

__all__ = [
    "ShapefileReader",
    "GeoJsonReader",
    # "CsvWktReader",
]
