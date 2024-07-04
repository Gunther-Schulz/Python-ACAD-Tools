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


class ProjectProcessor:
    def __init__(self, project_name: str, update_wmts_only: bool = False):
        self.project_settings, self.folder_prefix = self.load_project_settings(
            project_name)
        if not self.project_settings:
            raise ValueError(f"Project {project_name} not found.")

        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(
            self.project_settings['dxfFilename'])
        self.wmts = self.project_settings.get('wmts', [])
        self.clip_distance_layers = self.project_settings.get('clipDistanceLayers', [])
        # self.buffer_distance_layers = self.project_settings.get('bufferDistanceLayers', [])

        if update_wmts_only:
            print("Updating WMTS tiles only...")
            self.update_wmts()
            return

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
        self.color_map = {
            'red': 1, 'yellow': 2, 'green': 3, 'cyan': 4, 'blue': 5, 'magenta': 6,
            'white': 7, 'gray': 8, 'light_gray': 9, 'dark_red': 10, 'dark_yellow': 11,
            'dark_green': 12, 'dark_cyan': 13, 'dark_blue': 14, 'dark_magenta': 15,
            'orange': 16, 'pink': 17, 'brown': 18, 'purple': 19, 'lime': 20,
            'olive': 21, 'navy': 22, 'teal': 23, 'maroon': 24, 'silver': 25,
            'gold': 26, 'beige': 27, 'coral': 28, 'ivory': 29, 'khaki': 30,
            'lavender': 31, 'peach': 32, 'mint': 33, 'apricot': 34, 'rose': 35,
            'plum': 36, 'mustard': 37, 'turquoise': 38, 'violet': 39, 'charcoal': 40,
            'aqua': 41, 'burgundy': 42, 'emerald': 43, 'fuchsia': 44, 'indigo': 45,
            'jade': 46, 'lavender_blush': 47, 'lemon': 48, 'mauve': 49, 'pearl': 50,
            'ruby': 51, 'sapphire': 52, 'amber': 53, 'amethyst': 54, 'topaz': 55,
            'opal': 56, 'garnet': 57, 'peridot': 58, 'aquamarine': 59, 'tanzanite': 60,
            'moonstone': 61, 'onyx': 62, 'quartz': 63, 'citrine': 64, 'jasper': 65,
            'lapis': 66, 'malachite': 67, 'obsidian': 68, 'agate': 69, 'turquoise_blue': 70,
            'copper': 71, 'bronze': 72, 'brass': 73, 'nickel': 74, 'platinum': 75,
            'zinc': 76, 'aluminum': 77, 'steel': 78, 'chrome': 79, 'titanium': 80,
            'pewter': 81, 'lead': 82, 'tin': 83, 'mercury': 84, 'bismuth': 85,
            'antimony': 86, 'arsenic': 87, 'cadmium': 88, 'cobalt': 89, 'gallium': 90,
            'germanium': 91, 'hafnium': 92, 'iridium': 93, 'osmium': 94, 'palladium': 95,
            'rhodium': 96, 'ruthenium': 97, 'scandium': 98, 'strontium': 99, 'tellurium': 100,
        }

        self.colors = {layer['name']: self.get_color_code(layer['color'])
                       for layer in self.project_settings['layers']}

        self.coverage = self.project_settings['coverage']

        # Modify this part to create a dictionary of WMTS layers
        self.wmts_layers = {
            wmts['name']: f"WMTS {wmts['name']}" for wmts in self.wmts}

        self.export_format = self.project_settings.get('exportFormat', 'dxf')

        if sys.platform == "darwin" and os.path.exists("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"):
            odafc.unix_exec_path = "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"

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
        return shapefile, label

    def load_shapefile(self, file_path: str) -> gpd.GeoDataFrame:
        gdf = gpd.read_file(file_path)
        gdf = gdf.set_crs(self.crs, allow_override=True)
        return gdf

    def geoms_missing(self, gdf: gpd.GeoDataFrame, coverage: dict) -> set:
        return set(coverage["parcelList"]).difference(gdf[self.parcel_label])

    def filter_parcels(self, parcel, flur, gemarkung, gemeinde, coverage):
        parcels_missing = self.geoms_missing(parcel, coverage)
        if not parcels_missing:
            print("All parcels found.")

        buffered_flur = flur[flur[self.flur_label].isin(
            coverage["flurList"])].unary_union.buffer(-10)
        buffered_gemeinde = gemeinde[gemeinde[self.gemeinde_label].isin(
            coverage["gemeindeList"])].unary_union.buffer(-10)
        buffered_gemarkung = gemarkung[gemarkung[self.gemarkung_label].isin(
            coverage["gemarkungList"])].unary_union.buffer(-10)

        selected_parcels = parcel[parcel[self.parcel_label].isin(
            coverage["parcelList"])]
        selected_parcels_mask = parcel.index.isin(selected_parcels.index)

        flur_mask = parcel.intersects(buffered_flur)
        gemeinde_mask = parcel.intersects(buffered_gemeinde)
        gemarkung_mask = parcel.intersects(buffered_gemarkung)

        result = parcel[selected_parcels_mask &
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

    def add_text(self, msp, text, x, y, layer_name, style_name):
        msp.add_text(text, dxfattribs={
            'style': style_name,
            'layer': layer_name,
            'insert': (x, y),
            'align_point': (x, y),
            'halign': 1,
            'valign': 1
        })

    def add_text_to_center(self, msp, labeled_centroid_points_df, layer_name, style_name=None):
        if style_name is None or not msp.styles.has_entry(style_name):
            style_name = "default"
        for index, row in labeled_centroid_points_df.iterrows():
            x, y = row['geometry'].coords[0]
            self.add_text(msp, row['label'], x, y, layer_name, style_name)

    def add_geometries(self, msp, geometries, layer_name, close=False):
        if isinstance(geometries, gpd.GeoSeries) or isinstance(geometries, gpd.GeoDataFrame):
            geometries = geometries.geometry
        
        for geom in geometries:
            if geom is None:
                print(
                    f"Warning: None geometry encountered in layer '{layer_name}'")
            elif isinstance(geom, (Polygon, LineString, MultiPolygon, MultiLineString)):
                if geom.geom_type == 'Polygon':
                    points = [(x, y) for x, y in geom.exterior.coords]
                    msp.add_lwpolyline(points, close=close, dxfattribs={
                                       'layer': layer_name})
                elif geom.geom_type == 'MultiPolygon':
                    for polygon in geom.geoms:
                        points = [(x, y) for x, y in polygon.exterior.coords]
                        msp.add_lwpolyline(points, close=close, dxfattribs={
                                           'layer': layer_name})
                elif geom.geom_type == 'LineString':
                    points = [(x, y) for x, y in geom.coords]
                    msp.add_lwpolyline(points, close=close, dxfattribs={
                                       'layer': layer_name})
                elif geom.geom_type == 'MultiLineString':
                    for line in geom.geoms:
                        points = [(x, y) for x, y in line.coords]
                        msp.add_lwpolyline(points, close=close, dxfattribs={
                                           'layer': layer_name})
                else:
                    print(f"Unsupported geometry type: {geom.geom_type}")
            else:
                print(
                    f"Unsupported object type: {type(geom)} in layer '{layer_name}'")

    def add_layer(self, doc, layer_name, color):
        if layer_name not in doc.layers:
            color_code = self.get_color_code(color)
            doc.layers.new(name=layer_name, dxfattribs={'color': color_code})

    def get_color_code(self, color):
        if isinstance(color, int):
            if color == 0:
                # Choose a random color between 1 and 255
                return random.randint(1, 255)
            return color
        elif isinstance(color, str):
            # Default to white (7) if color name not found
            return self.color_map.get(color.lower(), 7)
        else:
            return 7  # Default to white (7) for any other type

    def add_image_with_worldfile(self, msp, image_path, world_file_path, layer_name):
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
    
    def main(self):
        # Load shapefiles
        shapefiles = {
            "parcels": self.load_shapefile(self.resolve_full_path(self.parcel_shapefile)),
            "flur": self.load_shapefile(self.resolve_full_path(self.flur_shapefile)),
            "orig_flur": self.load_shapefile(self.resolve_full_path(self.flur_shapefile)),
            "gemarkung": self.load_shapefile(self.resolve_full_path(self.gemarkung_shapefile)),
            "gemeinde": self.load_shapefile(self.resolve_full_path(self.gemeinde_shapefile)),
            "wald": self.load_shapefile(self.resolve_full_path(self.wald_shapefile)),
            "biotope": self.load_shapefile(self.resolve_full_path(self.biotope_shapefile))
        }

        # Filter parcels and calculate geltungsbereich
        target_parcels = self.filter_parcels(
            shapefiles["parcels"], shapefiles["flur"], shapefiles["gemarkung"], shapefiles["gemeinde"], self.coverage)
        geltungsbereich = target_parcels['geometry'].unary_union

        # Apply buffer zones from distance layers to reduce geltungsbereich
        geltungsbereich = self.clip_with_distance_layer_buffers(geltungsbereich)

        # Clip geltungsbereich with wald
        geltungsbereich = geltungsbereich.difference(shapefiles["wald"].unary_union)

        wald_abstand = self.get_distance_layer_buffers(shapefiles["wald"], 30, geltungsbereich)

        # # Only keep the wald_abstand within the geltungsbereich
        # wald_abstand = wald_abstand.intersection(geltungsbereich)

        # Download WMTS tiles and get their paths
        downloaded_tiles = []
        for wmts_info in self.wmts:
            target_folder = self.resolve_full_path(wmts_info['targetFolder'])
            os.makedirs(target_folder, exist_ok=True)
            tiles = download_wmts_tiles(
                wmts_info, geltungsbereich, 500, target_folder)
            downloaded_tiles.extend(tiles)

        # Generate labeled center points
        labeled_points = {
            "parcel_points": self.labeled_center_points(shapefiles["parcels"], self.parcel_label),
            "flur_points": self.labeled_center_points(shapefiles["flur"], self.flur_label),
            "gemeinde_points": self.labeled_center_points(shapefiles["gemeinde"], self.gemeinde_label),
            "gemarkung_points": self.labeled_center_points(shapefiles["gemarkung"], self.gemarkung_label),
            "wald_points": self.labeled_center_points(shapefiles["wald"], self.wald_label),
            "biotope_points": self.labeled_center_points(shapefiles["biotope"], self.biotope_label)
        }

        # Load or create DXF document
        doc = self.load_template(
        ) if self.project_settings['useTemplate'] and self.template_dxf else ezdxf.new('R2010', setup=True)

        # Add text styles and layers
        self.add_text_style(doc, 'default')
        layers = [
            ('Flur', self.colors['Flur']),
            ('FlurOrig', 'green'),
            ('Gemeinde', self.colors['Gemeinde']),
            ('Gemarkung', self.colors['Gemarkung']),
            ('Parcel', self.colors['Parcel']),
            ('Parcel Number', self.colors['Parcel']),
            ('Flur Number', self.colors['Flur']),
            ('Wald', self.colors['Wald']),
            ('Wald Abstand', 'dark_red'),
            ('Biotope', self.colors['Biotope']),
            ('Gemeinde Name', self.colors['Gemeinde']),
            ('Gemarkung Name', self.colors['Gemarkung']),
            ('Geltungsbereich', 'dark_red'),
        ]
        # Add WMTS layers
        layers.extend((layer_name, 'gray')
                      for layer_name in self.wmts_layers.values())

        for layer_name, color in layers:
            self.add_layer(doc, layer_name, color)

        text_styles = ['Parcel Number', 'Flur Number',
                       'Gemeinde Name', 'Gemarkung Name']
        for style in text_styles:
            self.add_text_style(doc, style)

        msp = doc.modelspace()

        # Add geometries to modelspace
        # self.add_geometries(msp, self.select_parcel_edges(shapefiles["flur"])['geometry'], 'Flur', close=False)
        # self.add_geometries(msp, shapefiles["parcels"]['geometry'], 'Parcel', close=True)
        self.add_geometries(msp, [geltungsbereich], 'Geltungsbereich', close=True)
        # self.add_geometries(msp, shapefiles["orig_flur"]['geometry'], 'FlurOrig', close=True)
        # self.add_geometries(msp, shapefiles["gemeinde"]['geometry'], 'Gemeinde', close=True)
        # self.add_geometries(msp, shapefiles["gemarkung"]['geometry'], 'Gemarkung', close=True)
        self.add_geometries(msp, shapefiles["wald"]['geometry'], 'Wald', close=True)
        self.add_geometries(msp, wald_abstand, 'Wald Abstand', close=True)
        # self.add_geometries(msp, shapefiles["biotope"]['geometry'], 'Biotope', close=True)

        # Add text to center points
        for label, points in labeled_points.items():
            layer_name = label.replace("_points", "").replace("_", " ").title()
            self.add_text_to_center(msp, points, layer_name)

        # Add WMTS tiles as images
        for wmts_info in self.wmts:
            target_folder = self.resolve_full_path(wmts_info['targetFolder'])
            os.makedirs(target_folder, exist_ok=True)
            tiles = download_wmts_tiles(
                wmts_info, geltungsbereich, 500, target_folder)

            layer_name = self.wmts_layers[wmts_info['name']]
            print(f"Adding {len(tiles)} WMTS tiles to layer '{layer_name}'")
            for tile_path, world_file_path in tiles:
                self.add_image_with_worldfile(
                    msp, tile_path, world_file_path, layer_name)

        if self.export_format == 'dwg':
            doc.header['$PROJECTNAME'] = ''
            odafc.export_dwg(doc, self.dxf_filename.replace('.dxf', '.dwg'))
        else:
            doc.saveas(self.dxf_filename)

    def update_wmts(self):
        print("Starting update_wmts...")  # Debugging statement
        # load existing dxf
        doc = ezdxf.readfile(self.dxf_filename)
        print(f"Loaded DXF file: {self.dxf_filename}")  # Debugging statement
        # Get all polylines from layer "Geltungsbereich"
        geltungsbereich_polylines = doc.modelspace().query(
            'LWPOLYLINE[layer=="Geltungsbereich"]')
        # Debugging statement
        print(
            f"Found {len(geltungsbereich_polylines)} polylines in 'Geltungsbereich' layer")

        # Convert polylines to shapely geometries
        geltungsbereich_geometries = []
        for polyline in geltungsbereich_polylines:
            points = polyline.get_points()
            # Extract only x and y coordinates
            xy_points = [(point[0], point[1]) for point in points]
            if len(xy_points) >= 3:  # Ensure we have at least 3 points to form a polygon
                geltungsbereich_geometries.append(Polygon(xy_points))
            else:
                print(
                    f"Warning: Skipping polyline with insufficient points: {len(xy_points)}")
        # Debugging statement
        print(
            f"Converted {len(geltungsbereich_geometries)} polylines to shapely geometries")

        # convert to shapely geometry
        geltungsbereich = unary_union(geltungsbereich_geometries)
        print("Converted geometries to unary union")  # Debugging statement

        # Download WMTS tiles
        for wmts_info in self.wmts:
            target_folder = self.resolve_full_path(wmts_info['targetFolder'])
            os.makedirs(target_folder, exist_ok=True)
            # Debugging statement
            print(f"Downloading WMTS tiles to {target_folder}")
            download_wmts_tiles(wmts_info, geltungsbereich,
                                500, target_folder, True)
            # Debugging statement
            print(
                f"Downloaded WMTS tiles for {wmts_info['url']} to layer '{self.wmts_layers[wmts_info['name']]}'")

        print("WMTS tiles updated successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python process.py <project_name> [--update-wmts-only | -u]")
        sys.exit(1)
    try:
        project_name = sys.argv[1]
        update_wmts_only = '--update-wmts-only' in sys.argv or '-u' in sys.argv
        processor = ProjectProcessor(project_name, update_wmts_only)
        if update_wmts_only:
            processor.update_wmts()
        else:
            processor.main()
    except ValueError as e:
        print(e)
