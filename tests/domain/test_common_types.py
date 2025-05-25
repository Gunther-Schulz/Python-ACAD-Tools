"""Comprehensive tests for common type aliases and data structures."""
import pytest
from typing import Tuple, Union

from src.domain.common_types import CoordsXY, CoordinateReferenceSystem


class TestCoordsXY:
    """Test cases for CoordsXY type alias."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_type_alias(self):
        """Test CoordsXY type alias accepts tuple of floats."""
        # Valid coordinate pairs
        coords1: CoordsXY = (10.5, 20.3)
        coords2: CoordsXY = (0.0, 0.0)
        coords3: CoordsXY = (-5.5, 15.7)

        assert isinstance(coords1, tuple)
        assert len(coords1) == 2
        assert isinstance(coords1[0], float)
        assert isinstance(coords1[1], float)

        assert coords1 == (10.5, 20.3)
        assert coords2 == (0.0, 0.0)
        assert coords3 == (-5.5, 15.7)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_with_integers(self):
        """Test CoordsXY works with integer coordinates (auto-converted to float)."""
        coords: CoordsXY = (10, 20)

        assert isinstance(coords, tuple)
        assert len(coords) == 2
        # Note: Type alias doesn't enforce runtime type conversion,
        # but the values are still valid for the use case
        assert coords == (10, 20)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_unpacking(self):
        """Test CoordsXY can be unpacked for x, y coordinates."""
        coords: CoordsXY = (100.5, 200.7)
        x, y = coords

        assert x == 100.5
        assert y == 200.7

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_indexing(self):
        """Test CoordsXY supports indexing."""
        coords: CoordsXY = (50.25, 75.75)

        assert coords[0] == 50.25  # x coordinate
        assert coords[1] == 75.75  # y coordinate

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_immutability(self):
        """Test CoordsXY tuples are immutable."""
        coords: CoordsXY = (10.0, 20.0)

        # Tuples are immutable, so this should raise TypeError
        with pytest.raises(TypeError):
            coords[0] = 15.0  # type: ignore

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_arithmetic_operations(self):
        """Test CoordsXY can be used in arithmetic operations."""
        coords1: CoordsXY = (10.0, 20.0)
        coords2: CoordsXY = (5.0, 15.0)

        # Addition (element-wise)
        result = (coords1[0] + coords2[0], coords1[1] + coords2[1])
        assert result == (15.0, 35.0)

        # Subtraction (element-wise)
        result = (coords1[0] - coords2[0], coords1[1] - coords2[1])
        assert result == (5.0, 5.0)

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_distance_calculation(self):
        """Test CoordsXY can be used for distance calculations."""
        import math

        coords1: CoordsXY = (0.0, 0.0)
        coords2: CoordsXY = (3.0, 4.0)

        # Calculate Euclidean distance
        dx = coords2[0] - coords1[0]
        dy = coords2[1] - coords1[1]
        distance = math.sqrt(dx * dx + dy * dy)

        assert distance == 5.0  # 3-4-5 triangle

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coords_xy_list_of_coordinates(self):
        """Test CoordsXY can be used in lists for coordinate sequences."""
        coordinate_list: list[CoordsXY] = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0),
            (0.0, 0.0)  # Closed polygon
        ]

        assert len(coordinate_list) == 5
        assert coordinate_list[0] == (0.0, 0.0)
        assert coordinate_list[-1] == (0.0, 0.0)  # Closed

        # Calculate perimeter
        perimeter = 0.0
        for i in range(len(coordinate_list) - 1):
            x1, y1 = coordinate_list[i]
            x2, y2 = coordinate_list[i + 1]
            segment_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            perimeter += segment_length

        assert perimeter == 40.0  # 10 + 10 + 10 + 10


class TestCoordinateReferenceSystem:
    """Test cases for CoordinateReferenceSystem type alias."""

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_string_format(self):
        """Test CoordinateReferenceSystem accepts string CRS definitions."""
        # EPSG format
        crs1: CoordinateReferenceSystem = "EPSG:4326"
        crs2: CoordinateReferenceSystem = "EPSG:3857"

        # PROJ4 format
        crs3: CoordinateReferenceSystem = "+proj=longlat +datum=WGS84 +no_defs"

        # WKT format (simplified)
        crs4: CoordinateReferenceSystem = 'GEOGCS["WGS 84",DATUM["WGS_1984"]]'

        assert isinstance(crs1, str)
        assert isinstance(crs2, str)
        assert isinstance(crs3, str)
        assert isinstance(crs4, str)

        assert crs1 == "EPSG:4326"
        assert crs2 == "EPSG:3857"
        assert crs3.startswith("+proj=")
        assert crs4.startswith('GEOGCS[')

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_integer_epsg_code(self):
        """Test CoordinateReferenceSystem accepts integer EPSG codes."""
        crs1: CoordinateReferenceSystem = 4326  # WGS84
        crs2: CoordinateReferenceSystem = 3857  # Web Mercator
        crs3: CoordinateReferenceSystem = 32633  # UTM Zone 33N

        assert isinstance(crs1, int)
        assert isinstance(crs2, int)
        assert isinstance(crs3, int)

        assert crs1 == 4326
        assert crs2 == 3857
        assert crs3 == 32633

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_common_epsg_codes(self):
        """Test common EPSG codes used in GIS applications."""
        common_crs_codes = {
            4326: "WGS84 Geographic",
            3857: "Web Mercator",
            32633: "UTM Zone 33N",
            25832: "ETRS89 UTM Zone 32N",
            2154: "RGF93 Lambert-93",
            3035: "ETRS89 LAEA Europe"
        }

        for epsg_code, description in common_crs_codes.items():
            crs: CoordinateReferenceSystem = epsg_code
            assert isinstance(crs, int)
            assert crs == epsg_code

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_string_epsg_format(self):
        """Test EPSG string format variations."""
        epsg_formats = [
            "EPSG:4326",
            "epsg:4326",
            "EPSG:3857",
            "EPSG:32633"
        ]

        for epsg_string in epsg_formats:
            crs: CoordinateReferenceSystem = epsg_string
            assert isinstance(crs, str)
            assert ":" in crs
            assert crs.upper().startswith("EPSG:")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_proj4_format(self):
        """Test PROJ4 string format."""
        proj4_examples = [
            "+proj=longlat +datum=WGS84 +no_defs",
            "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs",
            "+proj=utm +zone=33 +datum=WGS84 +units=m +no_defs"
        ]

        for proj4_string in proj4_examples:
            crs: CoordinateReferenceSystem = proj4_string
            assert isinstance(crs, str)
            assert crs.startswith("+proj=")

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_type_flexibility(self):
        """Test that CRS type alias accepts both string and int as documented."""
        # Function that accepts CRS parameter
        def process_crs(crs: CoordinateReferenceSystem) -> str:
            if isinstance(crs, int):
                return f"EPSG:{crs}"
            elif isinstance(crs, str):
                if crs.upper().startswith("EPSG:"):
                    return crs.upper()
                else:
                    return crs
            else:
                return str(crs)

        # Test with integer
        result1 = process_crs(4326)
        assert result1 == "EPSG:4326"

        # Test with EPSG string
        result2 = process_crs("epsg:3857")
        assert result2 == "EPSG:3857"

        # Test with PROJ4 string
        proj4_crs = "+proj=longlat +datum=WGS84 +no_defs"
        result3 = process_crs(proj4_crs)
        assert result3 == proj4_crs

    @pytest.mark.unit
    @pytest.mark.domain
    @pytest.mark.fast
    def test_crs_in_data_structures(self):
        """Test CRS type alias in various data structures."""
        # Dictionary mapping
        crs_mapping: dict[str, CoordinateReferenceSystem] = {
            "geographic": 4326,
            "web_mercator": "EPSG:3857",
            "utm_33n": 32633,
            "custom_proj4": "+proj=longlat +datum=WGS84 +no_defs"
        }

        assert crs_mapping["geographic"] == 4326
        assert crs_mapping["web_mercator"] == "EPSG:3857"
        assert isinstance(crs_mapping["utm_33n"], int)
        assert isinstance(crs_mapping["custom_proj4"], str)

        # List of CRS
        crs_list: list[CoordinateReferenceSystem] = [
            4326,
            "EPSG:3857",
            32633,
            "+proj=utm +zone=33 +datum=WGS84"
        ]

        assert len(crs_list) == 4
        assert isinstance(crs_list[0], int)
        assert isinstance(crs_list[1], str)


class TestCommonTypesIntegration:
    """Integration tests for common types working together."""

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.fast
    def test_coordinate_transformation_workflow(self):
        """Test a realistic workflow using both CoordsXY and CRS types."""
        # Define source and target CRS
        source_crs: CoordinateReferenceSystem = 4326  # WGS84
        target_crs: CoordinateReferenceSystem = "EPSG:3857"  # Web Mercator

        # Define coordinates in WGS84 (longitude, latitude)
        wgs84_coords: list[CoordsXY] = [
            (0.0, 0.0),      # Null Island
            (2.3522, 48.8566),  # Paris
            (-74.0060, 40.7128), # New York
            (139.6917, 35.6895)  # Tokyo
        ]

        # Simulate coordinate transformation (simplified)
        def transform_coords(coords: CoordsXY, from_crs: CoordinateReferenceSystem,
                           to_crs: CoordinateReferenceSystem) -> CoordsXY:
            """Simplified coordinate transformation simulation."""
            lon, lat = coords

            # This is a simplified Web Mercator transformation
            # In real applications, use proper transformation libraries
            if from_crs == 4326 and (to_crs == "EPSG:3857" or to_crs == 3857):
                import math
                x = lon * 20037508.34 / 180
                y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
                y = y * 20037508.34 / 180
                return (x, y)
            else:
                # Identity transformation for other cases
                return coords

        # Transform all coordinates
        transformed_coords: list[CoordsXY] = []
        for coord in wgs84_coords:
            transformed = transform_coords(coord, source_crs, target_crs)
            transformed_coords.append(transformed)

        # Verify transformation results
        assert len(transformed_coords) == len(wgs84_coords)

        # Null Island should transform to (0, 0) in Web Mercator
        null_island_transformed = transformed_coords[0]
        assert abs(null_island_transformed[0]) < 1e-6  # Close to 0
        assert abs(null_island_transformed[1]) < 1e-6  # Close to 0

        # Other coordinates should have reasonable Web Mercator values
        for transformed in transformed_coords[1:]:
            x, y = transformed
            # Web Mercator coordinates should be in reasonable ranges
            assert -20037508.34 <= x <= 20037508.34
            assert -20037508.34 <= y <= 20037508.34

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.fast
    def test_geometry_with_crs_metadata(self):
        """Test combining coordinates with CRS metadata."""
        # Define a simple geometry with CRS information
        class SimpleGeometry:
            def __init__(self, coordinates: list[CoordsXY], crs: CoordinateReferenceSystem):
                self.coordinates = coordinates
                self.crs = crs

            def get_bounds(self) -> tuple[CoordsXY, CoordsXY]:
                """Get bounding box as (min_coords, max_coords)."""
                if not self.coordinates:
                    return ((0.0, 0.0), (0.0, 0.0))

                min_x = min(coord[0] for coord in self.coordinates)
                min_y = min(coord[1] for coord in self.coordinates)
                max_x = max(coord[0] for coord in self.coordinates)
                max_y = max(coord[1] for coord in self.coordinates)

                return ((min_x, min_y), (max_x, max_y))

        # Create geometry with WGS84 coordinates
        polygon_coords: list[CoordsXY] = [
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.0, 1.0),
            (0.0, 0.0)  # Closed polygon
        ]

        geometry = SimpleGeometry(polygon_coords, 4326)

        # Test geometry properties
        assert len(geometry.coordinates) == 5
        assert geometry.crs == 4326

        # Test bounding box calculation
        min_coords, max_coords = geometry.get_bounds()
        assert min_coords == (0.0, 0.0)
        assert max_coords == (1.0, 1.0)

        # Test with different CRS
        utm_geometry = SimpleGeometry(
            [(500000.0, 5000000.0), (501000.0, 5001000.0)],
            "EPSG:32633"
        )

        assert utm_geometry.crs == "EPSG:32633"
        utm_min, utm_max = utm_geometry.get_bounds()
        assert utm_min == (500000.0, 5000000.0)
        assert utm_max == (501000.0, 5001000.0)

    @pytest.mark.integration
    @pytest.mark.domain
    @pytest.mark.fast
    def test_type_alias_documentation_examples(self):
        """Test examples that would appear in documentation."""
        # Example 1: Point definition
        point_location: CoordsXY = (123.456, 789.012)
        x_coordinate, y_coordinate = point_location
        assert x_coordinate == 123.456
        assert y_coordinate == 789.012

        # Example 2: CRS specification
        project_crs: CoordinateReferenceSystem = "EPSG:25832"  # ETRS89 UTM Zone 32N
        backup_crs: CoordinateReferenceSystem = 25832  # Same CRS as integer

        # Both should represent the same CRS conceptually
        assert isinstance(project_crs, str)
        assert isinstance(backup_crs, int)

        # Example 3: Coordinate list for a line
        line_coordinates: list[CoordsXY] = [
            (0.0, 0.0),
            (10.0, 10.0),
            (20.0, 5.0)
        ]

        # Calculate line length (simplified)
        total_length = 0.0
        for i in range(len(line_coordinates) - 1):
            x1, y1 = line_coordinates[i]
            x2, y2 = line_coordinates[i + 1]
            segment_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            total_length += segment_length

        # Verify reasonable length calculation
        assert total_length > 0
        expected_length = (10 * 2**0.5) + ((10**2 + 5**2)**0.5)  # sqrt(200) + sqrt(125)
        assert abs(total_length - expected_length) < 1e-10
