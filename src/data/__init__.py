"""
Data handling module for OLADPP.
Handles reading and writing various data formats.
"""
from .shapefile_utils import read_shapefile, write_shapefile

__all__ = ['read_shapefile', 'write_shapefile']
