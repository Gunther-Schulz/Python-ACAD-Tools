import os
import sys
import yaml
import geopandas as gpd
import ezdxf
import matplotlib.pyplot as plt
from shapely.ops import linemerge, unary_union
from wmts_downloader import download_wmts_tiles
from shapely.geometry import Point, Polygon, LineString, MultiPolygon, MultiLineString


class ProjectProcessor:
    def __init__(self, project_name: str):
        self.project_settings, self.folder_prefix = self.load_project_settings(
            project_name)
        if not self.project_settings:
            raise ValueError(f"Project {project_name} not found.")

        self.crs = self.project_settings['crs']
        self.dxf_filename = self.resolve_full_path(
            self.project_settings['dxfFilename'])
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
        self.colors = {layer['name']: layer['color']
                       for layer in self.project_settings['layers']}
        self.coverage = self.project_settings['coverage']
        self.wmts = self.project_settings.get('wmts', [])

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

    def select_parcel_edges(self, geom: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        edge_lines = []
        for poly in geom.geometry:
            boundary_line = poly.boundary
            buffered_line_out = boundary_line.buffer(10, join_style=2)
            buffered_line_in = boundary_line.buffer(-10, join_style=2)
            edge_lines.append(boundary_line.difference(
                buffered_line_in).difference(buffered_line_out))
        return gpd.GeoDataFrame(geometry=edge_lines, crs=geom.crs)

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
        for geom in geometries:
            if geom is None:
                print(
                    f"Warning: None geometry encountered in layer '{layer_name}'")
            elif isinstance(geom, (Polygon, LineString, MultiPolygon, MultiLineString)):
                if geom.geom_type == 'Polygon':
                    points = [(x, y) for x, y in geom.exterior.coords]
                    msp.add_lwpolyline(points, close=True, dxfattribs={
                                       'layer': layer_name})
                elif geom.geom_type == 'MultiPolygon':
                    for polygon in geom.geoms:
                        points = [(x, y) for x, y in polygon.exterior.coords]
                        msp.add_lwpolyline(points, close=True, dxfattribs={
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
            doc.layers.new(name=layer_name, dxfattribs={'color': color})

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

        # Apply buffer to wald and update geltungsbereich
        wald_buffered = shapefiles["wald"].buffer(30)
        geltungsbereich = geltungsbereich.difference(wald_buffered.unary_union)

        # Download WMTS tiles
        for wmts_info in self.wmts:
            target_folder = self.resolve_full_path(wmts_info['targetFolder'])
            os.makedirs(target_folder, exist_ok=True)
            download_wmts_tiles(wmts_info, geltungsbereich, 500, target_folder)

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
            ('FlurOrig', 3),
            ('Gemeinde', self.colors['Gemeinde']),
            ('Gemarkung', self.colors['Gemarkung']),
            ('Parcel', self.colors['Parcel']),
            ('Parcel Number', self.colors['Parcel']),
            ('Flur Number', self.colors['Flur']),
            ('Wald', self.colors['Wald']),
            ('Biotope', self.colors['Biotope']),
            ('Gemeinde Name', self.colors['Gemeinde']),
            ('Gemarkung Name', self.colors['Gemarkung']),
            ('Geltungsbereich', 10)
        ]
        for layer_name, color in layers:
            self.add_layer(doc, layer_name, color)

        text_styles = ['Parcel Number', 'Flur Number',
                       'Gemeinde Name', 'Gemarkung Name']
        for style in text_styles:
            self.add_text_style(doc, style)

        msp = doc.modelspace()

        # Add geometries to modelspace
        self.add_geometries(msp, self.select_parcel_edges(
            shapefiles["flur"]), 'Flur', True)
        self.add_geometries(
            msp, shapefiles["parcels"]['geometry'], 'Parcel', True)
        self.add_geometries(msp, [geltungsbereich], 'Geltungsbereich', True)
        self.add_geometries(
            msp, shapefiles["orig_flur"]['geometry'], 'Flur', True)
        self.add_geometries(
            msp, shapefiles["gemeinde"]['geometry'], 'Gemeinde', True)
        self.add_geometries(
            msp, shapefiles["gemarkung"]['geometry'], 'Gemarkung', True)
        self.add_geometries(msp, shapefiles["wald"]['geometry'], 'Wald', True)
        self.add_geometries(
            msp, shapefiles["biotope"]['geometry'], 'Biotope', True)

        # Add text to center points
        for label, points in labeled_points.items():
            layer_name = label.replace("_points", "").replace("_", " ").title()
            self.add_text_to_center(msp, points, layer_name)

        # Save the DXF document
        doc.saveas(self.dxf_filename)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process.py <project_name>")
        sys.exit(1)
    try:
        processor = ProjectProcessor(sys.argv[1])
        processor.main()
    except ValueError as e:
        print(e)
