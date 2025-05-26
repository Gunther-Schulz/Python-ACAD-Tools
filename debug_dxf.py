#!/usr/bin/env python3
"""Debug script to check actual lineweight values in DXF."""

import ezdxf
import geopandas as gpd
from shapely.geometry import LineString
from tests.styling.base_test_utils import MockConfigLoader
from src.services.style_applicator_service import StyleApplicatorService
from src.services.logging_service import LoggingService
from tests.styling.base_test_utils import StyleTestFixtures

def main():
    # Create test setup
    line_geom = LineString([(0, 0), (10, 10)])
    gdf = gpd.GeoDataFrame({'geometry': [line_geom]})
    dxf_document = ezdxf.new('R2010')

    # Get style and service
    styles = StyleTestFixtures.load_comprehensive_styles()
    style = styles.styles['basic_layer_red']
    mock_config = MockConfigLoader()
    logger = LoggingService(log_level_console="DEBUG")  # Set console logging to DEBUG
    service = StyleApplicatorService(mock_config, logger)

    print(f"Style lineweight: {style.layer.lineweight}")

    # Check domain model validation
    from src.domain.style_models import DXFLineweight
    print(f"Is style lineweight valid: {DXFLineweight.is_valid_lineweight(style.layer.lineweight)}")

        # Apply style and add to DXF
    service.add_geodataframe_to_dxf(dxf_document, gdf, 'test_lines', style)

    # Check immediately after layer creation
    layer_after_creation = dxf_document.layers.get('test_lines')
    if layer_after_creation:
        print(f"Layer lineweight immediately after add_geodataframe_to_dxf: {layer_after_creation.dxf.lineweight}")

    # Let's also check if the layer exists before we add geometries
    print("\\n--- Testing layer creation only ---")
    test_doc = ezdxf.new('R2010')
    service.apply_styles_to_dxf_layer(test_doc, 'test_layer_only', style)
    test_layer = test_doc.layers.get('test_layer_only')
    if test_layer:
        print(f"Layer lineweight after apply_styles_to_dxf_layer only: {test_layer.dxf.lineweight}")
        print(f"Layer lineweight (direct property): {test_layer.lineweight}")
        print(f"Layer lineweight (hasattr check): {hasattr(test_layer, 'lineweight')}")
        print(f"Layer dxf lineweight (hasattr check): {hasattr(test_layer.dxf, 'lineweight')}")

        # Let's also try to set it directly and see what happens
        print("\\n--- Direct lineweight test ---")
        test_layer.lineweight = 25
        print(f"After setting test_layer.lineweight = 25: {test_layer.lineweight}")
        print(f"After setting test_layer.lineweight = 25 (dxf): {test_layer.dxf.lineweight}")

        test_layer.dxf.lineweight = 25
        print(f"After setting test_layer.dxf.lineweight = 25: {test_layer.lineweight}")
        print(f"After setting test_layer.dxf.lineweight = 25 (dxf): {test_layer.dxf.lineweight}")

    # Check layer properties
    layer = dxf_document.layers.get('test_lines')
    if layer:
        print(f"Layer found: {layer.dxf.name}")
        print(f"Layer color: {layer.dxf.color}")
        print(f"Layer linetype: {layer.dxf.linetype}")
        print(f"Layer lineweight: {layer.dxf.lineweight}")
        print(f"Layer lineweight type: {type(layer.dxf.lineweight)}")

        # Check if lineweight is being set correctly
        print(f"Is valid lineweight: {DXFLineweight.is_valid_lineweight(layer.dxf.lineweight)}")
        print(f"Expected lineweight: 25")
        print(f"Actual lineweight: {layer.dxf.lineweight}")
        print(f"Match: {layer.dxf.lineweight == 25}")
    else:
        print("Layer not found!")

if __name__ == "__main__":
    main()
