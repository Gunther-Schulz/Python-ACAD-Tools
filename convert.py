import os
import sys
import yaml
import geopandas as gpd
import ezdxf
import matplotlib.pyplot as plt
from shapely.ops import linemerge, unary_union
from wmts_downloader import download_wmts_tiles
from shapely.geometry import Point, Polygon, LineString, MultiPolygon, MultiLineString
import random
from ezdxf.addons import odafc
import argparse
import colorama

colorama.init()

def print_warning(message):
    print(f"\033[93mWarning: {message}\033[0m", file=sys.stderr)

def print_error(message):
    print(f"\033[91mError: {message}\033[0m", file=sys.stderr)

class ProjectProcessor:
    def __init__(self, project_name: str, update_layers_list: list = None):
        # Load the color mapping from the YAML file
        with open('colors.yaml', 'r') as file:
            color_data = yaml.safe_load(file)
            self.name_to_aci = {item['name'].lower(): item['aciCode'] for item in color_data}
            self.aci_to_name = {item['aciCode']: item['name'] for item in color_data}

        self.project_settings, self.folder_prefix = self.load_project_settings(
            project_name)
        if not self.project_settings:
            raise ValueError(f"Project {project_name} not found.")

        self.exclusions = self.project_settings.get('exclusions', [])

        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(
            self.project_settings['dxfFilename'])
        self.wmts = self.project_settings.get('wmts', [])
        self.clip_distance_layers = self.project_settings.get('clipDistanceLayers', [])
        self.buffer_distance_layers = self.project_settings.get('bufferDistanceLayers', [])
        self.geltungsbereich_layers = self.project_settings.get('geltungsbereichLayers', [])

        self.template_dxf = self.resolve_full_path(self.project_settings.get(
            'template', '')) if self.project_settings.get('template') else None
        self.gemeinde_shapefile, self.gemeinde_label = self.get_layer_info(
            "Gemeinde")
        self.gemarkung_shapefile, self.gemarkung_label = self.get_layer_info(
            "Gemarkung")
        self.flur_shapefile, self.flur_label = self.get_layer_info("Flur")
        self.parcel_shapefile, self.parcel_label = self.get_layer_info(
            "Parcel")
        self.wald_shapefile, self.wald_label = self.get_layer_info("Wald")
        self.biotope_shapefile, self.biotope_label = self.get_layer_info(
            "Biotope")

        # Load shapefiles
        self.gemeinde_shapefile = self.load_shapefile(self.gemeinde_shapefile)
        self.gemarkung_shapefile = self.load_shapefile(self.gemarkung_shapefile)
        self.flur_shapefile = self.load_shapefile(self.flur_shapefile)
        self.parcel_shapefile = self.load_shapefile(self.parcel_shapefile)
        self.wald_shapefile = self.load_shapefile(self.wald_shapefile)
        self.biotope_shapefile = self.load_shapefile(self.biotope_shapefile)
        
        self.colors = {}
        for layer in self.project_settings['layers']:
            color_code = self.get_color_code(layer['color'])
            self.colors[layer['name']] = color_code
            self.colors[f"{layer['name']} Number"] = color_code  # Add color for label layer

        # Modify this part to create a dictionary of WMTS layers
        self.wmts_layers = {
            wmts['name']: f"WMTS {wmts['name']}" for wmts in self.wmts}

        self.export_format = self.project_settings.get('exportFormat', 'dxf')

        if sys.platform == "darwin" and os.path.exists("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"):
            odafc.unix_exec_path = "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"

        self.update_layers_list = update_layers_list

        # Add layer definitions for all layers, including buffer distance layers
        self.layer_properties = {}
        for layer in self.project_settings['layers']:
            self.add_layer_properties(layer['name'], layer)

        for buffer_layer in self.buffer_distance_layers:
            layer_name = buffer_layer['name']
            if layer_name not in self.layer_properties:
                self.add_layer_properties(layer_name, {
                    'color': "Light Green",
                    'close': True,
                    'locked': False
                })

        # Handle WMTS layers
        for wmts in self.wmts:
            layer_name = f"WMTS {wmts['name']}"
            self.layer_properties[layer_name] = {
                'color': 7,  # Default to white
                'locked': wmts.get('locked', False),
                'close': True
            }

        # Handle exclusion layers
        for exclusion in self.exclusions:
            layer_info = self.find_layer_by_name(exclusion['name'])
            if layer_info:
                self.layer_properties[exclusion['name']] = {
                    'color': self.get_color_code(layer_info['color']),
                    'locked': layer_info.get('locked', False),
                    'close': layer_info.get('close', True)
                }
            else:
                print_warning(f"Layer '{exclusion['name']}' not found in project settings.")

        # Handle buffer distance layers
        for buffer_layer in self.buffer_distance_layers:
            # Use the shapefile name (without extension) as the layer name if not provided
            layer_name = buffer_layer.get('name', os.path.splitext(os.path.basename(buffer_layer['shapeFile']))[0])
            buffer_layer['name'] = layer_name  # Add the name to the buffer_layer dict
            self.add_layer_properties(layer_name, buffer_layer)

        # Create clip distance layers
        self.create_clip_distance_layers()

        # Create buffer distance layers
        self.create_buffer_distance_layers()

        # Create Geltungsbereich layers
        self.create_geltungsbereich_layers()

    def find_layer_by_name(self, layer_name):
        """Find a layer in the project settings by its name."""
        for layer in self.project_settings['layers']:
            if layer['name'] == layer_name:
                return layer
        return None

    def load_project_settings(self, project_name: str):
        with open('projects.yaml', 'r') as file:
            data = yaml.safe_load(file)
            projects = data['projects']
            folder_prefix = data.get('folderPrefix', '')
            return next((project for project in projects if project['name'] == project_name), None), folder_prefix

    def resolve_full_path(self, path: str) -> str:
        return os.path.abspath(os.path.expanduser(os.path.join(self.folder_prefix, path)))

    def get_layer_info(self, layer_name: str):
        shapefile = next(
            (layer['shapeFile'] for layer in self.project_settings['layers'] if layer['name'] == layer_name), None)
        label = next((layer['label'] for layer in self.project_settings['layers']
                     if layer['name'] == layer_name), None)
        return self.resolve_full_path(shapefile), label

    def load_shapefile(self, file_path: str) -> gpd.GeoDataFrame:
        gdf = gpd.read_file(file_path)
        gdf = gdf.set_crs(self.crs, allow_override=True)
        return gdf

    def parcel_missing(self, gdf: gpd.GeoDataFrame, coverage: dict) -> set:
        return set(coverage["parcelList"]).difference(gdf[self.parcel_label])

    def filter_parcels(self, coverage):
        parcels_missing = self.parcel_missing(self.parcel_shapefile, coverage)
        if not parcels_missing:
            print("All parcels found.")

        buffered_flur = self.flur_shapefile[self.flur_shapefile[self.flur_label].isin(
            coverage["flurList"])].unary_union.buffer(-10)
        buffered_gemeinde = self.gemeinde_shapefile[self.gemeinde_shapefile[self.gemeinde_label].isin(
            coverage["gemeindeList"])].unary_union.buffer(-10)
        buffered_gemarkung = self.gemarkung_shapefile[self.gemarkung_shapefile[self.gemarkung_label].isin(
            coverage["gemarkungList"])].unary_union.buffer(-10)

        selected_parcels = self.parcel_shapefile[self.parcel_shapefile[self.parcel_label].isin(
            coverage["parcelList"])]
        selected_parcels_mask = self.parcel_shapefile.index.isin(selected_parcels.index)

        flur_mask = self.parcel_shapefile.intersects(buffered_flur)
        gemeinde_mask = self.parcel_shapefile.intersects(buffered_gemeinde)
        gemarkung_mask = self.parcel_shapefile.intersects(buffered_gemarkung)

        result = self.parcel_shapefile[selected_parcels_mask &
                        flur_mask & gemeinde_mask & gemarkung_mask]
        return result

    def select_parcel_edges(self, geom):

        # Initialize a list to hold the edges derived from the input geometry
        edge_lines = []

        # Loop through each polygon in the input geometry collection
        for _, row in geom.iterrows():
            poly = row.geometry
            # Debugging: Print the type of each geometry
            if not isinstance(poly, (Polygon, MultiPolygon)):
                print(f"Skipping non-polygon geometry: {type(poly)}")
                continue

            # Extract the boundary of the polygon, converting it to a linestring
            boundary_line = poly.boundary

            # Create an outward buffer of 10 units from the boundary line
            buffered_line_out = boundary_line.buffer(10, join_style=2)  # Outward buffer with a mitered join
            # Create an inward buffer of 10 units from the boundary line
            buffered_line_in = boundary_line.buffer(-10, join_style=2)  # Inward buffer with a mitered join

            # Handle MultiPolygon and Polygon cases for outward buffer
            if buffered_line_out.geom_type == 'MultiPolygon':
                for part in buffered_line_out.geoms:  # Iterate over geoms attribute
                    edge_lines.append(part.exterior)
            elif buffered_line_out.geom_type == 'Polygon':
                edge_lines.append(buffered_line_out.exterior)

            # Handle MultiPolygon and Polygon cases for inward buffer
            if buffered_line_in.geom_type == 'MultiPolygon':
                for part in buffered_line_in.geoms:  # Iterate over geoms attribute
                    edge_lines.append(part.exterior)
            elif buffered_line_in.geom_type == 'Polygon':
                edge_lines.append(buffered_line_in.exterior)

        # Merge and simplify the collected edge lines into a single geometry
        merged_edges = linemerge(unary_union(edge_lines))

        # Convert the merged edges to a list of LineString objects
        if isinstance(merged_edges, MultiLineString):
            result_geometries = list(merged_edges.geoms)
        else:
            result_geometries = [merged_edges]

        # Create a GeoDataFrame to hold the merged edges, preserving the original CRS
        result_gdf = gpd.GeoDataFrame(geometry=result_geometries, crs=geom.crs)
        # Return the GeoDataFrame containing the processed geometry
        return result_gdf

    def load_template(self):
        if self.template_dxf:
            return ezdxf.readfile(self.template_dxf)
        return None

    def conditional_buffer(self, source_geom, target_geom, distance):
        if any(source_geom.intersects(geom) for geom in target_geom['geometry']):
            return source_geom.buffer(-distance)
        else:
            return source_geom.buffer(distance)

    def apply_conditional_buffering(self, source_geom, target_geom, distance):
        source_geom['geometry'] = source_geom['geometry'].apply(
            lambda x: self.conditional_buffer(x, target_geom, distance))
        return source_geom

    def labeled_center_points(self, source_geom, label):
        points_within = source_geom.representative_point()
        return gpd.GeoDataFrame(geometry=points_within, data={"label": source_geom[label]})

    def add_text_style(self, doc, text_style_name):
        if text_style_name not in doc.styles:
            doc.styles.new(name=text_style_name, dxfattribs={
                           'font': 'Arial.ttf', 'height': 0.1})

    def add_text(self, msp, text, x, y, layer_name, style_name, color):
        msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1,
            'color': color  # Set the color for the text
        })

    def add_text_to_center(self, msp, points, layer_name):
        text_layer_name = f"{layer_name} Number"
        self.add_layer(msp.doc, text_layer_name)
        self.add_text_style(msp.doc, 'Standard')
        
        # Get the color from the layer properties
        color = self.layer_properties[text_layer_name]['color']
        
        for idx, row in points.iterrows():
            if row.geometry.geom_type == 'Point':
                x, y = row.geometry.x, row.geometry.y
            elif row.geometry.geom_type in ['Polygon', 'MultiPolygon']:
                centroid = row.geometry.centroid
                x, y = centroid.x, centroid.y
            else:
                print_warning(f"Unsupported geometry type {row.geometry.geom_type} for label in layer {text_layer_name}")
                continue
            
            self.add_text(msp, str(row['label']), x, y, text_layer_name, 'Standard', color)

    def add_geometries(self, msp, geometries, layer_name, close=True):
        self.add_layer(msp.doc, layer_name)
        
        if isinstance(geometries, gpd.GeoSeries):
            geometries = geometries.tolist()
        
        for geom in geometries:
            if geom.geom_type == 'Polygon':
                points = list(geom.exterior.coords)
                if close:
                    points.append(points[0])  # Close the polygon
                msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
                for interior in geom.interiors:
                    points = list(interior.coords)
                    if close:
                        points.append(points[0])  # Close the interior ring
                    msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
            elif geom.geom_type == 'MultiPolygon':
                for poly in geom.geoms:
                    points = list(poly.exterior.coords)
                    if close:
                        points.append(points[0])  # Close the polygon
                    msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
                    for interior in poly.interiors:
                        points = list(interior.coords)
                        if close:
                            points.append(points[0])  # Close the interior ring
                        msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
            elif geom.geom_type == 'LineString':
                points = list(geom.coords)
                if close and points[0] != points[-1]:
                    points.append(points[0])  # Close the linestring if it's not already closed
                msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})
            elif geom.geom_type == 'MultiLineString':
                for line in geom.geoms:
                    points = list(line.coords)
                    if close and points[0] != points[-1]:
                        points.append(points[0])  # Close the linestring if it's not already closed
                    msp.add_lwpolyline(points, dxfattribs={'layer': layer_name})

    def add_layer(self, doc, layer_name):
        base_layer = layer_name.split('_')[0]  # Get the base layer name (e.g., 'WMTS DOP' from 'WMTS DOP_Hauptgeltungsbereich')
        properties = self.layer_properties.get(base_layer, {'color': 7, 'locked': False})
        if layer_name not in doc.layers:
            new_layer = doc.layers.new(name=layer_name)
        else:
            new_layer = doc.layers.get(layer_name)
        
        new_layer.color = properties['color']
        new_layer.lock = properties['locked']

    def get_color_code(self, color):
        if isinstance(color, int):
            if 1 <= color <= 255:
                return color
            else:
                random_color = random.randint(1, 255)
                print(f"Warning: Invalid color code {color}. Assigning random color: {random_color}")
                return random_color
        elif isinstance(color, str):
            color_lower = color.lower()
            if color_lower in self.name_to_aci:
                return self.name_to_aci[color_lower]
            else:
                random_color = random.randint(1, 255)
                print(f"Warning: Color name '{color}' not found. Assigning random color: {random_color}")
                return random_color
        else:
            random_color = random.randint(1, 255)
            print(f"Warning: Invalid color type. Assigning random color: {random_color}")
            return random_color

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
        self.add_layer(msp.doc, layer_name)
        # Create a relative path for the image
        relative_image_path = os.path.relpath(
            image_path, os.path.dirname(self.dxf_filename))

        # Create the image definition with the relative path
        image_def = msp.doc.add_image_def(
            filename=relative_image_path, size_in_pixel=(256, 256))

        # Read the world file to get the transformation parameters
        with open(world_file_path, 'r') as wf:
            a = float(wf.readline().strip())
            d = float(wf.readline().strip())
            b = float(wf.readline().strip())
            e = float(wf.readline().strip())
            c = float(wf.readline().strip())
            f = float(wf.readline().strip())

        # Calculate the insertion point and size
        insert_point = (c, f - abs(e) * 256)
        size_in_units = (a * 256, abs(e) * 256)

        # Add the image with relative path
        image = msp.add_image(
            insert=insert_point,
            size_in_units=size_in_units,
            image_def=image_def,
            rotation=0,
            dxfattribs={'layer': layer_name}
        )

        # Set the image path as a relative path
        image.dxf.image_def_handle = image_def.dxf.handle
        image.dxf.flags = 3  # Set bit 0 and 1 to indicate relative path

        # Set the $PROJECTNAME header variable to an empty string
        msp.doc.header['$PROJECTNAME'] = ''

    def clip_with_distance_layer_buffers(self, geom_to_clip):
        for layer in self.clip_distance_layers:
            shapefile = self.resolve_full_path(layer['shapeFile'])
            buffer_distance = layer['bufferDistance']

            # Load the shapefile
            gdf = self.load_shapefile(shapefile)

            # Create buffer
            buffered = gdf.buffer(buffer_distance)

            # Reduce geltungsbereich
            geom_to_clip = geom_to_clip.difference(buffered.unary_union)

        return geom_to_clip
    
    def get_distance_layer_buffers(self, geom_to_buffer, distance, clipping_geom=None):
        # Ensure geom_to_buffer is a GeoDataFrame
        if isinstance(geom_to_buffer, gpd.GeoSeries):
            geom_to_buffer = gpd.GeoDataFrame(geometry=geom_to_buffer)

        # Create buffer
        combined_buffer = geom_to_buffer.buffer(distance)

        # If a clipping geometry is provided, intersect the combined buffer with it
        if clipping_geom is not None:
            combined_buffer = combined_buffer.intersection(clipping_geom)

        return combined_buffer
    
    def create_exclusion_polygon(self, exclusion):
        scope_layer = exclusion['scopeLayer']
        exclude_layers = exclusion['excludeLayers']
        new_layer_name = exclusion['name']

        # Get the scope geometry
        scope_geom = self.geltungsbereich_geometries.get(scope_layer)
        if scope_geom is None:
            print_warning(f"Scope layer '{scope_layer}' not found.")
            return None

        # Initialize the exclusion geometry with the scope geometry
        exclusion_geom = scope_geom

        for layer in exclude_layers:
            layer_info = self.find_layer_by_name(layer)
            if layer_info and 'shapeFile' in layer_info:
                shapefile_path = self.resolve_full_path(layer_info['shapeFile'])
                if os.path.exists(shapefile_path):
                    layer_gdf = self.load_shapefile(shapefile_path)
                    layer_geom = layer_gdf['geometry'].unary_union
                    exclusion_geom = exclusion_geom.difference(layer_geom)
                else:
                    print_warning(f"Shapefile for exclusion layer '{layer}' not found: {shapefile_path}")
            else:
                # Check if it's a buffer distance layer
                buffer_layer = next((bl for bl in self.buffer_distance_layers if bl['name'] == layer), None)
                if buffer_layer:
                    buffer_shapefile = self.resolve_full_path(buffer_layer['shapeFile']).replace('.shp', f'_buffer_{buffer_layer["bufferDistance"]}.shp')
                    if os.path.exists(buffer_shapefile):
                        buffer_gdf = self.load_shapefile(buffer_shapefile)
                        buffer_geom = buffer_gdf['geometry'].unary_union
                        exclusion_geom = exclusion_geom.difference(buffer_geom)
                    else:
                        print_warning(f"Buffer shapefile for layer '{layer}' not found: {buffer_shapefile}")
                else:
                    print_warning(f"Exclusion layer '{layer}' not found in project settings or buffer distance layers.")

        # Store the resulting geometry
        self.exclusion_geometries[new_layer_name] = exclusion_geom

        print(f"Created exclusion polygon: {new_layer_name}")
        return exclusion_geom

    def process_single_layer(self, msp, layer):
        # Check if the layer is a clip distance layer
        if layer in [clip_layer['name'] for clip_layer in self.clip_distance_layers]:
            if not self.has_corresponding_layer(layer):
                print(f"Skipping clip distance layer: {layer} as it has no corresponding entry in 'layers'")
                return
            print(f"Processing clip distance layer: {layer}")
            geometry = self.clip_geometries[layer]
            self.add_geometries(msp, [geometry], layer, close=True)
            return

        # Remove existing entities in the layer
        for entity in msp.query(f'*[layer=="{layer}"]'):
            msp.delete_entity(entity)

        # Check if the layer is a Geltungsbereich layer
        if layer in self.geltungsbereich_geometries:
            print(f"Processing Geltungsbereich layer: {layer}")
            geometry = self.geltungsbereich_geometries[layer]
            self.add_geometries(msp, [geometry], layer, close=True)
        elif layer in self.exclusion_geometries:
            print(f"Processing exclusion layer: {layer}")
            geometry = self.exclusion_geometries[layer]
            self.add_geometries(msp, [geometry], layer, close=True)
        elif layer in [wmts['dxfLayer'] for wmts in self.wmts]:
            print(f"Processing WMTS layer: {layer}")
            wmts_info = next(wmts for wmts in self.wmts if wmts['dxfLayer'] == layer)
            target_folder = self.resolve_full_path(wmts_info['targetFolder'])
            os.makedirs(target_folder, exist_ok=True)
            print(f"Updating WMTS tiles for layer '{layer}'")
            
            # Combine all Geltungsbereich geometries
            combined_geometry = unary_union([geom for geom in self.geltungsbereich_geometries.values()])
            
            # Download tiles for the combined geometry
            tiles = download_wmts_tiles(wmts_info, combined_geometry, 500, target_folder, True)
            
            # Add all downloaded tiles to the DXF
            for tile_path, world_file_path in tiles:
                self.add_image_with_worldfile(msp, tile_path, world_file_path, layer)
        else:
            layer_info = self.find_layer_by_name(layer)
            if layer_info:
                if 'shapeFile' in layer_info:
                    shapefile_path = self.resolve_full_path(layer_info['shapeFile'])
                    if os.path.exists(shapefile_path):
                        gdf = gpd.read_file(shapefile_path)
                        self.add_geometries(msp, gdf['geometry'], layer, close=layer_info.get('close', True))
                        
                        # Add labels if 'label' is specified in layer_info
                        if 'label' in layer_info:
                            label_column = layer_info['label']
                            if label_column in gdf.columns:
                                gdf['label'] = gdf[label_column].astype(str)  # Ensure label is a string
                                self.add_text_to_center(msp, gdf, layer)  # Use the same layer for labels
                            else:
                                print_warning(f"Label column '{label_column}' not found in shapefile for layer '{layer}'")
                    else:
                        print_error(f"Shapefile for layer '{layer}' not found: {shapefile_path}")
                else:
                    # Layer without shapefile, possibly a dynamically created layer (like buffer layers)
                    print(f"Layer '{layer}' has no associated shapefile. It may be created dynamically.")
            else:
                print_warning(f"Layer '{layer}' not found in project settings")

        # Set layer properties
        self.add_layer(self.doc, layer)

        print(f"Finished processing layer: {layer}")

    def main(self):
        print(f"Starting processing for project: {self.project_settings['name']}")
        self.create_geltungsbereich_layers()
        self.create_clip_distance_layers()
        self.create_buffer_distance_layers()
        
        # Process exclusions
        self.exclusion_geometries = {}
        for exclusion in self.exclusions:
            if self.has_corresponding_layer(exclusion['name']):
                self.create_exclusion_polygon(exclusion)
        
        doc = self.process_layers(self.update_layers_list)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.dxf_filename), exist_ok=True)

        if self.export_format == 'dwg':
            print(f"Exporting to DWG: {self.dxf_filename.replace('.dxf', '.dwg')}")
            doc.header['$PROJECTNAME'] = ''
            odafc.export_dwg(doc, self.dxf_filename.replace('.dxf', '.dwg'))
        else:
            print(f"Saving DXF file: {self.dxf_filename}")
            doc.saveas(self.dxf_filename)

        # processed_layers = self.update_layers_list if self.update_layers_list else ['Flur', 'Parcel', 'Gemeinde', 'Gemarkung', 'Wald', 'Biotope'] + list(self.wmts_layers.values())
        print("Processing complete.")

    def add_layer_properties(self, layer_name, layer_info):
        color = self.get_color_code(layer_info.get('color', 'White'))
        self.layer_properties[layer_name] = {
            'color': color,
            'locked': layer_info.get('locked', False),
            'close': layer_info.get('close', True)
        }
        
        # Add properties for the text/number layer
        text_layer_name = f"{layer_name} Number"
        self.layer_properties[text_layer_name] = {
            'color': color,  # Use the same color as the main layer
            'locked': layer_info.get('locked', False),
            'close': True
        }

    def has_corresponding_layer(self, layer_name):
        """Check if the given layer name has a corresponding entry in the 'layers' section."""
        return any(layer['name'] == layer_name for layer in self.project_settings['layers'])

    def create_clip_distance_layers(self):
        print("Starting to create clip distance layers...")
        self.clip_geometries = {}
        for layer in self.clip_distance_layers:
            input_shapefile = self.resolve_full_path(layer['shapeFile'])
            buffer_distance = layer['bufferDistance']
            layer_name = layer['name']

            # Only process if there's a corresponding layer in the 'layers' section
            if self.has_corresponding_layer(layer_name):
                print(f"Processing clip distance layer: {layer_name}")
                print(f"Input shapefile: {input_shapefile}")
                print(f"Buffer distance: {buffer_distance}")

                # Load the input shapefile
                gdf = gpd.read_file(input_shapefile)

                # Create buffer
                buffered = gdf.buffer(buffer_distance)

                # Store the buffered geometry
                self.clip_geometries[layer_name] = buffered.unary_union

                print(f"Created clip distance geometry for layer: {layer_name}")
            else:
                print(f"Skipping clip distance layer '{layer_name}' as it has no corresponding entry in 'layers'")

        print("Finished creating clip distance layers.")

    def create_buffer_distance_layers(self):
        print("Creating buffer distance layers...")
        self.buffer_geometries = {}
        for buffer_layer in self.buffer_distance_layers:
            input_shapefile = self.resolve_full_path(buffer_layer['shapeFile'])
            buffer_distance = buffer_layer['bufferDistance']
            layer_name = buffer_layer['name']

            # Only process if there's a corresponding layer in the 'layers' section
            if self.has_corresponding_layer(layer_name):
                try:
                    # Load the input shapefile
                    gdf = gpd.read_file(input_shapefile)
                    
                    # Create buffer
                    buffered = gdf.buffer(buffer_distance)
                    
                    # Get the combined Geltungsbereich geometry
                    geltungsbereich_geometry = self.get_combined_geltungsbereich()
                    
                    # Intersect the buffer with the Geltungsbereich
                    clipped_buffer = buffered.intersection(geltungsbereich_geometry)
                    
                    # Store the buffered geometry
                    self.buffer_geometries[layer_name] = clipped_buffer
                
                    print(f"Created buffer for layer: {layer_name}")
                except Exception as e:
                    print(f"Error creating buffer for layer {layer_name}: {str(e)}")
            else:
                print(f"Skipping buffer distance layer '{layer_name}' as it has no corresponding entry in 'layers'")

    def get_combined_geltungsbereich(self):
        if not hasattr(self, 'geltungsbereich_geometries'):
            self.create_geltungsbereich_layers()
        return unary_union(list(self.geltungsbereich_geometries.values()))

    def create_geltungsbereich_layers(self):
        print("Starting to create Geltungsbereich layers...")
        self.geltungsbereich_geometries = {}
        for layer in self.geltungsbereich_layers:
            layer_name = layer['name']
            coverage = layer['coverage']
            
            # Filter parcels based on coverage
            gdf = self.filter_parcels(coverage)
            
            # Dissolve the geometry
            dissolved_geometry = gdf.unary_union
            
            # Clip with all layers in clipDistanceLayers
            for clip_layer in self.clip_distance_layers:
                clip_shapefile = self.resolve_full_path(clip_layer['shapeFile'])
                clip_gdf = gpd.read_file(clip_shapefile)
                
                if clip_layer['bufferDistance'] > 0:
                    clip_geometry = clip_gdf.geometry.buffer(clip_layer['bufferDistance']).unary_union
                else:
                    clip_geometry = clip_gdf.geometry.unary_union
                
                dissolved_geometry = dissolved_geometry.difference(clip_geometry)
            
            self.geltungsbereich_geometries[layer_name] = dissolved_geometry
            
            print(f"Created Geltungsbereich layer: {layer_name}")
            
            # Add the new layer to layer_properties
            self.layer_properties[layer_name] = {
                'color': self.get_color_code(layer.get('color', "Red")),
                'locked': layer.get('locked', False),
                'close': layer.get('close', True)
            }
            
            print(f"Added new Geltungsbereich layer to project settings: {layer_name}")
    
        print("Finished creating Geltungsbereich layers.")

    def update_layer_info(self, layer_name, shapefile_path, layer_info):
        # Update project settings
        new_layer = {
            'name': layer_name,
            'shapeFile': shapefile_path,
            'color': layer_info.get('color', "Light Green"),
            'close': layer_info.get('close', True),
            'locked': layer_info.get('locked', False)
        }
        self.project_settings['layers'].append(new_layer)

        # Update layer properties
        self.add_layer_properties(layer_name, new_layer)

        print(f"Updated project settings and layer properties for: {layer_name}")

    def process_layers(self, layers_to_process=None):
        try:
            doc = ezdxf.readfile(self.dxf_filename)
            print(f"Opened existing DXF file: {self.dxf_filename}")
        except FileNotFoundError:
            print(f"DXF file not found. Creating a new file: {self.dxf_filename}")
            doc = ezdxf.new('R2018')  # Create a new DXF document
            doc.header['$INSUNITS'] = 6  # Set units to meters

        self.doc = doc  # Store the doc object in the class instance
        msp = doc.modelspace()

        # Dynamically generate the list of layers from projects.yaml
        wmts_layers = [wmts['dxfLayer'] for wmts in self.wmts]
        other_layers = [layer['name'] for layer in self.project_settings['layers']]
        
        # Only include exclusion layers that have corresponding entries in 'layers'
        exclusion_layers = [exc['name'] for exc in self.exclusions if self.has_corresponding_layer(exc['name'])]
    
        buffer_distance_layers = [layer['name'] for layer in self.buffer_distance_layers if self.has_corresponding_layer(layer['name'])]
        clip_distance_layers = [layer['name'] for layer in self.clip_distance_layers if self.has_corresponding_layer(layer['name'])]
        
        geltungsbereich_layers = [layer['name'] for layer in self.geltungsbereich_layers]
        
        all_layers = wmts_layers + other_layers + exclusion_layers + buffer_distance_layers + clip_distance_layers + geltungsbereich_layers

        layers_to_process = layers_to_process or all_layers

        print("Layers to process:", layers_to_process)

        # Process layers in the order they appear in all_layers
        for layer in all_layers:
            if layer in layers_to_process:
                print(f"Processing layer: {layer}")
                self.process_single_layer(msp, layer)

        # Add buffer geometries to their respective layers
        for layer_name, geometry in self.buffer_geometries.items():
            if self.has_corresponding_layer(layer_name):
                print(f"Adding buffer geometry to layer: {layer_name}")
                self.add_geometries(msp, geometry, layer_name, close=self.layer_properties[layer_name]['close'])

        return doc

    def add_layer(self, doc, layer_name):
        base_layer = layer_name.split('_')[0]  # Get the base layer name (e.g., 'WMTS DOP' from 'WMTS DOP_Hauptgeltungsbereich')
        properties = self.layer_properties.get(base_layer, {'color': 7, 'locked': False})
        if layer_name not in doc.layers:
            new_layer = doc.layers.new(name=layer_name)
        else:
            new_layer = doc.layers.get(layer_name)
        
        new_layer.color = properties['color']
        new_layer.lock = properties['locked']

    def main(self):
        print(f"Starting processing for project: {self.project_settings['name']}")
        self.create_geltungsbereich_layers()
        self.create_clip_distance_layers()
        self.create_buffer_distance_layers()
        
        # Process exclusions
        self.exclusion_geometries = {}
        for exclusion in self.exclusions:
            if self.has_corresponding_layer(exclusion['name']):
                self.create_exclusion_polygon(exclusion)
        
        doc = self.process_layers(self.update_layers_list)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.dxf_filename), exist_ok=True)

        if self.export_format == 'dwg':
            print(f"Exporting to DWG: {self.dxf_filename.replace('.dxf', '.dwg')}")
            doc.header['$PROJECTNAME'] = ''
            odafc.export_dwg(doc, self.dxf_filename.replace('.dxf', '.dwg'))
        else:
            print(f"Saving DXF file: {self.dxf_filename}")
            doc.saveas(self.dxf_filename)

        # processed_layers = self.update_layers_list if self.update_layers_list else ['Flur', 'Parcel', 'Gemeinde', 'Gemarkung', 'Wald', 'Biotope'] + list(self.wmts_layers.values())
        print("Processing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process project data.")
    parser.add_argument("project_name", help="Name of the project to process")
    parser.add_argument("-u", "--update", help="Update specific layers (comma-separated list)")
    args = parser.parse_args()

    try:
        processor = ProjectProcessor(args.project_name)
        processor.update_layers_list = args.update.split(',') if args.update else None
        processor.main()
    except ValueError as e:
        print(e)




