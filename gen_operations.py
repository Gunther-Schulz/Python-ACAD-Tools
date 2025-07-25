import os
import re
import shutil

def remove_existing_files():
    if os.path.exists('src/layer_processor.py'):
        os.remove('src/layer_processor.py')
        log_info("Removed existing layer_processor.py")
    if os.path.exists('src/operations'):
        shutil.rmtree('src/operations')
        log_info("Removed existing operations directory")

def create_directory_structure():
    os.makedirs('src/operations', exist_ok=True)

def create_file(filename, content):
    with open(filename, 'w') as f:
        f.write(content)

def extract_class_method(content, class_name, method_name):
    pattern = rf'def {method_name}\(self,.*?\):.*?(?=\n    def|\Z)'
    class_pattern = rf'class {class_name}:.*?(?=\nclass|\Z)'
    class_match = re.search(class_pattern, content, re.DOTALL)
    if class_match:
        class_content = class_match.group(0)
        method_match = re.search(pattern, class_content, re.DOTALL)
        if method_match:
            return method_match.group(0)
    return ''

def remove_self_references(content):
    content = re.sub(r'def (\w+)\(self,?\s*', r'def \1(all_layers, project_settings, crs, ', content)
    content = re.sub(r'self\.all_layers', 'all_layers', content)
    content = re.sub(r'self\.project_settings', 'project_settings', content)
    content = re.sub(r'self\.crs', 'crs', content)
    content = re.sub(r'self\.', '', content)
    return content

def add_imports(content, file_name):
    common_imports = [
        "import geopandas as gpd",
        "from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint",
        "from src.utils import log_info, log_warning, log_error",
    ]

    specific_imports = {
        'common_operations.py': [
            "from shapely.ops import unary_union",
            "from shapely.validation import make_valid",
            "import pandas as pd",
            "from geopandas import GeoSeries",
            "import re"
        ],
        'buffer_operation.py': [
            "from shapely.ops import unary_union",
            "from src.operations.common_operations import _process_layer_info, _get_filtered_geometry"
        ],
        'copy_operation.py': [
            "from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe"
        ],
        'difference_operation.py': [
            "from shapely.ops import unary_union",
            "from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, _remove_empty_geometries"
        ],
        'filter_operation.py': [
            "from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe"
        ],
        'intersection_operation.py': [
            "import traceback",
            "from src.operations.common_operations import _create_overlay_layer"
        ],
        'merge_operation.py': [
            "from shapely.ops import unary_union",
            "from src.operations.common_operations import _process_layer_info, _get_filtered_geometry"
        ],
        'smooth_operation.py': [
            "from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe"
        ],
        'contour_operation.py': [
            "from src.contour_processor import process_contour",
            "from src.operations.common_operations import _get_filtered_geometry"
        ],
        'wmts_wms_operation.py': [
            "import os",
            "from src.wmts_downloader import download_wmts_tiles, download_wms_tiles, process_and_stitch_tiles",
            "from owslib.wmts import WebMapTileService",
            "from src.project_loader import project_loader"
        ],
        'utils.py': [
            "from shapely.ops import unary_union, linemerge",
            "from shapely.validation import make_valid",
            "from shapely.geometry import LinearRing",
            "import math"
        ],
        'layer_processor.py': [
            "import os",
            "import shutil",
            "from src.project_loader import project_loader",
            "import ezdxf"
        ]
    }

    imports = common_imports + specific_imports.get(file_name, [])
    if file_name != 'common_operations.py':
        imports.append("from src.operations.common_operations import *")
    return "\n".join(imports) + "\n\n" + content

def main():
    remove_existing_files()

    # BROKEN: Referenced file does not exist
    # with open('src/layer_processor.old.py', 'r') as f:
    #     content = f.read()
    print("ERROR: gen_operations.py references non-existent 'src/layer_processor.old.py'")
    print("This script appears to be broken and should be fixed or removed.")
    return

    create_directory_structure()
    create_file('src/operations/__init__.py', '')

    common_functions = [
        '_get_filtered_geometry',
        '_process_layer_info',
        '_extract_coords_from_reason',
        'ensure_geodataframe',
        'standardize_layer_crs',
        'plot_operation_result',
        'write_shapefile',
        '_clean_geometry',
        '_remove_empty_geometries'
    ]

    common_content = ""
    for func in common_functions:
        extracted_func = extract_class_method(content, 'LayerProcessor', func)
        if extracted_func:
            common_content += remove_self_references(extracted_func) + '\n\n'
    common_content = add_imports(common_content, 'common_operations.py')
    create_file('src/operations/common_operations.py', common_content)

    operations = {
        'buffer_operation.py': ['create_buffer_layer'],
        'copy_operation.py': ['create_copy_layer'],
        'difference_operation.py': ['create_difference_layer', '_should_reverse_difference'],
        'filter_operation.py': ['create_filtered_by_intersection_layer'],
        'intersection_operation.py': ['create_intersection_layer', '_create_overlay_layer'],
        'merge_operation.py': ['create_merged_layer'],
        'smooth_operation.py': ['create_smooth_layer', 'smooth_geometry'],
        'contour_operation.py': ['_handle_contour_operation'],
        'wmts_wms_operation.py': ['process_wmts_or_wms_layer'],
    }

    for file, functions in operations.items():
        file_content = ""
        for func in functions:
            extracted_func = extract_class_method(content, 'LayerProcessor', func)
            if extracted_func:
                file_content += remove_self_references(extracted_func) + '\n\n'
        file_content = add_imports(file_content, file)
        create_file(f'src/operations/{file}', file_content)

    utils_functions = [
        '_clean_single_geometry', '_remove_thin_growths',
        '_clean_polygon', '_clean_linear_ring', '_remove_small_polygons',
        '_merge_close_vertices', 'blunt_sharp_angles', '_blunt_polygon_angles',
        '_blunt_ring', '_blunt_linestring_angles', '_calculate_angle',
        '_create_radical_blunt_segment'
    ]

    utils_content = ""
    for func in utils_functions:
        extracted_func = extract_class_method(content, 'LayerProcessor', func)
        if extracted_func:
            utils_content += remove_self_references(extracted_func) + '\n\n'
    utils_content = add_imports(utils_content, 'utils.py')
    create_file('src/operations/utils.py', utils_content)

    layer_processor_content = "from src.operations import *\n\n"
    layer_processor_content += "class LayerProcessor:\n"
    methods = ['__init__', 'process_layers', 'process_layer', 'process_operation', 'setup_shapefiles', 'load_dxf_layer', '_process_hatch_config', 'levenshtein_distance']

    for method in methods:
        extracted_method = extract_class_method(content, 'LayerProcessor', method)
        if extracted_method:
            layer_processor_content += '    ' + extracted_method.replace('\n', '\n    ') + '\n\n'

    layer_processor_content = add_imports(layer_processor_content, 'layer_processor.py')
    create_file('src/layer_processor.py', layer_processor_content)

    log_info("Files and directories created successfully!")

if __name__ == "__main__":
    main()
