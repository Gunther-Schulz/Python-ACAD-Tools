#!/usr/bin/env python3

import ezdxf
import geopandas as gpd
from shapely.geometry import LineString
from src.adapters.ezdxf_adapter import EzdxfAdapter
from src.services.logging_service import LoggingService
from src.services.config_loader_service import ConfigLoaderService
from src.services.style_applicator_service import StyleApplicatorService
from src.domain.style_models import NamedStyle, LayerStyleProperties

def main():
    # Create the same objects as the test
    logger_service = LoggingService()
    config_loader = ConfigLoaderService(logger_service=logger_service)
    dxf_adapter = EzdxfAdapter(logger_service=logger_service)

    service = StyleApplicatorService(
        config_loader=config_loader,
        logger_service=logger_service,
        dxf_adapter=dxf_adapter
    )

    # Create DXF document like the test
    dxf_document = ezdxf.new('R2010')
    print(f"DXF document created: {dxf_document}")

    # Test adapter directly
    print(f"Adapter available: {dxf_adapter.is_available()}")
    msp_direct = dxf_adapter.get_modelspace(dxf_document)
    print(f"Direct modelspace call: {msp_direct}")
    print(f"Modelspace type: {type(msp_direct)}")
    print(f"Modelspace bool: {bool(msp_direct)}")
    print(f"Modelspace is None: {msp_direct is None}")
    print(f"Modelspace == None: {msp_direct == None}")
    print(f"not msp_direct: {not msp_direct}")

    # Test the truthiness check that's failing
    if not msp_direct:
        print("ERROR: Modelspace evaluates to False!")
    else:
        print("OK: Modelspace evaluates to True")

    # Test the adapter's add_lwpolyline method directly
    coords = [(0, 0), (10, 10)]
    try:
        entity = dxf_adapter.add_lwpolyline(msp_direct, points=coords, dxfattribs={'layer': 'test'})
        print(f"Direct add_lwpolyline call successful: {entity}")
    except Exception as e:
        print(f"Direct add_lwpolyline call failed: {e}")

    # Create test data like the test
    line_geom = LineString([(0, 0), (10, 10)])
    gdf = gpd.GeoDataFrame({'geometry': [line_geom]})

    style = NamedStyle(
        layer=LayerStyleProperties(
            color="red",
            linetype="Continuous",
            lineweight=25
        )
    )

    layer_name = "test_lines"

    print(f"About to call service.add_geodataframe_to_dxf...")
    print(f"  dxf_document: {dxf_document}")
    print(f"  gdf: {gdf}")
    print(f"  layer_name: {layer_name}")
    print(f"  style: {style}")

    try:
        service.add_geodataframe_to_dxf(dxf_document, gdf, layer_name, style)
        print("Service call completed successfully")
    except Exception as e:
        print(f"Service call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
